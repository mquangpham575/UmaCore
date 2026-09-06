"""
Quota calculation service with multi-club support
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple, Set
from uuid import UUID
import logging
import calendar
import math

from models import Member, QuotaHistory, QuotaRequirement
from config.database import db

logger = logging.getLogger(__name__)


class QuotaCalculator:
    """Handles all quota calculations and tracking per club"""
    
    @staticmethod
    async def calculate_expected_fans(club_id: UUID, member_join_date: date,
                                     current_date: date, quota_period: str = 'daily',
                                     pre_fetched_requirements: Optional[list] = None,
                                     default_quota: Optional[int] = None) -> int:
        """
        Calculate expected cumulative fans based on days active in current month.

        For weekly/biweekly periods the stored quota is the period amount (e.g. 700 000 for
        weekly), so we divide by the period length to get the per-day contribution.

        Args:
            club_id: Club UUID
            member_join_date: When the member joined the club
            current_date: The date the data belongs to (not necessarily today)
            quota_period: 'daily', 'weekly', or 'biweekly'
            pre_fetched_requirements: Optional list of pre-fetched quota requirements
            default_quota: Optional default daily quota for the club

        Returns:
            Expected cumulative fan count for this month only
        """
        # Determine the effective start date for this month
        if member_join_date.year == current_date.year and member_join_date.month == current_date.month:
            start_date = member_join_date
        else:
            start_date = date(current_date.year, current_date.month, 1)

        period_days = {'daily': 1, 'weekly': 7, 'biweekly': 14}.get(quota_period, 1)

        total_expected = 0.0

        day_count = (current_date - start_date).days + 1
        current_day = start_date

        if pre_fetched_requirements is None or default_quota is None:
            from models import Club
            club = await Club.get_by_id(club_id)
            default_quota = club.daily_quota if club else 1000000
            
            query = """
                SELECT effective_date, daily_quota
                FROM quota_requirements
                WHERE club_id = $1 AND effective_date <= $2
                ORDER BY effective_date ASC
            """
            rows = await db.fetch(query, club_id, current_date)
            pre_fetched_requirements = [(r['effective_date'], r['daily_quota']) for r in rows]

        for _ in range(day_count):
            applicable_quota = default_quota
            for req_date, quota_val in pre_fetched_requirements:
                if req_date <= current_day:
                    applicable_quota = quota_val
                else:
                    break
            
            total_expected += applicable_quota / period_days
            current_day += timedelta(days=1)

        result = round(total_expected)
        logger.debug(f"Expected fans calculation: {start_date} to {current_date} = {day_count} days "
                     f"(period={quota_period}) = {result:,}")
        return result
    
    @staticmethod
    def calculate_days_active_in_month(member_join_date: date, current_date: date) -> int:
        """Calculate how many days a member has been active this month"""
        # Determine the effective start date for this month
        if member_join_date.year == current_date.year and member_join_date.month == current_date.month:
            # Joined this month
            start_date = member_join_date
        else:
            # Joined in previous month(s) - active since first day of current month
            start_date = date(current_date.year, current_date.month, 1)
        
        return (current_date - start_date).days + 1
    
    @staticmethod
    def calculate_deficit_surplus(actual_fans: int, expected_fans: int) -> int:
        """Calculate deficit or surplus (positive = surplus, negative = deficit)"""
        return actual_fans - expected_fans
    
    async def _get_previous_cumulative_totals(self, club_id: UUID) -> Dict[str, int]:
        """
        Get the latest cumulative fan counts from database for monthly reset detection
        
        Args:
            club_id: Club UUID
        
        Returns:
            Dict mapping trainer_id/name -> cumulative_fans
        """
        query = """
            SELECT m.trainer_id, m.trainer_name, qh.cumulative_fans
            FROM members m
            JOIN quota_history qh ON m.member_id = qh.member_id
            WHERE m.club_id = $1 AND qh.date = (
                SELECT MAX(date) FROM quota_history WHERE club_id = $1
            )
        """
        rows = await db.fetch(query, club_id)
        
        result = {}
        for row in rows:
            key = row['trainer_id'] if row['trainer_id'] else row['trainer_name']
            result[key] = row['cumulative_fans']
        
        return result
    
    def _detect_monthly_reset_from_scraped(self, scraped_data: Dict[str, Dict], 
                                           previous_totals: Dict[str, int]) -> bool:
        """
        Detect if a monthly reset has occurred by comparing scraped data to previous totals.

        A monthly reset drops everyone's fans to ~0, so it is only treated as a reset
        when the majority (>50%) of members with previous totals dropped below half of
        them. A single member dipping (left the club, stopped playing, bad scrape) must
        not wipe the whole club's history.
        """
        if not previous_totals:
            logger.info("No previous data found, skipping reset detection")
            return False
        
        if not scraped_data:
            logger.warning("No scraped data, cannot detect reset")
            return False
        
        dropped: List[str] = []
        compared = 0
        
        for key, member_data in scraped_data.items():
            if key not in previous_totals:
                continue
            compared += 1
            current_fans = member_data["fans"][-1] if member_data["fans"] else 0
            previous_fans = previous_totals[key]
            
            if current_fans > 0 and current_fans < previous_fans * 0.5:
                dropped.append(member_data["name"])
        
        if not compared:
            return False
        
        is_reset = len(dropped) / compared > 0.5
        if is_reset:
            logger.warning(
                f"Monthly reset detected: {len(dropped)}/{compared} members dropped "
                f"below 50% of previous fans ({', '.join(dropped)})"
            )
        return is_reset
    
    async def _auto_deactivate_missing_members(self, club_id: UUID, scraped_trainer_ids: Set[str]):
        """Auto-deactivate members who are no longer in the scraped data"""
        active_members = await Member.get_all_active(club_id)
        
        deactivated_count = 0
        for member in active_members:
            member_key = member.trainer_id if member.trainer_id else member.trainer_name
            
            if member_key not in scraped_trainer_ids:
                await member.deactivate(manual=False)
                deactivated_count += 1
                logger.info(f"Auto-deactivated member (no longer in club): {member.trainer_name}")
        
        if deactivated_count > 0:
            logger.info(f"Auto-deactivated {deactivated_count} member(s) who left the club")
    
    async def process_scraped_data(self, club_id: UUID, scraped_data: Dict[str, Dict],
                                   current_date: date, current_day: int,
                                   quota_period: str = 'daily') -> Tuple[int, int]:
        """
        Process scraped data and update database for a specific club.
        
        Args:
            club_id: Club UUID
            scraped_data: Dict of trainer_id -> {name, trainer_id, fans[], join_day}
            current_date: Date the data represents (calculated by scraper/tasks)
            current_day: Day number in the array (used for array indexing)
        
        Returns:
            Tuple of (new_members_count, updated_members_count)
        """
        # Use the date already calculated by the scraper and tasks.py
        data_date = current_date
        logger.info(f"Processing scraped data for club {club_id}: data_date = {data_date}, current_day = {current_day}")
        
        # Check for monthly reset
        logger.info(f"Checking for monthly reset for club {club_id}...")
        previous_totals = await self._get_previous_cumulative_totals(club_id)
        
        if self._detect_monthly_reset_from_scraped(scraped_data, previous_totals):
            logger.warning(f"Monthly reset detected for club {club_id}! Clearing all history...")
            
            # Clear club-specific data
            await db.execute("DELETE FROM quota_history WHERE club_id = $1", club_id)
            await db.execute("DELETE FROM bombs WHERE club_id = $1", club_id)
            await db.execute("DELETE FROM quota_requirements WHERE club_id = $1", club_id)
            
            # Clear manual deactivation flags for this club
            await db.execute(
                "UPDATE members SET manually_deactivated = FALSE, monthly_best_day = 0 WHERE club_id = $1",
                club_id
            )
            logger.info(f"Monthly reset complete for club {club_id}")
        
        # Auto-deactivate members who are no longer in the scraped data
        scraped_trainer_ids = set(scraped_data.keys())
        await self._auto_deactivate_missing_members(club_id, scraped_trainer_ids)
        
        # Pre-fetch default quota and custom requirements
        from models import Club
        club = await Club.get_by_id(club_id)
        default_quota = club.daily_quota if club else 1000000
        
        query = """
            SELECT effective_date, daily_quota
            FROM quota_requirements
            WHERE club_id = $1 AND effective_date <= $2
            ORDER BY effective_date ASC
        """
        rows = await db.fetch(query, club_id, data_date)
        pre_fetched_requirements = [(r['effective_date'], r['daily_quota']) for r in rows]

        # Process each member
        new_members = 0
        updated_members = 0
        
        for key, member_data in scraped_data.items():
            trainer_id = member_data.get("trainer_id")
            trainer_name = member_data["name"]
            daily_fans = member_data["fans"]
            detected_join_day = member_data["join_day"]
            
            if not daily_fans:
                logger.warning(f"No fan data for {trainer_name}")
                continue
            
            # Use the last value in the fans array
            cumulative_fans = daily_fans[-1]
            
            # Resolve the scraped join day into a full date
            last_day_of_month = calendar.monthrange(data_date.year, data_date.month)[1]
            if 1 <= detected_join_day <= last_day_of_month:
                # Join day is within the current month being processed
                scraped_join_date = date(data_date.year, data_date.month, detected_join_day)
            else:
                # Join day exceeds current month, must be from previous month
                if data_date.month == 1:
                    scraped_join_date = date(data_date.year - 1, 12, detected_join_day)
                else:
                    scraped_join_date = date(data_date.year, data_date.month - 1, detected_join_day)

            # Look up member by trainer_id first, then by name
            if trainer_id:
                member = await Member.get_by_trainer_id(club_id, trainer_id)
            else:
                member = await Member.get_by_name(club_id, trainer_name)
            
            if not member:
                # New member
                member = await Member.create(club_id, trainer_name, scraped_join_date, trainer_id)
                new_members += 1
                logger.info(f"New member added: {trainer_name} (ID: {trainer_id}, joined {scraped_join_date.strftime('%Y-%m-%d')})")
            else:
                # Existing member
                if member.trainer_name != trainer_name:
                    await member.update_name(trainer_name)
                
                # SELF-CORRECTION: Keep DB in sync when an authoritative Chrono join_time is available,
                # or when scraped_join_date is later than the initial default join date.
                if (member_data.get("join_day_reliable") or scraped_join_date > member.join_date) and scraped_join_date != member.join_date:
                    old_date = member.join_date
                    await member.update_join_date(scraped_join_date)
                    member.join_date = scraped_join_date # Update local object for subsequent calculations
                    logger.info(f"Corrected join date for {trainer_name}: {old_date} -> {scraped_join_date}")
                    # Retroactively recompute stale quota_history records for this month
                    await self._recalculate_member_history(
                        member, club_id, data_date, quota_period,
                        pre_fetched_requirements, default_quota
                    )

                # Reactivate if previously auto-deactivated
                if not member.is_active:
                    if member.manually_deactivated:
                        logger.info(f"Skipping reactivation of manually deactivated member: {trainer_name}")
                        continue
                    else:
                        await member.activate()
                        # Only reset join_date to today if the scraped data doesn't provide a specific one
                        # (returning members usually get a reset, but Chrono history tells us exactly when they rejoined)
                        if scraped_join_date > member.join_date:
                            await member.update_join_date(data_date)
                            logger.info(f"Reactivated returning member: {trainer_name} (join_date local-reset to {data_date})")
            
            # last_seen tracks when we actually observed them (wall-clock date)
            await member.update_last_seen(current_date)
            
            # All quota calculations use data_date
            days_active = self.calculate_days_active_in_month(member.join_date, data_date)
            
            expected_fans = await self.calculate_expected_fans(
                club_id, member.join_date, data_date, quota_period,
                pre_fetched_requirements=pre_fetched_requirements,
                default_quota=default_quota
            )
            
            deficit_surplus = self.calculate_deficit_surplus(cumulative_fans, expected_fans)

            # Store history keyed to data_date
            # Resolve current daily quota in-memory for the effort-based days_behind calculation
            stored_quota = default_quota
            for req_date, quota_val in pre_fetched_requirements:
                if req_date <= data_date:
                    stored_quota = quota_val
                else:
                    break
            
            days_behind = await self._calculate_days_behind(member.member_id, deficit_surplus, data_date, stored_quota)
            
            # Calculate daily gain from the JSON history array (ensures consistency with raw data)
            daily_gain = 0
            if current_day > 1 and len(daily_fans) >= current_day:
                # Array is 0-indexed: current_day 13 is at index 12
                daily_gain = daily_fans[current_day - 1] - daily_fans[current_day - 2]
            elif current_day == 1 and len(daily_fans) >= 1:
                daily_gain = daily_fans[0]
            
            # Store history keyed to data_date
            await QuotaHistory.create(
                member_id=member.member_id,
                club_id=club_id,
                date=data_date,
                cumulative_fans=cumulative_fans,
                expected_fans=expected_fans,
                deficit_surplus=deficit_surplus,
                days_behind=days_behind,
                daily_gain=daily_gain
            )
            
            updated_members += 1
            
            # Accurate "Best Day" calculation from the full monthly history array
            if len(daily_fans) >= 2:
                best_day = 0
                for i in range(1, len(daily_fans)):
                    # Only compare days that have valid data (greater than 0)
                    if daily_fans[i] > 0 and daily_fans[i-1] > 0:
                        gain = daily_fans[i] - daily_fans[i-1]
                        if gain > best_day:
                            best_day = gain
                
                if best_day > 0:
                    await member.update_monthly_best_day(best_day)
                    logger.debug(f"Updated Best Day for {trainer_name}: +{best_day:,}")
            
            logger.debug(f"{trainer_name}: {cumulative_fans:,} fans "
                        f"(expected: {expected_fans:,}, {deficit_surplus:+,}, days active: {days_active})")
        
        logger.info(f"Processed {updated_members} members ({new_members} new) for club {club_id}")
        return new_members, updated_members
    
    async def _recalculate_member_history(self, member, club_id: UUID, current_date: date,
                                          quota_period: str, pre_fetched_requirements: list, default_quota: int):
        """Retroactively recalculate expected fans and deficit for a member's current-month history rows"""
        rows = await db.fetch(
            """
            SELECT id, date, cumulative_fans
            FROM quota_history
            WHERE member_id = $1
              AND date_part('year', date) = $2
              AND date_part('month', date) = $3
            ORDER BY date ASC
            """,
            member.member_id, current_date.year, current_date.month
        )
        for row in rows:
            row_date = row['date']
            if row_date < member.join_date:
                exp = 0
                def_sur = 0
                d_behind = 0
            else:
                exp = await self.calculate_expected_fans(
                    club_id, member.join_date, row_date, quota_period,
                    pre_fetched_requirements=pre_fetched_requirements,
                    default_quota=default_quota
                )
                def_sur = self.calculate_deficit_surplus(row['cumulative_fans'], exp)
                stored_q = default_quota
                for req_date, q_val in pre_fetched_requirements:
                    if req_date <= row_date:
                        stored_q = q_val
                    else:
                        break
                d_behind = await self._calculate_days_behind(member.member_id, def_sur, row_date, stored_q)

            await db.execute(
                """
                UPDATE quota_history
                SET expected_fans = $1, deficit_surplus = $2, days_behind = $3
                WHERE id = $4
                """,
                exp, def_sur, d_behind, row['id']
            )

    async def _calculate_days_behind(self, member_id: UUID, current_deficit_surplus: int,
                                    data_date: date, daily_quota: int = 5000000) -> int:
        """Calculate how many 'days of work' a member is behind based on daily quota"""
        if current_deficit_surplus >= 0:
            return 0

        # Formula: ceil(abs(deficit) / daily_quota)
        # Represents how many full days of work are missing.
        deficit = abs(current_deficit_surplus)
        days_behind = math.ceil(deficit / daily_quota) if daily_quota > 0 else 1
        
        logger.debug(f"Member {member_id}: {days_behind} effort-days behind (deficit: {deficit:,})")
        return days_behind
    
    @staticmethod
    def get_period_info(quota_period: str, current_date: date) -> Optional[Dict]:
        """
        Return period metadata for the current date under weekly/biweekly quota.
        Returns None for daily quota.
        """
        if quota_period == 'daily':
            return None

        period_days = {'weekly': 7, 'biweekly': 14}[quota_period]
        days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]

        day_of_month = current_date.day  # 1-indexed
        period_number = (day_of_month - 1) // period_days + 1

        period_start_day = (period_number - 1) * period_days + 1
        period_end_day = min(period_start_day + period_days - 1, days_in_month)

        period_start = date(current_date.year, current_date.month, period_start_day)
        period_end = date(current_date.year, current_date.month, period_end_day)

        total_periods = math.ceil(days_in_month / period_days)
        quota_label = 'week' if quota_period == 'weekly' else 'biweek'

        return {
            'period_number': period_number,
            'total_periods': total_periods,
            'period_start': period_start,
            'period_end': period_end,
            'period_days': period_days,
            'quota_label': quota_label,
        }

    async def get_member_status_summary(self, club_id: UUID, current_date: date,
                                        quota_period: str = 'daily') -> Dict:
        """
        Get summary of all members' status for a club.

        For weekly/biweekly quotas, each member_status entry will additionally
        contain 'period_start_fans' and 'period_info'.

        Returns:
            Dict with categorized member data
        """
        members = await Member.get_all_active(club_id)

        period_info = self.get_period_info(quota_period, current_date)

        # Pre-compute period_quota for the current period when not daily
        if period_info:
            actual_period_length = (period_info['period_end'] - period_info['period_start']).days + 1
            stored_quota = await QuotaRequirement.get_quota_for_date(club_id, period_info['period_start'])
            period_quota = round(stored_quota / period_info['period_days'] * actual_period_length)
            period_info['period_quota'] = period_quota

        from models import Club
        club = await Club.get_by_id(club_id)
        default_quota = club.daily_quota if club else 1000000

        query = """
            SELECT effective_date, daily_quota
            FROM quota_requirements
            WHERE club_id = $1 AND effective_date <= $2
            ORDER BY effective_date ASC
        """
        req_rows = await db.fetch(query, club_id, current_date)
        pre_fetched = [(r['effective_date'], r['daily_quota']) for r in req_rows]

        on_track = []
        behind = []

        for member in members:
            latest_history = await QuotaHistory.get_latest_for_member(member.member_id)

            if not latest_history:
                continue

            # Auto-healing: Ensure expected_fans and deficit strictly match member.join_date
            if latest_history.date.year == current_date.year and latest_history.date.month == current_date.month:
                correct_exp = await self.calculate_expected_fans(
                    club_id, member.join_date, latest_history.date, quota_period,
                    pre_fetched_requirements=pre_fetched,
                    default_quota=default_quota
                )
                if latest_history.expected_fans != correct_exp:
                    correct_def = self.calculate_deficit_surplus(latest_history.cumulative_fans, correct_exp)
                    stored_q = default_quota
                    for req_date, q_val in pre_fetched:
                        if req_date <= latest_history.date:
                            stored_q = q_val
                        else:
                            break
                    correct_behind = await self._calculate_days_behind(member.member_id, correct_def, latest_history.date, stored_q)

                    # Update local object
                    latest_history.expected_fans = correct_exp
                    latest_history.deficit_surplus = correct_def
                    latest_history.days_behind = correct_behind

                    # Persist fix to DB
                    await db.execute(
                        "UPDATE quota_history SET expected_fans = $1, deficit_surplus = $2, days_behind = $3 WHERE id = $4",
                        correct_exp, correct_def, correct_behind, latest_history.id
                    )

            member_status = {
                'member': member,
                'history': latest_history
            }

            if period_info:
                # Fans earned before this period started
                if period_info['period_start'].day == 1:
                    period_start_fans = 0
                else:
                    day_before_period = period_info['period_start'] - timedelta(days=1)
                    prev_record = await QuotaHistory.get_for_member_date(member.member_id, day_before_period)
                    period_start_fans = prev_record.cumulative_fans if prev_record else 0

                member_status['period_start_fans'] = period_start_fans
                member_status['period_info'] = period_info

            if latest_history.deficit_surplus >= 0:
                on_track.append(member_status)
            else:
                behind.append(member_status)

        # Sort on_track by total cumulative fans (descending - highest total fans first)
        on_track.sort(key=lambda x: x['history'].cumulative_fans, reverse=True)

        # Sort behind by deficit (descending - least behind first, to follow the flow from on_track)
        behind.sort(key=lambda x: x['history'].deficit_surplus, reverse=True)

        return {
            'on_track': on_track,
            'behind': behind,
            'total_members': len(members),
            'period_info': period_info,
        }