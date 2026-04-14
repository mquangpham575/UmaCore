import asyncio
import os
import argparse
import sys
from dotenv import load_dotenv

# Ensure we can import from the project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import db

load_dotenv()

async def clear_club_data(club_identifier: str, deactivate: bool = False):
    """
    Clears all member and history data for a specific club.
    
    Args:
        club_identifier: Club name or UUID
        deactivate: Whether to also deactivate the club entry
    """
    db.url = os.getenv("DATABASE_URL")
    await db.connect()
    
    try:
        # 1. Resolve club
        query = "SELECT club_id, club_name FROM clubs WHERE club_name = $1"
        try:
            import uuid
            uuid.UUID(club_identifier)
            query = "SELECT club_id, club_name FROM clubs WHERE club_id = $1"
        except ValueError:
            pass
            
        club = await db.fetchrow(query, club_identifier)
        if not club:
            print(f"Club '{club_identifier}' not found.")
            return
        
        club_id = club['club_id']
        club_name = club['club_name']
        print(f"Targeting club '{club_name}' (ID: {club_id})")
        
        # 2. Perform cleanup
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                if deactivate:
                    await conn.execute("UPDATE clubs SET is_active = FALSE WHERE club_id = $1", club_id)
                    print("Club deactivated.")
                
                # Tables to clear
                tables = [
                    "quota_history",
                    "bombs",
                    "quota_requirements",
                    "scrape_history",
                    "club_rank_history",
                    "scrape_locks",
                    "raw_scraped_data",
                    "members" # This will cascade to user_links
                ]
                
                for table in tables:
                    try:
                        res = await conn.execute(f"DELETE FROM {table} WHERE club_id = $1", club_id)
                        print(f"Cleared {table}: {res}")
                    except Exception as e:
                        print(f"Note: Could not clear {table} (might not have club_id column): {e}")

        print(f"Successfully cleared data for '{club_name}'.")
        
    finally:
        await db.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear all data for a specific club while keeping the club entry.")
    parser.add_argument("club", help="Club name or UUID")
    parser.add_argument("--deactivate", action="store_true", help="Deactivate the club after clearing data")
    
    args = parser.parse_args()
    
    asyncio.run(clear_club_data(args.club, args.deactivate))
