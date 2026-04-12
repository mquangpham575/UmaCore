import asyncio
import logging
from config.database import db
from config.settings import DATABASE_URL
from datetime import date

async def check_club_updates():
    db.url = DATABASE_URL
    await db.connect()
    
    try:
        query = """
            SELECT c.club_name, MAX(qh.date) as last_update
            FROM clubs c
            LEFT JOIN quota_history qh ON c.club_id = qh.club_id
            WHERE c.is_active = TRUE
            GROUP BY c.club_name
            ORDER BY last_update DESC;
        """
        rows = await db.fetch(query)
        
        today = date(2026, 4, 12)
        print(f"Club Update Status (Today is {today}):")
        print("-" * 50)
        
        updated = []
        pending = []
        
        for row in rows:
            name = row['club_name']
            last_date = row['last_update']
            
            if last_date == today:
                updated.append(name)
            else:
                pending.append((name, last_date))
        
        print(f"\n✅ UPDATED TODAY ({len(updated)}/{(len(updated) + len(pending))}):")
        for name in updated:
            print(f"  - {name}")
            
        print(f"\n⏳ PENDING / LAST UPDATE ({len(pending)}):")
        for name, last_date in pending:
            print(f"  - {name}: {last_date or 'No data found'}")
            
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(check_club_updates())
