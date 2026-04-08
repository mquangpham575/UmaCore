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

        # Chrome user-agent prevents Cloudflare Turnstile from blocking Chromium
        chrome_ua = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        )

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

        return self._parse_api_json(json.loads(best_response))

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
            
            # Use 'adjusted_interpolated_fan_gain' from uma_tracking, fallback to 'fan_count'
            fans = entry.get("adjusted_interpolated_fan_gain")
            if fans is None:
                fans = entry.get("fan_count", 0)
            
            if not trainer_id:
                continue
            
            if trainer_id not in member_data:
                member_data[trainer_id] = {
                    "name": name,
                    "trainer_id": trainer_id,
                    "daily_map": {}
                }
            
            member_data[trainer_id]["daily_map"][day] = fans
            all_days.add(day)

        if not all_days:
            return {}
        
        day_numbers = sorted(list(all_days))
        self.club_start_day = day_numbers[0]
        self.current_day_count = day_numbers[-1]
        
        logger.info(f"Parsed {len(member_data)} members. Data covers days {self.club_start_day} to {self.current_day_count}.")

        final_data = {}
        for tid, info in member_data.items():
            fans_list = []
            join_day = self.club_start_day
            found_first = False
            
            for d in day_numbers:
                f = info["daily_map"].get(d, 0)
                fans_list.append(f)
                if not found_first and f > 0:
                    found_first = True
                    join_day = d
            
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