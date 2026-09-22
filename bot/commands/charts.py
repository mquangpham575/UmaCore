"""
Chart commands for visualizing member fan progression
"""
import discord
from discord import app_commands
from discord.ext import commands
import io
import logging
from datetime import date, datetime
import pytz

from models import Club, QuotaHistory
from scrapers import ClubScraper


logger = logging.getLogger(__name__)


async def _fetch_via_scraper(circle_id: str) -> tuple[dict[str, dict], int, int, int]:
    """
    Fetch full-month fan progression via ClubScraper.
    """
    scraper = ClubScraper(circle_id)
    parsed_data = await scraper.scrape()

    current_day = scraper.get_current_day()
    data_date = scraper.get_data_date() or date.today()
    year = data_date.year
    month = data_date.month

    member_data: dict[str, dict] = {}
    for data in parsed_data.values():
        name = data["name"]
        join_day = data["join_day"]
        fans_array: list[int] = data["fans"]  # monthly cumulative, index 0 = day 1

        dates: list[date] = []
        fans: list[int] = []
        for day_idx, monthly_val in enumerate(fans_array):
            day_num = day_idx + 1
            if day_num < join_day:
                continue  # skip pre-join zeros
            
            try:
                dt = date(year, month, day_num)
                dates.append(dt)
                fans.append(monthly_val)
            except ValueError:
                # Handle potential day-out-of-range for the month
                continue

        if dates:
            member_data[name] = {"dates": dates, "fans": fans}

    return member_data, current_day, year, month


def _build_chart(member_data: dict[str, dict]) -> bytes:
    """Render the fan progression chart using matplotlib and return PNG bytes."""
    import glob
    from datetime import timedelta
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.font_manager as fm
    for font_path in glob.glob('/usr/share/fonts/**/*.otf', recursive=True) + glob.glob('/usr/share/fonts/**/*.ttf', recursive=True):
        try:
            fm.fontManager.addfont(font_path)
        except Exception:
            pass

    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.ticker as ticker

    plt.style.use('dark_background')
    plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'Noto Sans CJK SC', 'DejaVu Sans', 'Arial', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False

    num_members = len(member_data)
    fig_height = max(7.0, 4.0 + (num_members * 0.15))
    fig, ax = plt.subplots(figsize=(12, fig_height), dpi=160)

    fig.patch.set_facecolor('#111827')
    ax.set_facecolor('#111827')

    # Color palette
    colors = plt.cm.tab20.colors + plt.cm.tab20b.colors

    all_dates: list[date] = []
    for idx, (name, data) in enumerate(member_data.items()):
        # Sort each member's points chronologically
        sorted_pairs = sorted(zip(data["dates"], data["fans"]), key=lambda p: p[0])
        dates = [p[0] for p in sorted_pairs]
        fans = [p[1] for p in sorted_pairs]
        all_dates.extend(dates)

        color = colors[idx % len(colors)]
        ax.plot(
            dates,
            fans,
            label=name,
            color=color,
            linewidth=2,
            marker='o',
            markersize=3.5,
            alpha=0.9
        )

    ax.set_title("Member Progression", fontsize=15, fontweight='bold', color='white', pad=15, loc='left')
    ax.set_xlabel("Date", fontsize=10, color='#a0aec0', labelpad=8)
    ax.set_ylabel("Fans", fontsize=10, color='#a0aec0', labelpad=8)

    # Chronological continuous date scale
    if all_dates:
        min_date = min(all_dates)
        max_date = max(all_dates)
        # Always align starting x-limit to Day 1 of the month if available
        first_of_month = date(min_date.year, min_date.month, 1)
        start_bound = first_of_month if first_of_month <= min_date else min_date
        ax.set_xlim(start_bound - timedelta(hours=12), max_date + timedelta(hours=12))

        span_days = (max_date - start_bound).days + 1
        day_interval = 1 if span_days <= 10 else (2 if span_days <= 20 else 3)
    else:
        day_interval = 1

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=day_interval))

    def fan_formatter(x, pos):
        if x >= 1_000_000_000:
            return f"{x / 1_000_000_000:.1f}B"
        elif x >= 1_000_000:
            return f"{x / 1_000_000:.0f}M"
        elif x >= 1_000:
            return f"{x / 1_000:.0f}K"
        return str(int(x))

    ax.yaxis.set_major_formatter(ticker.FuncFormatter(fan_formatter))
    ax.grid(True, linestyle='--', alpha=0.25, color='#4b5563')
    ax.tick_params(colors='#a0aec0', labelsize=9)

    ncol = 2 if num_members > 15 else 1
    ax.legend(
        bbox_to_anchor=(1.02, 1),
        loc='upper left',
        ncol=ncol,
        framealpha=0.3,
        facecolor='#1f2937',
        edgecolor='#374151',
        fontsize=8.5,
        labelcolor='#e2e8f0'
    )

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


