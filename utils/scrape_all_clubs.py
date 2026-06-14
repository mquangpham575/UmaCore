"""
utils/scrape_all_clubs.py - Bulk sync utility for all active clubs.
This script is triggered by 'bot_control.ps1 sync-all'.
"""
import asyncio
import logging
import sys
import os
from datetime import datetime
import pytz

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import db
from config.settings import DATABASE_URL
from models import Club
from scrapers import UmaGitHubScraper
from services import QuotaCalculator, ScrapeContext

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("scrape_all_clubs")

async def scrape_club(club: Club, quota_calculator: QuotaCalculator):
    """Scrape and process data for a single club"""
    logger.info(f"Processing club: {club.club_name} (ID: {club.club_id})")
    
    try:
        async with ScrapeContext(club.club_id, "bulk_sync_utility"):
            # Select circle_id
            circle_id = club.circle_id
            if not circle_id:
                import re
                match = re.search(r'circle_id=(\d+)', club.scrape_url)
                if not match:
                    match = re.search(r'circles/(\d+)', club.scrape_url)
                if match:
                    circle_id = match.group(1)
            
            if not circle_id:
                logger.error(f"Club {club.club_name} missing circle_id and not in scrape_url. Skipping.")
                return False

            scraper = UmaGitHubScraper(circle_id)
            scraped_data = await scraper.scrape()
            current_day = scraper.get_current_day()
            
            if not scraped_data:
                logger.error(f"Failed to scrape data for {club.club_name}")
                return False

            # Determine data date
            club_tz = pytz.timezone(club.timezone)
            current_date = datetime.now(club_tz).date()
            
            data_date = scraper.get_data_date()
            if data_date:
                current_date = data_date
                logger.info(f"Using scraper's data date: {current_date}")

            # Process data (this triggers self-correction for join dates)
            new_members, updated_members = await quota_calculator.process_scraped_data(
                club.club_id, scraped_data, current_date, current_day,
                quota_period=club.quota_period
            )
            
            logger.info(f"Successfully processed {club.club_name}: {new_members} new, {updated_members} updated.")
            return True

    except Exception as e:
        logger.error(f"Error processing {club.club_name}: {e}", exc_info=True)
        return False

async def main():
    """Main execution function"""
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set.")
        return

    db.url = DATABASE_URL
    
    try:
        await db.connect()
        logger.info("Connected to database.")
        
        clubs = await Club.get_all_active()
        logger.info(f"Found {len(clubs)} active clubs to sync.")
        
        quota_calculator = QuotaCalculator()
        
        results = []
        for club in clubs:
            success = await scrape_club(club, quota_calculator)
            results.append(success)
            # Small delay between clubs to prevent API rate limits
            await asyncio.sleep(2)
            
        success_count = sum(1 for r in results if r)
        logger.info(f"Bulk sync finished. Success: {success_count}/{len(clubs)}")
        
    except Exception as e:
        logger.error(f"Fatal error in bulk sync: {e}", exc_info=True)
    finally:
        await db.disconnect()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    asyncio.run(main())
