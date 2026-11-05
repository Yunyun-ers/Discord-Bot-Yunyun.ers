import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv
from services.settings import SettingsStore

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
logger = logging.getLogger(__name__)


class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.settings = SettingsStore(BASE_DIR / "data" / "bot.db")

    async def setup_hook(self):
        for path in sorted((BASE_DIR / "cogs").glob("*.py")):
            if not path.name.startswith("_"):
                await self.load_extension(f"cogs.{path.stem}")
                logger.info("Loaded cog: %s", path.stem)

        synced = await self.tree.sync()
        logger.info("Synced %s application commands", len(synced))
        

    async def on_ready(self):
        await self.change_presence(status=discord.Status.idle,activity=discord.CustomActivity(name="もうー限界だよ\n╰（‵□′）╯"))
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        
        


def main():
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set DISCORD_BOT_TOKEN in .env before starting the bot.")
    DiscordBot().run(token)


if __name__ == "__main__":
    main()
