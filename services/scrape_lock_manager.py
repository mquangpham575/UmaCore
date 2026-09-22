"""
Scrape lock manager to prevent concurrent scraping conflicts
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID
import logging

from config.database import db

logger = logging.getLogger(__name__)


class ScrapeLockManager:
    """Manages scraping locks to prevent concurrent scrapes"""
    
    LOCK_TIMEOUT_MINUTES = 30  # Auto-release locks older than 30 minutes
    
    @staticmethod
    async def acquire_lock(club_id: UUID, locked_by: str = "bot") -> bool:
        """
        Try to acquire a scrape lock for a club
        
        Args:
            club_id: Club UUID
            locked_by: Identifier for who locked it
        
        Returns:
            True if lock acquired, False if already locked
        """
        try:
            # First, clean up stale locks
            await ScrapeLockManager._cleanup_stale_locks()
            
            # Try to insert lock
            query = """
                INSERT INTO scrape_locks (club_id, locked_at, locked_by)
                VALUES ($1, NOW(), $2)
                ON CONFLICT (club_id) DO NOTHING
                RETURNING club_id
            """
            result = await db.fetchrow(query, club_id, locked_by)
            
            if result:
                logger.info(f"Acquired scrape lock for club {club_id}")
                return True
            else:
                logger.warning(f"Could not acquire scrape lock for club {club_id} - already locked")
                return False
                
        except Exception as e:
            logger.error(f"Error acquiring scrape lock: {e}")
            return False
    
    @staticmethod
    async def release_lock(club_id: UUID):
        """Release a scrape lock"""
        try:
            query = "DELETE FROM scrape_locks WHERE club_id = $1"
            await db.execute(query, club_id)
            logger.info(f"Released scrape lock for club {club_id}")
        except Exception as e:
            logger.error(f"Error releasing scrape lock: {e}")
    
    @staticmethod
    async def _cleanup_stale_locks():
        """Remove locks older than LOCK_TIMEOUT_MINUTES"""
        try:
            timeout_threshold = datetime.now(timezone.utc) - timedelta(minutes=ScrapeLockManager.LOCK_TIMEOUT_MINUTES)
            
            query = """
                DELETE FROM scrape_locks 
                WHERE locked_at < $1
                RETURNING club_id
            """
            result = await db.fetch(query, timeout_threshold)
            
            if result:
                count = len(result)
                logger.warning(f"Cleaned up {count} stale scrape lock(s)")
                
        except Exception as e:
            logger.error(f"Error cleaning up stale locks: {e}")
    
    @staticmethod
    async def force_release_all():
        """Force release all locks (use with caution)"""
        try:
            query = "DELETE FROM scrape_locks"
            await db.execute(query)
            logger.warning("Force released all scrape locks")
        except Exception as e:
            logger.error(f"Error force releasing locks: {e}")


class ScrapeContext:
    """Context manager for scrape locks"""
    
    def __init__(self, club_id: UUID, locked_by: str = "bot"):
        self.club_id = club_id
        self.locked_by = locked_by
        self.lock_acquired = False
    
    async def __aenter__(self):
        """Acquire lock when entering context"""
        self.lock_acquired = await ScrapeLockManager.acquire_lock(
            self.club_id, self.locked_by
        )
        if not self.lock_acquired:
            raise RuntimeError(f"Could not acquire scrape lock for club {self.club_id}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release lock when exiting context"""
        if self.lock_acquired:
            await ScrapeLockManager.release_lock(self.club_id)
        return False
