"""
Club management commands (add, remove, edit, list)
"""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, time
import logging
import pytz
import asyncio

from models import Club, Member
from bot.decorators import is_admin_or_authorized

from config.settings import USE_UMAMOE_API

logger = logging.getLogger(__name__)

# Bot author ID for pre-migration club deletion
AUTHOR_ID = 139769063948681217


class ClubManagementCommands(commands.Cog):
    """Commands for managing club registrations"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def club_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for club names visible in this guild"""
        try:
            club_names = await Club.get_names_for_guild(interaction.guild_id)
            return [
                app_commands.Choice(name=name, value=name)
                for name in club_names
                if current.lower() in name.lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in club autocomplete: {e}")
            return []
    
    @app_commands.command(name="add_club", description="Register a new club to track (Staff only)")
    @is_admin_or_authorized()
    @app_commands.choices(quota_period=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly"),
        app_commands.Choice(name="Biweekly (every 2 weeks)", value="biweekly"),
    ])
    async def add_club(self, interaction: discord.Interaction,
                       club_name: str,
                       circle_id: str,
                       daily_quota: int,
                       quota_period: app_commands.Choice[str] = None,
                       timezone: str = "UTC",
                       scrape_time: str = "10:10"):
        """Register a new club"""
        await interaction.response.defer()
        
        try:
            # Check for duplicate
            existing = await Club.get_by_name(club_name)
            if existing:
                await interaction.followup.send(f"❌ Club '{club_name}' already exists")
                return
            
            # Validate circle_id format
            if not circle_id.isdigit():
                await interaction.followup.send(
                    f"❌ Invalid Circle ID format: `{circle_id}`\n\n"
                    f"The circle_id must be a **numeric ID** from Uma.moe.\n\n"
                    f"**How to find it:**\n"
                    f"1. Go to https://uma.moe/circles/\n"
                    f"2. Search for **{club_name}**\n"
                    f"3. Click on it and copy the **number** from the URL\n"
                    f"   Example: `https://uma.moe/circles/860280110` → use `860280110`"
                )
                return
            
            # Auto-generate scrape_url from circle_id
            scrape_url = f"https://chronogenesis.net/club_profile?circle_id={circle_id}"
            
            # Validate timezone
            try:
                pytz.timezone(timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                await interaction.followup.send(f"❌ Invalid timezone: `{timezone}`")
                return
            
            # Parse scrape time
            try:
                hour, minute = map(int, scrape_time.split(':'))
                if not (0 <= hour < 24 and 0 <= minute < 60):
                    raise ValueError
                scrape_time_obj = time(hour=hour, minute=minute)
            except (ValueError, AttributeError):
                await interaction.followup.send("❌ Invalid scrape time format. Use HH:MM (e.g., 16:00)")
                return
            
            resolved_quota_period = quota_period.value if quota_period else 'daily'

            club = await Club.create(
                club_name=club_name,
                scrape_url=scrape_url,
                circle_id=circle_id,
                guild_id=interaction.guild_id,
                daily_quota=daily_quota,
                quota_period=resolved_quota_period,
                timezone=timezone,
                scrape_time=scrape_time_obj
            )

            # Format quota for display
            if daily_quota >= 1_000_000:
                quota_formatted = f"{daily_quota / 1_000_000:.1f}M"
            elif daily_quota >= 1_000:
                quota_formatted = f"{daily_quota / 1_000:.1f}K"
            else:
                quota_formatted = str(daily_quota)

            period_label = {'daily': 'day', 'weekly': 'week', 'biweekly': '2 weeks'}.get(resolved_quota_period, 'day')
            
            embed = discord.Embed(
                title="✅ Club Added",
                description=f"Successfully registered **{club_name}**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="Club Details",
                value=f"**Name:** {club_name}\n"
                      f"**Circle ID:** {circle_id}\n"
                      f"**Scrape URL:** {scrape_url}",
                inline=False
            )
            
            embed.add_field(
                name="Settings",
                value=f"**Quota:** {quota_formatted} fans per {period_label}\n"
                      f"**Scrape Time:** {scrape_time} {timezone}\n"
                      f"**Bombs:** Disabled ❌ (3 days trigger, 7 days countdown)",
                inline=False
            )
            
            embed.add_field(
                name="Next Steps",
                value=f"1. Set channels: `/set_report_channel club:{club_name}` and `/set_alert_channel club:{club_name}`\n"
                      f"2. Adjust settings: `/edit_club club:{club_name}`\n"
                      f"3. Manual check: `/force_check club:{club_name}`",
                inline=False
            )
            
            embed.set_footer(text=f"Added by {interaction.user}")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"Club '{club_name}' added by {interaction.user} (circle_id: {circle_id}, guild_id: {interaction.guild_id})")
            
        except Exception as e:
            logger.error(f"Error in add_club: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="remove_club", description="Permanently delete a club (Staff only)")
    @is_admin_or_authorized()
    async def remove_club(self, interaction: discord.Interaction, club: str):
        """Permanently delete a club and all associated data"""
        await interaction.response.defer()
        
        try:
            club_obj = await Club.get_by_name(club)
            
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found")
                return
            
            # Pre-migration clubs (guild_id IS NULL) can only be deleted by bot author
            if club_obj.guild_id is None:
                if interaction.user.id != AUTHOR_ID:
                    await interaction.followup.send(
                        f"❌ Cannot delete **{club}**\n\n"
                        f"This club was created before multi-server support and can only be deleted by the bot author."
                    )
                    return
            else:
                # Regular clubs must belong to this guild
                if not club_obj.belongs_to_guild(interaction.guild_id):
                    await interaction.followup.send(
                        f"❌ Club '{club}' is not registered in this server."
                    )
                    return
            
            # Create warning embed
            warning_embed = discord.Embed(
                title="⚠️ Confirm Club Deletion",
                description=f"You are about to **permanently delete** the club: **{club}**",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            
            warning_embed.add_field(
                name="🗑️ What will be deleted",
                value="• All member records\n"
                      "• All quota history\n"
                      "• All active bombs\n"
                      "• All quota requirements\n"
                      "• All user links\n"
                      "• All settings",
                inline=False
            )
            
            warning_embed.add_field(
                name="⚠️ This action is irreversible",
                value="**This cannot be undone.** All data will be permanently lost.\n\n"
                      f"Reply with `confirm delete {club}` within 30 seconds to proceed.",
                inline=False
            )
            
            warning_embed.set_footer(text=f"Requested by {interaction.user}")
            
            await interaction.followup.send(embed=warning_embed)
            
            # Wait for confirmation
            def check(m):
                return (m.author.id == interaction.user.id and 
                       m.channel.id == interaction.channel.id and
                       m.content.strip().lower() == f"confirm delete {club.lower()}")
            
            try:
                confirmation = await self.bot.wait_for('message', check=check, timeout=30.0)
            except asyncio.TimeoutError:
                await interaction.followup.send(
                    f"⏰ Deletion cancelled - confirmation timed out for **{club}**"
                )
                return
            
            # Delete the club
            await club_obj.delete()
            
            # Success embed
            embed = discord.Embed(
                title="✅ Club Deleted",
                description=f"**{club}** and all associated data have been permanently deleted.",
                color=discord.Color.dark_gray(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.set_footer(text=f"Deleted by {interaction.user}")
            
            await interaction.followup.send(embed=embed)
            logger.warning(f"Club '{club}' permanently deleted by {interaction.user} (ID: {interaction.user.id})")
            
        except Exception as e:
            logger.error(f"Error in remove_club: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="activate_club", description="Reactivate a club (Staff only)")
    @is_admin_or_authorized()
    async def activate_club(self, interaction: discord.Interaction, club: str):
        """Reactivate a deactivated club"""
        await interaction.response.defer()
        
        try:
            club_obj = await Club.get_by_name(club)
            
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found")
                return
            
            if not club_obj.belongs_to_guild(interaction.guild_id):
                await interaction.followup.send(f"❌ Club '{club}' is not registered in this server.")
                return
            
            if club_obj.is_active:
                await interaction.followup.send(f"ℹ️ Club '{club}' is already active")
                return
            
            await club_obj.activate()
            
            embed = discord.Embed(
                title="✅ Club Reactivated",
                description=f"**{club}** has been reactivated",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="ℹ️ What's next",
                value="Daily scraping will resume at the scheduled time.",
                inline=False
            )
            
            embed.set_footer(text=f"Reactivated by {interaction.user}")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"Club '{club}' reactivated by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error in activate_club: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="deactivate_club", description="Deactivate a club (Staff only)")
    @is_admin_or_authorized()
    async def deactivate_club(self, interaction: discord.Interaction, club: str):
        """Deactivate a club (stops daily scraping)"""
        await interaction.response.defer()
        
        try:
            club_obj = await Club.get_by_name(club)
            
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found")
                return
            
            if not club_obj.belongs_to_guild(interaction.guild_id):
                await interaction.followup.send(f"❌ Club '{club}' is not registered in this server.")
                return
            
            if not club_obj.is_active:
                await interaction.followup.send(f"ℹ️ Club '{club}' is already inactive")
                return
            
            await club_obj.deactivate()
            
            embed = discord.Embed(
                title="✅ Club Deactivated",
                description=f"**{club}** has been deactivated",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="ℹ️ What this means",
                value="Daily scraping and reports are paused for this club. All data is preserved. Use `/activate_club` to resume.",
                inline=False
            )
            
            embed.set_footer(text=f"Deactivated by {interaction.user}")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"Club '{club}' deactivated by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error in deactivate_club: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="list_clubs", description="View all registered clubs")
    async def list_clubs(self, interaction: discord.Interaction):
        """List clubs registered in this server"""
        await interaction.response.defer()
        
        try:
            # Only show clubs belonging to the current guild (plus any pre-migration clubs)
            clubs = await Club.get_all_for_guild(interaction.guild_id)
            
            if not clubs:
                await interaction.followup.send("No clubs registered in this server. Use `/add_club` to add one.")
                return
            
            embed = discord.Embed(
                title="🏆 Registered Clubs",
                description=f"Total: {len(clubs)} club{'s' if len(clubs) != 1 else ''}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            for club in clubs:
                status = "✅ Active" if club.is_active else "❌ Inactive"

                # Format quota
                if club.daily_quota >= 1_000_000:
                    quota_formatted = f"{club.daily_quota / 1_000_000:.1f}M"
                elif club.daily_quota >= 1_000:
                    quota_formatted = f"{club.daily_quota / 1_000:.1f}K"
                else:
                    quota_formatted = str(club.daily_quota)

                period_label = {'daily': 'day', 'weekly': 'week', 'biweekly': '2 weeks'}.get(
                    getattr(club, 'quota_period', 'daily'), 'day'
                )
                
                # Scraper type indicator
                if USE_UMAMOE_API and club.circle_id and club.is_circle_id_valid():
                    scraper_info = "\n**Scraper:** Uma.moe API 🚀"
                else:
                    source_desc = "ChronoGenesis" if not club.circle_id else "Chrono (via circle_id)"
                    scraper_info = f"\n**Scraper:** {source_desc}"

                # Bomb status indicator
                bomb_status = "Enabled ✅" if club.bombs_enabled else "Disabled ❌"

                embed.add_field(
                    name=f"{status} {club.club_name}",
                    value=f"**Quota:** {quota_formatted} fans/{period_label}\n"
                          f"**Schedule:** {club.get_scrape_time_str()} {club.timezone}"
                          f"{scraper_info}\n"
                          f"**Bombs:** {bomb_status}",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in list_clubs: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="edit_club", description="Edit club settings (Staff only)")
    @is_admin_or_authorized()
    @app_commands.choices(quota_period=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly"),
        app_commands.Choice(name="Biweekly (every 2 weeks)", value="biweekly"),
    ])
    async def edit_club(self, interaction: discord.Interaction,
                       club: str,
                       circle_id: str = None,
                       daily_quota: int = None,
                       quota_period: app_commands.Choice[str] = None,
                       scrape_time: str = None,
                       timezone: str = None,
                       bomb_trigger_days: int = None,
                       bomb_countdown_days: int = None,
                       bombs_enabled: bool = None):
        """Edit club configuration"""
        await interaction.response.defer()
        
        try:
            club_obj = await Club.get_by_name(club)
            
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found")
                return
            
            if not club_obj.belongs_to_guild(interaction.guild_id):
                await interaction.followup.send(f"❌ Club '{club}' is not registered in this server.")
                return
            
            # Validate circle_id if being updated
            if circle_id is not None and circle_id != "" and not circle_id.isdigit():
                await interaction.followup.send(
                    f"❌ Invalid Circle ID format: `{circle_id}`\n\n"
                    f"The circle_id must be a **numeric ID** from Uma.moe.\n\n"
                    f"**How to find it:**\n"
                    f"1. Go to https://uma.moe/circles/\n"
                    f"2. Search for **{club}**\n"
                    f"3. Click on it and copy the **number** from the URL\n"
                    f"   Example: `https://uma.moe/circles/860280110` → use `860280110`\n\n"
                    f"To remove circle_id (use ChronoGenesis), use an empty string."
                )
                return
            
            updates = {}
            if circle_id is not None:
                updates['circle_id'] = circle_id if circle_id != "" else None
            if daily_quota is not None:
                updates['daily_quota'] = daily_quota
            if quota_period is not None:
                updates['quota_period'] = quota_period.value
            if scrape_time is not None:
                try:
                    hour, minute = map(int, scrape_time.split(':'))
                    if not (0 <= hour < 24 and 0 <= minute < 60):
                        raise ValueError
                    updates['scrape_time'] = time(hour=hour, minute=minute)
                except (ValueError, AttributeError):
                    await interaction.followup.send("❌ Invalid time format. Use HH:MM (e.g., 16:00)")
                    return
            if timezone is not None:
                try:
                    pytz.timezone(timezone)
                except pytz.exceptions.UnknownTimeZoneError:
                    await interaction.followup.send(f"❌ Invalid timezone: `{timezone}`")
                    return
                updates['timezone'] = timezone
            if bomb_trigger_days is not None:
                updates['bomb_trigger_days'] = bomb_trigger_days
            if bomb_countdown_days is not None:
                updates['bomb_countdown_days'] = bomb_countdown_days
            if bombs_enabled is not None:
                updates['bombs_enabled'] = bombs_enabled

            if not updates:
                await interaction.followup.send("❌ No changes specified")
                return

            # If bombs are being disabled, deactivate all active bombs
            from datetime import date
            from models import Bomb
            deactivated_count = 0
            if bombs_enabled is False and club_obj.bombs_enabled:
                deactivated_count = await Bomb.deactivate_all(club_obj.club_id, date.today())

            await club_obj.update_settings(**updates)
            
            embed = discord.Embed(
                title="✅ Club Settings Updated",
                description=f"Successfully updated **{club}**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            # Determine the effective quota_period for display (may have just been changed)
            effective_period = updates.get('quota_period', club_obj.quota_period)
            period_label = {'daily': 'day', 'weekly': 'week', 'biweekly': '2 weeks'}.get(effective_period, 'day')

            # Warn if changing quota_period mid-month
            period_warning = ""
            if 'quota_period' in updates and updates['quota_period'] != club_obj.quota_period:
                period_warning = "\n⚠️ Quota period changed mid-month — historical data may be inconsistent until the next monthly reset."

            changes_text = []
            for key, value in updates.items():
                if key == 'circle_id':
                    if value:
                        scraper_desc = "Uma.moe API enabled 🚀" if USE_UMAMOE_API else "Chrono (via circle_id)"
                        changes_text.append(f"**Circle ID:** {value} ({scraper_desc})")
                    else:
                        changes_text.append(f"**Circle ID:** Removed (will use ChronoGenesis)")
                elif key == 'daily_quota':
                    if value >= 1_000_000:
                        formatted = f"{value / 1_000_000:.1f}M"
                    elif value >= 1_000:
                        formatted = f"{value / 1_000:.1f}K"
                    else:
                        formatted = str(value)
                    changes_text.append(f"**Quota:** {formatted} fans per {period_label}")
                elif key == 'quota_period':
                    period_names = {'daily': 'Daily', 'weekly': 'Weekly', 'biweekly': 'Biweekly'}
                    changes_text.append(f"**Quota Period:** {period_names.get(value, value)}")
                elif key == 'scrape_time':
                    changes_text.append(f"**Scrape Time:** {value}")
                elif key == 'timezone':
                    changes_text.append(f"**Timezone:** {value}")
                elif key == 'bomb_trigger_days':
                    changes_text.append(f"**Bomb Trigger:** {value} days")
                elif key == 'bomb_countdown_days':
                    changes_text.append(f"**Bomb Countdown:** {value} days")
                elif key == 'bombs_enabled':
                    status = "Enabled ✅" if value else "Disabled ❌"
                    changes_text.append(f"**Bombs:** {status}")
                    if not value and deactivated_count > 0:
                        changes_text.append(f"  ↳ Deactivated {deactivated_count} active bomb{'s' if deactivated_count != 1 else ''}")

            embed.add_field(
                name="Changes Applied",
                value="\n".join(changes_text) + period_warning,
                inline=False
            )

            embed.set_footer(text=f"Updated by {interaction.user}")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"Club '{club}' settings updated by {interaction.user}: {updates}")
            
        except Exception as e:
            logger.error(f"Error in edit_club: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @app_commands.command(name="transfer_club", description="Transfer a club from another server to this server")
    @is_admin_or_authorized()
    async def transfer_club(self, interaction: discord.Interaction, club: str):
        """Move a club from another guild (or from pre-migration) to the current guild"""
        await interaction.response.defer()
        
        try:
            club_obj = await Club.get_by_name(club)
            
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found in the global database.")
                return
            
            if club_obj.guild_id == interaction.guild_id:
                await interaction.followup.send(f"ℹ️ Club '{club}' is already registered in this server.")
                return

            old_guild_id = club_obj.guild_id
            await club_obj.update_settings(guild_id=interaction.guild_id)
            
            embed = discord.Embed(
                title="✅ Club Transferred",
                description=f"Successfully transferred **{club}** to this server!",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="Information",
                value=f"**Old Server ID:** `{old_guild_id or 'Global/Pre-migration'}`\n"
                      f"**New Server ID:** `{interaction.guild_id}`",
                inline=False
            )
            
            embed.add_field(
                name="⚠️ Next Steps",
                value="Registration channels (reports, alerts) were NOT moved. You MUST set new ones:\n\n"
                      f"1. `/set_report_channel club:{club}`\n"
                      f"2. `/set_alert_channel club:{club}`",
                inline=False
            )
            
            embed.set_footer(text=f"Transferred by {interaction.user}")
            
            await interaction.followup.send(embed=embed)
            logger.warning(f"Club '{club}' transferred from guild {old_guild_id} to {interaction.guild_id} by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error in transfer_club: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error during transfer: {str(e)}")

    @app_commands.command(name="list_members", description="List all active members of a club from the database")
    async def list_members(self, interaction: discord.Interaction, club: str):
        """List active members from the database without scraping"""
        await interaction.response.defer()
        
        try:
            club_obj = await Club.get_by_name(club)
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found")
                return
            
            if not club_obj.belongs_to_guild(interaction.guild_id):
                await interaction.followup.send(f"❌ Club '{club}' is not registered in this server.")
                return
            
            members = await Member.get_all_active(club_obj.club_id)
            
            if not members:
                await interaction.followup.send(f"ℹ️ No active members found for **{club}** in the database.")
                return
            
            # Group members into chunks for multiple embeds if needed (Discord has limits)
            chunk_size = 50
            member_chunks = [members[i:i + chunk_size] for i in range(0, len(members), chunk_size)]
            
            for idx, chunk in enumerate(member_chunks):
                embed = discord.Embed(
                    title=f"👥 Members: {club}",
                    description=f"Showing active members from database (Total: {len(members)})",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                
                member_list = []
                for m in chunk:
                    trainer_id = f" (`{m.trainer_id}`)" if m.trainer_id else ""
                    member_list.append(f"• **{m.trainer_name}**{trainer_id}")
                
                # Split member list into columns or just joined text
                embed.description += "\n\n" + "\n".join(member_list)
                
                if len(member_chunks) > 1:
                    embed.set_footer(text=f"Page {idx + 1}/{len(member_chunks)}")
                
                if idx == 0:
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(embed=embed)
                    
            logger.info(f"Listed {len(members)} members for club {club} for user {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error in list_members: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")

    # Autocomplete for club parameter
    async def global_club_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete that shows ALL active clubs globally"""
        try:
            club_names = await Club.get_all_names()
            return [
                app_commands.Choice(name=name, value=name)
                for name in club_names
                if current.lower() in name.lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in global club autocomplete: {e}")
            return []

    remove_club.autocomplete('club')(club_autocomplete)
    activate_club.autocomplete('club')(club_autocomplete)
    deactivate_club.autocomplete('club')(club_autocomplete)
    edit_club.autocomplete('club')(club_autocomplete)
    transfer_club.autocomplete('club')(global_club_autocomplete)
    list_members.autocomplete('club')(club_autocomplete)


async def setup(bot):
    """Setup function for loading the cog"""
    await bot.add_cog(ClubManagementCommands(bot))