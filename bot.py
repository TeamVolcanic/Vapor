import logging
import os
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

# --- Configuration (DO NOT CHECK IN A REAL TOKEN) ---
# This structure correctly pulls the token from the Railway environment variable (DISCORD_BOT_TOKEN)
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN")

# Required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vapor-bot")

# NOTE: The command_prefix parameter is removed. Since you are using app_commands
# (slash commands), the prefix is automatically `/`.
bot = commands.Bot(command_prefix=None, intents=intents)


# --- 1. Custom Button View (for Verification) ---


class VerificationView(ui.View):
    """A persistent view with a Verify button that adds a role to the clicking user."""

    def __init__(self, verified_role_name: str = "Verified"):
        # Persistent view (timeout=None) keeps the button active across restarts
        super().__init__(timeout=None)
        self.verified_role_name = verified_role_name

    @ui.button(label="Verify Me", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        # Ensure this interaction happened in a guild
        if interaction.guild is None:
            await interaction.response.send_message(
                "This verification button can only be used inside servers.", ephemeral=True
            )
            return

        # Resolve role
        role = discord.utils.get(interaction.guild.roles, name=self.verified_role_name)
        if role is None:
            await interaction.response.send_message(
                f"Error: The `{self.verified_role_name}` role does not exist on this server.", ephemeral=True
            )
            return

        # Resolve member object (interaction.user can be a Member or a User)
        member: Optional[discord.Member] = None
        if isinstance(interaction.user, discord.Member):
            member = interaction.user
        else:
            member = interaction.guild.get_member(interaction.user.id)

        if member is None:
            await interaction.response.send_message(
                "Could not resolve your member object. Try again or contact an admin.", ephemeral=True
            )
            return

        # Permission checks for the bot before trying to add roles
        me = interaction.guild.me
        if me is None:
            await interaction.response.send_message(
                "Bot member object unavailable; cannot assign roles.", ephemeral=True
            )
            return

        if not me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "I do not have the Manage Roles permission. Ask an admin to grant it to me.", ephemeral=True
            )
            return

        # Ensure the bot's top role is above the target role
        if role.position >= me.top_role.position:
            await interaction.response.send_message(
                "I cannot assign that role because it is higher or equal to my top role. An admin must fix role ordering.",
                ephemeral=True,
            )
            return

        # Add the role if the user doesn't already have it
        if role in member.roles:
            await interaction.response.send_message("You are already verified!", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason="Self-verification via verify button")
            await interaction.response.send_message(
                f"Verification successful! You now have the **{self.verified_role_name}** role.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I lack permissions to add that role. Please contact an administrator.", ephemeral=True
            )
        except Exception as e:
            logger.exception("Failed to add verification role")
            await interaction.response.send_message(
                f"An unexpected error occurred while assigning the role: {e}", ephemeral=True
            )


# --- 2. Custom Modal (for Post Message Command) ---


