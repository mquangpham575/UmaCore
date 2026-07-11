"""
Member status and user linking commands
"""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import aiohttp
import asyncio
import os
import io
import logging

from models import Member, QuotaHistory, Bomb, UserLink, Club, QuotaRequirement, ClubRankHistory
from services import QuotaCalculator, BombManager, ReportGenerator
import pytz

logger = logging.getLogger(__name__)


# Global in-memory cache for resolved Discord user info to prevent API throttling
# Mapping: discord_user_id (int) -> (username, avatar_url, expires_at)
_discord_user_cache = {}

class CachedDiscordUser:
    """Mock user object to compatibility-wrap cached user details."""
    def __init__(self, name: str, avatar_url: str | None):
        self.name = name
        self.avatar_url = avatar_url

    @property
    def display_avatar(self):
        return self

    @property
    def url(self):
        return self.avatar_url

    def with_format(self, format: str):
        """Mock method for compatibility with discord.Asset.with_format."""
        return self


class LeaderboardView(discord.ui.View):
    """View class for handling paginated leaderboard controls using disk cache"""
    
    def __init__(self, user_id: int, cache_prefix: str, total_pages: int,
                 club_name: str, leaderboard_data: list, current_date_str: str):
        # Intent: Initialize the paginated leaderboard view with buttons using disk cache
        super().__init__(timeout=180.0)
        self.user_id = user_id
        self.cache_prefix = cache_prefix
        self.current_page = 0
        self.total_pages = total_pages
        self.club_name = club_name
        self.leaderboard_data = leaderboard_data
        self.current_date_str = current_date_str
        self._update_buttons()

    def _update_buttons(self):
        # Intent: Enable or disable navigation buttons based on current page index
        self.prev_page.disabled = (self.current_page == 0)
        self.next_page.disabled = (self.current_page == self.total_pages - 1)

    async def get_page_file(self) -> discord.File:
        # Intent: Load pre-rendered page image from disk cache or generate on the fly
        import os
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "leaderboards")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{self.cache_prefix}_page_{self.current_page}.webp")
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return discord.File(io.BytesIO(f.read()), filename="leaderboard.webp")
            except Exception as e:
                logger.warning(f"Failed to read leaderboard cache file {cache_path}: {e}")
                
        # Fallback: render on the fly and cache it
        start_idx = self.current_page * 10
        end_idx = start_idx + 10
        page_data = self.leaderboard_data[start_idx:end_idx] if self.leaderboard_data else []
        
        from utils.leaderboard_renderer import render_leaderboard_image
        img_bytes = await render_leaderboard_image(
            club_name=self.club_name,
            leaderboard_data=page_data,
            current_date_str=self.current_date_str,
            start_rank=start_idx + 1
        )
        try:
            with open(cache_path, "wb") as f:
                f.write(img_bytes)
        except Exception as e:
            logger.warning(f"Failed to write leaderboard cache file {cache_path}: {e}")
            
        return discord.File(io.BytesIO(img_bytes), filename="leaderboard.webp")

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Intent: Handle click event for the previous page button
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the user who ran the command can navigate.", ephemeral=True)
            return
            
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.defer()
        file = await self.get_page_file()
        await interaction.edit_original_response(attachments=[file], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Intent: Handle click event for the next page button
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the user who ran the command can navigate.", ephemeral=True)
            return
            
        self.current_page += 1
        self._update_buttons()
        await interaction.response.defer()
        file = await self.get_page_file()
        await interaction.edit_original_response(attachments=[file], view=self)


class MemberCommands(commands.Cog):
    """Member status and user linking commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.quota_calculator = QuotaCalculator()
        self.bomb_manager = BombManager()
        self.report_generator = ReportGenerator()
    
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
    
    @app_commands.command(name="link_trainer", description="Link your Discord account to your trainer")
    async def link_trainer(self, interaction: discord.Interaction, trainer_name: str, club: str):
        """Link your Discord account to a trainer"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            club_obj = await Club.get_by_name(club)
            if not club_obj:
                await interaction.followup.send(
                    f"❌ Club '{club}' not found.",
                    ephemeral=True
                )
                return
            
            member = await Member.get_by_name(club_obj.club_id, trainer_name)
            
            if not member:
                await interaction.followup.send(
                    f"❌ Trainer '{trainer_name}' not found in {club}. Make sure the name matches exactly.",
                    ephemeral=True
                )
                return
            
            # Check if already linked to another trainer
            existing_link = await UserLink.get_by_discord_id(interaction.user.id)
            clubs_to_update = {club_obj.club_id}
            if existing_link:
                existing_member = await Member.get_by_id(existing_link.member_id)
                if existing_member.member_id == member.member_id:
                    await interaction.followup.send(
                        f"ℹ️ You're already linked to **{trainer_name}** in **{club}**",
                        ephemeral=True
                    )
                    return
                else:
                    # Unlink from old trainer
                    await UserLink.delete(interaction.user.id)
                    logger.info(f"Unlinked user {interaction.user.id} from {existing_member.trainer_name}")
                    clubs_to_update.add(existing_member.club_id)
            
            # Create link
            await UserLink.create(
                discord_user_id=interaction.user.id,
                member_id=member.member_id,
                notify_on_bombs=True,
                notify_on_deficit=False
            )
            
            # Re-generate the leaderboard cache in the background
            for cid in clubs_to_update:
                asyncio.create_task(pre_render_and_cache_leaderboard(self.bot, club_id=cid))
            asyncio.create_task(pre_render_and_cache_leaderboard(self.bot, guild_id=interaction.guild_id))
            
            embed = discord.Embed(
                title="✅ Trainer Linked!",
                description=f"Your Discord account is now linked to **{trainer_name}** in **{club}**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="🔔 Notifications Enabled",
                value="• **Bomb Warnings:** ✅ Enabled\n"
                      "• **Deficit Alerts:** ❌ Disabled",
                inline=False
            )
            
            embed.add_field(
                name="💡 Next Steps",
                value="• Use `/my_status` to check your progress\n"
                      "• Use `/notification_settings` to customize alerts\n"
                      "• Use `/unlink` to remove the link",
                inline=False
            )
            
            embed.set_footer(text="You'll receive DMs when important events happen")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user.id} linked to {trainer_name} in {club}")
            
        except Exception as e:
            logger.error(f"Error in link_trainer: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="unlink", description="Unlink your Discord account from your trainer")
    async def unlink(self, interaction: discord.Interaction):
        """Unlink your Discord account"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            user_link = await UserLink.get_by_discord_id(interaction.user.id)
            
            if not user_link:
                await interaction.followup.send(
                    "ℹ️ You don't have a linked trainer",
                    ephemeral=True
                )
                return
            
            member = await Member.get_by_id(user_link.member_id)
            await UserLink.delete(interaction.user.id)
            
            # Re-generate the leaderboard cache in the background
            asyncio.create_task(pre_render_and_cache_leaderboard(self.bot, club_id=member.club_id))
            asyncio.create_task(pre_render_and_cache_leaderboard(self.bot, guild_id=interaction.guild_id))
            
            embed = discord.Embed(
                title="✅ Trainer Unlinked",
                description=f"Your Discord account has been unlinked from **{member.trainer_name}**",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="ℹ️ What this means",
                value="You will no longer receive DM notifications about quota status.",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user.id} unlinked from {member.trainer_name}")
            
        except Exception as e:
            logger.error(f"Error in unlink: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="notification_settings", description="Manage your notification preferences")
    async def notification_settings(self, interaction: discord.Interaction, 
                                   bomb_warnings: bool = None, 
                                   deficit_alerts: bool = None):
        """Manage notification settings"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            user_link = await UserLink.get_by_discord_id(interaction.user.id)
            
            if not user_link:
                await interaction.followup.send(
                    "❌ You need to link a trainer first using `/link_trainer`",
                    ephemeral=True
                )
                return
            
            # If no settings provided, show current settings
            if bomb_warnings is None and deficit_alerts is None:
                member = await Member.get_by_id(user_link.member_id)
                
                embed = discord.Embed(
                    title="🔔 Notification Settings",
                    description=f"Settings for **{member.trainer_name}**",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                
                bomb_status = "✅ Enabled" if user_link.notify_on_bombs else "❌ Disabled"
                deficit_status = "✅ Enabled" if user_link.notify_on_deficit else "❌ Disabled"
                
                embed.add_field(
                    name="Current Settings",
                    value=f"**💣 Bomb Warnings:** {bomb_status}\n"
                          f"**⚠️ Deficit Alerts:** {deficit_status}",
                    inline=False
                )
                
                embed.add_field(
                    name="ℹ️ How to change",
                    value="Use `/notification_settings bomb_warnings:True` or similar to update settings",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Update settings
            new_bomb_setting = bomb_warnings if bomb_warnings is not None else user_link.notify_on_bombs
            new_deficit_setting = deficit_alerts if deficit_alerts is not None else user_link.notify_on_deficit
            
            await user_link.update_notifications(new_bomb_setting, new_deficit_setting)
            
            member = await Member.get_by_id(user_link.member_id)
            
            embed = discord.Embed(
                title="✅ Settings Updated",
                description=f"Notification settings for **{member.trainer_name}** have been updated",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            bomb_status = "✅ Enabled" if new_bomb_setting else "❌ Disabled"
            deficit_status = "✅ Enabled" if new_deficit_setting else "❌ Disabled"
            
            embed.add_field(
                name="New Settings",
                value=f"**💣 Bomb Warnings:** {bomb_status}\n"
                      f"**⚠️ Deficit Alerts:** {deficit_status}",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user.id} updated notification settings")
            
        except Exception as e:
            logger.error(f"Error in notification_settings: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="my_status", description="View your own quota status")
    async def my_status(self, interaction: discord.Interaction):
        """View your own linked trainer status"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            user_link = await UserLink.get_by_discord_id(interaction.user.id)
            
            if not user_link:
                await interaction.followup.send(
                    "❌ You haven't linked a trainer yet. Use `/link_trainer` to get started!",
                    ephemeral=True
                )
                return
            
            member = await Member.get_by_id(user_link.member_id)
            await self._send_member_status(interaction, member, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in my_status: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="member_status", description="View status of a specific member")
    async def member_status(self, interaction: discord.Interaction, trainer_name: str, club: str):
        """Get detailed status for a specific member"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            club_obj = await Club.get_by_name(club)
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found", ephemeral=True)
                return
            
            member = await Member.get_by_name(club_obj.club_id, trainer_name)
            
            if not member:
                await interaction.followup.send(f"❌ Member '{trainer_name}' not found in {club}", ephemeral=True)
                return
            
            await self._send_member_status(interaction, member, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in member_status: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="verify", description="Verify a trainer's stats and current club from uma.moe")
    @app_commands.describe(trainer_id="The 12-digit Trainer ID (Viewer ID) to check")
    async def verify(self, interaction: discord.Interaction, trainer_id: str):
        """Verify a trainer's stats and current club from uma.moe"""
        await interaction.response.defer()
        
        try:
            # Validate trainer_id
            if not trainer_id.isdigit():
                await interaction.followup.send("❌ Invalid Trainer ID. Must be numeric.")
                return

            now = datetime.utcnow()
            # uma.moe API uses current month/year
            month = now.month
            year = now.year
            
            url = f"https://uma.moe/api/v4/rankings/monthly?month={month}&year={year}&page=0&limit=100&query={trainer_id}&circle_name={trainer_id}"
            
            headers = {}
            api_key = os.getenv("UMAMOE_API_KEY")
            if api_key:
                headers["X-API-Key"] = api_key
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        await interaction.followup.send(f"❌ uma.moe API error (Status: {response.status})")
                        return
                    
                    data = await response.json()
            
            rankings = data.get('rankings', [])
            if not rankings:
                await interaction.followup.send(f"❌ No data found for Trainer ID: `{trainer_id}` on uma.moe for {month}/{year}.")
                return
            
            trainer = rankings[0]
            name = trainer.get('trainer_name', 'Unknown')
            total_fans = trainer.get('total_fans', 0)
            monthly_gain = trainer.get('monthly_gain', 0)
            avg_daily = trainer.get('avg_daily', 0)
            active_days = trainer.get('active_days', 0)
            club_name = trainer.get('circle_name', 'None')
            
            embed = discord.Embed(
                title=f"✅ Verification: {name}",
                description=f"Stats retrieved from uma.moe for **{datetime(year, month, 1).strftime('%B %Y')}**",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="👤 Trainer Info",
                value=f"**Name:** {name}\n"
                      f"**ID:** `{trainer_id}`\n"
                      f"**Current Club:** {club_name}",
                inline=False
            )
            
            embed.add_field(
                name="📈 Monthly Performance",
                value=f"**Monthly Gain:** {monthly_gain:,} 👥\n"
                      f"**Active Days:** {active_days} days\n"
                      f"**Average Daily:** {avg_daily:,.0f} fans/day",
                inline=True
            )
            
            embed.add_field(
                name="📊 Career",
                value=f"**Total Fans:** {total_fans:,} 👥",
                inline=False
            )
            
            embed.set_footer(text="Data source: uma.moe")
            
            await interaction.followup.send(embed=embed)
            logger.info(f"Verified trainer {trainer_id} ({name}) for user {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error in verify command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error during verification: {str(e)}")

    @app_commands.command(name="check_club", description="Show the current club status report from database (all members)")
    @app_commands.autocomplete(club=club_autocomplete)
    async def check_club(self, interaction: discord.Interaction, club: str):
        # Displays the full status report for a club using database-only data (no scraping).
        await interaction.response.defer()

        try:
            club_obj = await Club.get_by_name(club)
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found")
                return

            if not club_obj.belongs_to_guild(interaction.guild_id):
                await interaction.followup.send(f"❌ Club '{club}' is not registered in this server.")
                return

            club_tz = pytz.timezone(club_obj.timezone)
            current_date = datetime.now(club_tz).date()

            # Process cached data from DB
            status_summary = await self.quota_calculator.get_member_status_summary(
                club_obj.club_id, current_date, quota_period=club_obj.quota_period
            )

            # Only fetch bomb data if bombs are enabled
            if club_obj.bombs_enabled:
                bombs_data = await self.bomb_manager.get_active_bombs_with_members(club_obj.club_id)
            else:
                bombs_data = []

            # Try to get the latest rank data from DB if available
            rank_data = None
            latest_rank_record = await ClubRankHistory.get_latest(club_obj.club_id)
            if latest_rank_record:
                # Get the previous record for delta comparison
                prev_rank_record = await ClubRankHistory.get_previous(club_obj.club_id, latest_rank_record.date)
                
                rank_data = {
                    'monthly_rank': latest_rank_record.monthly_rank,
                    'yesterday_rank': prev_rank_record.monthly_rank if prev_rank_record else None,
                    'last_month_rank': None # Cannot easily determine without more logic, but monthly_rank is most important
                }

            effective_quota = await QuotaRequirement.get_quota_for_date(club_obj.club_id, current_date)
            daily_reports = self.report_generator.create_daily_report(
                club_obj.club_name, effective_quota, status_summary, bombs_data, current_date,
                rank_data=rank_data, quota_period=club_obj.quota_period
            )

            # Send all report embeds in the interaction reply
            if daily_reports:
                # First embed as followup, others as followups too
                for i, embed in enumerate(daily_reports):
                    await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("ℹ️ No status data found for this club.")

            logger.info(f"Report for {club} shown to {interaction.user} via /check_club")

        except Exception as e:
            logger.error(f"Error in check_club: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error generating report: {str(e)}")
    
    async def _send_member_status(self, interaction: discord.Interaction, member: Member, ephemeral: bool = False):
        """Send a detailed status embed for a member"""
        latest_history = await QuotaHistory.get_latest_for_member(member.member_id)
        
        if not latest_history:
            await interaction.followup.send(f"No quota data found for {member.trainer_name}", ephemeral=ephemeral)
            return
        
        active_bomb = await Bomb.get_active_for_member(member.member_id)
        
        # Get club info and effective quota
        from models import Club
        club = await Club.get_by_id(member.club_id)
        if club:
            daily_quota = await QuotaRequirement.get_quota_for_date(club.club_id, latest_history.date)
        else:
            daily_quota = 1000000
        
        # Determine color based on status
        if active_bomb:
            color = 0xFF0000  # Red for bomb
        elif latest_history.deficit_surplus < 0:
            color = 0xFFA500  # Orange for behind
        else:
            color = 0x3498db  # Blue for on track
        
        # Build title
        if active_bomb:
            title = "💣 Quota Status - Bomb Active"
        elif latest_history.deficit_surplus < 0:
            title = "⚠️ Quota Status - Behind"
        else:
            title = "📊 Quota Status"
        
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        # Trainer info - split into two columns
        status_text = "✅ Active" if member.is_active else "❌ Inactive"
        if member.manually_deactivated:
            status_text += " (Manually Deactivated)"
        
        embed.add_field(
            name="👤 Trainer Information",
            value=f"**Name:** {member.trainer_name}\n"
                  f"**Trainer ID:** `{member.trainer_id or 'N/A'}`\n"
                  f"**Club:** {club.club_name if club else 'Unknown'}",
            inline=True
        )
        
        embed.add_field(
            name="📅 Membership",
            value=f"**Joined:** {member.join_date.strftime('%b %d, %Y')}\n"
                  f"**Status:** {status_text}",
            inline=True
        )
        
        # Get total quota for the month
        import calendar
        from services.quota_calculator import QuotaCalculator
        last_day = calendar.monthrange(latest_history.date.year, latest_history.date.month)[1]
        end_of_month_date = latest_history.date.replace(day=last_day)
        
        total_month_quota = await QuotaCalculator.calculate_expected_fans(
            club_id=member.club_id,
            member_join_date=member.join_date,
            current_date=end_of_month_date,
            quota_period=club.quota_period if club else 'daily'
        )
        quota_left = max(0, total_month_quota - latest_history.cumulative_fans)

        # Progress bar
        if latest_history.expected_fans > 0:
            progress_pct = int((latest_history.cumulative_fans / latest_history.expected_fans) * 100)
        else:
            progress_pct = 0
        
        # Determine color indicator
        if progress_pct >= 500:
            color_indicator = "🟨"
        elif progress_pct >= 400:
            color_indicator = "🟧"
        elif progress_pct >= 300:
            color_indicator = "🟪"
        elif progress_pct >= 200:
            color_indicator = "🟦"
        elif progress_pct >= 100:
            color_indicator = "🟩"
        else:
            color_indicator = "⬜"
        
        # Calculate bar display
        if progress_pct >= 100:
            bar = "█" * 20
        else:
            filled = int(progress_pct / 5)
            empty = 20 - filled
            bar = "█" * filled + "░" * empty
        
        progress_title = "📈 Current Progress" if latest_history.deficit_surplus >= 0 else "📉 Current Progress"
        
        embed.add_field(
            name=progress_title,
            value=f"```\nCurrent:  {latest_history.cumulative_fans:,} 👥\n"
                  f"Expected: {latest_history.expected_fans:,} 👥\n"
                  f"━━━━━━━━━━━━━━━━━━━━\n"
                  f"Progress: {bar} {color_indicator}{progress_pct}%\n```",
            inline=False
        )
        
        # Performance section
        if latest_history.deficit_surplus >= 0:
            status_emoji = "🎯"
            deficit_text = f"+{latest_history.deficit_surplus:,}"
            performance_title = "🎯 Performance"
        else:
            status_emoji = "⚠️"
            deficit_text = f"{latest_history.deficit_surplus:,}"
            performance_title = "⚠️ Performance"
        
        embed.add_field(
            name=performance_title,
            value=f"**Surplus/Deficit:** {deficit_text} fans {status_emoji}\n"
                  f"**Days Behind:** {latest_history.days_behind} days\n"
                  f"**Daily Quota:** {daily_quota:,} fans/day",
            inline=True
        )
        
        # Bomb status
        if active_bomb:
            urgency_emoji = "🔴" if active_bomb.days_remaining <= 2 else "🟠" if active_bomb.days_remaining <= 4 else "🟡"
            
            embed.add_field(
                name="💣 Active Bomb",
                value=f"{urgency_emoji} **{active_bomb.days_remaining} days remaining**\n"
                      f"Activated: {active_bomb.activation_date.strftime('%b %d, %Y')}\n"
                      f"Get back on track!",
                inline=True
            )
        elif latest_history.days_behind == 2:
            embed.add_field(
                name="💣 Bomb Warning",
                value="🟡 **1 more day** behind\n"
                      "and a bomb will activate!\n"
                      "Get on track today.",
                inline=True
            )
        else:
            embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        # Recommendations
        if quota_left > 0:
            days_remaining = max(1, last_day - latest_history.date.day)
            monthly_pace = quota_left // days_remaining
            embed.add_field(
                name="📅 Rest of Month Pace",
                value=f"Target: **{monthly_pace:,} fans/day** (next {days_remaining} day{'s' if days_remaining != 1 else ''})\n"
                      f"Month Left: **{quota_left:,} fans**",
                inline=False
            )
        
        # Calculate streak and get history
        history_records = await QuotaHistory.get_last_n_days(member.member_id, 100)
        
        # Use calendar days in period for accurate averages (matches quota period)
        from services.quota_calculator import QuotaCalculator
        days_in_period = QuotaCalculator.calculate_days_active_in_month(member.join_date, latest_history.date)
        days_tracked = len(history_records) if history_records else 1
            
        avg_daily = latest_history.cumulative_fans / max(1, days_in_period)
        
        # Calculate streak (consecutive days on track)
        streak_days = 0
        if latest_history.deficit_surplus >= 0:
            streak_days = 1
            for record in history_records[1:]:
                if record.deficit_surplus >= 0:
                    streak_days += 1
                else:
                    break
        
        # Get best day from member record (now accurately calculated from full JSON history)
        best_day_fans = member.monthly_best_day
        
        # Format stats
        if avg_daily >= 1_000_000:
            avg_formatted = f"{avg_daily / 1_000_000:.2f}M"
        elif avg_daily >= 1_000:
            avg_formatted = f"{avg_daily / 1_000:.1f}K"
        else:
            avg_formatted = f"{int(avg_daily)}"
        
        if best_day_fans >= 1_000_000:
            best_formatted = f"{best_day_fans / 1_000_000:.2f}M"
        elif best_day_fans >= 1_000:
            best_formatted = f"{best_day_fans / 1_000:.1f}K"
        else:
            best_formatted = f"{best_day_fans}"
        
        # Streak emoji
        if streak_days >= 30:
            streak_emoji = "🔥🔥🔥"
        elif streak_days >= 14:
            streak_emoji = "🔥🔥"
        elif streak_days >= 7:
            streak_emoji = "🔥"
        elif streak_days >= 3:
            streak_emoji = "✨"
        else:
            streak_emoji = ""
        
        embed.add_field(
            name="📊 Statistics",
            value=f"**Days Tracked:** {days_tracked} ({days_in_period}d period)\n"
                  f"**Avg Daily:** {avg_formatted}/day\n"
                  f"**Best Day:** +{best_formatted}\n"
                  f"**Streak:** {streak_days} day{'s' if streak_days != 1 else ''} {streak_emoji}",
            inline=True
        )
        
        # Global Rank
        member_rankings = await QuotaHistory.get_latest_global_rankings()
        
        member_rank = 0
        for idx, ranking in enumerate(member_rankings, start=1):
            if ranking['member_id'] == member.member_id:
                member_rank = idx
                break
        
        total_members = len(member_rankings)
        
        if total_members > 0:
            percentile_raw = (member_rank / total_members) * 100
            
            if member_rank == 1:
                percentile_desc = "Top 0.01% 👑"
                rank_label = "🏆 World Rank"
            elif percentile_raw <= 1:
                percentile_desc = f"Top {percentile_raw:.2f}%"
                rank_label = "🌍 Global Rank"
            elif percentile_raw <= 10:
                percentile_desc = f"Top {percentile_raw:.1f}%"
                rank_label = "🌍 Global Rank"
            elif percentile_raw <= 50:
                percentile_desc = f"Top {int(percentile_raw)}%"
                rank_label = "🌍 Global Rank"
            else:
                percentile_desc = f"Bottom {100 - int(percentile_raw)}%"
                rank_label = "🌍 Global Rank"
        else:
            percentile_desc = "N/A"
            rank_label = "🌍 Global Rank"
        
        embed.add_field(
            name=rank_label,
            value=f"**Rank:** #{member_rank} of {total_members}\n"
                  f"**Percentile:** {percentile_desc}",
            inline=True
        )
        
        embed.set_footer(text=f"Last updated: {latest_history.date.strftime('%b %d, %Y')} • Today at {datetime.now().strftime('%I:%M %p')}")
        
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    
    @app_commands.command(name="leaderboard", description="View the leaderboard of synced trainers")
    @app_commands.autocomplete(club=club_autocomplete)
    async def leaderboard(self, interaction: discord.Interaction, club: str = None):
        """View visual leaderboard of synced trainers (guild-wide or per-club)"""
        await interaction.response.defer()
        
        try:
            from config.database import db
            import os
            
            # 1. Resolve target clubs and display title
            if club:
                club_obj = await Club.get_by_name(club)
                if not club_obj:
                    await interaction.followup.send(f"❌ Club '{club}' not found.")
                    return
                if not club_obj.belongs_to_guild(interaction.guild_id):
                    await interaction.followup.send(f"❌ Club '{club_obj.club_name}' is not registered in this server.")
                    return
                active_clubs = [club_obj]
                display_name = club_obj.club_name
                timezone_str = club_obj.timezone
                
                club_tz = pytz.timezone(timezone_str)
                current_date_str = datetime.now(club_tz).strftime("%B %d, %Y")
                date_slug = datetime.now(club_tz).strftime("%Y-%m-%d")
                cache_prefix = f"club_{club_obj.club_id}_{date_slug}"
            else:
                # Global guild-wide leaderboard
                clubs = await Club.get_all_for_guild(interaction.guild_id)
                if not clubs:
                    await interaction.followup.send("❌ No clubs registered in this server.")
                    return
                active_clubs = [c for c in clubs if c.is_active]
                if not active_clubs:
                    await interaction.followup.send("❌ No active clubs registered in this server.")
                    return
                
                # If only one club exists, treat it as that specific club's leaderboard
                if len(active_clubs) == 1:
                    display_name = active_clubs[0].club_name
                    timezone_str = active_clubs[0].timezone
                    club_tz = pytz.timezone(timezone_str)
                    current_date_str = datetime.now(club_tz).strftime("%B %d, %Y")
                    date_slug = datetime.now(club_tz).strftime("%Y-%m-%d")
                    cache_prefix = f"club_{active_clubs[0].club_id}_{date_slug}"
                else:
                    display_name = interaction.guild.name
                    timezone_str = active_clubs[0].timezone
                    club_tz = pytz.timezone(timezone_str)
                    current_date_str = datetime.now(club_tz).strftime("%B %d, %Y")
                    date_slug = datetime.now(club_tz).strftime("%Y-%m-%d")
                    cache_prefix = f"guild_{interaction.guild_id}_{date_slug}"

            club_ids = [c.club_id for c in active_clubs]
            club_names_map = {c.club_id: c.club_name for c in active_clubs}

            # Check if cache exists
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "leaderboards")
            os.makedirs(cache_dir, exist_ok=True)
            
            cache_files = [f for f in os.listdir(cache_dir) if f.startswith(cache_prefix) and f.endswith(".webp")]
            
            if cache_files:
                total_pages = len(cache_files)
                first_page_path = os.path.join(cache_dir, f"{cache_prefix}_page_0.webp")
                if os.path.exists(first_page_path):
                    try:
                        with open(first_page_path, "rb") as f:
                            file = discord.File(io.BytesIO(f.read()), filename="leaderboard.webp")
                        
                        view = LeaderboardView(
                            user_id=interaction.user.id,
                            cache_prefix=cache_prefix,
                            total_pages=total_pages,
                            club_name=display_name,
                            leaderboard_data=[],
                            current_date_str=current_date_str
                        )
                        if total_pages > 1:
                            await interaction.followup.send(file=file, view=view)
                        else:
                            await interaction.followup.send(file=file)
                        logger.info(f"Leaderboard image served from disk cache for {display_name} by user {interaction.user}")
                        return
                    except Exception as e:
                        logger.warning(f"Failed to read leaderboard cache for {display_name}: {e}. Falling back to DB query.")

            # 2. Query all active users (even unsynced)
            query = """
                WITH latest_history AS (
                    SELECT DISTINCT ON (member_id) member_id, cumulative_fans, expected_fans, deficit_surplus, date, days_behind
                    FROM quota_history
                    WHERE club_id = ANY($1::uuid[])
                    ORDER BY member_id, date DESC
                )
                SELECT ul.discord_user_id, m.member_id, m.trainer_name, m.trainer_id, m.club_id,
                       lh.cumulative_fans, lh.expected_fans, lh.deficit_surplus, lh.date, lh.days_behind,
                       b.is_active as is_bomb
                FROM members m
                LEFT JOIN user_links ul ON m.member_id = ul.member_id
                LEFT JOIN latest_history lh ON m.member_id = lh.member_id
                LEFT JOIN bombs b ON m.member_id = b.member_id AND b.is_active = TRUE
                WHERE m.club_id = ANY($1::uuid[]) AND m.is_active = TRUE
                ORDER BY COALESCE(lh.cumulative_fans, 0) DESC
            """
            
            rows = await db.fetch(query, club_ids)
            if not rows:
                target_desc = f"**{display_name}**" if club else "this server"
                await interaction.followup.send(
                    f"ℹ️ No trainers found in {target_desc}."
                )
                return

            # 3. Resolve usernames and avatars in parallel
            fetch_sem = asyncio.Semaphore(3)
            async def resolve_user(row):
                import time
                discord_user_id = row['discord_user_id']
                if not discord_user_id:
                    return row, None
                now = time.time()
                
                # Check cache first
                if discord_user_id in _discord_user_cache:
                    cached_name, cached_avatar, expires_at = _discord_user_cache[discord_user_id]
                    if now < expires_at:
                        if cached_name is None:
                            return row, None
                        return row, CachedDiscordUser(cached_name, cached_avatar)
                
                user = interaction.guild.get_member(discord_user_id)
                if not user:
                    async with fetch_sem:
                        await asyncio.sleep(0.1)
                        try:
                            user = await interaction.guild.fetch_member(discord_user_id)
                        except Exception:
                            try:
                                user = await self.bot.fetch_user(discord_user_id)
                            except Exception:
                                user = None
                
                if user:
                    username = user.name
                    avatar_url = user.display_avatar.with_format("webp").url if user.display_avatar else None
                    _discord_user_cache[discord_user_id] = (username, avatar_url, now + 86400) # Cache successes for 24 hours
                    return row, CachedDiscordUser(username, avatar_url)
                else:
                    _discord_user_cache[discord_user_id] = (None, None, now + 3600) # Cache failures for 1 hour
                    return row, None

            tasks = [resolve_user(row) for row in rows]
            resolved_results = await asyncio.gather(*tasks)

            leaderboard_data = []
            for row, user in resolved_results:
                if user:
                    # Synced trainer display format
                    if len(active_clubs) > 1:
                        trainer_label = f"{row['trainer_name']} ({club_names_map.get(row['club_id'], 'Unknown')})"
                    else:
                        trainer_label = row['trainer_name']
                    
                    username = f"@{user.name}"
                    avatar_url = user.display_avatar.url
                else:
                    # Unsynced trainer display format
                    if len(active_clubs) > 1:
                        trainer_label = f"({club_names_map.get(row['club_id'], 'Unknown')})"
                    else:
                        trainer_label = ""
                    
                    username = row['trainer_name']
                    avatar_url = None

                leaderboard_data.append({
                    "username": username,
                    "trainer_name": trainer_label,
                    "avatar_url": avatar_url,
                    "cumulative_fans": row['cumulative_fans'] or 0,
                    "expected_fans": row['expected_fans'] or 0,
                    "is_bomb": bool(row['is_bomb']),
                    "is_behind": bool(row['deficit_surplus'] is not None and row['deficit_surplus'] < 0)
                })

            # 4. Generate the leaderboard image(s) via paginated view (Max 60 trainers / 6 pages)
            leaderboard_data = leaderboard_data[:60]
            total_pages = (len(leaderboard_data) - 1) // 10 + 1
            
            # Pre-render all pages and save to disk cache
            from utils.leaderboard_renderer import render_leaderboard_image
            for page_idx in range(total_pages):
                start_idx = page_idx * 10
                end_idx = start_idx + 10
                page_data = leaderboard_data[start_idx:end_idx]
                
                img_bytes = await render_leaderboard_image(
                    club_name=display_name,
                    leaderboard_data=page_data,
                    current_date_str=current_date_str,
                    start_rank=start_idx + 1
                )
                page_cache_path = os.path.join(cache_dir, f"{cache_prefix}_page_{page_idx}.webp")
                try:
                    with open(page_cache_path, "wb") as f:
                        f.write(img_bytes)
                except Exception as e:
                    logger.warning(f"Failed to write leaderboard cache file {page_cache_path}: {e}")
            
            # Load page 0
            first_page_path = os.path.join(cache_dir, f"{cache_prefix}_page_0.webp")
            with open(first_page_path, "rb") as f:
                file = discord.File(io.BytesIO(f.read()), filename="leaderboard.webp")
                
            view = LeaderboardView(
                user_id=interaction.user.id,
                cache_prefix=cache_prefix,
                total_pages=total_pages,
                club_name=display_name,
                leaderboard_data=leaderboard_data,
                current_date_str=current_date_str
            )
            if total_pages > 1:
                await interaction.followup.send(file=file, view=view)
            else:
                await interaction.followup.send(file=file)
            logger.info(f"Leaderboard image generated and sent for {display_name} by user {interaction.user}")

        except Exception as e:
            logger.error(f"Error in leaderboard command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    # Apply autocomplete
    link_trainer.autocomplete('club')(club_autocomplete)
    member_status.autocomplete('club')(club_autocomplete)
    check_club.autocomplete('club')(club_autocomplete)
    leaderboard.autocomplete('club')(club_autocomplete)


async def pre_render_and_cache_leaderboard(bot, club_id: str = None, guild_id: int = None):
    """
    Query, resolve, render, and cache leaderboard pages to disk in the background.
    Supports either club-level or guild-level caching.
    """
    try:
        from config.database import db
        import os
        import pytz
        import asyncio
        from datetime import datetime
        
        # 1. Resolve clubs, timezone, display name, and cache prefix
        if club_id:
            club_obj = await Club.get_by_id(club_id)
            if not club_obj:
                return
            active_clubs = [club_obj]
            display_name = club_obj.club_name
            timezone_str = club_obj.timezone
            club_tz = pytz.timezone(timezone_str)
            current_date_str = datetime.now(club_tz).strftime("%B %d, %Y")
            date_slug = datetime.now(club_tz).strftime("%Y-%m-%d")
            cache_prefix = f"club_{club_obj.club_id}_{date_slug}"
        elif guild_id:
            clubs = await Club.get_all_for_guild(guild_id)
            if not clubs:
                return
            active_clubs = [c for c in clubs if c.is_active]
            if not active_clubs:
                return
            if len(active_clubs) == 1:
                display_name = active_clubs[0].club_name
                timezone_str = active_clubs[0].timezone
                club_tz = pytz.timezone(timezone_str)
                current_date_str = datetime.now(club_tz).strftime("%B %d, %Y")
                date_slug = datetime.now(club_tz).strftime("%Y-%m-%d")
                cache_prefix = f"club_{active_clubs[0].club_id}_{date_slug}"
            else:
                guild = bot.get_guild(guild_id)
                display_name = guild.name if guild else "Guild Leaderboard"
                timezone_str = active_clubs[0].timezone
                club_tz = pytz.timezone(timezone_str)
                current_date_str = datetime.now(club_tz).strftime("%B %d, %Y")
                date_slug = datetime.now(club_tz).strftime("%Y-%m-%d")
                cache_prefix = f"guild_{guild_id}_{date_slug}"
        else:
            return

        club_ids = [c.club_id for c in active_clubs]
        club_names_map = {c.club_id: c.club_name for c in active_clubs}

        # 2. Query all active users (even unsynced)
        query = """
            WITH latest_history AS (
                SELECT DISTINCT ON (member_id) member_id, cumulative_fans, expected_fans, deficit_surplus, date, days_behind
                FROM quota_history
                WHERE club_id = ANY($1::uuid[])
                ORDER BY member_id, date DESC
            )
            SELECT ul.discord_user_id, m.member_id, m.trainer_name, m.trainer_id, m.club_id,
                   lh.cumulative_fans, lh.expected_fans, lh.deficit_surplus, lh.date, lh.days_behind,
                   b.is_active as is_bomb
            FROM members m
            LEFT JOIN user_links ul ON m.member_id = ul.member_id
            LEFT JOIN latest_history lh ON m.member_id = lh.member_id
            LEFT JOIN bombs b ON m.member_id = b.member_id AND b.is_active = TRUE
            WHERE m.club_id = ANY($1::uuid[]) AND m.is_active = TRUE
            ORDER BY COALESCE(lh.cumulative_fans, 0) DESC
        """
        
        rows = await db.fetch(query, club_ids)
        if not rows:
            return

        # 3. Resolve usernames and avatars in parallel
        fetch_sem = asyncio.Semaphore(3)
        async def resolve_user(row):
            import time
            discord_user_id = row['discord_user_id']
            if not discord_user_id:
                return row, None
            now = time.time()
            
            if discord_user_id in _discord_user_cache:
                cached_name, cached_avatar, expires_at = _discord_user_cache[discord_user_id]
                if now < expires_at:
                    if cached_name is None:
                        return row, None
                    return row, CachedDiscordUser(cached_name, cached_avatar)
            
            # Look up guild member
            target_guild_id = guild_id if guild_id else active_clubs[0].guild_id
            guild = bot.get_guild(target_guild_id)
            user = guild.get_member(discord_user_id) if guild else None
            if not user:
                async with fetch_sem:
                    await asyncio.sleep(0.1)
                    try:
                        user = await guild.fetch_member(discord_user_id) if guild else None
                    except Exception:
                        try:
                            user = await bot.fetch_user(discord_user_id)
                        except Exception:
                            user = None
            
            if user:
                username = user.name
                avatar_url = user.display_avatar.with_format("webp").url if user.display_avatar else None
                _discord_user_cache[discord_user_id] = (username, avatar_url, now + 86400) # Cache successes for 24 hours
                return row, CachedDiscordUser(username, avatar_url)
            else:
                _discord_user_cache[discord_user_id] = (None, None, now + 3600) # Cache failures for 1 hour
                return row, None

        tasks = [resolve_user(row) for row in rows]
        resolved_results = await asyncio.gather(*tasks)

        leaderboard_data = []
        for row, user in resolved_results:
            if user:
                # Synced trainer display format
                if len(active_clubs) > 1:
                    trainer_label = f"{row['trainer_name']} ({club_names_map.get(row['club_id'], 'Unknown')})"
                else:
                    trainer_label = row['trainer_name']
                
                username = f"@{user.name}"
                avatar_url = user.display_avatar.url
            else:
                # Unsynced trainer display format
                if len(active_clubs) > 1:
                    trainer_label = f"({club_names_map.get(row['club_id'], 'Unknown')})"
                else:
                    trainer_label = ""
                
                username = row['trainer_name']
                avatar_url = None

            leaderboard_data.append({
                "username": username,
                "trainer_name": trainer_label,
                "avatar_url": avatar_url,
                "cumulative_fans": row['cumulative_fans'] or 0,
                "expected_fans": row['expected_fans'] or 0,
                "is_bomb": bool(row['is_bomb']),
                "is_behind": bool(row['deficit_surplus'] is not None and row['deficit_surplus'] < 0)
            })

        leaderboard_data = leaderboard_data[:60]
        total_pages = (len(leaderboard_data) - 1) // 10 + 1
        
        # Pre-render all pages and save to disk cache
        from utils.leaderboard_renderer import render_leaderboard_image
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "leaderboards")
        os.makedirs(cache_dir, exist_ok=True)
        
        # Clean old cache files for this prefix to avoid duplicates/leftovers
        for f in os.listdir(cache_dir):
            if f.startswith(cache_prefix) and f.endswith(".webp"):
                try:
                    os.remove(os.path.join(cache_dir, f))
                except Exception:
                    pass

        for page_idx in range(total_pages):
            start_idx = page_idx * 10
            end_idx = start_idx + 10
            page_data = leaderboard_data[start_idx:end_idx]
            
            img_bytes = await render_leaderboard_image(
                club_name=display_name,
                leaderboard_data=page_data,
                current_date_str=current_date_str,
                start_rank=start_idx + 1
            )
            page_cache_path = os.path.join(cache_dir, f"{cache_prefix}_page_{page_idx}.webp")
            try:
                with open(page_cache_path, "wb") as f:
                    f.write(img_bytes)
            except Exception as e:
                logger.warning(f"Failed to write leaderboard cache file {page_cache_path}: {e}")
                
        logger.info(f"✅ Background pre-rendered {total_pages} pages for prefix {cache_prefix}")
    except Exception as e:
        logger.error(f"❌ Error in pre_render_and_cache_leaderboard: {e}", exc_info=True)
