"""
Scrapers package
"""
from .base_scraper import BaseScraper
from .chrono_api_scraper import UmaGitHubScraper

__all__ = ['BaseScraper', 'UmaGitHubScraper']
