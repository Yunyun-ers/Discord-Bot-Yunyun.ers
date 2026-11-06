import logging
import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


def embed(description, subtitle=None, icon_url=None):
    card = discord.Embed(title="Setup", description=description, colour=0x8B5CF6)
    if icon_url:
        card.set_author(name="ʏᴜɴʏᴜɴ ᴘ.", icon_url=icon_url)
    if subtitle:
        card.add_field(name=subtitle[0], value=subtitle[1], inline=False)
    #card.set_footer(text="Server settings • Applies only to this server")
    return card


class SetupView(discord.ui.View):
    active_sessions = {}
    def __init__(self, owner, guild_id):
        super().__init__(timeout=300)
        self.owner = owner
        self.guild_id = guild_id
        self.message = None
        self.session_key = (guild_id, owner)
        old = self.active_sessions.get(self.session_key)
        if old and old is not self:
            old.stop()
        self.active_sessions[self.session_key] = self

    async def interaction_check(self, interaction):
        if self.active_sessions.get(self.session_key) is not self:
            await interaction.response.send_message("This setup session is no longer active. Run /setup again.", ephemeral=True)
            return False
        if interaction.user.id != self.owner or interaction.guild_id != self.guild_id:
            await interaction.response.send_message("Please open your own setup panel with /setup.", ephemeral=True)
            return False
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message("You need Manage Server permission to use this panel.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.active_sessions.get(self.session_key) is self:
            self.active_sessions.pop(self.session_key, None)
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="This setup session has expired. Run /setup again.", view=self)
            except discord.HTTPException:
                pass

    async def on_error(self, interaction, error, item):
        log.error("Setup interaction failed", exc_info=(type(error), error, error.__traceback__))
        try:
            if interaction.response.is_done():
                await interaction.followup.send("Setup failed. Please try again.", ephemeral=True)
            else:
                await interaction.response.send_message("Setup failed. Please try again.", ephemeral=True)
        except discord.NotFound:
            log.warning("Setup interaction expired before the error message could be sent.")

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction, button):
        self.active_sessions.pop(self.session_key, None)
        await interaction.response.edit_message(content="ᴍᴇɴᴜ ᴄʟᴏsᴇᴅ.", embed=None, view=None)
        self.stop()


class FeatureSelect(discord.ui.Select):
    def __init__(self, panel):
        options = [discord.SelectOption(label=str(c.setup_label)[:100], value=c.qualified_name) for c in panel.features]
        if not options:
            options = [discord.SelectOption(label="No features available", value="none", description="Add a feature Cog first")]
        super().__init__(placeholder="sᴇᴛᴜᴘ — ʟɪsᴛ", options=options[:25], row=0)

    async def callback(self, interaction):
        panel = self.view
        panel.selected_feature = self.values[0]
        for option in self.options:
            option.default = option.value == panel.selected_feature
            if option.default:
                self.placeholder = option.label
        panel.next_button.disabled = panel.selected_feature == "none"
        await interaction.response.edit_message(view=panel)


class FeatureView(SetupView):
    def __init__(self, bot, owner, guild_id):
        super().__init__(owner, guild_id)
        self.bot = bot
        self.features = [c for c in bot.cogs.values() if hasattr(c, "setup_label") and callable(getattr(c, "open_setup", None))]
        self.selected_feature = None
        self.add_item(FeatureSelect(self))
        self.next_button = NextButton()
        self.add_item(self.next_button)

    def card(self):
        icon_url = self.bot.user.display_avatar.url if self.bot.user else None
        return embed(
            "Select a feature below, then click Next to configure it.",
            ("Features", "".join(f"• {c.setup_label}\n" for c in self.features[:24]) or "No features installed"),
            icon_url=icon_url,
        )


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Next", style=discord.ButtonStyle.primary, row=1, disabled=True)

    async def callback(self, interaction):
        panel = self.view
        feature = panel.bot.get_cog(panel.selected_feature)
        if feature is None:
            await interaction.response.send_message("This feature is unavailable. Run /setup again.", ephemeral=True)
            return
        await feature.open_setup(interaction)
        panel.stop()


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Open the server feature setup panel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_command(self, interaction: discord.Interaction):
        view = FeatureView(self.bot, interaction.user.id, interaction.guild_id)
        await interaction.response.send_message(embed=view.card(), view=view, ephemeral=True)
        view.message = await interaction.original_response()

    async def cog_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You need Manage Server permission to use /setup.", ephemeral=True)
        else:
            log.error("Setup command failed", exc_info=(type(error), error, error.__traceback__))
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("Could not open setup. Please try again.", ephemeral=True)
            except discord.NotFound:
                log.warning("Setup command interaction expired before the error message could be sent.")


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
