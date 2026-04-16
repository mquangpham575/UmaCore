"""
Uma.moe API scraper for club data fetching
"""
from typing import Dict, Optional, List
import logging
import calendar
import aiohttp
import os
import json
import base64
from datetime import datetime, date

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class UmaGitHubScraper(BaseScraper):
    """Scraper using Chrono API for direct data retrieval (Legacy name kept for compatibility)"""

    def __init__(self, circle_id: str):
        self.circle_id = circle_id
        self.chrono_token = os.getenv("CHRONO_API_KEY")
        self.current_day_count = 1
        self._fetched_year = None
        self._fetched_month = None
        self._data_date: Optional[date] = None
        self._monthly_rank: Optional[int] = None
        self._last_month_rank: Optional[int] = None
        self._yesterday_rank: Optional[int] = None
        self._data_source: str = "chrono_api"
        # Base URL for the Chrono API
        super().__init__(f"https://api.chronogenesis.net/club_profile?circle_id={circle_id}")

    async def _fetch_remote_raw_data(self, session: aiohttp.ClientSession) -> Optional[dict]:
        """Fetch tracking JSON from Chrono API directly."""
        api_url = f"https://api.chronogenesis.net/club_profile?circle_id={self.circle_id}"
        
        headers = {
            "Authorization": f"{self.chrono_token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                
                if response.status == 403:
                    logger.warning(f"Chrono API: 403 Forbidden. Check your CHRONO_API_KEY.")
                elif response.status == 404:
                    logger.info(f"Chrono API: No data found for circle {self.circle_id}")
                else:
                    text = await response.text()
                    logger.warning(f"Chrono API request failed ({response.status}): {text[:200]}")
                
                return None
        except Exception as e:
            logger.error(f"Error fetching from Chrono API: {e}")
            return None

    def _parse_tracker_raw_data(self, raw_data: dict) -> Dict[str, Dict]:
        """Parse raw JSON from Chrono API (Same format as tracking exports)"""
        profile = raw_data.get("club_friend_profile") or []
        history = raw_data.get("club_friend_history") or []

        if not history:
            raise ValueError("Tracking raw data missing club_friend_history")

        ym = None
        month_filter = raw_data.get("month_filter") or []
        if month_filter and isinstance(month_filter[0], dict):
            sdate = month_filter[0].get("sdate")
            if isinstance(sdate, str) and len(sdate) >= 7:
                try:
                    dt = datetime.strptime(sdate, "%Y-%m-%d")
                    ym = (dt.year, dt.month)
                except ValueError:
                    ym = None

        if ym:
            self._fetched_year, self._fetched_month = ym
        else:
            now = datetime.now()
            self._fetched_year, self._fetched_month = now.year, now.month

        names_by_id: Dict[str, str] = {}
        for p in profile:
            vid = p.get("friend_viewer_id")
            if vid is None:
                continue
            names_by_id[str(vid)] = p.get("name") or f"Member {vid}"

        by_member: Dict[str, Dict[int, int]] = {}
        max_day = 1
        for row in history:
            vid = row.get("friend_viewer_id")
            day = row.get("actual_date")
            cumulative = row.get("adjusted_fan_gain_cumulative")
            if vid is None or day is None or cumulative is None:
                continue

            day_int = int(day)
            if day_int < 1:
                continue

            member_id = str(vid)
            by_member.setdefault(member_id, {})[day_int] = int(cumulative)
            max_day = max(max_day, day_int)

        self.current_day_count = max_day
        self._data_date = date(self._fetched_year, self._fetched_month, max_day)

        club = (raw_data.get("club") or [{}])[0]
        self._monthly_rank = club.get("rank")
        self._yesterday_rank = None

        monthly_history = raw_data.get("club_monthly_history") or []
        if monthly_history:
            self._last_month_rank = monthly_history[1].get("rank") if len(monthly_history) > 1 else None
        else:
            self._last_month_rank = None

        parsed_data: Dict[str, Dict] = {}
        for trainer_id, day_values in by_member.items():
            fans = [0] * max_day
            for day_num, cumulative in day_values.items():
                if day_num <= max_day:
                    fans[day_num - 1] = cumulative

            join_day = 1
            for idx, val in enumerate(fans, start=1):
                if val > 0:
                    join_day = idx
                    break

            if fans[-1] == 0:
                continue

            parsed_data[trainer_id] = {
                "name": names_by_id.get(trainer_id, f"Member {trainer_id}"),
                "trainer_id": trainer_id,
                "fans": fans,
                "join_day": join_day,
            }

        logger.info(
            f"Parsed tracking raw data for circle {self.circle_id}: "
            f"{len(parsed_data)} active members, day {self.current_day_count}"
        )
        return parsed_data

    async def scrape(self) -> Dict[str, Dict]:
        """
        Scrape club data from Chrono API directly.
        
        This replaces the indirect GitHub-based fetching to provide 
        near real-time data directly from the source.
        """
        try:
            async with aiohttp.ClientSession() as session:
                remote_data = await self._fetch_remote_raw_data(session)
                if not remote_data:
                    raise ValueError(f"Could not fetch data from Chrono API for circle {self.circle_id}")

                self._raw_response = remote_data
                self._data_source = "chrono_api"
                logger.info(f"Using Chrono API data for circle {self.circle_id}")

                # Format check: API format (has 'club_friend_history' or 'club_daily_history')
                if "club_friend_history" in remote_data or "club_daily_history" in remote_data:
                    return self._parse_tracker_raw_data(remote_data)
                
                # Format check: Legacy API-like format (has 'members')
                if "members" in remote_data:
                    now = datetime.now()
                    parsed_data = self._parse_api_data(remote_data.get("members", []), calendar_day=now.day)
                    logger.info(f"Successfully parsed {len(parsed_data)} active members from Chrono format")
                    return parsed_data

                raise ValueError("Unsupported data format: expected 'club_friend_history' or 'members'")

        except Exception as e:
            logger.error(f"Error during Chrono API scraping: {e}")
            raise

    def _parse_api_data(self, members: list, endpoint_members: Optional[List] = None, calendar_day: int = None) -> Dict[str, Dict]:
        """
        Parse API member data into scraper format.
        """
        parsed_data = {}

        now = datetime.now()

        if now.day == 1:
            # Day 1: Fetched previous month, use last day of that month
            current_day = calendar.monthrange(self._fetched_year, self._fetched_month)[1]
            logger.info(f"Day 1 fallback: using day {current_day} (last day of {self._fetched_year}-{self._fetched_month:02d})")
        else:
            # Day 2+: Check if current day data exists
            current_day = calendar_day if calendar_day else now.day
            current_day_index = current_day - 1

            # Check if current day data exists by sampling active members
            data_exists = False
            if members:
                # Find a member with recent activity to check data availability
                for member in members:
                    sample_fans = member.get("daily_fans", [])
                    if sample_fans and len(sample_fans) > current_day_index and sample_fans[current_day_index] > 0:
                        data_exists = True
                        logger.debug(f"Found current day data in member {member.get('trainer_name')}")
                        break

            if not data_exists:
                fallback_day = now.day - 1
                fallback_idx = fallback_day - 1   # 0-based index for fallback day
                prev_idx = fallback_day - 2       # 0-based index for the day before that

                # When falling back past day 1, verify the fallback data is genuinely fresh.
                if fallback_day >= 2 and prev_idx >= 0:
                    relevant = [
                        m for m in members
                        if len(m.get("daily_fans", [])) > fallback_idx
                        and len(m.get("daily_fans", [])) > prev_idx
                        and m["daily_fans"][fallback_idx] > 0
                    ]
                    any_growth = any(
                        m["daily_fans"][fallback_idx] > m["daily_fans"][prev_idx]
                        for m in relevant
                    )
                    if relevant and not any_growth:
                        raise ValueError(
                            f"Day {fallback_day} data appears stale — fan counts are unchanged from "
                            f"day {fallback_day - 1} for all sampled members. "
                            f"Uma.moe likely hasn't published today's update yet (typically ~15:10 UTC)."
                        )

                current_day = fallback_day
                logger.warning(
                    f"Current day {now.day} data not available yet (Uma.moe updates ~15:10 UTC). "
                    f"Using day {current_day} data."
                )
                self._data_date = date(now.year, now.month, current_day)
            else:
                # Current day data exists
                current_day = now.day
                self._data_date = date(now.year, now.month, now.day)
                logger.info(f"Day {current_day} data is available (represents day {now.day - 1} competition results)")

        self.current_day_count = current_day

        # Build endpoint lookup for Day 1 correction
        endpoint_totals = {}
        if endpoint_members:
            for m in endpoint_members:
                vid = m.get("viewer_id")
                fans = m.get("daily_fans", [])
                if vid and fans and len(fans) > 0 and fans[0] > 0:
                    endpoint_totals[str(vid)] = fans[0]
            logger.info(f"Endpoint correction available for {len(endpoint_totals)} members")

        for member in members:
            viewer_id = member.get("viewer_id")
            trainer_name = member.get("trainer_name")
            lifetime_fans = member.get("daily_fans", [])

            if not viewer_id or not trainer_name:
                logger.warning(f"Skipping member with missing data: viewer_id={viewer_id}, name={trainer_name}")
                continue

            # Skip members who left the club (0 fans on current day)
            current_day_index = current_day - 1
            if current_day_index >= len(lifetime_fans):
                logger.warning(f"Current day {current_day} exceeds array length for {trainer_name}")
                continue

            current_day_lifetime_fans = lifetime_fans[current_day_index]
            if current_day_lifetime_fans == 0:
                logger.debug(f"Skipping inactive member (left club): {trainer_name} (ID: {viewer_id})")
                continue

            viewer_id_str = str(viewer_id)

            # Detect join day (first non-zero value) and starting lifetime fans
            join_day = 1
            starting_lifetime_fans = 0

            for idx, fans in enumerate(lifetime_fans[:current_day], start=1):
                if fans > 0:
                    join_day = idx
                    starting_lifetime_fans = fans
                    break

            # Convert lifetime cumulative fans to monthly cumulative fans
            monthly_fans = []
            for day_idx in range(current_day):
                lifetime_total = lifetime_fans[day_idx]

                if lifetime_total == 0:
                    fans_this_month = 0
                else:
                    fans_this_month = lifetime_total - starting_lifetime_fans

                monthly_fans.append(fans_this_month)

            # Day 1 endpoint correction
            if endpoint_totals and viewer_id_str in endpoint_totals:
                endpoint_lifetime = endpoint_totals[viewer_id_str]
                if endpoint_lifetime >= starting_lifetime_fans:
                    corrected_monthly = endpoint_lifetime - starting_lifetime_fans
                    if corrected_monthly > monthly_fans[-1]:
                        logger.debug(
                            f"Endpoint correction for {trainer_name}: "
                            f"{monthly_fans[-1]:,} → {corrected_monthly:,} "
                            f"(+{corrected_monthly - monthly_fans[-1]:,} recovered)"
                        )
                        monthly_fans[-1] = corrected_monthly
                else:
                    logger.warning(
                        f"Endpoint correction skipped for {trainer_name}: "
                        f"endpoint lifetime ({endpoint_lifetime:,}) < starting ({starting_lifetime_fans:,})"
                    )

            parsed_data[viewer_id_str] = {
                "name": trainer_name,
                "trainer_id": viewer_id_str,
                "fans": monthly_fans,
                "join_day": join_day
            }

            logger.debug(
                f"Parsed {trainer_name}: joined day {join_day}, "
                f"lifetime: {starting_lifetime_fans:,} → {current_day_lifetime_fans:,}, "
                f"monthly: {monthly_fans[-1]:,}"
            )

        return parsed_data

    def get_current_day(self) -> int:
        """Get the current day number"""
        return self.current_day_count

    def get_data_date(self) -> Optional[date]:
        """
        Returns the date the scraped data belongs to when fallback was used,
        or None when the data matches today.
        """
        return self._data_date

    def get_monthly_rank(self) -> Optional[int]:
        """Return the club's current monthly position rank (from circle.monthly_rank)."""
        return self._monthly_rank

    def get_last_month_rank(self) -> Optional[int]:
        """Return the club's previous month position rank (from circle.last_month_rank)."""
        return self._last_month_rank

    def get_yesterday_rank(self) -> Optional[int]:
        """Return the club's rank as of yesterday (from circle.yesterday_rank)."""
        return self._yesterday_rank

    def get_data_source(self) -> str:
        """Return the source used for the latest scrape: 'api' or 'github_raw'."""
        return self._data_source
