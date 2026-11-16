import logging

import discord
import wavelink
from discord.ext import commands
from cogs.radio import DEFAULT_RADIO_VOLUME, STATIONS

logger = logging.getLogger(__name__)



class RadioSwitchView(discord.ui.View):
    def __init__(self, author_id, channel_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.channel_id = channel_id
        self.confirmed = False
        self.decided = False

    async def interaction_check(self, interaction):
        voice = getattr(interaction.user, 'voice', None)
        if interaction.user.id == self.author_id and voice and getattr(voice.channel, 'id', None) == self.channel_id:
            return True
        await interaction.response.send_message('ผู้เรียก !play ต้องอยู่ในห้องเสียงเดิมเพื่อใช้ปุ่มนี้', ephemeral=True)
        return False

    async def decide(self, interaction, confirmed):
        if self.decided:
            return await interaction.response.defer()
        self.decided = True
        self.confirmed = confirmed
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label='สลับไปเล่นเพลง', style=discord.ButtonStyle.primary)
    async def confirm(self, interaction, button):
        await self.decide(interaction, True)

    @discord.ui.button(label='ยกเลิก', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await self.decide(interaction, False)


class MusicCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    async def player_for(self, voice_channel):
        player = voice_channel.guild.voice_client
        if player and isinstance(player, wavelink.Player): return player
        return await voice_channel.connect(cls=wavelink.Player)

    @commands.command(name='play')
    @commands.guild_only()
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    async def play(self, ctx, *, query: str):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send('เข้าห้องเสียงก่อนใช้คำสั่งนี้')
        channel = ctx.author.voice.channel
        current = ctx.voice_client
        if current and current.channel != channel:
            return await ctx.send('กรุณาเข้าห้องเสียงเดียวกับบอท')
        radio = self.bot.get_cog('RadioCog')
        switching = current is not None and not isinstance(current, wavelink.Player)
        radio_station = self.bot.settings.get(ctx.guild.id, 'radio.station') if switching else None
        if switching:
            if not radio or radio.voice_clients.get(ctx.guild.id) is not current:
                return await ctx.send('บอทกำลังใช้ตัวเล่นเสียงอื่นอยู่')
            station_name = STATIONS.get(radio_station, ('Radio', ''))[0]
            view = RadioSwitchView(ctx.author.id, channel.id)
            prompt = await ctx.send(f'ตอนนี้กำลังเล่น {station_name} ต้องการสลับไปเล่นเพลงไหม?', view=view)
            timed_out = await view.wait()
            if not view.confirmed:
                await prompt.edit(content='หมดเวลายืนยัน' if timed_out else 'ยกเลิกการสลับแล้ว', view=None)
                return
            await prompt.edit(content='กำลังเตรียมเพลง…', view=None)

        query = query.strip().strip('<>')
        direct = query.startswith(('http://', 'https://'))
        sources = (None,) if direct else ('scsearch', 'dzsearch', 'ytsearch')
        failed = False
        try:
            for source in sources:
                try:
                    tracks = await wavelink.Playable.search(query, source=source)
                except wavelink.LavalinkLoadException:
                    logger.warning('Music lookup failed for source %s', source, exc_info=True)
                    failed = True
                    continue
                if tracks:
                    break
            else:
                message = 'แหล่งเพลงโหลดไม่สำเร็จ' if failed else 'ไม่พบเพลงที่ค้นหา'
                return await ctx.send(message)

            track = tracks[0]
            voice = ctx.author.voice
            if (
                not voice or voice.channel != channel
                or ctx.voice_client is not current
                or (current and current.channel != channel)
                or (switching and (
                    radio.voice_clients.get(ctx.guild.id) is not current
                    or self.bot.settings.get(ctx.guild.id, 'radio.station') != radio_station
                ))
            ):
                return await ctx.send('ห้องเสียงหรือตัวเล่นเปลี่ยนระหว่างเตรียมเพลง กรุณาลองใหม่')
            if switching:
                await current.disconnect()
                if radio.voice_clients.get(ctx.guild.id) is current:
                    radio.voice_clients.pop(ctx.guild.id)
            player = await self.player_for(channel)
            await player.play(track, volume=DEFAULT_RADIO_VOLUME)
        except wavelink.InvalidNodeException:
            return await ctx.send('Lavalink ยังไม่พร้อม กรุณาเปิด Lavalink แล้วลองใหม่')
        except (wavelink.LavalinkException, discord.DiscordException, TimeoutError):
            logger.exception('Music playback request failed')
            return await ctx.send('เริ่มเล่นเพลงไม่สำเร็จ กรุณาตรวจ log ของบอทและ Lavalink')
        await ctx.send(f'ส่งคำขอเล่น: **{track.title}**', allowed_mentions=discord.AllowedMentions.none())

    @play.error
    async def play_error(self, ctx, error):
        if isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send('มีคำขอเล่นเพลงกำลังดำเนินการอยู่ครับ')
        else:
            raise error

    @commands.command(name='pause')
    async def pause(self, ctx):
        player = ctx.voice_client
        if isinstance(player, wavelink.Player): await player.pause(True)

    @commands.command(name='resume')
    async def resume(self, ctx):
        player = ctx.voice_client
        if isinstance(player, wavelink.Player): await player.pause(False)

    @commands.command(name='stop')
    async def stop(self, ctx):
        player = ctx.voice_client
        if isinstance(player, wavelink.Player): await player.disconnect()


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
