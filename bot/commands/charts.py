"""
Chart commands for visualizing member fan progression
"""
import calendar
import discord
from discord import app_commands
from discord.ext import commands
import io
import math
import logging
from datetime import date, datetime
import pytz
import aiohttp

from models import Club, QuotaHistory, QuotaRequirement
from scrapers import UmaGitHubScraper


# Removed _fetch_previous_month_totals

logger = logging.getLogger(__name__)


async def _fetch_via_scraper(circle_id: str) -> tuple[dict[str, dict], int, int, int]:
    """
    Fetch full-month fan progression by using UmaGitHubScraper.
    """
    scraper = UmaGitHubScraper(circle_id)
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

        dates: list[str] = []
        fans: list[int] = []
        for day_idx, monthly_val in enumerate(fans_array):
            day_num = day_idx + 1
            if day_num < join_day:
                continue  # skip pre-join zeros
            
            try:
                dt = date(year, month, day_num)
                dates.append(dt.strftime("%d.%m"))
                fans.append(monthly_val)
            except ValueError:
                # Handle potential day-out-of-range for the month
                continue

        if dates:
            member_data[name] = {"dates": dates, "fans": fans}

    return member_data, current_day, year, month


def _build_chart(member_data: dict[str, dict]) -> bytes:
    """Render the Plotly chart and return PNG bytes."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for name, data in member_data.items():
        fig.add_trace(go.Scatter(
            x=data["dates"],
            y=data["fans"],
            mode="lines",
            name=name,
            line=dict(width=2),
            hovertemplate=f"<b>{name}</b><br>%{{x}}<br>%{{y:,.0f}} fans<extra></extra>",
        ))

    all_fans = [v for d in member_data.values() for v in d["fans"]]
    max_val = max(all_fans) if all_fans else 1_000_000

    # Compute clean Y-axis ticks
    raw_step = max_val / 8
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step > 0 else 1
    tick_step = max(round(raw_step / magnitude) * magnitude, 1)
    tick_vals = list(range(0, int(max_val * 1.15) + tick_step, tick_step))

    def fmt_fans(v: int) -> str:
        if v >= 1_000_000_000:
            return f"{v / 1_000_000_000:.1f}B"
        elif v >= 1_000_000:
            return f"{v / 1_000_000:.0f}M"
        elif v >= 1_000:
            return f"{v / 1_000:.0f}K"
        return str(v)

    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="Member Progression",
            font=dict(size=18, color="white"),
            x=0,
            xref="paper",
            pad=dict(l=10),
        ),
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        xaxis=dict(
            showgrid=True,
            gridcolor="#2d3748",
            gridwidth=1,
            tickfont=dict(size=11, color="#a0aec0"),
            tickangle=0,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#2d3748",
            gridwidth=1,
            tickvals=tick_vals,
            ticktext=[fmt_fans(v) for v in tick_vals],
            tickfont=dict(size=11, color="#a0aec0"),
        ),
        legend=dict(
            font=dict(size=10, color="#e2e8f0"),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
        ),
        margin=dict(l=70, r=20, t=60, b=40),
        width=1100,
        height=max(500, 60 + len(member_data) * 22),
        hovermode="x unified",
    )

    return fig.to_image(format="png", scale=2)


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
            import plotly.graph_objects  # noqa: F401 — verify installed early
        except ImportError:
            await interaction.followup.send(
                "❌ Plotly is not installed. Run `pip install plotly kaleido`."
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
                await interaction.followup.send("🔍 Fetching monthly history via GitHub API...")
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
                    member_data[name]["dates"].append(row["date"].strftime("%d.%m"))
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
                    "❌ Failed to render chart image. "
                    "Make sure `kaleido` is installed: `pip install kaleido`"
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

    # Removed previous_month command


async def setup(bot):
    await bot.add_cog(ChartCommands(bot))
