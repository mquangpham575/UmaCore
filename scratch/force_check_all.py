
import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

import sys
import os
# Add the project root to sys.path to import models and services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import Database
from config.settings import DATABASE_URL
from models.club import Club
from scrapers.umamoe_api_scraper import UmaGitHubScraper
from services.quota_calculator import QuotaCalculator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ForceCheckAll")

async def force_check_all():
    if not DATABASE_URL:
        logger.error("DATABASE_URL not found in environment")
        return

    db = Database(DATABASE_URL)
    await db.connect()
    
    # Initialize global DB for models
    from models.club import Club
    from models.member import Member
    from models.quota_history import QuotaHistory
    from models.quota_requirement import QuotaRequirement
    
    Club.db = db
    Member.db = db
    QuotaHistory.db = db
    QuotaRequirement.db = db
    
    calculator = QuotaCalculator()
    
    try:
        # Get all active clubs
        clubs = await Club.get_active_clubs()
        logger.info(f"Found {len(clubs)} active clubs to sync")
        
        for club in clubs:
            logger.info(f"Syncing club: {club.club_name} (ID: {club.circle_id})")
            try:
                scraper = UmaGitHubScraper(club.circle_id)
                scraped_data = await scraper.scrape()
                
                if not scraped_data:
                    logger.warning(f"No data scraped for {club.club_name}")
                    continue
                
                current_day = scraper.get_current_day()
                data_date = scraper.get_data_date() or datetime.now().date()
                
                new_count, updated_count = await calculator.process_scraped_data(
                    club.club_id, scraped_data, data_date, current_day
                )
                
                logger.info(f"Successfully synced {club.club_name}: {updated_count} members updated, {new_count} new")
            except Exception as e:
                logger.error(f"Failed to sync {club.club_name}: {e}")
                
        logger.info("Force check completed for all clubs.")
        
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(force_check_all())
