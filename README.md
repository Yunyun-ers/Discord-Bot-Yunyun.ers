# Discord bot

A fresh discord.py project. No old code, features, or credentials are included.

## Setup (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set DISCORD_BOT_TOKEN in .env, then run:

```powershell
.\.venv\Scripts\python.exe main.py
```

Add feature extensions under cogs/. See cogs/README.md for the template.

## Radio dependencies

The Python environment is local to this folder (`.venv`). Install voice support from this folder with:

```powershell
.\.venv\Scripts\python.exe -m pip install PyNaCl
```

You can place `ffmpeg.exe` directly beside `main.py`. Radio checks this local file first, so you do not need to add FFmpeg to the system PATH. Alternatively set `RADIO_FFMPEG_PATH` in `.env` to a local or absolute executable path.

## /setup

Invite the bot with bot and applications.commands scopes. Start it, then use /setup in each server with Manage Server permission. The command is synced globally on startup; allow time for Discord to display it. The private Setup panel includes feature selection, General > Language, Save, Back, Cancel, and a five-minute timeout. Settings are stored in data/bot.db by guild ID. Only Setup language is configured today; no old features are included.

### Add a feature to Setup

A loaded Cog can expose setup_label, optional setup_description, and async open_setup(interaction). It will appear in the feature dropdown (up to 24 feature Cogs). The method must respond to the interaction and own its View timeout and permissions. Save settings using bot.settings.get(interaction.guild_id, key, default) and bot.settings.set(interaction.guild_id, key, value), with namespaced keys such as music.channel_id. Use cogs.setup.SetupView for owner/guild/Manage Server checks and timeout handling.
