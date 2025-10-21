import asyncio
import json
import logging
import os
import secrets
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

# --- Configuration (DO NOT CHECK IN A REAL TOKEN) ---
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN")
TICKET_CONFIG_FILE = "ticket_config.json"  # simple persistence for category IDs per guild

# Required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vapor-bot")

bot = commands.Bot(command_prefix=None, intents=intents)


# Simple helper to persist ticket category mappings {guild_id: category_id}
def load_ticket_config():
    if not os.path.exists(TICKET_CONFIG_FILE):
        return {}
    try:
        with open(TICKET_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load ticket config file")
        return {}


def save_ticket_config(config: dict):
    try:
        with open(TICKET_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception:
        logger.exception("Failed to save ticket config file")


# --- 1. Custom Button View (for Verification) ---


class VerificationView(ui.View):
    """A persistent view with a Verify button that adds a role to the clicking user."""

    def __init__(self, verified_role_name: str = "Verified"):
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
            # Try to get from cache then fallback to fetch
            member = interaction.guild.get_member(interaction.user.id)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(interaction.user.id)
                except Exception:
                    member = None

        if member is None:
            await interaction.response.send_message(
                "Could not resolve your member object. Try again or contact an admin.", ephemeral=True
            )
            return

        # Permission checks for the bot before trying to add roles
        me = interaction.guild.me or interaction.guild.get_member(bot.user.id)
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
            # Best-effort response
            try:
                await interaction.response.send_message(
                    f"An unexpected error occurred while assigning the role: {e}", ephemeral=True
                )
            except Exception:
                logger.exception("Failed to send error response for verification failure")


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
            # If we can't send in the target channel, inform the user
            try:
                await interaction.response.send_message(
                    "I do not have permission to post messages in that channel.", ephemeral=True
                )
            except Exception:
                logger.exception("Failed to send permission error after failing to post message")
            return
        except Exception as e:
            logger.exception("Failed to send custom post to channel")
            try:
                await interaction.response.send_message(f"Failed to post message: {e}", ephemeral=True)
            except Exception:
                logger.exception("Failed to send followup error for post_message")
            return

        # Acknowledge the user
        try:
            await interaction.response.send_message("✅ Your custom message has been posted!", ephemeral=True)
        except Exception:
            logger.exception("Failed to acknowledge modal submit")


# --- NEW: Ticketing System Components ---

# 1. Custom View for closing a ticket
class TicketCloseView(ui.View):
    """A view with a button to close the ticket channel."""

    def __init__(self, ticket_opener: discord.Member):
        super().__init__(timeout=None)
        # Store the original user who opened the ticket
        self.ticket_opener_id = ticket_opener.id

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_button")
    async def close_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        member = interaction.user
        # Check if the user is the ticket opener OR a user with Manage Channels permission
        can_close = (member.id == self.ticket_opener_id) or (
            isinstance(member, discord.Member) and member.guild_permissions.manage_channels
        )

        if not can_close:
            await interaction.response.send_message("Only the staff or the ticket creator can close this ticket.", ephemeral=True)
            return

        # Inform, wait shortly, then attempt to delete the channel
        try:
            await interaction.response.send_message("Ticket closing in 5 seconds...", ephemeral=True)
        except Exception:
            # If we can't send ephemeral response (e.g., interaction already responded), continue to delete
            logger.debug("Could not send ephemeral confirmation for ticket close; continuing.")

        # Sleep briefly to allow the user to see the message
        await asyncio.sleep(5)

        if interaction.channel is None:
            logger.warning("Attempted to close a ticket but interaction.channel is None")
            return

        try:
            await interaction.channel.delete(reason=f"Ticket closed by {getattr(member, 'display_name', str(member))}")
        except discord.Forbidden:
            logger.exception("Missing permission to delete ticket channel")
            try:
                # Try to inform in guild (best-effort)
                await interaction.followup.send("I don't have permission to delete the ticket channel. Ask an admin to remove it.", ephemeral=True)
            except Exception:
                logger.exception("Failed to send followup after Forbidden on channel.delete")
        except Exception:
            logger.exception("Failed to delete ticket channel")


# 2. Modal for collecting ticket reason
class TicketModal(ui.Modal, title="Open a New Support Ticket"):
    """Modal that collects the reason for opening the ticket."""

    ticket_reason = ui.TextInput(
        label="Reason for the ticket",
        style=discord.TextStyle.long,
        placeholder="Briefly describe your issue or question.",
        required=True,
        max_length=500,
    )

    def __init__(self, category_id: int):
        super().__init__()
        self.category_id = category_id

    async def on_submit(self, interaction: discord.Interaction):
        # Initial response to prevent "Interaction Failed"
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(member, discord.Member):
            await interaction.followup.send("This action can only be performed in a server.", ephemeral=True)
            return

        # Check for existing open tickets from the user (optional but recommended)
        # We assume ticket channel names start with 'ticket-'
        ticket_prefix = f"ticket-{member.name.lower().replace(' ', '-')}"
        existing_tickets = [
            c for c in guild.text_channels if c.name.startswith(ticket_prefix)
        ]
        if existing_tickets:
            try:
                await interaction.followup.send(
                    f"You already have an open ticket: {existing_tickets[0].mention}", ephemeral=True
                )
            except Exception:
                logger.exception("Failed to notify user about existing ticket")
            return

        # 1. Find the target category
        category = discord.utils.get(guild.categories, id=self.category_id)
        if category is None:
            await interaction.followup.send(
                f"Error: The ticket category (ID: `{self.category_id}`) does not exist or has been deleted.",
                ephemeral=True,
            )
            return

        # 2. Define permissions: Deny view for everyone, but allow staff/bot/opener
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),  # Hide for everyone
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),  # Allow opener
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),  # Allow bot
        }

        # OPTIONAL: Add a staff role (if present)
        staff_role = discord.utils.get(guild.roles, name="Staff")  # Replace 'Staff' with your staff role name if different
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # 3. Create the ticket channel
        try:
            random_suffix = secrets.token_hex(4)
            # Limit length to 100 (Discord channel name length cap is 100)
            base_name = f"ticket-{member.name.lower().replace(' ', '-')}-{random_suffix}"
            channel_name = base_name[:100]

            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket opened by {member.display_name} ({member.id}). Reason: {self.ticket_reason.value}",
                reason="New support ticket creation"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I do not have the required permissions to create channels or set permissions in that category.", ephemeral=True
            )
            return
        except Exception as e:
            logger.exception("Failed to create ticket channel")
            await interaction.followup.send(f"An error occurred while creating the ticket: {e}", ephemeral=True)
            return

        # 4. Send the initial message and follow up to the user
        ticket_embed = discord.Embed(
            title=f"Support Ticket for {member.display_name}",
            description=f"**Reason:** {self.ticket_reason.value}\n\nOur support team will be with you shortly. Please provide any necessary details or screenshots here.",
            color=discord.Color.gold(),
        )
        ticket_embed.set_footer(text="Click the button below to close this ticket once your issue is resolved.")

        # Mention the ticket opener and optionally a staff role
        staff_ping = ""
        if staff_role:
            staff_ping = staff_role.mention + ", "

        try:
            await ticket_channel.send(
                content=f"{member.mention} {staff_ping}A new ticket has been opened.",
                embed=ticket_embed,
                view=TicketCloseView(ticket_opener=member)
            )
        except Exception:
            logger.exception("Failed to send initial message in ticket channel")

        try:
            await interaction.followup.send(f"✅ Your ticket has been created! Go to: {ticket_channel.mention}", ephemeral=True)
        except Exception:
            logger.exception("Failed to send followup confirming ticket creation")