class PostMessageModal(ui.Modal, title="Create Custom Post"):
    """Modal that collects embed title, message, and optional link buttons."""

    embed_title = ui.TextInput(
        label="Embed Title (Optional)",
        style=discord.TextStyle.short,
        placeholder="Enter a title for the embed...",
        required=False,
        max_length=256,
    )

    message_content = ui.TextInput(
        label="Message/Embed Description",
        style=discord.TextStyle.long,
        placeholder="Enter the main text content here...",
        required=True,
        max_length=2000,
    )

    button_data = ui.TextInput(
        label="Buttons (Label|URL, Label|URL)",
        style=discord.TextStyle.short,
        placeholder="Example: Website|https://example.com, Discord|https://discord.gg/invite",
        required=False,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Ensure the modal submission happened in a guild text channel (channel may be None in DM)
        if interaction.channel is None:
            await interaction.response.send_message(
                "Cannot post to the channel because the interaction has no channel context.", ephemeral=True
            )
            return

        # Build embed
        title = self.embed_title.value.strip() if self.embed_title.value else None
        description = self.message_content.value.strip()
        embed = discord.Embed(title=title if title else None, description=description, color=discord.Color.blue())

        # Parse buttons
        view = ui.View()
        button_str = self.button_data.value.strip() if self.button_data.value else ""
        if button_str:
            # Accept label|url pairs separated by commas
            pairs = [p.strip() for p in button_str.split(",") if p.strip()]
            for pair in pairs:
                if "|" not in pair:
                    await interaction.response.send_message(
                        "❌ Error: Each button must be in the format `Label|URL` (pairs separated by commas).",
                        ephemeral=True,
                    )
                    return
                label, url = pair.split("|", 1)
                label = label.strip()
                url = url.strip()
                if not label:
                    await interaction.response.send_message("❌ Error: Button label cannot be empty.", ephemeral=True)
                    return
                if not url.lower().startswith(("http://", "https://")):
                    await interaction.response.send_message(
                        f"❌ Error: Invalid URL for button `{label}`. URLs must start with http:// or https://", ephemeral=True
                    )
                    return
                # Add a Link button
                view.add_item(ui.Button(label=label, url=url))

        # Send embed to the channel
        try:
            await interaction.channel.send(embed=embed, view=view if len(view.children) > 0 else None)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I do not have permission to post messages in that channel.", ephemeral=True
            )
            return
        except Exception as e:
            logger.exception("Failed to send custom post to channel")
            await interaction.response.send_message(f"Failed to post message: {e}", ephemeral=True)
            return

        # Acknowledge the user
        await interaction.response.send_message("✅ Your custom message has been posted!", ephemeral=True)


# --- 3. Bot Events & Setup ---


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (id: {bot.user.id})")
    # Register persistent view (so previously posted buttons keep working after restarts)
    # The default VerificationView name is used as the custom_id remains "verify_button"
    bot.add_view(VerificationView()) 

    # Sync global app commands (consider using guild-specific sync during development)
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.exception("Failed to sync commands")


# --- 4. Slash Commands ---


@bot.tree.command(name="setup_verify", description="Posts the verification message with a button.")
@commands.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    """Command for admins to post a verification embed with a persistent button."""
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Server Verification",
        description="Click the **Verify Me** button below to gain full access to the server channels.",
        color=discord.Color.green(),
    )
    embed.set_footer(text="Read the rules first!")

    # Send the embed with a fresh view instance (persistent custom_id ensures the button remains functional)
    try:
        await interaction.response.send_message(embed=embed, view=VerificationView())
    except discord.Forbidden:
        await interaction.response.send_message(
            "I do not have permission to send messages in this channel.", ephemeral=True
        )


@bot.tree.command(name="post_message", description="Posts a custom embed and optional link buttons.")
@commands.has_permissions(manage_messages=True)
async def post_message_command(interaction: discord.Interaction):
    """Opens a modal asking for embed/message details and optional buttons."""
    try:
        await interaction.response.send_modal(PostMessageModal())
    except Exception as e:
        logger.exception("Failed to open modal")
        await interaction.response.send_message(f"Could not open the modal: {e}", ephemeral=True)


# --- 5. Error Handling & Start ---


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Permission errors
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You do not have the required permissions to use this command.", ephemeral=True
        )
        return

    # Generic handler
    logger.exception("App command error")
    try:
        # Check if a response has already been sent (e.g., by the modal error handler)
        if interaction.response.is_done():
            # If done, follow up instead
            await interaction.followup.send(f"An unexpected error occurred: {error}", ephemeral=True)
        else:
             await interaction.response.send_message(f"An unexpected error occurred: {error}", ephemeral=True)
    except Exception:
        # If the interaction response is already done or closed
        logger.exception("Failed to respond to interaction error")


if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN" or not BOT_TOKEN:
        logger.error("Please set the DISCORD_BOT_TOKEN environment variable (or update BOT_TOKEN).")
        print("\nERROR: Please set 'DISCORD_BOT_TOKEN' in your environment (or on Railway) before running.\n")
    else:
        bot.run(BOT_TOKEN)
