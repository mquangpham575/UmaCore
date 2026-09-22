# UmaCore Club Quota Tracker

<div align="center">

**Discord bot for tracking and managing Umamusume club member quotas**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Discord.py](https://img.shields.io/badge/discord.py-2.3+-5865F2?style=flat-square&logo=discord)](https://discordpy.readthedocs.io/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Ko-Fi](https://img.shields.io/badge/Support-Ko--fi-FF5E5B?style=flat-square&logo=ko-fi)](https://ko-fi.com/harukidev)

</div>

## Overview

Automated Discord bot that tracks club member fan quotas, manages warning systems, and generates daily performance reports. Supports multiple clubs with independent tracking and customizable settings. Club data comes from the ChronoGenesis API, with the Uma.moe API as an automatic fallback.

## Key Features

- **Multi-Club Support**: Track multiple clubs independently with separate quotas and schedules
- **ChronoGenesis API**: Primary data source (needs `CHRONO_API_KEY`)
- **Uma.moe API**: Automatic fallback when Chrono is unavailable or no key is set
- **Dynamic Quota System**: Flexible daily quota requirements with mid-month changes
- **Bomb Warning System**: 3-strike countdown system for members falling behind
- **User Linking**: Members can link their Discord accounts for DM notifications
- **Smart Member Management**: Auto-detects when members leave or return
- **Monthly Reset Handling**: Automatically detects and handles monthly game resets
- **Scrape Locking**: Prevents concurrent scraping conflicts

## Setup

### Prerequisites

- Python 3.10 or higher
- PostgreSQL database ([Neon](https://neon.tech), [Supabase](https://supabase.com), etc.)
- Discord bot token ([Discord Developer Portal](https://discord.com/developers/applications))

### Installation

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd umamusume-bot
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up PostgreSQL database**
   - Create a database on your preferred PostgreSQL provider
   - Copy the connection string

4. **Configure Discord bot**
   - Visit [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application and bot
   - Enable "Server Members Intent" and "Message Content Intent" under Bot settings
   - Copy the bot token
   - Invite the bot with permissions: Send Messages, Embed Links, Read Messages

5. **Create `.env` file**

   ```env
   DISCORD_TOKEN=your_bot_token_here
   DATABASE_URL=postgresql://user:password@host:5432/database_name
   LOG_LEVEL=INFO
   UMAMOE_API_KEY=your_uma_moe_key
   CHRONO_API_KEY=your_chrono_key   # optional, primary source
   ```

6. **Run the bot**
   ```bash
   python main.py
   ```

The bot will automatically create database tables on first run.

## Quick Start

1. **Add your club**

   ```
   /add_club club_name:YourClubName circle_id:your_circle_id
   ```

   The `circle_id` is a numeric ID from Uma.moe. To find it:
   1. Go to https://uma.moe/circles/
   2. Search for your club
   3. Copy the number at the end of the URL (e.g., `https://uma.moe/circles/860280110` → `860280110`)

2. **Set up channels**

   ```
   /set_report_channel club:YourClubName channel:#daily-reports
   /set_alert_channel club:YourClubName channel:#mod-alerts
   ```

3. **Test the system**
   ```
   /force_check club:YourClubName
   ```

The bot will run daily checks automatically at the scheduled time (default: 16:00 CEST).

## Data Sources

Every scrape tries the sources in this order (see [docs/data-sources.md](docs/data-sources.md) for details):

1. **ChronoGenesis API** - used when `CHRONO_API_KEY` is set. Provides full history and exact join times.
2. **Uma.moe API** - fallback when Chrono has no key or fails. Requires `UMAMOE_API_KEY`; join days are inferred because the API has no join time.

Both use the same numeric `circle_id`, set per club with `/add_club` or `/edit_club`. If a club has no `circle_id`, the bot reports an error instead of guessing.

## Commands

### Club Management (Admin)

- `/add_club` - Register a new club to track
- `/remove_club` - Deactivate a club
- `/activate_club` - Reactivate a deactivated club
- `/list_clubs` - View all registered clubs
- `/edit_club` - Edit club settings (quota, schedule, circle_id, etc.)
- `/deactivate_club` - Pause tracking for a club
- `/transfer_club` - Move a club from another server to this one

### Channel Settings (Admin)

- `/set_report_channel` - Set where daily reports are posted
- `/set_alert_channel` - Set where alerts are posted
- `/set_report_channel_id` / `/set_alert_channel_id` - Same, using a raw channel or thread ID
- `/channel_settings` - View current channel configuration
- `/post_monthly_info` - Post the monthly info board

### Quota Management (Admin)

- `/quota` - Set daily quota requirement for a club
- `/quota_history` - View quota changes this month
- `/force_check` - Manually trigger daily check and report
- `/recalculate` - Recompute days-behind counts and bombs from existing history
- `/clear_locks` - Release stuck scraping locks

### Member Management (Admin)

- `/add_member` - Manually add a member
- `/deactivate_member` - Deactivate a member
- `/activate_member` - Reactivate a member
- `/bomb_status` - View all active bomb warnings

### User Commands

- `/link_trainer` - Link your Discord account to your trainer
- `/unlink` - Remove your trainer link
- `/my_status` - View your own quota status
- `/member_status` - View any member's quota status
- `/check_club` - View current club status report from database
- `/database_report` - Status report using only database data (no scraping)
- `/progress_chart` - Fan progression chart for the month
- `/leaderboard` - Leaderboard of synced trainers
- `/verify` - Verify a trainer's stats and current club from uma.moe
- `/list_clubs` - View all registered clubs
- `/list_members` - List active members of a club
- `/notification_settings` - Manage DM notification preferences

## How It Works

### Daily Quota System

- Configurable daily fan requirement (default: 1,000,000 fans/day)
- Tracks cumulative progress since joining
- Mid-month quota changes supported
- Members can catch up from previous deficits

### Bomb Warning System

- **Activation**: 3 consecutive days behind quota
- **Countdown**: 7 days to get back on track
- **Deactivation**: Immediate when member catches up
- **Expiration**: Manual kick required if still behind after countdown

### Member Auto-Detection

- **New Members**: Automatically added when they appear in scraped data
- **Departed Members**: Auto-deactivated when missing from scraped data
- **Returning Members**: Auto-reactivated when they rejoin (unless manually deactivated)

### DM Notifications

- Users can link their Discord accounts to trainers
- Receive DMs for bomb activations
- Optional daily deficit notifications
- Bomb deactivation celebrations

## Deployment

### Docker

```bash
docker-compose up -d --build
```

### Cloud Hosting

The bot works with Railway, Render, Fly.io, etc.

Create a `Procfile`:

```
worker: python main.py
```

### Systemd Service (Linux)

```bash
sudo nano /etc/systemd/system/umamusume-bot.service
sudo systemctl enable umamusume-bot
sudo systemctl start umamusume-bot
```

## Configuration

Each club can be configured independently:

- Daily quota requirement
- Scrape time and timezone
- Bomb trigger days (default: 3)
- Bomb countdown days (default: 7)
- Circle ID (numeric, required by both data sources)

Use `/edit_club` to modify settings after creation.

## Troubleshooting

**Bot doesn't start**

- Check `bot.log` for errors
- Verify `DISCORD_TOKEN` and `DATABASE_URL` in `.env`
- Ensure PostgreSQL database is accessible

**"Missing Circle ID" error**

- The club has no `circle_id` set
- Run `/edit_club club:YourClub circle_id:<numeric_id>` to fix
- Find your circle_id at https://uma.moe/circles/

**Scrape fails / no data**

- Verify the `circle_id` is correct and numeric
- Verify `UMAMOE_API_KEY` (and `CHRONO_API_KEY` if used) are set and valid
- Check if uma.moe / api.chronogenesis.net are reachable
- The bot logs which source was used for every scrape; check `bot.log`

**Database errors**

- Bot creates tables automatically on first run
- Verify database connection string format
- Check database permissions

## Project Structure

```
UmaCore/
├── main.py                # Entry point
├── bot/
│   ├── client.py          # Bot client and setup
│   ├── tasks.py           # Scheduled tasks
│   ├── decorators.py      # Permission checks
│   └── commands/          # Slash command cogs (admin, author, charts, club_management, member, settings, spot)
├── config/
│   ├── database.py        # Database connection and schema
│   └── settings.py        # Configuration
├── models/                # Data models (club, member, quota_history, bomb, ...)
├── scrapers/
│   ├── base_scraper.py
│   └── club_scraper.py    # ChronoGenesis API with Uma.moe fallback
├── services/              # Business logic (quota, bombs, reports, notifications, locks)
├── utils/                 # Logging and helper scripts
├── events/                # Event data
├── tests/
└── docs/                  # MkDocs documentation
```

## Support the Project

This bot is completely free and open source! If you find it useful, consider supporting development:

[![Ko-Fi Support](https://img.shields.io/badge/Buy%20me%20a%20coffee-Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/harukidev)

## License

MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with Discord.py, aiohttp, PostgreSQL, and asyncpg.
