"""
ChronoGenesis website scraper using zendriver (Network Interception)
"""
import asyncio
import json
import logging
import platform
from typing import Dict, List, Optional
from datetime import date

import zendriver as zd
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class ChronoGenesisScraper(BaseScraper):
    """Scraper for ChronoGenesis.net using network interception"""
    
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
        Scrape ChronoGenesis by intercepting API responses.
        """
        if not self.circle_id:
            logger.error(f"Could not extract circle_id from {self.url}")
            return {}

        system = platform.system()
        machine = platform.machine().lower()
        
        # Determine browser path based on platform (same logic as uma_tracking)
        if system == "Windows":
            executable = "C:/Program Files/Google/Chrome/Application/chrome.exe"
            # Fallback for Brave if needed, but Chrome is safer for Actions
        else:
            executable = "/usr/bin/google-chrome"
            if not os.path.exists(executable):
                executable = "/usr/bin/chromium-browser"

        logger.info(f"Starting zendriver with executable: {executable}")
        
        browser = await zd.start(
            browser="chrome" if system == "Linux" else "edge", # zendriver uses 'edge' for chromium-based on Windows sometimes
            browser_executable_path=executable if os.path.exists(executable) else None,
            headless=True,
            sandbox=False,
            browser_args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
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
                        captured_json = json.loads(body)
                        logger.info(f"Captured API response for {event.response.url}")
                    except Exception as e:
                        logger.debug(f"Failed to parse API body: {e}")

            page = await browser.get(self.url)
            await page.send(zd.cdp.network.enable())
            page.add_handler(zd.cdp.network.ResponseReceived, response_handler)
            
            # Wait for data to load
            logger.info("Waiting for API response capture...")
            for _ in range(20): # 20 second timeout
                if captured_json:
                    break
                await asyncio.sleep(1)
                
            if not captured_json:
                logger.error("Timed out waiting for ChronoGenesis API response")
                return {}

            return self._parse_api_json(captured_json)

        finally:
            await browser.stop()

    def _parse_api_json(self, data: dict) -> Dict[str, Dict]:
        """
        Parse the JSON from api.chronogenesis.net/club_profile
        """
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
            fans = entry.get("fan_count", 0) # API usually provides cumulative or daily?
            # ChronoGenesis API 'fan_count' in history is cumulative for that day.
            
            if not trainer_id: continue
            
            if trainer_id not in member_data:
                member_data[trainer_id] = {
                    "name": name,
                    "trainer_id": trainer_id,
                    "daily_map": {}
                }
            
            member_data[trainer_id]["daily_map"][day] = fans
            all_days.add(day)

        if not all_days: return {}
        
        day_numbers = sorted(list(all_days))
        self.club_start_day = day_numbers[0]
        self.current_day_count = day_numbers[-1]
        
        logger.info(f"Parsed {len(member_data)} members. Data covers days {self.club_start_day} to {self.current_day_count}.")

        final_data = {}
        for tid, info in member_data.items():
            # Create the list of daily cumulative fans
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

import os