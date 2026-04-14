import asyncio
import os
import sys
from datetime import datetime
import pytz
from dotenv import load_dotenv

# Ensure we can import from the project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Club
from scrapers import UmaGitHubScraper
from services import QuotaCalculator, ScrapeContext
from config.database import db

load_dotenv()

async def scrape_all_active_clubs():
    # Iterates through all active clubs and runs the GitHub scraper for each to repopulate data.
    db.url = os.getenv("DATABASE_URL")
    await db.connect()
    
    try:
        quota_calculator = QuotaCalculator()
        # Fetch all active clubs
        clubs = await Club.get_all_active()
        print(f"--- STARTING BATCH SCRAPE FOR {len(clubs)} CLUBS ---")
        
        for club in clubs:
            print(f"\nProcessing {club.club_name} (ID: {club.club_id})...")
            try:
                # Calculate current date in club's timezone
                club_tz = pytz.timezone(club.timezone)
                current_date = datetime.now(club_tz).date()

                # Use ScrapeContext to manage locks
                async with ScrapeContext(club.club_id, "batch_scrape"):
                    # Initialize the new GitHub scraper
                    scraper = UmaGitHubScraper(club.circle_id)
                    print(f"  - Scraping data...")
                    scraped_data = await scraper.scrape()
                    
                    # Use the scraper's day/date as it handles monthly overlaps correctly
                    current_day = scraper.get_current_day()
                    data_date = scraper.get_data_date() or current_date
                    
                    if not scraped_data:
                        print(f"  - No data found for {club.club_name}")
                        continue
                    
                    print(f"  - Processing {len(scraped_data)} members for date {data_date}...")
                    # Process and save data to DB
                    await quota_calculator.process_scraped_data(
                        club.club_id, 
                        scraped_data, 
                        data_date, 
                        current_day,
                        quota_period=club.quota_period
                    )
                    print(f"  - Success!")
            except Exception as e:
                print(f"  - FAILED: {e}")

        print("\n--- BATCH SCRAPE COMPLETE ---")
        
    finally:
        await db.disconnect()

if __name__ == "__main__":
    # Main entry point for the batch scrape.
    asyncio.run(scrape_all_active_clubs())
