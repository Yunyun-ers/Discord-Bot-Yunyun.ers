import os
from pathlib import Path

import discord
from discord import ui
from discord.ext import commands, tasks

from cogs.setup import FeatureView, SetupView, embed


STATIONS = {
    "listen_jpop": ("LISTEN.moe — J-Pop", "https://listen.moe/stream"),
    "listen_kpop": ("LISTEN.moe — K-Pop", "https://listen.moe/kpop/stream"),
    "coolfahrenheit": ("COOLfahrenheit 93 — Thai Radio", "https://coolism-web.cdn.byteark.com/;stream/1"),
}
PLAY_EMOJI = discord.PartialEmoji(name="play", id=1474749326608699432)
RADIO_BANNER_URL = "https://raw.githubusercontent.com/Yunyun-ers/Discord-Bot-Yunyun.ers/refs/heads/develop/assets/his.png"


class RadioStationSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select a radio station…",
            options=[discord.SelectOption(label=f"> {label}", value=key) for key, (label, _) in STATIONS.items()],
            row=0,
        )

    async def callback(self, interaction):
        panel = self.view
        panel.pending_station = self.values[0]
        for option in self.options:
            option.default = option.value == self.values[0]
            if option.default:
                self.placeholder = option.label
        panel.start_button.disabled = panel.pending_station not in STATIONS
        await interaction.response.edit_message(view=panel)


class RadioStationButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Station", style=discord.ButtonStyle.secondary, row=0)
    async def callback(self, interaction):
        await interaction.response.edit_message(content="Select a station, then press Select.", view=RadioStationEditorView(self.view))


class RadioStationEditorView(discord.ui.View):
    def __init__(self, panel):
        super().__init__(timeout=300); self.panel = panel; self.selected_station = panel.station
        self.add_item(RadioStationSelect()); self.add_item(RadioStationConfirmButton()); self.add_item(RadioStationBackButton())


class RadioStationConfirmButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Select", style=discord.ButtonStyle.success, row=1)
    async def callback(self, interaction):
        view = self.view; view.panel.station = view.selected_station
        view.panel.start_button.disabled = view.panel.station not in STATIONS
        await interaction.response.edit_message(content=None, embed=view.panel.card(), view=view.panel)


class RadioStationBackButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def callback(self, interaction): await interaction.response.edit_message(content=None, embed=self.view.panel.card(), view=self.view.panel)


class RadioStationView(SetupView):
    def __init__(self, cog, owner, guild_id, voice_channel_id):
        super().__init__(owner, guild_id)
        for item in list(self.children):
            if isinstance(item, discord.ui.Button) and item.label == "✕ Cancel":
                self.remove_item(item)
        self.cog = cog
        self.voice_channel_id = voice_channel_id
        self.station = cog.bot.settings.get(guild_id, "radio.station")
        self.pending_station = self.station
        self.volume = 3
        self.add_item(RadioStationSelect())
        self.start_button = StartRadioButton()
        self.start_button.disabled = self.station not in STATIONS
        self.add_item(self.start_button)
        self.add_item(RadioVolumeButton())
        self.add_item(RadioCancelButton())
        self.add_item(BackToFeaturesButton())

    def stop_session(self):
        self.cog.active_sessions.pop((self.guild_id, self.owner), None)
        self.stop()

    def card(self):
        channel = self.cog.bot.get_channel(self.voice_channel_id) if self.voice_channel_id else None
        room = channel.mention if channel else "-"
        selected = STATIONS.get(self.station, ("-", ""))[0]
        icon_url = self.cog.bot.user.display_avatar.url if self.cog.bot.user else None
        card = discord.Embed(
            title=": Radio Stations",
            description=(
                f"**Info :**    🔊 : `{self.volume}%`\n"
                "╭ Voice channel :\n"
                f"**{room}**\n"
                "╭ Radio Station :\n"
                f"**{selected}**"
            ),
            colour=0x5865F2,
        )
        if icon_url:
            card.set_author(name="ʏᴜɴʏᴜɴ ᴘ.", icon_url=icon_url)
        card.set_image(url=RADIO_BANNER_URL)
        return card


class StartRadioButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="▶", row=1)

    async def callback(self, interaction):
        panel = self.view
        current_voice = getattr(interaction.user, "voice", None)
        if current_voice and isinstance(current_voice.channel, discord.VoiceChannel):
            panel.voice_channel_id = current_voice.channel.id
        await panel.cog.start_radio(interaction, panel.voice_channel_id, panel.pending_station, panel)


class BackToFeaturesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction):
        panel = self.view
        view = FeatureView(panel.cog.bot, panel.owner, panel.guild_id)
        await interaction.response.edit_message(content=None, embed=view.card(), view=view)
        view.message = panel.message
        panel.stop_session()


class RadioCancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="✕ Cancel", style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction):
        await interaction.response.edit_message(content="ᴍᴇɴᴜ ᴄʟᴏsᴇᴅ.", embed=None, view=None)
        self.view.stop_session()


class RadioPlaybackView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None); self.cog, self.guild_id = cog, guild_id; self.add_item(RadioToggleButton(cog, guild_id))


class VolumeModal(discord.ui.Modal, title="Set Radio Volume"):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel

    volume = discord.ui.TextInput(label="Volume (1-100)", placeholder="3", min_length=1, max_length=3, required=True)
    async def on_submit(self, interaction):
        try: value = int(self.volume.value)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True); return
        if not 1 <= value <= 100:
            await interaction.response.send_message("Volume must be between 1 and 100.", ephemeral=True); return
        voice = interaction.client.get_cog("RadioCog").voice_clients.get(interaction.guild_id)
        if not voice or not voice.source or not hasattr(voice.source, "volume"):
            await interaction.response.send_message("Radio is not playing.", ephemeral=True); return
        voice.source.volume = value / 100
        self.panel.volume = value
        await interaction.response.edit_message(embed=self.panel.card(), view=self.panel)


class RadioVolumeButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Volume", style=discord.ButtonStyle.secondary, row=1)
    async def callback(self, interaction): await interaction.response.send_modal(VolumeModal(self.view))


class RadioToggleButton(discord.ui.Button):
    def __init__(self, cog, guild_id):
        super().__init__(label="⏸", style=discord.ButtonStyle.primary); self.cog, self.guild_id = cog, guild_id

    async def callback(self, interaction):
        voice = self.cog.voice_clients.get(self.guild_id)
        if not voice or not voice.is_connected():
            await interaction.response.send_message("Radio is not connected.", ephemeral=True); return
        if voice.is_playing():
            voice.pause(); self.label = "▶"
        elif voice.is_paused():
            voice.resume(); self.label = "⏸"
        await interaction.response.edit_message(view=self.view)


class RadioStopButton(discord.ui.Button):
    def __init__(self, cog, guild_id):
        super().__init__(label="ᴅɪsᴄᴏɴɴᴇᴄᴛ", style=discord.ButtonStyle.danger, row=1)
        self.cog, self.guild_id = cog, guild_id

    async def callback(self, interaction):
        voice = self.cog.voice_clients.pop(self.guild_id, None)
        if voice:
            voice.stop()
            await voice.disconnect()
        panel = self.view
        panel.start_button.disabled = False
        panel.start_button.label = "▶"
        self.disabled = True
        await interaction.response.edit_message(content=None, embed=panel.card(), view=panel)


class RadioCog(commands.Cog):
    setup_label = "Radio"

    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.active_sessions = {}
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
        self.active_sessions[(interaction.guild_id, interaction.user.id)] = view
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
        key = (interaction.guild_id, interaction.user.id)
        old = self.active_sessions.get(key)
        if old and old.is_finished():
            self.active_sessions.pop(key, None)
            old = None
        if old:
            await interaction.response.send_message("You already have an open Radio menu. Use that menu or cancel it first.", ephemeral=True)
            return
        self.active_sessions[key] = view
        await interaction.response.send_message(embed=view.card(), view=view, ephemeral=True)
        view.message = await interaction.original_response()

    async def start_radio(self, interaction, voice_channel_id, station_key, panel=None):
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
            # Send Opus directly from FFmpeg. This avoids the extra PCM -> Opus
            # encoding step in Python, which can result in a silent voice stream
            # on small/headless VPS instances even while FFmpeg is running.
            source = discord.FFmpegOpusAudio(
                stream_url,
                executable=ffmpeg,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn -ac 2 -ar 48000 -c:a libopus -b:a 128k",
            )
            voice.play(source)
            self.voice_clients[interaction.guild_id] = voice
            self.bot.settings.set(interaction.guild_id, "radio.station", station_key)
            if panel is not None:
                panel.station = station_key
                panel.pending_station = station_key
                panel.start_button.disabled = True
                panel.start_button.label = "▶"
                for item in list(panel.children):
                    if isinstance(item, RadioStopButton):
                        panel.remove_item(item)
                panel.add_item(RadioStopButton(self, interaction.guild_id))
                await interaction.response.edit_message(content=None, embed=panel.card(), view=panel)
            else:
                await interaction.response.edit_message(content=None, embed=None, view=RadioPlaybackView(self, interaction.guild_id))
        except (discord.ClientException, discord.HTTPException, FileNotFoundError, RuntimeError) as exc:
            await interaction.response.send_message(f"Could not start radio. Check FFmpeg and voice permissions. ({exc})", ephemeral=True)


async def setup(bot):
    await bot.add_cog(RadioCog(bot))
