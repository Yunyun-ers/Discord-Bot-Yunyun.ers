import logging
import os
from pathlib import Path

import discord
from discord import ui
from discord.ext import commands, tasks

DEFAULT_RADIO_VOLUME = 5
STATION_ICON = "<:boombox:1571635076607901777>"
REQUESTER_ICON = "<:circleuserround:1571635080278052894>"
VOICE_ICON = "<:messagescircle:1571635093305430036>"
logger = logging.getLogger(__name__)


class RadioPCMSource(discord.PCMVolumeTransformer):
    def __init__(self, source):
        super().__init__(source, volume=DEFAULT_RADIO_VOLUME / 100)
        self.frames_read = 0
        self.signal_frames = 0

    def read(self):
        frame = super().read()
        if frame:
            self.frames_read += 1
            has_signal = any(frame)
            if self.frames_read == 1:
                logger.info("Radio first PCM frame: %d bytes, nonzero=%s", len(frame), has_signal)
            if has_signal:
                self.signal_frames += 1
                if self.signal_frames == 1:
                    logger.info("Radio first nonzero PCM frame: #%d (%d bytes)", self.frames_read, len(frame))
        return frame

    def finished(self, error):
        if error:
            logger.error("Radio playback failed after %d PCM frames (%d nonzero, %s)", self.frames_read, self.signal_frames, type(error).__name__, exc_info=error)
        else:
            logger.info("Radio player ended after %d PCM frames (%d nonzero)", self.frames_read, self.signal_frames)

STATIONS = {
    "listen_jpop": ("LISTEN.moe — J-Pop", "https://listen.moe/stream"),
    "listen_kpop": ("LISTEN.moe — K-Pop", "https://listen.moe/kpop/stream"),
    "coolfahrenheit": ("COOLfahrenheit 93 — Thai Radio", "https://coolism-web.cdn.byteark.com/;stream/1"),
}
PLAY_EMOJI = discord.PartialEmoji(name="play", id=1474749326608699432)
RADIO_AVATAR_URL = "https://raw.githubusercontent.com/Yunyun-ers/Discord-Bot-Yunyun.ers/refs/heads/docker_version/assets/Avatar.png"
RADIO_PLAYBACK_IMAGE_URL = "https://raw.githubusercontent.com/Yunyun-ers/Discord-Bot-Yunyun.ers/refs/heads/docker_version/assets/FaceWriteing.png"




class RadioStationView(ui.LayoutView):
    def __init__(self, cog, owner, guild_id, voice_channel_id, *, playback=None):
        super().__init__(timeout=300)
        self.cog, self.owner, self.guild_id = cog, owner, guild_id
        self.playback = playback
        self.voice = cog.voice_clients.get(guild_id)
        self.voice_channel_id = voice_channel_id
        self.message = None
        self.pending_station = cog.bot.settings.get(guild_id, "radio.station")

        self.title = ui.TextDisplay(self.summary())
        self.select = ui.Select(
            placeholder="เลือกสถานีวิทยุ",
            options=[
                discord.SelectOption(label=label, value=key, default=key == self.pending_station)
                for key, (label, _) in STATIONS.items()
            ],
        )
        self.start_button = ui.Button(
            label="เล่น", emoji=PLAY_EMOJI, style=discord.ButtonStyle.primary,
            disabled=self.pending_station not in STATIONS,
        )
        self.cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        self.select.callback = self.select_station
        self.start_button.callback = self.play
        self.cancel_button.callback = self.cancel
        controls = ui.ActionRow(self.start_button, self.cancel_button)
        self.disconnect_button = None
        if self.voice and self.voice.is_connected():
            self.disconnect_button = ui.Button(label="ᴅɪsᴄᴏɴɴᴇᴄᴛ", style=discord.ButtonStyle.danger)
            self.disconnect_button.callback = self.disconnect
            controls.add_item(self.disconnect_button)
        self.add_item(ui.Container(
            ui.Section(self.title, accessory=ui.Thumbnail(RADIO_AVATAR_URL)),
            ui.ActionRow(self.select),
            controls,
            accent_colour=0xFFA3A8,
        ))

    def summary(self):
        station = STATIONS.get(self.pending_station, ("ยังไม่ได้เลือกสถานี", ""))[0]
        requester = self.cog.requesters.get(self.guild_id, self.owner)
        return (
            f"### Radio Station\n{STATION_ICON} : **{station}**"
            f"\n\n{REQUESTER_ICON} : <@{requester}>\n\n{VOICE_ICON} : <#{self.voice_channel_id}>"
        )

    async def interaction_check(self, interaction):
        if self.cog.active_sessions.get((self.guild_id, self.owner)) is not self:
            await interaction.response.send_message("เมนูนี้หมดอายุแล้วครับ", ephemeral=True)
            return False
        return await self.cog.check_voice_room(interaction, self.voice_channel_id)

    async def disconnect(self, interaction):
        if self.cog.voice_clients.get(self.guild_id) is not self.voice:
            return await interaction.response.send_message("Radio ในเมนูนี้หยุดแล้วครับ", ephemeral=True)
        await self.cog.stop_radio(interaction, self.voice)
        self.stop_session()

    def stop_session(self):
        key = (self.guild_id, self.owner)
        if self.cog.active_sessions.get(key) is self:
            self.cog.active_sessions.pop(key)
        self.stop()

    async def on_timeout(self):
        self.stop_session()
        for control in (self.select, self.start_button, self.cancel_button, self.disconnect_button):
            if control:
                control.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def select_station(self, interaction):
        self.pending_station = self.select.values[0]
        for option in self.select.options:
            option.default = option.value == self.pending_station
        self.title.content = self.summary()
        self.start_button.disabled = False
        await interaction.response.edit_message(view=self)

    async def play(self, interaction):
        state = getattr(interaction.user, "voice", None)
        if not state or not isinstance(state.channel, discord.VoiceChannel):
            return await interaction.response.send_message("เข้าห้องเสียงก่อนเล่น Radio ครับ", ephemeral=True)
        self.voice_channel_id = state.channel.id
        await self.cog.start_radio(interaction, self.voice_channel_id, self.pending_station, self)

    async def close(self, interaction):
        closed = ui.LayoutView()
        closed.add_item(ui.TextDisplay("ปิดเมนู Radio แล้ว"))
        await interaction.response.edit_message(view=closed)
        self.stop_session()

    async def cancel(self, interaction):
        playback = self.playback
        if (
            playback and not playback.is_finished()
            and self.cog.voice_clients.get(self.guild_id) is playback.voice
            and playback.voice.is_connected() and playback.voice.source is playback.source
        ):
            await interaction.response.edit_message(view=playback)
            self.stop_session()
            return
        await self.close(interaction)

