"""
Logging configuration
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from config.settings import LOG_LEVEL, LOG_FILE


def setup_logging():
    """Configure logging for the application"""
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(name)s - %(levelname)s: %(message)s'
    )
    
    # Console handler (stdout) with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # Fix for Windows: Force UTF-8 encoding on console
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    # File handler with rotation and UTF-8 encoding
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'  # Added UTF-8 encoding
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    # Aggressive suppression
    # Set root to WARNING to catch all third-party noise, then explicitly enable our code
    logger.setLevel(logging.WARNING)
    logging.getLogger('bot').setLevel(logging.INFO)
    logging.getLogger('scrapers').setLevel(logging.INFO)
    logging.getLogger('services').setLevel(logging.INFO)
    logging.getLogger('utils').setLevel(logging.INFO)
    logging.getLogger('models').setLevel(logging.INFO)
    logging.getLogger('__main__').setLevel(logging.INFO)
    
    # Specifically target the loudest ones
    logging.getLogger('zendriver').setLevel(logging.CRITICAL)
    logging.getLogger('cdp').setLevel(logging.CRITICAL)
    logging.getLogger('asyncio').setLevel(logging.CRITICAL)
    
    logger.info("Logging configured successfully - filtering third-party noise")