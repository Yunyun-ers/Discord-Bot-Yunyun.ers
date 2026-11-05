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

## Requirements
ลง Plugin `ffmpeg.exe` ที่ Folder เดียวกันกับ main.py
## Bot Commands

Setup Bot :
```/setup```