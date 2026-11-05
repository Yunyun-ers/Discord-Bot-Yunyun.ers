# Feature Cogs

Place one feature per Python file in this folder. main.py loads all .py files except names starting with _.
Each extension must expose an async setup function:

```python
from discord.ext import commands

class MyFeature(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

async def setup(bot):
    await bot.add_cog(MyFeature(bot))
```

No features are included yet. Prefix commands require enabling Message Content Intent in both code and Discord Developer Portal. Slash command features should configure command sync when added.
