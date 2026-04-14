import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure we can import from the project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import db

load_dotenv()

async def reset_all_club_data():
    # Truncates all member and history tables for a full database reset.
    db.url = os.getenv("DATABASE_URL")
    await db.connect()
    
    try:
        print("--- DATABASE RESET STARTED ---")
        
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                # Tables to clear in order of dependency
                tables = [
                    "quota_history",
                    "bombs",
                    "quota_requirements",
                    "scrape_history",
                    "club_rank_history",
                    "scrape_locks",
                    "raw_scraped_data",
                    "user_links",
                    "members"
                ]
                
                for table in tables:
                    try:
                        # Check if table exists first to avoid unnecessary errors
                        table_exists = await conn.fetchval(
                            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)", 
                            table
                        )
                        if not table_exists:
                            print(f"Skipping {table} (table does not exist)")
                            continue
                            
                        res = await conn.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
                        print(f"Truncated {table}: {res}")
                    except Exception as e:
                        print(f"Failed to clear {table}: {e}")

        print("\n--- DATABASE RESET COMPLETE ---")
        print("All member and history data has been cleared.")
        print("Club configurations and bot settings have been preserved.")
        
    finally:
        await db.disconnect()

if __name__ == "__main__":
    # Main entry point for non-interactive execution.
    asyncio.run(reset_all_club_data())