class RadioPlaybackView(ui.LayoutView):
    def __init__(self, cog, guild_id, station_label, voice, source, requester_id):
        super().__init__(timeout=900)
        self.cog = cog
        self.guild_id = guild_id
        self.station_label = station_label
        self.voice = voice
        self.source = source
        self.status = ui.TextDisplay("▶ กำลังเล่น")
        heading = ui.TextDisplay(
            f"### Currently Playing\n{STATION_ICON} : **{station_label}**"
            f"\n\n{REQUESTER_ICON} : <@{requester_id}>\n\n{VOICE_ICON} : {voice.channel.mention}"
        )
        self.pause_button = ui.Button(label="พัก", style=discord.ButtonStyle.secondary)
        self.station_button = ui.Button(label="เปลี่ยนสถานี", style=discord.ButtonStyle.secondary)
        self.stop_button = ui.Button(label="หยุด", style=discord.ButtonStyle.danger)
        self.pause_button.callback = self.toggle
        self.station_button.callback = self.change_station
        self.stop_button.callback = self.disconnect
        controls = ui.ActionRow(self.pause_button, self.station_button, self.stop_button)
        self.add_item(ui.Container(
            ui.Section(heading, accessory=ui.Thumbnail(RADIO_PLAYBACK_IMAGE_URL)),
            ui.Separator(),
            self.status,
            controls,
            accent_colour=0xFFA3A8,
        ))

    async def interaction_check(self, interaction):
        if not await self.cog.check_voice_room(interaction, getattr(self.voice.channel, "id", None)):
            return False
        if (
            self.cog.voice_clients.get(self.guild_id) is self.voice
            and self.voice.is_connected()
            and self.voice.source is self.source
        ):
            return True
        await interaction.response.send_message(
            "ต้องอยู่ในห้องเดียวกับ Radio และใช้การ์ดของสถานีที่กำลังเล่นครับ", ephemeral=True
        )
        return False

    async def toggle(self, interaction):
        if self.voice.is_paused():
            self.voice.resume()
            self.pause_button.label = "พัก"
            self.status.content = "▶ กำลังเล่น"
        elif self.voice.is_playing():
            self.voice.pause()
            self.pause_button.label = "เล่นต่อ"
            self.status.content = "⏸ พักอยู่"
        await interaction.response.edit_message(view=self)

    async def change_station(self, interaction):
        await self.cog.show_radio_menu(interaction, playback=self)

    async def disconnect(self, interaction):
        await self.cog.stop_radio(interaction, self.voice)
        self.stop()


class RadioCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.active_sessions = {}
        self.requesters = {}
        self.playback_messages = {}
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

    async def check_voice_room(self, interaction, channel_id):
        state = getattr(interaction.user, "voice", None)
        voice = interaction.guild.voice_client
        target = getattr(getattr(voice, "channel", None), "id", channel_id)
        if target is not None and state and getattr(state.channel, "id", None) == target:
            return True
        await interaction.response.send_message("เข้าห้องเสียงเดียวกับบอทก่อนครับ", ephemeral=True)
        return False

    async def stop_radio(self, interaction, voice):
        await interaction.response.defer()
        guild_id = interaction.guild_id
        await voice.disconnect()
        if self.voice_clients.get(guild_id) is voice:
            self.voice_clients.pop(guild_id)
            self.requesters.pop(guild_id, None)
        previous = self.playback_messages.pop(guild_id, None)
        for message in {m for m in (previous, interaction.message) if m is not None}:
            try:
                await message.delete()
            except discord.NotFound:
                pass

    @discord.app_commands.command(name="radio", description="Open the radio panel for your current voice channel")
    @discord.app_commands.guild_only()
    async def radio_command(self, interaction: discord.Interaction):
        await self.show_radio_menu(interaction)

    async def show_radio_menu(self, interaction: discord.Interaction, *, playback=None):
        voice_state = getattr(interaction.user, "voice", None)
        channel = voice_state.channel if voice_state else None
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Join a voice channel first, then run /radio.", ephemeral=True)
            return
        if not await self.check_voice_room(interaction, channel.id):
            return
        view = RadioStationView(self, interaction.user.id, interaction.guild_id, channel.id, playback=playback)
        key = (interaction.guild_id, interaction.user.id)
        old = self.active_sessions.get(key)
        self.active_sessions[key] = view
        try:
            if playback is None:
                await interaction.response.send_message(view=view, allowed_mentions=discord.AllowedMentions.none())
            else:
                await interaction.response.edit_message(view=view)
        except discord.HTTPException:
            if self.active_sessions.get(key) is view:
                if old and not old.is_finished():
                    self.active_sessions[key] = old
                else:
                    self.active_sessions.pop(key)
            raise
        if old:
            old.stop()
        view.message = await interaction.original_response()

    async def start_radio(self, interaction, voice_channel_id, station_key, panel=None):
        if station_key not in STATIONS:
            await interaction.response.send_message("Select a radio station first.", ephemeral=True)
            return
        channel = self.bot.get_channel(int(voice_channel_id))
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("The configured voice channel no longer exists.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            station_label, stream_url = STATIONS[station_key]
            voice = self.voice_clients.get(interaction.guild_id)
            current = interaction.guild.voice_client
            if current and (current is not voice or current.channel != channel):
                await interaction.followup.send("เข้าห้องเสียงเดียวกับ Radio หรือหยุด Music ก่อนครับ", ephemeral=True)
                return
            if not voice or not voice.is_connected():
                voice = await channel.connect()
            if voice.is_playing() or voice.is_paused():
                voice.stop()
            local_ffmpeg = Path(__file__).resolve().parents[1] / "ffmpeg.exe"
            ffmpeg = os.getenv("RADIO_FFMPEG_PATH", str(local_ffmpeg if local_ffmpeg.exists() else "ffmpeg"))
            raw_source = discord.FFmpegPCMAudio(
                stream_url,
                executable=ffmpeg,
                before_options="-re -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
            )
            source = RadioPCMSource(raw_source)
            try:
                voice.play(source, after=source.finished)
            except Exception:
                source.cleanup()
                raise
            self.voice_clients[interaction.guild_id] = voice
            self.bot.settings.set(interaction.guild_id, "radio.station", station_key)
            self.requesters[interaction.guild_id] = interaction.user.id
            message = await interaction.edit_original_response(
                content=None,
                embed=None,
                view=RadioPlaybackView(self, interaction.guild_id, station_label, voice, source, interaction.user.id),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            previous = self.playback_messages.get(interaction.guild_id)
            self.playback_messages[interaction.guild_id] = message
            if previous and previous.id != message.id:
                try:
                    await previous.delete()
                except discord.NotFound:
                    pass
            if panel is not None:
                panel.stop_session()
        except (discord.ClientException, discord.HTTPException, FileNotFoundError, RuntimeError) as exc:
            await interaction.followup.send(f"Could not start radio. ({exc})", ephemeral=True)


async def setup(bot):
    await bot.add_cog(RadioCog(bot))
