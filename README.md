# Discord Bot
<p align = "center">
<img src="assets/Discord_Bot.png" width="300">
Discord Bot สำหรับใช้งานใน Server VoiceChat ทั่วไป
</p>

# Function

- Radio (API)
    - COOLfahrenheit (Thai Radio Station)
    - Listen.moe (J,K-pop Radio Station)


## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

ตั้งคต่า `DISCORD_BOT_TOKEN` จาก DDP ลงใน .env และเริ่ม Run Bot :

```powershell
.\.venv\Scripts\python.exe main.py
```

เพิ่ม Function, Feature ของตนเองได้ที่ cogs/. 

## Requirements
ลง Plugin `ffmpeg.exe` ที่ Folder เดียวกันกับ main.py
## Bot Commands

Setup Bot :
```/setup```