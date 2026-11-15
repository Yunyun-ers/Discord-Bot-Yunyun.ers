import asyncio
import logging
from urllib.parse import parse_qs, urlencode, urlsplit

import discord
import wavelink
import yt_dlp
from discord.ext import commands
from cogs.radio import youtube_media_info

logger = logging.getLogger(__name__)

YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'}


def is_youtube_url(url):
    return urlsplit(url).hostname in YOUTUBE_HOSTS


def single_video_url(url):
    parsed = urlsplit(url)
    video_id = parsed.path.strip('/') if parsed.hostname == 'youtu.be' else parse_qs(parsed.query).get('v', [''])[0]
    if video_id:
        return 'https://www.youtube.com/watch?' + urlencode({'v': video_id})
    return url


class MusicCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    async def player_for(self, voice_channel):
        player = voice_channel.guild.voice_client
        if player and isinstance(player, wavelink.Player): return player
        return await voice_channel.connect(cls=wavelink.Player)

    @commands.command(name='play')
    async def play(self, ctx, *, query: str):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send('เข้าห้องเสียงก่อนใช้คำสั่งนี้')
        channel = ctx.author.voice.channel
        current = ctx.voice_client
        if current and not isinstance(current, wavelink.Player):
            return await ctx.send('กรุณาหยุด Radio ก่อนเล่นเพลง')
        if current and current.channel != channel:
            return await ctx.send('กรุณาเข้าห้องเสียงเดียวกับบอท')

        query = query.strip().strip('<>')
        direct = query.startswith(('http://', 'https://'))
        title = None
        failed = False
        try:
            if not direct:
                sources = ('ytsearch', 'ytmsearch', 'scsearch')
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
                    message = 'แหล่งเพลงโหลดไม่สำเร็จ ลองลิงก์จากแหล่งอื่น' if failed else 'ไม่พบเพลงที่ค้นหา'
                    return await ctx.send(message)
                track = tracks[0]
                query = track.uri or ''
                title = track.title

            if is_youtube_url(query):
                info = await asyncio.to_thread(youtube_media_info, single_video_url(query))
                if not info or not info.get('url'):
                    return await ctx.send('yt-dlp ไม่พบลิงก์เสียงของวิดีโอนี้')
                tracks = await wavelink.Playable.search(info['url'], source=None)
                if not tracks:
                    return await ctx.send('Lavalink โหลดลิงก์เสียงจาก YouTube ไม่ได้')
                track = tracks[0]
                title = info.get('title') or title
            elif direct:
                tracks = await wavelink.Playable.search(query, source=None)
                if not tracks:
                    return await ctx.send('ไม่พบเสียงจากลิงก์นี้')
                track = tracks[0]
            player = await self.player_for(channel)
            await player.play(track)
        except yt_dlp.utils.DownloadError:
            return await ctx.send('yt-dlp โหลดเสียง YouTube ไม่สำเร็จ กรุณาตรวจ PO provider ที่ใช้กับ Radio')
        except wavelink.InvalidNodeException:
            return await ctx.send('Lavalink ยังไม่พร้อม กรุณาเปิด Lavalink แล้วลองใหม่')
        except (wavelink.LavalinkException, discord.DiscordException, TimeoutError):
            logger.exception('Music playback request failed')
            return await ctx.send('เริ่มเล่นเพลงไม่สำเร็จ กรุณาตรวจ log ของบอทและ Lavalink')
        await ctx.send(f'ส่งคำขอเล่น: **{title or track.title}**', allowed_mentions=discord.AllowedMentions.none())

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
