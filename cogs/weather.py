import asyncio
import json
import logging
from urllib.parse import urlencode
from urllib.request import urlopen

import discord
from discord.ext import commands, tasks

from cogs.setup import FeatureView, SetupView, embed


log = logging.getLogger(__name__)

LOCATION_NAME = "กระทุ่มแบน"
LOCATION_LATITUDE = 13.6535
LOCATION_LONGITUDE = 100.2597
UPDATE_SECONDS = 3600


def weather_label(code):
    if code in (0, 1):
        return "☀️"
    if code in (2, 3):
        return "⛅"
    if code in (45, 48):
        return "🌫️"
    if code in (51, 53, 55, 56, 57):
        return "🌦️"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "🌧️"
    if code in (95, 96, 99):
        return "⛈️"
    return "🌤️"


def fetch_weather():
    query = urlencode(
        {
            "latitude": LOCATION_LATITUDE,
            "longitude": LOCATION_LONGITUDE,
            "daily": "weather_code,temperature_2m_max,precipitation_probability_max",
            "timezone": "Asia/Bangkok",
            "forecast_days": 1,
        }
    )
    with urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def format_topic(data):
    daily = data["daily"]
    code = int(daily["weather_code"][0])
    temperature = round(float(daily["temperature_2m_max"][0]))
    rain_chance = int(daily["precipitation_probability_max"][0] or 0)
    return f"{weather_label(code)} {LOCATION_NAME} {temperature}°C | ฝน {rain_chance}%"


class WeatherChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Select a text channel…",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction):
        self.view.channel_id = self.values[0].id
        await interaction.response.edit_message(embed=self.view.card(), view=self.view)


class WeatherSaveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Save", style=discord.ButtonStyle.success, row=1)

    async def callback(self, interaction):
        panel = self.view
        if not panel.channel_id:
            await interaction.response.send_message("Select a text channel first.", ephemeral=True)
            return
        panel.cog.bot.settings.set(panel.guild_id, "weather.channel_id", str(panel.channel_id))
        await panel.cog.update_guild(panel.guild_id)
        await interaction.response.edit_message(content="Weather settings saved.", embed=panel.card(), view=panel)


class WeatherBackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=1)

    async def callback(self, interaction):
        panel = self.view
        view = FeatureView(panel.cog.bot, panel.owner, panel.guild_id)
        await interaction.response.edit_message(content=None, embed=view.card(), view=view)
        panel.stop()


class WeatherPanel(SetupView):
    def __init__(self, cog, owner, guild_id):
        super().__init__(owner, guild_id)
        self.cog = cog
        self.channel_id = cog.bot.settings.get(guild_id, "weather.channel_id", "")
        self.add_item(WeatherChannelSelect())
        self.add_item(WeatherSaveButton())
        self.add_item(WeatherBackButton())

    def card(self):
        channel = self.cog.bot.get_channel(int(self.channel_id)) if self.channel_id else None
        channel_text = channel.mention if channel else "Not selected"
        icon_url = self.cog.bot.user.display_avatar.url if self.cog.bot.user else None
        return embed(
            f"**Location :** {LOCATION_NAME}\n**Update :** Every 1 hour\n**Channel :** {channel_text}",
            ("Weather", "Short daily forecast in the channel topic."),
            icon_url=icon_url,
        )


class WeatherCog(commands.Cog):
    setup_label = "Weather"

    def __init__(self, bot):
        self.bot = bot
        self.update_weather.start()

    def cog_unload(self):
        self.update_weather.cancel()

    async def open_setup(self, interaction):
        view = WeatherPanel(self, interaction.user.id, interaction.guild_id)
        await interaction.response.edit_message(content=None, embed=view.card(), view=view)
        view.message = await interaction.original_response()

    async def update_guild(self, guild_id):
        channel_id = self.bot.settings.get(guild_id, "weather.channel_id", "")
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            topic = format_topic(await asyncio.to_thread(fetch_weather))
            if channel.topic != topic:
                await channel.edit(topic=topic, reason="Update daily weather topic")
        except (OSError, ValueError, KeyError, discord.HTTPException):
            log.exception("Weather update failed for guild %s", guild_id)

    @tasks.loop(seconds=UPDATE_SECONDS)
    async def update_weather(self):
        for guild in self.bot.guilds:
            await self.update_guild(guild.id)

    @update_weather.before_loop
    async def before_update_weather(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self.update_guild(guild.id)


async def setup(bot):
    await bot.add_cog(WeatherCog(bot))
