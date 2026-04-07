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
            headless=False, # xvfb-run provides a virtual display
            sandbox=False,
            browser_args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
            browser_connection_timeout=1.0,
            browser_connection_max_tries=30,
        )

        captured_json = None
        
        try:
            target_url_fragment = f"api.chronogenesis.net/club_profile?circle_id={self.circle_id}"
            
            async def response_handler(event: zd.cdp.network.ResponseReceived):
                nonlocal captured_json
                if target_url_fragment in event.response.url:
                    try:
                        # Fetch the body for this request
                        body, _ = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
                        # Basic validation that it's the correct data
                        if "club_friend_history" in body:
                            captured_json = json.loads(body)
                            logger.info(f"Captured API response for {event.response.url}")
                    except Exception as e:
                        logger.debug(f"Captured data, but failed to parse API body: {e}")

            # 1. Navigate directly to the club profile with circle_id (skips fragile search UI)
            direct_url = f"https://chronogenesis.net/club_profile?circle_id={self.circle_id}"
            logger.info(f"Navigating directly to: {direct_url}")
            page = await browser.get(direct_url)
            await page.send(zd.cdp.network.enable())
            page.add_handler(zd.cdp.network.ResponseReceived, response_handler)

            # The page auto-loads data when circle_id is in the URL.
            # If the API call already fired before our handler was attached,
            # trigger a reload to ensure we capture it.
            if not captured_json:
                await asyncio.sleep(2)
            if not captured_json:
                logger.info("No API response captured yet, reloading to trigger data fetch...")
                page = await browser.get(direct_url)
                await page.send(zd.cdp.network.enable())
                page.add_handler(zd.cdp.network.ResponseReceived, response_handler)

            # 3. Wait for data to be captured via network intercept
            logger.info("Waiting for data capture...")
            for _ in range(30): # 30 second timeout for the capture
                if captured_json:
                    break
                await asyncio.sleep(1)
                
            if not captured_json:
                logger.error("Timed out waiting for ChronoGenesis API response via UI flow")
                return {}

            return self._parse_api_json(captured_json)

        finally:
            await browser.stop()

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