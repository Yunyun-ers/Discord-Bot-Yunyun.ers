"""Lightweight Valorant player analysis using HenrikDev API.

The API key is read from HENRIKDEV_API_KEY. Results are cached briefly and
requests are throttled so a Basic key (30 requests/minute) is not exhausted.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from io import BytesIO
from urllib.parse import quote
from uuid import UUID

import aiohttp
import discord
from discord.ext import commands


BASE_URL = "https://api.henrikdev.xyz/valorant"
CACHE_SECONDS = 120
MAX_REQUESTS = 28  # leave a small safety margin under the 30/min limit


class HenrikClient:
    def __init__(self):
        self.key = os.getenv("HENRIKDEV_API_KEY", "").strip()
        self.cache: dict[str, tuple[float, object]] = {}
        self.calls: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def get(self, path: str):
        if not self.key:
            raise RuntimeError("HENRIKDEV_API_KEY is not configured.")
        now = time.monotonic()
        cached = self.cache.get(path)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
        async with self.lock:
            now = time.monotonic()
            while self.calls and now - self.calls[0] >= 60:
                self.calls.popleft()
            if len(self.calls) >= MAX_REQUESTS:
                wait = 60 - (now - self.calls[0])
                raise RuntimeError(f"API rate limit reached. Try again in {max(1, int(wait))}s.")
            self.calls.append(now)
            headers = {"Authorization": self.key}
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(BASE_URL + path, headers=headers) as response:
                    payload = await response.json(content_type=None)
                    if response.status == 429:
                        raise RuntimeError("HenrikDev rate limit reached. Please try again later.")
                    if response.status >= 400:
                        message = payload.get("errors", payload) if isinstance(payload, dict) else payload
                        raise RuntimeError(f"API error ({response.status}): {message}")
                    self.cache[path] = (time.monotonic(), payload)
                    return payload


def _find_player(match: dict, name: str, tag: str):
    target = f"{name}#{tag}".casefold()
    for player in match.get("players", []) or []:
        game_name = player.get("name") or player.get("game_name") or ""
        game_tag = player.get("tag") or player.get("tag_line") or ""
        if f"{game_name}#{game_tag}".casefold() == target:
            return player
        if player.get("riot_id") and str(player["riot_id"]).casefold() == target:
            return player
    return None


def asset_icon(collection, asset_id, filename):
    if not isinstance(asset_id, str):
        return None
    try:
        asset_id = UUID(asset_id)
    except ValueError:
        return None
    return f"https://media.valorant-api.com/{collection}/{asset_id}/{filename}.png"


def analyse(matches: list[dict], name: str, tag: str):
    games = kills = deaths = headshots = bodyshots = legshots = 0
    agents = []
    card_id = None
    wins = 0
    for match in matches:
        player = _find_player(match, name, tag)
        if not player:
            continue
        stats = player.get("stats") or {}
        shots = stats.get("shots") or stats
        if not games:
            card_id = (player.get("customization") or {}).get("card") or player.get("player_card")
        games += 1
        kills += int(stats.get("kills", 0) or 0)
        deaths += int(stats.get("deaths", 0) or 0)
        headshots += int(shots.get("head", shots.get("headshots", 0)) or 0)
        bodyshots += int(shots.get("body", shots.get("bodyshots", 0)) or 0)
        legshots += int(shots.get("leg", shots.get("legshots", 0)) or 0)
        agent = player.get("agent") or player.get("character") or {}
        if not isinstance(agent, dict):
            agent = {"name": str(agent)}
        agents.append((agent.get("name") or "Unknown", agent.get("id")))
        team = player.get("team_id") or player.get("team")
        teams = match.get("teams") or {}
        if isinstance(teams, list) and any(
            entry.get("team_id") == team and entry.get("won") for entry in teams
        ):
            wins += 1
        elif isinstance(teams, dict) and (teams.get(team) or {}).get("won"):
            wins += 1
    total_shots = headshots + bodyshots + legshots
    return {
        "games": games, "wins": wins,
        "hs": (headshots / total_shots * 100) if total_shots else None,
        "kd": (kills / deaths) if deaths else float(kills),
        "agents": agents, "card_id": card_id,
    }


async def agent_strip(agents):
    from PIL import Image, ImageDraw

    urls = [asset_icon("agents", agent_id, "displayicon") for _, agent_id in agents]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        async def download(url):
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    return await response.read()
            except (aiohttp.ClientError, TimeoutError):
                return None

        unique_urls = list(dict.fromkeys(url for url in urls if url))
        icons = dict(zip(unique_urls, await asyncio.gather(*(download(url) for url in unique_urls))))

    strip = Image.new("RGBA", (72 * len(urls) - 8, 64))
    draw = ImageDraw.Draw(strip)
    for index, url in enumerate(urls):
        x = index * 72
        draw.rounded_rectangle((x, 0, x + 63, 63), radius=8, fill="#242631")
        if icons.get(url):
            try:
                with Image.open(BytesIO(icons[url])) as image:
                    icon = image.convert("RGBA")
                    icon.thumbnail((56, 56), Image.Resampling.LANCZOS)
                    strip.alpha_composite(icon, (x + (64 - icon.width) // 2, (64 - icon.height) // 2))
                continue
            except OSError:
                pass
        draw.text((x + 32, 32), "?", anchor="mm", fill="white")
    output = BytesIO()
    strip.save(output, format="PNG")
    output.seek(0)
    return output


class ValorantProfileModal(discord.ui.Modal, title="Valorant Profile"):
    riot_id = discord.ui.TextInput(label="Riot ID", placeholder="Name#Tag", max_length=64)

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self.cog.show_profile(interaction.followup.send, self.riot_id.value)


class ValorantProfileView(discord.ui.View):
    def __init__(self, cog, owner_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("Run `!valoyun` to open your own form.", ephemeral=True)
        return False

    @discord.ui.button(label="Enter Riot ID", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ValorantProfileModal(self.cog))


class Valorant(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = HenrikClient()
        self.rank_icons = {}
        self.rank_icons_until = 0

    async def rank_icon(self, tier_id):
        if tier_id is None:
            return None
        if time.monotonic() >= self.rank_icons_until:
            timeout = aiohttp.ClientTimeout(total=4)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get("https://valorant-api.com/v1/competitivetiers") as response:
                        response.raise_for_status()
                        payload = await response.json()
                self.rank_icons = {
                    tier["tier"]: tier["largeIcon"]
                    for tier_set in payload["data"]
                    for tier in tier_set["tiers"]
                    if tier.get("largeIcon")
                }
                self.rank_icons_until = time.monotonic() + 86400
            except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError):
                self.rank_icons_until = time.monotonic() + 60
        return self.rank_icons.get(tier_id)

    @commands.command(name="valoyun")
    async def valorant(self, ctx: commands.Context, *, riot_id: str = ""):
        if not riot_id.strip():
            await ctx.send(view=ValorantProfileView(self, ctx.author.id))
            return
        await self.show_profile(ctx.send, riot_id)

    async def show_profile(self, send, riot_id):
        name, separator, tag = riot_id.strip().partition("#")
        name, tag = name.strip(), tag.strip()
        if not separator or not name or not tag or "#" in tag or any(c.isspace() for c in tag):
            await send("Enter a Riot ID in the format `Name#Tag`.")
            return
        region, matches = "ap", 5
        try:
            player_path = f"{region}/pc/{quote(name, safe='')}/{quote(tag, safe='')}"
            mmr = await self.api.get(f"/v3/mmr/{player_path}")
            history = await self.api.get(f"/v4/matches/{player_path}?size={matches}")
            data = history.get("data", []) if isinstance(history, dict) else []
            stats = analyse(data, name, tag)
            mmr_data = mmr.get("data") or {}
            current_tier = (mmr_data.get("current") or {}).get("tier") or {}
            peak_tier = (mmr_data.get("peak") or {}).get("tier") or {}
            rank_icon = await self.rank_icon(current_tier.get("id"))
            banner = asset_icon("playercards", stats["card_id"], "wideart")
            embed = discord.Embed(title=f"{name}#{tag}", color=discord.Color.blurple())
            embed.set_author(name=f"VALORANT • {region.upper()}")
            if rank_icon:
                embed.set_thumbnail(url=rank_icon)
            if banner:
                embed.set_image(url=banner)
            embed.add_field(name="Rank", value=current_tier.get("name") or "—", inline=True)
            embed.add_field(name="Peak Rank", value=peak_tier.get("name") or "—", inline=True)
            embed.add_field(name="Matches", value=f"{stats['games']} ({stats['wins']} wins)", inline=True)
            embed.add_field(name="K/D", value=f"{stats['kd']:.2f}", inline=True)
            hs = stats["hs"]
            embed.add_field(name="HS%", value=f"{hs:.1f}%" if hs is not None else "—", inline=True)
        except Exception as exc:
            await send(f"Could not fetch Valorant data: {exc}", allowed_mentions=discord.AllowedMentions.none())
            return
        agents = stats["agents"]
        if not agents:
            await send(embed=embed)
            return
        names = " → ".join(name for name, _ in agents)
        recent = discord.Embed(title="Recent Agents · Newest to Oldest", description=names, color=embed.color)
        try:
            strip = await agent_strip(agents)
        except (ImportError, OSError):
            await send(embeds=[embed, recent])
            return
        recent.set_image(url="attachment://recent-agents.png")
        with strip:
            file = discord.File(strip, filename="recent-agents.png", description=names[:1024])
            try:
                await send(embeds=[embed, recent], file=file)
            finally:
                file.close()


async def setup(bot):
    await bot.add_cog(Valorant(bot))
