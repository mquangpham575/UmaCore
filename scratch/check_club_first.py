import asyncio
from config.database import db
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    db.url = os.getenv("DATABASE_URL")
    await db.connect()
    try:
        row = await db.fetchrow("SELECT * FROM clubs WHERE UPPER(club_name) = 'FIRST'")
        if row:
            print("Club details:")
            for key, val in dict(row).items():
                print(f"  {key}: {val}")
        else:
            print("Club 'First' not found in database.")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
