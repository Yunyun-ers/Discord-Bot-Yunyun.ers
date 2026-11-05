import os
from pathlib import Path

import discord
from discord.ext import commands, tasks

from cogs.setup import FeatureView, SetupView, embed


STATIONS = {
    "listen_jpop": ("LISTEN.moe — J-Pop", "https://listen.moe/stream"),
    "listen_kpop": ("LISTEN.moe — K-Pop", "https://listen.moe/kpop/stream"),
    "coolfahrenheit": ("COOLfahrenheit 93 — Thai Radio", "https://coolism-web.cdn.byteark.com/;stream/1"),
}
PLAY_EMOJI = discord.PartialEmoji(name="play", id=1474749326608699432)


class RadioStationSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select a radio station…",
            options=[discord.SelectOption(label=f"> {label}", value=key) for key, (label, _) in STATIONS.items()],
            row=0,
        )

    async def callback(self, interaction):
        panel = self.view
        panel.station = self.values[0]
        for option in self.options:
            option.default = option.value == panel.station
            if option.default:
                self.placeholder = option.label
        panel.start_button.disabled = False
        await interaction.response.edit_message(embed=panel.card(), view=panel)


class RadioStationView(SetupView):
    def __init__(self, cog, owner, guild_id, voice_channel_id):
        super().__init__(owner, guild_id)
        self.cog = cog
        self.voice_channel_id = voice_channel_id
        self.station = cog.bot.settings.get(guild_id, "radio.station")
        self.add_item(RadioStationSelect())
        self.start_button = StartRadioButton()
        self.start_button.disabled = self.station not in STATIONS
        self.add_item(self.start_button)
        self.add_item(BackToFeaturesButton())

    def card(self):
        channel = self.cog.bot.get_channel(self.voice_channel_id) if self.voice_channel_id else None
        room = channel.mention if channel else "-"
        selected = STATIONS.get(self.station, ("-", ""))[0]
        icon_url = self.cog.bot.user.display_avatar.url if self.cog.bot.user else None
        return embed(
            f"\n**Mode : Radio Stations**\n\n**Info :**\n╭ Voice channel :\n{room}\n╭ Radio Station :\n{selected}\n\n",
            icon_url=icon_url,
        )


class StartRadioButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, emoji=PLAY_EMOJI, row=1)

    async def callback(self, interaction):
        panel = self.view
        await panel.cog.start_radio(interaction, panel.voice_channel_id, panel.station)
        panel.stop()


class BackToFeaturesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=1)

    async def callback(self, interaction):
        panel = self.view
        view = FeatureView(panel.cog.bot, panel.owner, panel.guild_id)
        await interaction.response.edit_message(content=None, embed=view.card(), view=view)
        view.message = panel.message
        panel.stop()


class RadioCog(commands.Cog):
    setup_label = "Radio"

    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.empty_room_watcher.start()

    def cog_unload(self):
        self.empty_room_watcher.cancel()

    @tasks.loop(seconds=30)
    async def empty_room_watcher(self):
        for guild_id, voice in list(self.voice_clients.items()):
            if not voice.is_connected() or not voice.channel:
                self.voice_clients.pop(guild_id, None)
                continue
            humans = [member for member in voice.channel.members if not member.bot]
            if not humans:
                if voice.is_playing():
                    voice.stop()
                await voice.disconnect()
                self.voice_clients.pop(guild_id, None)

    @empty_room_watcher.before_loop
    async def before_empty_room_watcher(self):
        await self.bot.wait_until_ready()

    async def open_setup(self, interaction):
        voice_state = getattr(interaction.user, "voice", None)
        channel = voice_state.channel if voice_state else None
        if not isinstance(channel, discord.VoiceChannel):
            message = "Join a voice channel first, then run /radio or select Radio from /setup."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return
        view = RadioStationView(self, interaction.user.id, interaction.guild_id, channel.id)
        await interaction.response.edit_message(embed=view.card(), view=view)
        view.message = await interaction.original_response()

    @discord.app_commands.command(name="radio", description="Open the radio panel for your current voice channel")
    @discord.app_commands.guild_only()
    async def radio_command(self, interaction: discord.Interaction):
        voice_state = getattr(interaction.user, "voice", None)
        channel = voice_state.channel if voice_state else None
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Join a voice channel first, then run /radio.", ephemeral=True)
            return
        view = RadioStationView(self, interaction.user.id, interaction.guild_id, channel.id)
        await interaction.response.send_message(embed=view.card(), view=view, ephemeral=True)
        view.message = await interaction.original_response()

    async def start_radio(self, interaction, voice_channel_id, station_key):
        if station_key not in STATIONS:
            await interaction.response.send_message("Select a radio station first.", ephemeral=True)
            return
        channel = self.bot.get_channel(int(voice_channel_id))
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("The configured voice channel no longer exists.", ephemeral=True)
            return
        try:
            voice = self.voice_clients.get(interaction.guild_id)
            if voice and voice.is_connected() and voice.channel != channel:
                await voice.move_to(channel)
            elif not voice or not voice.is_connected():
                voice = await channel.connect()
            if voice.is_playing():
                voice.stop()
            station_label, stream_url = STATIONS[station_key]
            local_ffmpeg = Path(__file__).resolve().parents[1] / "ffmpeg.exe"
            ffmpeg = os.getenv("RADIO_FFMPEG_PATH", str(local_ffmpeg if local_ffmpeg.exists() else "ffmpeg"))
            source = discord.FFmpegPCMAudio(stream_url, executable=ffmpeg, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", options="-vn")
            voice.play(source)
            self.voice_clients[interaction.guild_id] = voice
            self.bot.settings.set(interaction.guild_id, "radio.station", station_key)
            await interaction.response.edit_message(content=f"{PLAY_EMOJI} **{station_label}** | **{channel.mention}**", embed=None, view=None)
        except (discord.ClientException, discord.HTTPException, FileNotFoundError, RuntimeError) as exc:
            await interaction.response.send_message(f"Could not start radio. Check FFmpeg and voice permissions. ({exc})", ephemeral=True)


async def setup(bot):
    await bot.add_cog(RadioCog(bot))
