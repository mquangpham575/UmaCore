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
        match = re.search(r'circle_id=(\d+)', url)
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
            for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
                path = shutil.which(name)
                if path:
                    executable = path
                    break
            if not executable:
                for path in ("/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"):
                    if os.path.isfile(path):
                        executable = path
                        break
            if not executable:
                logger.error("No Chrome/Chromium browser found on this system")
                return {}

        logger.info(f"Starting zendriver UI-flow with executable: {executable}")


        # We use headless=False because xvfb is now enabled in Docker
        browser = await zd.start(
            browser="chrome" if system == "Linux" else "edge",
            browser_executable_path=executable,
            headless=False, # Revert to use virtual display
            sandbox=False,
            browser_args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
            browser_connection_timeout=5.0,
            browser_connection_max_tries=30,
        )

        best_response = None

        try:
            # Store request_ids only — fetch bodies after page settles
            # (matching uma_tracking's proven pattern that avoids CDP listener deadlock)
            captured_responses = {}

            async def response_handler(*args, **kwargs):
                if args and hasattr(args[0], 'response'):
                    url = args[0].response.url
                    if "api.chronogenesis.net/club_profile" in url:
                        try:
                            captured_responses[args[0].request_id] = url
                        except Exception:
                            pass

            # Navigate directly to the club profile page like uma_tracking/src/chrono_scraper.py
            page = await browser.get("https://chronogenesis.net/club_profile")
            await page.send(zd.cdp.network.enable())
            page.add_handler(zd.cdp.network.ResponseReceived, response_handler)
            
            # Wait for any potential redirection or loading
            await asyncio.sleep(5)

            search_box = await page.select(".club-id-input", timeout=60)
            await search_box.send_keys(self.circle_id)
            await search_box.send_keys(zd.SpecialKeys.ENTER)
            await asyncio.sleep(3)

            # Click the result to ensure full club data is loaded
            try:
                results = await page.select_all(".club-results-row", timeout=10)
                for result in results:
                    content = result.text_all.lower()
                    if self.circle_id in content:
                        await result.click()
                        break
            except Exception:
                pass

            # Wait for background requests to complete
            await asyncio.sleep(8)

            target_url_prefix = f"https://api.chronogenesis.net/club_profile?circle_id={self.circle_id}"
            logger.info(f"Captured {len(captured_responses)} club_profile request(s)")

            for req_id, url in captured_responses.items():
                try:
                    response_body, _ = await page.send(
                        zd.cdp.network.get_response_body(request_id=req_id)
                    )
                    # Priority selection matching uma_tracking logic:
                    # Prefer responses that explicitly contain history data or match the target URL
                    if "club_friend_history" in response_body or url.startswith(target_url_prefix):
                        if best_response is None or "club_friend_history" in response_body:
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
        history = data.get("club_friend_history", [])
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
                    "daily_map": {}, # day -> (lifetime, gain)
                }
            
            member_data[trainer_id]["daily_map"][day] = (lifetime, gain)
            all_days.add(day)

        if not all_days:
            return {}
        
        day_numbers = sorted(list(all_days))
        self.club_start_day = day_numbers[0]
        self.current_day_count = day_numbers[-1]
        
        # Set the data date based on current month/year and the latest day in history
        now = date.today()
        self._data_date = date(now.year, now.month, self.current_day_count)
        
        logger.info(f"Parsed {len(member_data)} members. Data covers days {self.club_start_day} to {self.current_day_count}. Data date: {self._data_date}")

        final_data = {}
        for tid, info in member_data.items():
            # FILTER: only include members who are present in the latest snapshot
            if self.current_day_count not in info["daily_map"]:
                logger.debug(f"Skipping member {info['name']} (ID: {tid}) - no data for latest day {self.current_day_count}")
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
                "join_day": join_day
            }

        return final_data

    def get_current_day(self) -> int:
        return self.current_day_count
    
    def get_club_start_day(self) -> int:
        return self.club_start_day
    
    def get_data_date(self) -> Optional[date]:
        return self._data_date