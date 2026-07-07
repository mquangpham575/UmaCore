import discord
from discord import app_commands
from discord.ext import commands
import logging
import asyncio
import aiohttp
from datetime import datetime

from config.database import db
from bot.decorators import is_admin_or_authorized
from models.bot_settings import BotSettings

logger = logging.getLogger(__name__)

TARGET_CHANNEL_ID = 1469142049163837492


class SpotCommands(commands.GroupCog, name="spot"):
    """Cog for tracking member spots in UMA clubs"""

    def __init__(self, bot):
        """Initialize the SpotCommands cog with bot instance."""
        self.bot = bot
        self.lock = asyncio.Lock()

    async def _update_spots_message(self) -> bool:
        """Delete old spots message and post new embed summarizing all club spots."""
        async with self.lock:
            channel = self.bot.get_channel(TARGET_CHANNEL_ID)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(TARGET_CHANNEL_ID)
                except Exception as e:
                    logger.error(f"Failed to fetch spots channel {TARGET_CHANNEL_ID}: {e}")
                    return False

            logger.info(f"Target channel: {channel} (ID: {channel.id}) in guild: {channel.guild} (ID: {channel.guild.id})")
            if hasattr(channel, 'guild') and channel.guild:
                perms = channel.permissions_for(channel.guild.me)
                logger.info(f"Bot permissions: view_channel={perms.view_channel}, send_messages={perms.send_messages}, embed_links={perms.embed_links}")

            # Get all spots from database sorted by daily_quota (descending) and name (ascending)
            query = """
                SELECT 
                    cs.club_name, 
                    cs.member_count, 
                    cs.max_members, 
                    cs.pending_count
                FROM club_spots cs
                LEFT JOIN clubs c ON UPPER(cs.club_name) = UPPER(c.club_name)
                ORDER BY COALESCE(c.daily_quota, 0) DESC, cs.club_name ASC
            """
            rows = await db.fetch(query)

            embed = discord.Embed(
                title="📊 **UMA Club Spots Status**",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            if not rows:
                embed.description = "No clubs are currently being tracked for spots."
            else:
                lines = []
                for row in rows:
                    c_name = row['club_name']
                    cnt = row['member_count']
                    mx = 30  # Max capacity is always 30
                    pending = row.get('pending_count', 0)

                    if cnt >= mx:
                        status_emoji = "🔴"  # Red when full
                    elif cnt + pending >= mx:
                        status_emoji = "🟠"  # Orange when current + pending >= 30
                    else:
                        status_emoji = "🟢"  # Green when not full

                    pending_str = f" +{pending} pending" if pending > 0 else ""
                    lines.append(f"{status_emoji} **{c_name}** `{cnt}/{mx}`{pending_str}")

                embed.description = "\n".join(lines)

            embed.set_footer(text="Updated automatically on spot changes")

            # Get old message ID from bot_settings
            old_msg_id = await BotSettings.get('spots_message_id')
            if old_msg_id:
                try:
                    old_msg = await channel.fetch_message(int(old_msg_id))
                    await old_msg.delete()
                    logger.info(f"Deleted old spots message: {old_msg_id}")
                except discord.NotFound:
                    logger.debug("Old spots message already deleted/not found")
                except Exception as e:
                    logger.error(f"Failed to delete old spots message {old_msg_id}: {e}")

            # Send new message
            try:
                new_msg = await channel.send(embed=embed)
                await BotSettings.set('spots_message_id', str(new_msg.id))
                logger.info(f"Posted new spots message: {new_msg.id}")
                return True
            except Exception as e:
                logger.error(f"Failed to send new spots message: {e}")
                return False

    async def club_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete club name from database configuration and active spots."""
        try:
            from models.club import Club
            db_clubs = await Club.get_names_for_guild(interaction.guild_id)

            # Fetch from club_spots table
            query = "SELECT club_name FROM club_spots"
            spot_rows = await db.fetch(query)
            spot_clubs = [row['club_name'] for row in spot_rows]

            # Case-insensitively map names, prioritizing the database configurations (db_clubs)
            name_map = {}
            for name in spot_clubs:
                name_map[name.upper()] = name
            for name in db_clubs:
                name_map[name.upper()] = name

            all_names = list(name_map.values())
            all_names.sort()

            return [
                app_commands.Choice(name=name, value=name)
                for name in all_names
                if current.lower() in name.lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in club autocomplete: {e}")
            return []

    @app_commands.command(name="set", description="Set the current and pending member count for a club")
    @is_admin_or_authorized()
    async def set_spots(self, interaction: discord.Interaction, club_name: str, members: int, pending: int = 0):
        """Set the current and pending member count for a club."""
        if interaction.channel_id != TARGET_CHANNEL_ID:
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{TARGET_CHANNEL_ID}>.",
                ephemeral=True
            )
            return

        if members < 0 or pending < 0:
            await interaction.response.send_message(
                "❌ Member and pending counts must be non-negative numbers.",
                ephemeral=True
            )
            return

        # Validate that the club is registered in the clubs table
        club_row = await db.fetchrow(
            "SELECT club_name FROM clubs WHERE UPPER(club_name) = $1 AND is_active = TRUE",
            club_name.upper().strip()
        )
        if not club_row:
            await interaction.response.send_message(
                f"❌ Club **{club_name}** is not a registered active club. Use `/list_clubs` to check names.",
                ephemeral=True
            )
            return

        matched_name = club_row['club_name']

        # Clean up any case-conflicted duplicate entries in club_spots first (e.g. ENDGOON (S) vs Endgoon (S))
        existing = await db.fetchrow(
            "SELECT club_name FROM club_spots WHERE UPPER(club_name) = $1",
            matched_name.upper()
        )
        if existing and existing['club_name'] != matched_name:
            await db.execute("DELETE FROM club_spots WHERE club_name = $1", existing['club_name'])

        # Update or Insert, max_members is always 30
        query = """
            INSERT INTO club_spots (club_name, member_count, max_members, pending_count, updated_at)
            VALUES ($1, $2, 30, $3, NOW())
            ON CONFLICT (club_name)
            DO UPDATE SET
                member_count = $2,
                max_members = 30,
                pending_count = $3,
                updated_at = NOW()
        """
        try:
            await db.execute(query, matched_name, members, pending)
            pending_response = f" (+{pending} pending)" if pending > 0 else ""
            await interaction.response.send_message(
                f"✅ Set **{matched_name}** current members to `{members}/30`{pending_response}.",
                ephemeral=True
            )
            # Update public message
            await self._update_spots_message()
        except Exception as e:
            logger.error(f"Error in spot set command: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="add", description="Add members to a club's current spots")
    @is_admin_or_authorized()
    async def add_spots(self, interaction: discord.Interaction, club_name: str, amount: int = 1):
        """Add members to a club's current spots count."""
        if interaction.channel_id != TARGET_CHANNEL_ID:
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{TARGET_CHANNEL_ID}>.",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount to add must be a positive number.",
                ephemeral=True
            )
            return

        # Validate that the club is registered in the clubs table
        club_row = await db.fetchrow(
            "SELECT club_name FROM clubs WHERE UPPER(club_name) = $1 AND is_active = TRUE",
            club_name.upper().strip()
        )
        if not club_row:
            await interaction.response.send_message(
                f"❌ Club **{club_name}** is not a registered active club. Use `/list_clubs` to check names.",
                ephemeral=True
            )
            return

        matched_name = club_row['club_name']

        # Clean up any case-conflicted duplicate entries in club_spots first (e.g. ENDGOON (S) vs Endgoon (S))
        existing = await db.fetchrow(
            "SELECT club_name FROM club_spots WHERE UPPER(club_name) = $1",
            matched_name.upper()
        )
        if existing and existing['club_name'] != matched_name:
            await db.execute("DELETE FROM club_spots WHERE club_name = $1", existing['club_name'])

        # Check if club exists in club_spots
        row = await db.fetchrow("SELECT member_count FROM club_spots WHERE club_name = $1", matched_name)
        current_members = amount if not row else row['member_count'] + amount

        query = """
            INSERT INTO club_spots (club_name, member_count, max_members, updated_at)
            VALUES ($1, $2, 30, NOW())
            ON CONFLICT (club_name)
            DO UPDATE SET
                member_count = $2,
                max_members = 30,
                updated_at = NOW()
        """
        try:
            await db.execute(query, matched_name, current_members)
            await interaction.response.send_message(
                f"✅ Added {amount} member(s) to **{matched_name}**. Now: `{current_members}/30`.",
                ephemeral=True
            )
            await self._update_spots_message()
        except Exception as e:
            logger.error(f"Error in spot add command: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="sub", description="Subtract members from a club's current spots")
    @is_admin_or_authorized()
    async def sub_spots(self, interaction: discord.Interaction, club_name: str, amount: int = 1):
        """Subtract members from a club's current spots count."""
        if interaction.channel_id != TARGET_CHANNEL_ID:
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{TARGET_CHANNEL_ID}>.",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ Amount to subtract must be a positive number.",
                ephemeral=True
            )
            return

        # Validate that the club is registered in the clubs table
        club_row = await db.fetchrow(
            "SELECT club_name FROM clubs WHERE UPPER(club_name) = $1 AND is_active = TRUE",
            club_name.upper().strip()
        )
        if not club_row:
            await interaction.response.send_message(
                f"❌ Club **{club_name}** is not a registered active club. Use `/list_clubs` to check names.",
                ephemeral=True
            )
            return

        matched_name = club_row['club_name']

        # Clean up any case-conflicted duplicate entries in club_spots first (e.g. ENDGOON (S) vs Endgoon (S))
        existing = await db.fetchrow(
            "SELECT club_name FROM club_spots WHERE UPPER(club_name) = $1",
            matched_name.upper()
        )
        if existing and existing['club_name'] != matched_name:
            await db.execute("DELETE FROM club_spots WHERE club_name = $1", existing['club_name'])

        row = await db.fetchrow("SELECT member_count FROM club_spots WHERE club_name = $1", matched_name)
        if not row:
            await interaction.response.send_message(
                f"❌ Club **{matched_name}** is not currently tracked. Use `/spot set` first.",
                ephemeral=True
            )
            return

        current_members = max(0, row['member_count'] - amount)

        query = """
            UPDATE club_spots
            SET member_count = $2, updated_at = NOW()
            WHERE club_name = $1
        """
        try:
            await db.execute(query, matched_name, current_members)
            await interaction.response.send_message(
                f"✅ Subtracted {amount} member(s) from **{matched_name}**. Now: `{current_members}/30`.",
                ephemeral=True
            )
            await self._update_spots_message()
        except Exception as e:
            logger.error(f"Error in spot sub command: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="remove", description="Remove a club from spots tracking")
    @is_admin_or_authorized()
    async def remove_spots(self, interaction: discord.Interaction, club_name: str):
        """Remove a club from spots tracking entirely."""
        if interaction.channel_id != TARGET_CHANNEL_ID:
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{TARGET_CHANNEL_ID}>.",
                ephemeral=True
            )
            return

        # Validate that the club is registered in the clubs table or exists in club_spots
        club_row = await db.fetchrow(
            "SELECT club_name FROM clubs WHERE UPPER(club_name) = $1 AND is_active = TRUE",
            club_name.upper().strip()
        )
        matched_name = club_row['club_name'] if club_row else club_name.upper().strip()

        try:
            result = await db.execute("DELETE FROM club_spots WHERE UPPER(club_name) = $1", matched_name.upper())
            if " 0" in result:
                await interaction.response.send_message(
                    f"ℹ️ Club **{matched_name}** was not being tracked.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                f"✅ Removed **{matched_name}** from spots tracking.",
                ephemeral=True
            )
            await self._update_spots_message()
        except Exception as e:
            logger.error(f"Error in spot remove command: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="list", description="Resend the public spots status list message")
    @is_admin_or_authorized()
    async def list_spots(self, interaction: discord.Interaction):
        """Resend the public spots list to the target channel."""
        if interaction.channel_id != TARGET_CHANNEL_ID:
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{TARGET_CHANNEL_ID}>.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            success = await self._update_spots_message()
            if success:
                await interaction.followup.send("✅ Spots list successfully resent.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to resend spots list.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in spot list command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="check", description="Automatically check spots for all active clubs using the UMA APIs")
    @is_admin_or_authorized()
    async def check_spots(self, interaction: discord.Interaction):
        # Intent: Automatically check/sync member counts from the UMA APIs (uma.moe / Chrono hybrid) for active clubs.
        if interaction.channel_id != TARGET_CHANNEL_ID:
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{TARGET_CHANNEL_ID}>.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            from models import Club
            guild_clubs = await Club.get_all_for_guild(interaction.guild_id)
            
            # Filter active clubs with numeric circle_id
            clubs_to_sync = [c for c in guild_clubs if c.is_active and c.circle_id and c.circle_id.isdigit()]
            
            if not clubs_to_sync:
                await interaction.followup.send(
                    "❌ No active clubs have a valid numeric Circle ID set. Configure them with `/edit_club`.",
                    ephemeral=True
                )
                return
            import os
            api_key = os.getenv("UMAMOE_API_KEY")
            chrono_token = os.getenv("CHRONO_API_KEY")
            if not api_key and not chrono_token:
                await interaction.followup.send(
                    "❌ Neither `UMAMOE_API_KEY` nor `CHRONO_API_KEY` is configured in the environment.",
                    ephemeral=True
                )
                return

            synced = []
            failed = []

            async with aiohttp.ClientSession() as session:
                for club in clubs_to_sync:
                    # Hybrid Fetch: prioritize uma.moe API
                    member_count = None
                    try_chrono = True
                    
                    if api_key:
                        url = f"https://uma.moe/api/v4/circles?circle_id={club.circle_id}"
                        headers = {
                            "X-API-Key": api_key,
                            "accept": "application/json"
                        }
                        try:
                            async with session.get(url, headers=headers, timeout=15) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    circle_data = data.get("circle")
                                    if circle_data and isinstance(circle_data, dict):
                                        member_count = circle_data.get("member_count")
                                        if member_count is not None:
                                            try_chrono = False  # Success!
                                        else:
                                            logger.warning(f"uma.moe API returned null member_count for circle {club.circle_id}")
                                    else:
                                        logger.warning(f"uma.moe API response invalid structure for circle {club.circle_id}")
                                else:
                                    logger.warning(f"uma.moe API request failed for circle {club.circle_id} with status {response.status}")
                        except Exception as e:
                            logger.error(f"Error querying uma.moe for circle {club.circle_id}: {e}")

                    # Fallback to Chrono API if primary failed and Chrono token is available
                    if try_chrono:
                        if chrono_token:
                            url = f"https://api.chronogenesis.net/club_profile?circle_id={club.circle_id}"
                            headers = {
                                "Authorization": f"{chrono_token}",
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                            }
                            try:
                                async with session.get(url, headers=headers, timeout=15) as response:
                                    if response.status == 200:
                                        data = await response.json()
                                        club_list = data.get("club")
                                        if club_list and isinstance(club_list, list):
                                            member_count = club_list[0].get("member_num")
                                        else:
                                            failed.append(f"**{club.club_name}** (Chrono: No club data)")
                                            continue
                                    else:
                                        failed.append(f"**{club.club_name}** (Chrono HTTP {response.status})")
                                        continue
                            except Exception as e:
                                logger.error(f"Error querying Chrono API for circle {club.circle_id}: {e}")
                                failed.append(f"**{club.club_name}** (Chrono: {str(e)})")
                                continue
                        else:
                            failed.append(f"**{club.club_name}** (uma.moe failed, Chrono API key missing)")
                            continue

                    if member_count is None:
                        failed.append(f"**{club.club_name}** (Failed to retrieve member count)")
                        continue

                    # Update or Insert, max_members is 30, preserve pending_count (but auto-clear/cap)
                    query = """
                        INSERT INTO club_spots (club_name, member_count, max_members, pending_count, updated_at)
                        VALUES ($1, $2, 30, 0, NOW())
                        ON CONFLICT (club_name)
                        DO UPDATE SET
                            member_count = $2,
                            pending_count = CASE 
                                WHEN $2 >= 30 THEN 0
                                ELSE LEAST(club_spots.pending_count, 30 - $2)
                            END,
                            updated_at = NOW()
                    """
                    try:
                        await db.execute(query, club.club_name, int(member_count))
                        synced.append(f"**{club.club_name}** (`{member_count}/30`)")
                    except Exception as e:
                        logger.error(f"Failed to update spots in DB for {club.club_name}: {e}", exc_info=True)
                        failed.append(f"**{club.club_name}** (DB error: {str(e)})")

            if synced:
                await self._update_spots_message()

            response_parts = []
            if synced:
                response_parts.append(f"✅ Checked: {', '.join(synced)}")
            if failed:
                response_parts.append(f"❌ Failed: {', '.join(failed)}")

            await interaction.followup.send("\n".join(response_parts), ephemeral=True)

        except Exception as e:
            logger.error(f"Error in spot sync command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error during sync: {str(e)}", ephemeral=True)

    async def update_spots_for_club(self, club_id, club_name: str) -> bool:
        # Intent: Count active members for a club in the database, update club_spots if tracked, and refresh public message.
        try:
            existing = await db.fetchrow(
                "SELECT club_name FROM club_spots WHERE UPPER(club_name) = $1",
                club_name.upper().strip()
            )
            if not existing:
                return False

            matched_name = existing['club_name']

            active_count_row = await db.fetchrow(
                "SELECT COUNT(*) as cnt FROM members WHERE club_id = $1 AND is_active = TRUE",
                club_id
            )
            active_count = active_count_row['cnt'] if active_count_row else 0

            query = """
                UPDATE club_spots
                SET member_count = $2,
                    pending_count = CASE 
                        WHEN $2 >= 30 THEN 0
                        ELSE LEAST(pending_count, 30 - $2)
                    END,
                    updated_at = NOW()
                WHERE club_name = $1
            """
            await db.execute(query, matched_name, int(active_count))
            logger.info(f"Auto-updated spots for {matched_name} to {active_count}/30 (active database count)")
            
            await self._update_spots_message()
            return True
        except Exception as e:
            logger.error(f"Failed to auto-update spots for {club_name}: {e}", exc_info=True)
            return False

    # Register autocomplete handlers
    set_spots.autocomplete('club_name')(club_autocomplete)
    add_spots.autocomplete('club_name')(club_autocomplete)
    sub_spots.autocomplete('club_name')(club_autocomplete)
    remove_spots.autocomplete('club_name')(club_autocomplete)


async def setup(bot):
    """Load the SpotCommands cog into the bot."""
    await bot.add_cog(SpotCommands(bot))