class ChartCommands(commands.Cog):
    """Chart and visualization commands"""

    def __init__(self, bot):
        self.bot = bot

    async def club_autocomplete(self, interaction: discord.Interaction, current: str):
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

    @app_commands.command(
        name="progress_chart",
        description="View fan progression chart for all members this month"
    )
    async def progress_chart(self, interaction: discord.Interaction, club: str):
        """Generate a cumulative fan progression line chart for all active club members."""
        await interaction.response.defer()

        try:
            import matplotlib  # noqa: F401 — verify installed early
        except ImportError:
            await interaction.followup.send(
                "❌ Matplotlib is not installed. Run `pip install matplotlib`."
            )
            return

        try:
            club_obj = await Club.get_by_name(club)
            if not club_obj:
                await interaction.followup.send(f"❌ Club '{club}' not found.")
                return

            if not club_obj.belongs_to_guild(interaction.guild_id):
                await interaction.followup.send(
                    f"❌ Club '{club}' is not registered in this server."
                )
                return

            club_tz = pytz.timezone(club_obj.timezone)
            now = datetime.now(club_tz)

            display_month_label = now.strftime("%B %Y")
            member_data: dict[str, dict] | None = None

            try:
                await interaction.followup.send("🔍 Aston Macching data history")
                member_data, _, fetched_year, fetched_month = await _fetch_via_scraper(
                    club_obj.circle_id
                )
                display_month_label = date(fetched_year, fetched_month, 1).strftime("%B %Y")
                logger.info(
                    f"progress_chart: fetched {len(member_data)} members via UI simulation for {club}"
                )
            except Exception as e:
                logger.warning(
                    f"UI simulation fetch failed for chart ({club}), falling back to DB: {e}"
                )
                member_data = None

            # DB fallback for ChronoGenesis clubs or API failures
            if member_data is None:
                rows = await QuotaHistory.get_current_month_for_club(
                    club_obj.club_id, now.year, now.month
                )
                if not rows:
                    await interaction.followup.send(
                        f"❌ No data available for **{club}** this month yet."
                    )
                    return
                member_data = {}
                for row in rows:
                    name = row["trainer_name"]
                    if name not in member_data:
                        member_data[name] = {"dates": [], "fans": []}
                    row_date = row["date"].date() if isinstance(row["date"], datetime) else row["date"]
                    member_data[name]["dates"].append(row_date)
                    member_data[name]["fans"].append(row["cumulative_fans"])

            if not member_data:
                await interaction.followup.send(
                    f"❌ No member data found for **{club}** this month."
                )
                return

            try:
                img_bytes = _build_chart(member_data)
            except Exception as e:
                logger.error(f"Failed to render chart image: {e}", exc_info=True)
                await interaction.followup.send(
                    "❌ Failed to render chart image."
                )
                return

            file = discord.File(io.BytesIO(img_bytes), filename="progress_chart.png")
            embed = discord.Embed(
                title=f"📈 Member Progression — {club}",
                description=f"{display_month_label} · {len(member_data)} members",
                color=0x3B82F6,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_image(url="attachment://progress_chart.png")
            embed.set_footer(text="Cumulative fan count over the month")

            await interaction.followup.send(embed=embed, file=file)
            logger.info(
                f"progress_chart sent for {club} ({len(member_data)} members) "
                f"by {interaction.user}"
            )

        except Exception as e:
            logger.error(f"Error in progress_chart: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {str(e)}")

    progress_chart.autocomplete("club")(club_autocomplete)


async def setup(bot):
    await bot.add_cog(ChartCommands(bot))
