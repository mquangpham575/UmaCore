"""
/events command - shows current Uma Musume Global gacha banners and events.
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from .client import GametoraClient, char_image_url

logger = logging.getLogger(__name__)

GAMETORA_CHAR_URL = "https://gametora.com/umamusume/characters/{url_name}"
GAMETORA_SUPPORT_URL = "https://gametora.com/umamusume/supports/{url_name}"

# Embed colours
COLOUR_GACHA = discord.Colour.from_str("#9b59b6")   # purple
COLOUR_EVENTS = discord.Colour.from_str("#e67e22")  # orange


def _ts(unix: int | None, style: str = "R") -> str:
    if not unix:
        return "Unknown"
    return f"<t:{unix}:{style}>"


def _end_line(unix: int | None) -> str:
    if not unix:
        return ""
    return f"\nEnds {_ts(unix, 'R')} ({_ts(unix, 'D')})"


class EventsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = GametoraClient()

    def cog_unload(self):
        self.bot.loop.create_task(self.client.close())

    @app_commands.command(
        name="events",
        description="View current Uma Musume Global gacha banners and events",
    )
    async def events(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            data = await self.client.get_events_data()
        except Exception as e:
            logger.error(f"Failed to fetch events data: {e}", exc_info=True)
            await interaction.followup.send(
                "Failed to fetch events data from GameTora. Try again later."
            )
            return

        embeds = []

        # ---------------------------------------------------------------- #
        #  Gacha banners embed                                              #
        # ---------------------------------------------------------------- #
        layout = data["layout"]
        nav = layout.get("right_nav_newest", {})
        chars_info = nav.get("chars", {})
        supports_info = nav.get("supports", {})
        char_banner = data["char_banner"]
        support_banner = data["support_banner"]

        gacha_embed = discord.Embed(
            title="Gacha Banners  \N{GAME DIE}",
            colour=COLOUR_GACHA,
            timestamp=discord.utils.utcnow(),
        )

        # Character banner
        chars = chars_info.get("list", [])
        if chars:
            char = chars[0]
            card_id: int | None = char.get("id")
            name_en: str = char.get("name_en", "Unknown")
            url_name: str = char.get("url_name", "")
            rerun_tag = "  *(Rerun)*" if chars_info.get("rerun") else ""
            end_ts = char_banner.get("end") if char_banner else None

            char_link = (
                f"[{name_en}]({GAMETORA_CHAR_URL.format(url_name=url_name)})"
                if url_name
                else name_en
            )
            value = f"{char_link}{rerun_tag}{_end_line(end_ts)}"
            gacha_embed.add_field(name="\u2728 Character Banner", value=value, inline=False)

            if card_id:
                gacha_embed.set_thumbnail(url=char_image_url(card_id))

        # Support banner
        supports = supports_info.get("list", [])
        if supports:
            rerun_tag = "  *(Rerun)*" if supports_info.get("rerun") else ""
            end_ts = support_banner.get("end") if support_banner else None

            support_lines = []
            for s in supports:
                s_name = s.get("name_en", "Unknown")
                s_url = s.get("url_name", "")
                if s_url:
                    support_lines.append(
                        f"[{s_name}]({GAMETORA_SUPPORT_URL.format(url_name=s_url)})"
                    )
                else:
                    support_lines.append(s_name)

            value = "  /  ".join(support_lines) + rerun_tag + _end_line(end_ts)
            gacha_embed.add_field(name="\U0001f0cf Support Banner", value=value, inline=False)

        if not chars and not supports:
            gacha_embed.description = "No active banners found."

        gacha_embed.set_footer(text="Source: GameTora (Global)")
        embeds.append(gacha_embed)

        # ---------------------------------------------------------------- #
        #  Events embed                                                     #
        # ---------------------------------------------------------------- #
        story_events = data["story_events"]
        champ = data["champions_meeting"]
        legend = data["legend_race"]
        limited_missions = data["limited_missions"]

        if story_events or champ or legend or limited_missions:
            events_embed = discord.Embed(
                title="Current Events  \U0001f3aa",
                colour=COLOUR_EVENTS,
                timestamp=discord.utils.utcnow(),
            )

            for event in story_events[:5]:
                name = (
                    event.get("storyEventEn")
                    or event.get("name_en")
                    or event.get("name")
                    or f"Story Event #{event.get('storyEventId', event.get('id', '?'))}"
                )
                end_ts = event.get("endDate") or event.get("end") or event.get("end_date")
                if end_ts and end_ts > 10 ** 11:
                    end_ts //= 1000
                value = f"Active{_end_line(end_ts)}"
                events_embed.add_field(name=f"\U0001f4d6 {name}", value=value, inline=False)

            for mission in limited_missions[:5]:
                name = (
                    mission.get("eventEn")
                    or mission.get("eventOriginal")
                    or f"Mission Event #{mission.get('eventId', '?')}"
                )
                end_ts = mission.get("endDate") or mission.get("end")
                if end_ts and end_ts > 10 ** 11:
                    end_ts //= 1000
                value = f"Active{_end_line(end_ts)}"
                events_embed.add_field(name=f"\U0001f4cb {name}", value=value, inline=False)

            if champ:
                name = champ.get("name") or f"Champions Meeting #{champ.get('id', '?')}"
                end_ts = champ.get("end") or champ.get("end_date")
                value = f"Active{_end_line(end_ts)}"
                events_embed.add_field(name=f"\U0001f3c6 {name}", value=value, inline=False)

            if legend:
                name = legend.get("name") or f"Legend Race #{legend.get('id', '?')}"
                end_ts = legend.get("end") or legend.get("end_date")
                value = f"Active{_end_line(end_ts)}"
                events_embed.add_field(name=f"\U0001f31f {name}", value=value, inline=False)

            events_embed.set_footer(text="Source: GameTora (Global)")
            embeds.append(events_embed)

        await interaction.followup.send(embeds=embeds)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCommands(bot))
