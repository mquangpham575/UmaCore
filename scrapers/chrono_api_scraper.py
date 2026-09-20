"""
Uma.moe API scraper for club data fetching
"""
from typing import Dict, Optional, List
import logging
import calendar
import aiohttp
import os
from datetime import datetime, date, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class UmaGitHubScraper(BaseScraper):
    """Scraper using Chrono API for direct data retrieval (Legacy name kept for compatibility)"""

    def __init__(self, circle_id: str):
        self.circle_id = circle_id
        self.chrono_token = os.getenv("CHRONO_API_KEY")
        self.umamoe_token = os.getenv("UMAMOE_API_KEY")
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

    async def _fetch_chrono_data(self, session: aiohttp.ClientSession) -> Optional[dict]:
        """Fetch tracking JSON from Chrono API directly."""
        if not self.chrono_token:
            logger.warning("Chrono API: CHRONO_API_KEY is not set.")
            return None

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
                    logger.warning("Chrono API: 403 Forbidden. Check your CHRONO_API_KEY.")
                elif response.status == 404:
                    logger.info(f"Chrono API: No data found for circle {self.circle_id}")
                else:
                    text = await response.text()
                    logger.warning(f"Chrono API request failed ({response.status}): {text[:200]}")
                
                return None
        except Exception as e:
            logger.warning(f"Error fetching from Chrono API: {e}")
            return None

    async def _fetch_remote_raw_data(self, session: aiohttp.ClientSession) -> Optional[dict]:
        """Alias for _fetch_chrono_data for compatibility."""
        return await self._fetch_chrono_data(session)

    async def _fetch_umamoe_data(self, session: aiohttp.ClientSession, year: int, month: int) -> Optional[dict]:
        """Fetch circle tracking JSON from Uma.moe API as a fallback."""
        api_url = "https://uma.moe/api/v4/circles"
        params = {
            "circle_id": self.circle_id,
            "year": year,
            "month": month
        }
        headers = {
            "accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if self.umamoe_token:
            headers["X-API-Key"] = self.umamoe_token

        try:
            async with session.get(api_url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                text = await response.text()
                logger.warning(f"Uma.moe API request failed ({response.status}): {text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"Error fetching from Uma.moe API: {e}")
            return None

    def _join_day_from_join_time(self, join_time: Optional[str]) -> Optional[int]:
        """Resolve the join_time from the profile into a game-day within the fetched month.

        Chrono timestamps are JST (Asia/Tokyo). The game day turns over at 05:00 JST,
        so the effective game date of a timestamp is its JST timestamp shifted back by 5 hours.
        E.g. a join_time of 2026-09-05T06:27:27 JST -> 2026-09-05 01:27:27 -> join day 5.
        A join_time of 2026-09-02T00:16:03 JST -> 2026-09-01 19:16:03 -> join day 1.

        Returns None when join_time is missing or unparseable (join day unknown).
        Members who joined in a previous month (in game-days) are treated as day 1
        (present from the start of the current month).
        """
        if not join_time:
            return None
        try:
            joined_jst = datetime.fromisoformat(join_time)
        except ValueError:
            return None
        # Chrono timestamps are in JST. Umamusume daily reset occurs at 05:00 JST.
        game_date = (joined_jst - timedelta(hours=5)).date()
        if (game_date.year, game_date.month) != (self._fetched_year, self._fetched_month):
            return 1
        return game_date.day

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
        join_time_by_id: Dict[str, str] = {}
        for p in profile:
            vid = p.get("friend_viewer_id")
            if vid is None:
                continue
            names_by_id[str(vid)] = p.get("name") or f"Member {vid}"
            if p.get("join_time"):
                join_time_by_id[str(vid)] = p["join_time"]

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

            # Join day comes from the profile's join_time (authoritative). Using the
            # history backfill here is wrong: Chrono lists every current member from
            # day 1 of the month, so mid-month joiners would all appear to join on day 1.
            join_day = self._join_day_from_join_time(join_time_by_id.get(trainer_id))

            if fans[-1] == 0:
                continue

            # Sync with the tracker sheets: count fan data only from the joined
            # game-day. Chrono backfills phantom cumulative values for the days a
            # member wasn't in the club yet, so subtract the pre-join baseline and
            # zero the pre-join days. This keeps cumulative_fans, daily_gain and
            # avg_daily aligned with the tracker's post-join totals.
            if join_day is not None and 1 < join_day <= max_day:
                baseline = max(fans[:join_day - 1])
                if baseline > 0:
                    for i in range(join_day - 1):
                        fans[i] = 0
                    for i in range(join_day - 1, max_day):
                        fans[i] = fans[i] - baseline if fans[i] >= baseline else 0

            parsed_data[trainer_id] = {
                "name": names_by_id.get(trainer_id, f"Member {trainer_id}"),
                "trainer_id": trainer_id,
                "fans": fans,
                "join_day": join_day if join_day is not None else 1,
                "join_day_reliable": join_day is not None,
            }

        logger.info(
            f"Parsed tracking raw data for circle {self.circle_id}: "
            f"{len(parsed_data)} active members, day {self.current_day_count}"
        )
        return parsed_data

    async def scrape(self) -> Dict[str, Dict]:
        """
        Scrape club data from Chrono API, falling back to Uma.moe API if Chrono fails.
        """
        errors = []
        async with aiohttp.ClientSession() as session:
            # 1. Primary: Chrono API
            try:
                chrono_data = await self._fetch_chrono_data(session)
                if chrono_data:
                    self._raw_response = chrono_data
                    self._data_source = "chrono_api"
                    logger.info(f"Using Chrono API data for circle {self.circle_id}")

                    if "club_friend_history" in chrono_data or "club_daily_history" in chrono_data:
                        return self._parse_tracker_raw_data(chrono_data)
                    elif "members" in chrono_data:
                        now = datetime.now()
                        self._fetched_year, self._fetched_month = now.year, now.month
                        parsed_data = self._parse_api_data(chrono_data.get("members", []), calendar_day=now.day)
                        logger.info(f"Successfully parsed {len(parsed_data)} active members from Chrono format")
                        return parsed_data
                    else:
                        errors.append("Chrono API returned unsupported data format")
                else:
                    errors.append("Chrono API returned empty/failed response")
            except Exception as e:
                logger.warning(f"Chrono API fetch error: {e}")
                errors.append(f"Chrono API error: {e}")

            # 2. Fallback: Uma.moe API
            logger.warning(f"Chrono API unavailable for circle {self.circle_id}. Attempting Uma.moe fallback...")
            try:
                # Uma.moe slot N holds the same data as Chrono day N, and the newest complete
                # slot on UTC calendar day D is D-1 ("Yesterday" - the same convention the
                # scheduler in bot/tasks.py expects). Fetch the month that day belongs to,
                # which on the 1st is the previous month.
                target = (datetime.now(timezone.utc) - timedelta(days=1)).date()
                fetch_year, fetch_month = target.year, target.month

                self._fetched_year = fetch_year
                self._fetched_month = fetch_month

                umamoe_data = await self._fetch_umamoe_data(session, fetch_year, fetch_month)
                if umamoe_data and "members" in umamoe_data:
                    self._raw_response = umamoe_data
                    self._data_source = "umamoe_api"
                    logger.info(f"Using Uma.moe API fallback for circle {self.circle_id} ({fetch_year}-{fetch_month:02d})")

                    circle_meta = umamoe_data.get("circle") or {}
                    self._monthly_rank = circle_meta.get("rank") or circle_meta.get("monthly_rank")
                    self._last_month_rank = circle_meta.get("last_month_rank")
                    self._yesterday_rank = circle_meta.get("yesterday_rank")

                    members_list = umamoe_data.get("members", [])
                    if not members_list:
                        raise ValueError(f"Uma.moe returned 0 members for circle {self.circle_id}")

                    parsed_data = self._parse_api_data(members_list, max_day=target.day)
                    if self.current_day_count < target.day:
                        logger.warning(
                            f"Uma.moe has only published up to day {self.current_day_count} of "
                            f"{fetch_year}-{fetch_month:02d}; expected day {target.day} "
                            f"(Uma.moe updates ~15:10 UTC). Using day {self.current_day_count}."
                        )
                    logger.info(f"Successfully parsed {len(parsed_data)} active members from Uma.moe API fallback")
                    return parsed_data
                else:
                    errors.append("Uma.moe API returned empty or missing 'members' field")
            except Exception as e:
                logger.error(f"Uma.moe API fallback failed: {e}")
                errors.append(f"Uma.moe API error: {e}")

        # Both failed
        error_summary = " | ".join(errors)
        raise ValueError(f"All data sources failed for circle {self.circle_id}: {error_summary}")

    @staticmethod
    def _latest_populated_day(members: list) -> int:
        """Newest day slot (>= 1) that holds data for at least one member.

        Slot 0 is the month-start baseline, so it never counts as a day of data.
        """
        latest = 0
        for member in members:
            fans = member.get("daily_fans") or []
            for idx in range(len(fans) - 1, latest, -1):
                if fans[idx]:
                    latest = idx
                    break
        return latest

    @staticmethod
    def _resolve_join_and_baseline(fans: list, latest_day: int) -> tuple:
        """Work out a member's join day and the lifetime-fan baseline to subtract.

        Uma.moe has no join_time (Chrono does), so this is inferred from the sign/zero pattern
        of ``daily_fans`` (lifetime fans, slot d == Chrono day d, slot 0 == month-start baseline):

        - negative values are days spent in a previous club, 0 means no record, positive means
          in this club.
        - first positive at slot 0: in the club since before the month -> join day 1.
        - first positive at slot 1: in the club from day 1 (a negative slot 0 is the previous
          club's month-start baseline and is used as the baseline, so day-1 gains are kept).
        - first positive at slot k >= 2: verified against Chrono join_time for a live club, Uma.moe
          flips to positive two slots before the Chrono game-day of the join (slot = join_day - 2),
          so the join day is k + 2 and only fans from that day on count (baseline = slot join_day-1).
          Members who joined before 05:00 JST land one day later than Chrono's game-day; Uma.moe
          simply doesn't carry the time of day.

        Returns (join_day, baseline_lifetime_fans).
        """
        first_pos = next(i for i in range(latest_day + 1) if fans[i] is not None and fans[i] > 0)

        if first_pos == 0:
            return 1, fans[0]
        if first_pos == 1:
            slot0 = fans[0]
            return 1, (abs(slot0) if slot0 is not None and slot0 < 0 else fans[1])

        join_day = min(first_pos + 2, latest_day)
        return join_day, fans[max(first_pos, join_day - 1)]

    def _parse_api_data(self, members: list, max_day: Optional[int] = None) -> Dict[str, Dict]:
        """
        Parse Uma.moe circle members into the same shape the Chrono parser produces.

        Uma.moe's ``daily_fans`` is a *lifetime* fan count per slot (32 slots for a 30-day
        month), where slot d matches Chrono's ``actual_date`` d and slot 0 is the baseline
        before day 1. Chrono instead reports fans gained this month, with ``fans[d - 1]`` being
        day d. This converts one into the other so ``fans[d - 1]`` means the same thing for both
        sources, and sets the data date/day from the newest populated slot (like Chrono's
        max ``actual_date``) instead of the wall clock.

        Args:
            members: ``members`` list from the Uma.moe ``/api/v4/circles`` response.
            max_day: Newest day allowed for the data (yesterday's day-of-month).
        """
        days_in_month = calendar.monthrange(self._fetched_year, self._fetched_month)[1]
        latest_day = min(self._latest_populated_day(members), days_in_month)
        if max_day is not None:
            latest_day = min(latest_day, max_day)

        if latest_day < 1:
            raise ValueError(
                f"Uma.moe has no fan data yet for {self._fetched_year}-{self._fetched_month:02d} "
                f"(typically published ~15:10 UTC)."
            )

        self.current_day_count = latest_day
        self._data_date = date(self._fetched_year, self._fetched_month, latest_day)
        logger.info(f"Uma.moe data covers day {latest_day} ({self._data_date})")

        parsed_data: Dict[str, Dict] = {}

        for member in members:
            viewer_id = member.get("viewer_id")
            trainer_name = member.get("trainer_name")
            lifetime_fans = member.get("daily_fans") or []

            if not viewer_id or not trainer_name:
                logger.warning(f"Skipping member with missing data: viewer_id={viewer_id}, name={trainer_name}")
                continue

            if len(lifetime_fans) <= latest_day:
                logger.warning(f"Day {latest_day} exceeds array length for {trainer_name}")
                continue

            # Skip members who are not in the club on the latest day (<= 0 = left / other club)
            latest_value = lifetime_fans[latest_day]
            if latest_value is None or latest_value <= 0:
                logger.debug(f"Skipping inactive member (left club or not in club): {trainer_name} (ID: {viewer_id})")
                continue

            join_day, baseline = self._resolve_join_and_baseline(lifetime_fans, latest_day)

            # Lifetime -> fans gained in this club this month, aligned with Chrono (index d-1 = day d).
            monthly_fans = []
            for day in range(1, latest_day + 1):
                value = lifetime_fans[day]
                if day < join_day or value is None or value <= 0:
                    monthly_fans.append(0)
                else:
                    monthly_fans.append(max(value - baseline, 0))

            viewer_id_str = str(viewer_id)
            parsed_data[viewer_id_str] = {
                "name": trainer_name,
                "trainer_id": viewer_id_str,
                "fans": monthly_fans,
                "join_day": join_day,
                "join_day_reliable": False,
            }

            logger.debug(
                f"Parsed {trainer_name}: joined day {join_day}, "
                f"lifetime: {baseline:,} -> {latest_value:,}, "
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
