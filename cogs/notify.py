import discord
from discord import app_commands
from discord.ext import commands

from .setup import SetupView, embed


DEFAULTS = {
    "enabled": False,
    "channel_id": "",
    "title": "Welcome to {server}!",
    "description": "Hello {user}, welcome to the server.",
    "author": "",
    "author_icon": "",
    "footer": "",
    "image": "",
    "thumbnail": "",
    "colour": "8B5CF6",
}


def render(text, member):
    return (text or "").replace("{user}", member.mention).replace("{username}", member.name).replace("{user_tag}", str(member)).replace("{user_avatar}", member.display_avatar.url).replace(
        "{server}", member.guild.name
    ).replace("{member_count}", str(member.guild.member_count or 0)).replace("{server_id}", str(member.guild.id))


class NotifyModal(discord.ui.Modal):
    def __init__(self, panel, section):
        super().__init__(title=f"Edit {section}")
        self.panel, self.section = panel, section
        if section == "basic information":
            self.title_input = discord.ui.TextInput(label="Title", default=panel.get("title"), required=False, max_length=256)
            self.desc_input = discord.ui.TextInput(label="Description", default=panel.get("description"), required=False, style=discord.TextStyle.paragraph, max_length=4000)
            self.colour_input = discord.ui.TextInput(label="Colour (hex)", default=panel.get("colour"), required=False, max_length=6)
            for item in (self.title_input, self.desc_input, self.colour_input): self.add_item(item)
        elif section == "author":
            self.author_input = discord.ui.TextInput(label="Author text", default=panel.get("author"), required=False, max_length=256)
            self.author_icon_input = discord.ui.TextInput(label="Author image URL", default=panel.get("author_icon"), required=False, max_length=500)
            self.add_item(self.author_input); self.add_item(self.author_icon_input)
        elif section == "footer":
            self.footer_input = discord.ui.TextInput(label="Footer text", default=panel.get("footer"), required=False, max_length=2048)
            self.add_item(self.footer_input)
        else:
            self.image_input = discord.ui.TextInput(label="Image URL", default=panel.get("image"), required=False, max_length=500)
            self.thumb_input = discord.ui.TextInput(label="Thumbnail URL", default=panel.get("thumbnail"), required=False, max_length=500)
            self.add_item(self.image_input); self.add_item(self.thumb_input)

    async def on_submit(self, interaction):
        if self.section == "basic information":
            self.panel.data.update(title=self.title_input.value, description=self.desc_input.value, colour=self.colour_input.value or "8B5CF6")
        elif self.section == "author": self.panel.data.update(author=self.author_input.value, author_icon=self.author_icon_input.value)
        elif self.section == "footer": self.panel.data["footer"] = self.footer_input.value
        else: self.panel.data.update(image=self.image_input.value, thumbnail=self.thumb_input.value)
        await interaction.response.edit_message(embed=self.panel.card(), view=self.panel)


