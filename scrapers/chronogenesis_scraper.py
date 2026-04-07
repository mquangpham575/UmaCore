"""
ChronoGenesis website scraper using zendriver (Network Interception & UI Search)
This implementation adopts the successful strategy from the 'uma_tracking' project.
"""
import os
import asyncio
import json
import logging
import platform
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
        
        # Determine browser path (reusing your verified paths)
        if system == "Windows":
            executable = "C:/Program Files/Google/Chrome/Application/chrome.exe"
        else:
            executable = "/usr/bin/google-chrome"
            if not os.path.exists(executable):
                executable = "/usr/bin/chromium-browser"

        logger.info(f"Starting zendriver UI-flow with executable: {executable}")
        
        # We use headless=False because xvfb is now enabled in Docker
        browser = await zd.start(
            browser="chrome" if system == "Linux" else "edge",
            browser_executable_path=executable if os.path.exists(executable) else None,
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

            # 1. Start with the base profile search page
            logger.info("Navigating to base profile page...")
            page = await browser.get("https://chronogenesis.net/club_profile")
            await page.send(zd.cdp.network.enable())
            page.add_handler(zd.cdp.network.ResponseReceived, response_handler)
            
            # 2. Simulate Search UI Interaction
            logger.info(f"Simulating UI search for ID: {self.circle_id}")
            try:
                # Wait for the search box
                search_box = await page.select(".club-id-input", timeout=20)
                await search_box.send_keys(self.circle_id)
                await search_box.send_keys(zd.SpecialKeys.ENTER)
                await asyncio.sleep(3) # Wait for search results
                
                # Click the result row to trigger full data load
                results = await page.select_all(".club-results-row", timeout=10)
                for res in results:
                    if self.circle_id in res.text_all:
                        logger.info("Clicking search result...")
                        await res.click()
                        break
            except Exception as e:
                logger.warning(f"UI interaction failed or timed out: {e}. Falling back to direct wait.")

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