# 3. View with the button to open the modal
class TicketPanelView(ui.View):
    """A persistent view with a button that triggers the TicketModal."""

    def __init__(self, category_id: int):
        super().__init__(timeout=None)
        # This ID needs to be persistent, so we store it on the class instance
        self.category_id = category_id

    @ui.button(label="Create a Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket_button")
    async def create_ticket_callback(self, interaction: discord.Interaction, button: ui.Button):
        # Open the modal, passing the category ID
        try:
            await interaction.response.send_modal(TicketModal(category_id=self.category_id))
        except Exception:
            logger.exception("Failed to open TicketModal")
            try:
                await interaction.response.send_message("Failed to open ticket modal.", ephemeral=True)
            except Exception:
                logger.exception("Failed to send modal error response")


# --- 3. Bot Events & Setup ---


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (id: {bot.user.id})")

    # Register persistent views
    bot.add_view(VerificationView())

    # Load persisted ticket category mappings and register TicketPanelView for each valid mapping
    ticket_config = load_ticket_config()
    registered = 0
    for guild_id_str, category_id in ticket_config.items():
        try:
            guild_id = int(guild_id_str)
        except Exception:
            continue
        # Only add view to bot; the view itself is not guild-scoped in registration.
        if category_id and isinstance(category_id, int):
            bot.add_view(TicketPanelView(category_id=category_id))
            registered += 1

    logger.info(f"Registered {registered} persisted TicketPanelView(s) on startup.")

    # Sync global app commands (consider using guild-specific sync during development)
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception:
        logger.exception("Failed to sync commands")