class NotifyPanel(SetupView):
    def __init__(self, cog, owner, guild_id, kind):
        super().__init__(owner, guild_id)
        # The generic setup view puts Cancel on row 1; ChannelSelect occupies
        # the full row, so move the generic cancel button out of this builder.
        for item in list(self.children):
            if isinstance(item, discord.ui.Button) and item.label == "✕ Cancel":
                self.remove_item(item)
        self.cog, self.kind = cog, kind
        self.data = {key: cog.bot.settings.get(guild_id, f"notify_{kind}_{key}", value) for key, value in DEFAULTS.items()}
        self.add_item(BuilderButton("Edit basic information", "basic information"))
        self.add_item(BuilderButton("Edit the author", "author"))
        self.add_item(BuilderButton("Edit the footer", "footer"))
        self.add_item(BuilderButton("Edit the images", "images"))
        self.add_item(NotifyChannelButton())
        self.add_item(NotifyTestButton("Preview", kind))
        self.add_item(NotifyToggleButton())
        self.add_item(NotifySaveButton())
        self.add_item(NotifyBackButton())

    def get(self, key): return self.data.get(key, DEFAULTS[key])

    def status_text(self):
        channel_id = self.get("channel_id")
        channel = self.cog.bot.get_channel(int(channel_id)) if str(channel_id).isdigit() else None
        channel_status = channel.mention if channel else "Not selected"
        enabled_status = "Enabled" if str(self.get("enabled")).lower() == "true" else "Disabled"
        return f"**Notifications:** {enabled_status}  •  **Channel:** {channel_status}\nCustomize your notification, then press **Save**."

    def card(self, member=None):
        title = render(self.get("title"), member) if member else self.get("title")
        description = render(self.get("description"), member) if member else self.get("description")
        colour = int(self.get("colour").replace("#", ""), 16) if all(c in "0123456789abcdefABCDEF" for c in self.get("colour")) else 0x8B5CF6
        card = discord.Embed(title=title or discord.Embed.Empty, description=description or discord.Embed.Empty, colour=colour)
        author = render(self.get("author"), member) if member else self.get("author")
        footer = render(self.get("footer"), member) if member else self.get("footer")
        author_icon = render(self.get("author_icon"), member) if member else self.get("author_icon")
        if not str(author_icon).lower().startswith(("http://", "https://")):
            author_icon = ""
        if author:
            card.set_author(name=author, **({"icon_url": author_icon} if author_icon else {}))
        if footer: card.set_footer(text=footer)
        image_url = render(self.get("image"), member) if member else self.get("image")
        thumbnail_url = render(self.get("thumbnail"), member) if member else self.get("thumbnail")
        if str(image_url).lower().startswith(("http://", "https://")): card.set_image(url=image_url)
        if str(thumbnail_url).lower().startswith(("http://", "https://")): card.set_thumbnail(url=thumbnail_url)
        return card


class BuilderButton(discord.ui.Button):
    def __init__(self, label, section):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=0)
        self.section = section
    async def callback(self, interaction): await interaction.response.send_modal(NotifyModal(self.view, self.section))


class NotifyChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Choose notification channel", channel_types=[discord.ChannelType.text], row=0)
    async def callback(self, interaction):
        self.view.selected_channel = self.values[0]
        await interaction.response.edit_message(view=self.view)


class NotifyChannelButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Choose channel", style=discord.ButtonStyle.secondary, row=1)
    async def callback(self, interaction):
        await interaction.response.edit_message(content="Select a channel, then press Select.", view=NotifyChannelEditorView(self.view))


class NotifyChannelEditorView(discord.ui.View):
    def __init__(self, panel):
        super().__init__(timeout=300); self.panel = panel; self.selected_channel = None
        for item in list(self.children):
            if isinstance(item, discord.ui.Button) and item.label == "✕ Cancel": self.remove_item(item)
        self.add_item(NotifyChannelSelect()); self.add_item(NotifyChannelSelectButton()); self.add_item(NotifyChannelClearButton()); self.add_item(NotifyChannelBackButton())


class NotifyChannelSelectButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Select", style=discord.ButtonStyle.success, row=1)
    async def callback(self, interaction):
        view = self.view
        if view.selected_channel is None:
            await interaction.response.send_message("Choose a channel first.", ephemeral=True); return
        view.panel.data["channel_id"] = str(view.selected_channel.id)
        await interaction.response.edit_message(content=view.panel.status_text(), embed=view.panel.card(), view=view.panel)


class NotifyChannelClearButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Clear", style=discord.ButtonStyle.danger, row=1)
    async def callback(self, interaction):
        self.view.panel.data["channel_id"] = ""
        await interaction.response.edit_message(content=self.view.panel.status_text(), embed=self.view.panel.card(), view=self.view.panel)


class NotifyChannelBackButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def callback(self, interaction):
        await interaction.response.edit_message(content=self.view.panel.status_text(), embed=self.view.panel.card(), view=self.view.panel)


class NotifyToggleButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Enable / Disable", style=discord.ButtonStyle.secondary, row=2)
    async def callback(self, interaction):
        self.view.data["enabled"] = not (str(self.view.get("enabled")).lower() == "true")
        await interaction.response.edit_message(content=self.view.status_text(), embed=self.view.card(), view=self.view)


class NotifySaveButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Save", style=discord.ButtonStyle.success, row=3)
    async def callback(self, interaction):
        panel = self.view
        for key, value in panel.data.items(): panel.cog.bot.settings.set(panel.guild_id, f"notify_{panel.kind}_{key}", str(value))
        await interaction.response.edit_message(content=f"✅ {panel.kind.title()} notification saved successfully.", embed=panel.card(), view=None)
        panel.stop()


class NotifyBackButton(discord.ui.Button):
    def __init__(self): super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=3)
    async def callback(self, interaction):
        panel = self.view
        view = NotifyKindView(panel.cog, panel.owner, panel.guild_id)
        await interaction.response.edit_message(content=None, embed=view.card(), view=view)
        panel.stop()


class NotifyTestButton(discord.ui.Button):
    def __init__(self, label, kind):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=2)
        self.kind = kind

    async def callback(self, interaction):
        panel = self.view
        channel_id = panel.get("channel_id")
        channel = panel.cog.bot.get_channel(int(channel_id)) if str(channel_id).isdigit() else None
        if channel is None:
            await interaction.response.send_message("Select a channel first.", ephemeral=True)
            return
        await interaction.response.send_message(
            content=f"Preview : `{self.kind.title()}`",
            embed=panel.card(interaction.user),
            ephemeral=True,
        )


class NotifyKindSelect(discord.ui.Select):
    def __init__(self, cog, owner, guild_id):
        self.cog, self.owner, self.guild_id = cog, owner, guild_id
        super().__init__(placeholder="Choose notification type", options=[discord.SelectOption(label="Welcome", value="welcome"), discord.SelectOption(label="Leave", value="leave")])
    async def callback(self, interaction):
        panel = NotifyPanel(self.cog, self.owner, self.guild_id, self.values[0])
        await interaction.response.edit_message(content=panel.status_text(), embed=panel.card(), view=panel)


class NotifyKindView(SetupView):
    def __init__(self, cog, owner, guild_id):
        super().__init__(owner, guild_id); self.cog = cog; self.add_item(NotifyKindSelect(cog, owner, guild_id))

    def card(self):
        lines = []
        for kind, label in (("welcome", "Welcome"), ("leave", "Leave")):
            enabled = self.cog.bot.settings.get(self.guild_id, f"notify_{kind}_enabled", "False") == "True"
            channel_id = self.cog.bot.settings.get(self.guild_id, f"notify_{kind}_channel_id", "")
            channel = self.cog.bot.get_channel(int(channel_id)) if str(channel_id).isdigit() else None
            room = channel.mention if channel else "Not selected"
            state = "🟢: On" if enabled else "🔴: Off"
            lines.append(f"**{label}** ー `{state}`\n└ Channel : {room}")
        icon_url = self.cog.bot.user.display_avatar.url if self.cog.bot.user else None
        card = discord.Embed(title="Setup : Notification", colour=0x8B5CF6)
        if icon_url:
            card.set_author(name="ʏᴜɴʏᴜɴ ᴘ.", icon_url=icon_url)
        card.add_field(name="Status :", value="\n\n".join(lines), inline=False)
        return card


class NotifyCog(commands.Cog):
    setup_label = "Notify ー Welcome, Leave"
    def __init__(self, bot): self.bot = bot

    async def open_setup(self, interaction):
        view = NotifyKindView(self, interaction.user.id, interaction.guild_id)
        await interaction.response.edit_message(content=None, embed=view.card(), view=view)

    async def send_notification(self, member, kind):
        if self.bot.settings.get(member.guild.id, f"notify_{kind}_enabled", "False") != "True": return
        channel_id = self.bot.settings.get(member.guild.id, f"notify_{kind}_channel_id", "")
        channel = member.guild.get_channel(int(channel_id)) if channel_id.isdigit() else None
        if not channel: return
        data = {key: self.bot.settings.get(member.guild.id, f"notify_{kind}_{key}", value) for key, value in DEFAULTS.items()}
        panel = NotifyPanel(self, member.id, member.guild.id, kind); panel.data = data
        await channel.send(embed=panel.card(member))

    @commands.Cog.listener()
    async def on_member_join(self, member): await self.send_notification(member, "welcome")

    @commands.Cog.listener()
    async def on_member_remove(self, member): await self.send_notification(member, "leave")


async def setup(bot): await bot.add_cog(NotifyCog(bot))
