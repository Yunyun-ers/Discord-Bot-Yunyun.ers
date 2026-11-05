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

## Bot Commands

Setup :
```/setup```