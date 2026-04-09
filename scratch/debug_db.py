import asyncio
import sys
import os
sys.path.append(os.getcwd())
from config.database import db
from config.settings import DATABASE_URL

async def debug_club_info():
    # Initialize DB (using the URL from settings)
    db.url = DATABASE_URL
    await db.connect()
    try:
        # Check column types for clubs table
        columns = await db.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'clubs'
        """)
        print("Column Types:")
        for col in columns:
            print(f"  {col['column_name']}: {col['data_type']}")
        
        # Check specific club info
        club_name = "Endcore (S+)"
        row = await db.fetchrow("SELECT club_name, report_channel_id, guild_id FROM clubs WHERE club_name = $1", club_name)
        if row:
            print(f"\nClub Info for '{club_name}':")
            print(f"  report_channel_id: {row['report_channel_id']} (Type: {type(row['report_channel_id'])})")
            print(f"  guild_id: {row['guild_id']}")
        else:
            print(f"\nClub '{club_name}' not found.")
            
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(debug_club_info())
