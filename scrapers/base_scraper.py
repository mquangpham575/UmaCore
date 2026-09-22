"""
Base class for club data scrapers
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
from datetime import date


class BaseScraper(ABC):
    """Abstract base class for club data scrapers"""
    
    def __init__(self, url: str):
        self.url = url
    
    @abstractmethod
    async def scrape(self) -> Dict[str, Dict]:
        """
        Fetch club member data.

        Returns:
            Dict mapping trainer_id -> {"name", "trainer_id", "fans", "join_day", "join_day_reliable"}
            where fans[d - 1] is the fans gained this month through day d.
            Example: {
                "721295221870": {"name": "TrainerName", "trainer_id": "721295221870",
                                 "fans": [1000000, 2100000, 3050000],  # Day 1, 2, 3
                                 "join_day": 1, "join_day_reliable": True}
            }
        """
        pass
    
    @abstractmethod
    def get_current_day(self) -> int:
        """Get the current day number (1-indexed)"""
        pass
    
    @abstractmethod
    def get_data_date(self) -> Optional[date]:
        """
        Get the actual date the scraped data belongs to.
        
        Returns:
            date object if data belongs to a different date than today (e.g., Day 1 fallback)
            None if data matches current calendar date
        """
        pass
    
