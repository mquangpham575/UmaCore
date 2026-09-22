"""
Configuration settings for the Umamusume Discord Bot
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Discord Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL")

# GitHub Action Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "mquangpham575/Uma_Club_Fan_Tracking")

# Quota Rules
DAILY_QUOTA = 1_000_000

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = "bot.log"

# Discord Embed Colors
COLOR_ON_TRACK = 0x00FF00  # Green
COLOR_BEHIND = 0xFFA500     # Orange
COLOR_BOMB = 0xFF0000       # Red
COLOR_INFO = 0x3498db       # Blue