# --- 4. Slash Commands (Verification & Custom Post) ---


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
    except Exception:
        logger.exception("Failed to open modal")
        try:
            await interaction.response.send_message(f"Could not open the modal.", ephemeral=True)
        except Exception:
            logger.exception("Failed to send modal error response")


# --- NEW: Ticketing Slash Command ---

@bot.tree.command(name="setup_ticket", description="Posts the ticket creation panel.")
@app_commands.describe(category="The category where new tickets should be created.")
@commands.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction, category: discord.CategoryChannel):
    """Command for admins to post a ticket creation embed with a persistent button."""
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    me = interaction.guild.me or interaction.guild.get_member(bot.user.id)
    if not me:
        await interaction.response.send_message("Bot member object unavailable.", ephemeral=True)
        return

    # Check bot guild-level perms for creating/managing channels
    if not me.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "I must have the **Manage Channels** permission in the server to create tickets.", ephemeral=True
        )
        return

    # Check category-specific permissions
    category_perms = category.permissions_for(me)
    # It's hard to perfectly validate every permission combination; ensure bot can create channels and manage perms
    if not category_perms.manage_channels:
        await interaction.response.send_message(
            "I must have sufficient permissions in that category to create channels there (Manage Channels).", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Support & Assistance",
        description="Need help? Click the **Create a Ticket** button below to open a private channel with our staff.",
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Please be patient; we'll respond as soon as possible.")

    # Send the embed with the persistent view, passing the Category ID
    try:
        await interaction.response.send_message(
            embed=embed,
            view=TicketPanelView(category_id=category.id)
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I do not have permission to send messages in this channel.", ephemeral=True
        )
        return

    # Persist the mapping so the view can be re-registered after restarts
    config = load_ticket_config()
    config[str(interaction.guild.id)] = category.id
    save_ticket_config(config)
    logger.info(f"Saved ticket panel category {category.id} for guild {interaction.guild.id}")


# --- 5. Error Handling & Start ---


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Permission errors
    if isinstance(error, app_commands.MissingPermissions):
        try:
            await interaction.response.send_message(
                "You do not have the required permissions to use this command.", ephemeral=True
            )
        except Exception:
            try:
                await interaction.followup.send("You do not have the required permissions to use this command.", ephemeral=True)
            except Exception:
                logger.exception("Failed to notify about missing permissions")
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
