"""
ChronoGenesis website scraper using zendriver (Network Interception & UI Search)
This implementation adopts the successful strategy from the 'uma_tracking' project.
"""

import os
import asyncio
import json
import logging
import platform
import shutil
from typing import Dict, Optional
from datetime import date

import zendriver as zd
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ChronoGenesisScraper(BaseScraper):
    """Scraper for ChronoGenesis.net using network interception and UI simulation"""

    def __init__(self, url: str):
        super().__init__(url)
        self.circle_id = self._extract_circle_id(url)
        self.current_day_count = 1
        self.club_start_day = 1
        self._data_date = None

    def _extract_circle_id(self, url: str) -> str:
        """Extract circle_id from URL"""
        import re

        match = re.search(r"circle_id=(\d+)", url)
        if match:
            return match.group(1)
        return ""

    async def scrape(self) -> Dict[str, Dict]:
        """
        Scrape ChronoGenesis by simulating UI search and intercepting API responses.
        Adopts the proven strategy from 'uma_tracking'.
        """
        if not self.circle_id:
            logger.error(f"Could not extract circle_id from {self.url}")
            return {}

        system = platform.system()

        # Determine browser path dynamically
        if system == "Windows":
            executable = "C:/Program Files/Google/Chrome/Application/chrome.exe"
        else:
            # Search PATH first, then check common hardcoded locations
            executable = None
            for name in (
                "google-chrome",
                "google-chrome-stable",
                "chromium-browser",
                "chromium",
            ):
                path = shutil.which(name)
                if path:
                    executable = path
                    break
            if not executable:
                for path in (
                    "/usr/bin/google-chrome",
                    "/usr/bin/chromium-browser",
                    "/usr/bin/chromium",
                ):
                    if os.path.isfile(path):
                        executable = path
                        break
            if not executable:
                logger.error("No Chrome/Chromium browser found on this system")
                return {}

        logger.info(f"Starting zendriver UI-flow with executable: {executable}")

        browser = await zd.start(
            browser_executable_path=executable,
            browser_connection_timeout=5.0,
            browser_connection_max_tries=60,
        )

        best_response = None

        try:
            # Store request_ids only — fetch bodies after page settles
            # (matching uma_tracking's proven pattern that avoids CDP listener deadlock)
            captured_responses = {}

            async def response_handler(*args, **kwargs):
                if args and hasattr(args[0], "response"):
                    url = args[0].response.url
                    if "api.chronogenesis.net/club_profile" in url:
                        try:
                            captured_responses[args[0].request_id] = url
                        except Exception:
                            pass

            page = await browser.get("https://chronogenesis.net/club_profile")
            await asyncio.sleep(3)
            await page.send(zd.cdp.network.enable())
            page.add_handler(zd.cdp.network.ResponseReceived, response_handler)

            search_box = await page.select(".club-id-input", timeout=60)
            logger.info("Search box found")
            await search_box.click()
            await asyncio.sleep(1)
            await search_box.send_keys(self.circle_id)
            await asyncio.sleep(1)
            await search_box.send_keys(zd.SpecialKeys.ENTER)
            logger.info(f"Entered circle_id {self.circle_id} and submitted search.")
            await asyncio.sleep(3)

            try:
                page_url = page.url
                logger.info(f"Current URL after search: {page_url}")
            except:
                logger.info("Could not get page URL")

            try:
                results = await page.select_all(".club-results-row", timeout=45)
                logger.info(f"Found {len(results)} club results")
                for result in results:
                    content = result.text_all.lower()
                    logger.info(f"Checking result: {content[:100]}...")
                    if self.circle_id in content:
                        await result.click()
                        logger.info(f"Clicked club row for {self.circle_id}")
                        break
            except Exception as e:
                logger.warning(f"Could not click club row: {e}")

            await asyncio.sleep(8)

            # Wait for background requests to complete
            await asyncio.sleep(8)

            target_url_prefix = (
                f"https://api.chronogenesis.net/club_profile?circle_id={self.circle_id}"
            )
            logger.info(f"Captured {len(captured_responses)} club_profile request(s)")

            for req_id, url in list(captured_responses.items()):
                try:
                    response_body, _ = await page.send(
                        zd.cdp.network.get_response_body(request_id=req_id)
                    )
                    logger.info(
                        f"Checking response {url[:80]}... has_history={('club_friend_history' in response_body)}"
                    )
                    if "club_friend_history" in response_body or url.startswith(
                        target_url_prefix
                    ):
                        if (
                            best_response is None
                            or "club_friend_history" in response_body
                        ):
                            best_response = response_body
                            logger.info(f"Selected response: {url}")
                except Exception:
                    pass
        finally:
            await browser.stop()

        if not best_response:
            logger.error("No ChronoGenesis API response captured")
            return {}

        self._raw_response = json.loads(best_response)
        return self._parse_api_json(self._raw_response)

    def _parse_api_json(self, data: dict) -> Dict[str, Dict]:
        """Parse core daily data from captured JSON"""
        history = data.get("club_friend_history") or data.get("club_daily_history") or []
        if not history:
            logger.warning("Empty club_friend_history in API response")
            return {}

        member_data = {}
        all_days = set()

        # Group data by member
        for entry in history:
            trainer_id = str(entry.get("friend_viewer_id", ""))
            name = entry.get("friend_name", "Unknown")
            day = entry.get("actual_date")

            # Chrono provides lifetime total as 'interpolated_fan_count' in history entries
            lifetime = entry.get("interpolated_fan_count")
            if lifetime is None:
                lifetime = entry.get("fan_count", 0)

            gain = entry.get("adjusted_interpolated_fan_gain", 0)

            if not trainer_id:
                continue

            if trainer_id not in member_data:
                member_data[trainer_id] = {
                    "name": name,
                    "trainer_id": trainer_id,
                    "daily_map": {},  # day -> (lifetime, gain)
                }

            member_data[trainer_id]["daily_map"][day] = (lifetime, gain)
            all_days.add(day)

        if not all_days:
            return {}

        day_numbers = sorted(list(all_days))
        self.club_start_day = day_numbers[0]
        self.current_day_count = day_numbers[-1]

        # Set the data date based on the month being filtered and the latest day in history
        # ChronoGenesis provides 'sdate' (e.g., "2026-04-01") in month_filter[0]
        month_filter = data.get("month_filter", [])
        if month_filter and "sdate" in month_filter[0]:
            try:
                from datetime import datetime as dt

                filter_date = dt.strptime(month_filter[0]["sdate"], "%Y-%m-%d").date()
                self._data_date = date(
                    filter_date.year, filter_date.month, self.current_day_count
                )
                logger.debug(f"Resolved data_date from month_filter: {self._data_date}")
            except Exception as e:
                logger.warning(
                    f"Failed to parse month_filter sdate: {e}. Falling back to server month."
                )
                now = date.today()
                self._data_date = date(now.year, now.month, self.current_day_count)
        else:
            now = date.today()
            self._data_date = date(now.year, now.month, self.current_day_count)

        logger.info(
            f"Parsed {len(member_data)} members. Data covers days {self.club_start_day} to {self.current_day_count}. Data date: {self._data_date}"
        )

        final_data = {}
        for tid, info in member_data.items():
            # FILTER: only include members who are present in the latest snapshot
            if self.current_day_count not in info["daily_map"]:
                logger.debug(
                    f"Skipping member {info['name']} (ID: {tid}) - no data for latest day {self.current_day_count}"
                )
                continue

            # CALIBRATION: Find the baseline (lifetime fans before the first history entry)
            # This ensures that even if history starts mid-month, growth is tracked correctly.
            earliest_day = min(info["daily_map"].keys())
            e_lifetime, e_gain = info["daily_map"][earliest_day]
            baseline = e_lifetime - e_gain

            fans_list = []
            join_day = earliest_day

            for d in day_numbers:
                if d in info["daily_map"]:
                    lifetime, gain = info["daily_map"][d]
                    # Monthly cumulative fans = Lifetime total - Baseline (fans at start of history)
                    current_val = lifetime - baseline
                else:
                    # No data for this day in history
                    current_val = 0

                fans_list.append(current_val)

            final_data[tid] = {
                "name": info["name"],
                "trainer_id": tid,
                "fans": fans_list,
                "join_day": join_day,
            }

        return final_data

    def get_current_day(self) -> int:
        return self.current_day_count

    def get_club_start_day(self) -> int:
        return self.club_start_day

    def get_data_date(self) -> Optional[date]:
        return self._data_date
