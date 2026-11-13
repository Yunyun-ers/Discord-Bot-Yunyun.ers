import sqlite3
from contextlib import contextmanager
from pathlib import Path


class SettingsStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS settings (guild_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(guild_id, key))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, guild_id, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE guild_id=? AND key=?", (guild_id, key)).fetchone()
        return row[0] if row else default

    def set(self, guild_id, key, value):
        with self.connect() as db:
            db.execute("INSERT INTO settings VALUES (?, ?, ?) ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value", (guild_id, key, value))

