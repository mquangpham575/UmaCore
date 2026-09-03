"""
utils/recompute_quotas.py - Recompute expected_fans, deficit_surplus, and
days_behind for a club's current-month quota_history using the current
quota_requirements + club default.

Usage: python utils/recompute_quotas.py "<club name>"
Run inside the bot container: docker exec -t umacore-bot python utils/recompute_quotas.py "ENDGAME (S)"
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
from services import QuotaCalculator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("recompute_quotas")


async def recompute_club(club_name: str):
    """Recompute quota history for a club's current month."""
    db.url = DATABASE_URL
    try:
        await db.connect()
        logger.info("Connected to database.")

        club = await Club.get_by_name(club_name)
        if not club:
            logger.error(f"Club '{club_name}' not found.")
            return

        club_tz = pytz.timezone(club.timezone)
        current_date = datetime.now(club_tz).date()

        # Current effective requirements + club default
        rows = await db.fetch(
            """
            SELECT effective_date, daily_quota
            FROM quota_requirements
            WHERE club_id = $1 AND effective_date <= $2
            ORDER BY effective_date ASC
            """,
            club.club_id, current_date
        )
        pre_fetched = [(r['effective_date'], r['daily_quota']) for r in rows]
        default_quota = club.daily_quota
        logger.info(
            f"{club.club_name}: default quota {default_quota:,}, "
            f"{len(pre_fetched)} requirement(s): "
            + ", ".join(f"{d}->{q:,}" for d, q in pre_fetched)
        )

        # Member join dates (all members, active or not, to cover departed members)
        member_rows = await db.fetch(
            "SELECT member_id, join_date FROM members WHERE club_id = $1", club.club_id
        )
        member_join = {r['member_id']: r['join_date'] for r in member_rows}

        hist_rows = await db.fetch(
            """
            SELECT id, member_id, date, cumulative_fans
            FROM quota_history
            WHERE club_id = $1
              AND date_part('year', date) = $2
              AND date_part('month', date) = $3
            ORDER BY member_id, date ASC
            """,
            club.club_id, current_date.year, current_date.month
        )

        by_member = {}
        for row in hist_rows:
            by_member.setdefault(row['member_id'], []).append(row)

        total = 0
        for member_id, member_hist in by_member.items():
            join_date = member_join.get(member_id)
            if not join_date:
                logger.warning(f"Member {member_id} has history but no join_date. Skipping.")
                continue

            consecutive = 0
            for row in member_hist:
                expected = await QuotaCalculator.calculate_expected_fans(
                    club.club_id, join_date, row['date'], club.quota_period,
                    pre_fetched_requirements=pre_fetched, default_quota=default_quota
                )
                deficit = row['cumulative_fans'] - expected
                consecutive = consecutive + 1 if deficit < 0 else 0
                await db.execute(
                    """
                    UPDATE quota_history
                    SET expected_fans = $1, deficit_surplus = $2, days_behind = $3
                    WHERE id = $4
                    """,
                    expected, deficit, consecutive, row['id']
                )
                total += 1

        logger.info(f"Recomputed {total} history entries for {club.club_name}.")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await db.disconnect()
        logger.info("Database connection closed.")


async def main():
    """Main execution function"""
    if len(sys.argv) < 2:
        logger.error("Usage: python utils/recompute_quotas.py '<club name>'")
        return
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set.")
        return
    await recompute_club(sys.argv[1])


if __name__ == "__main__":
    asyncio.run(main())
