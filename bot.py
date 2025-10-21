#!/usr/bin/env python3
"""
Unified bot.py: single-file Discord bot with:
- Verification button (persistent)
- Post message modal (embed builder)
- Interactive dynamic buttons (role assign or ticket creation)
- Ticket panel with persistent TICKET_CREATE:{category_id} custom_id handling
- Persistence for ticket panel mappings (ticket_config.json)
- Proper runtime registration of sent view instances and re-registration on startup
- Helpful guidance when required slash options are missing
"""

import asyncio
import json
import logging
import os
import secrets
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

# --- Configuration ---
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")  # Set this in Railway variables
TICKET_CONFIG_FILE = "ticket_config.json"  # persisted mapping: { "<guild_id>": <category_id> }

# Required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vapor-bot")

bot = commands.Bot(command_prefix=None, intents=intents)


# --- Persistence helpers ---
def load_ticket_config() -> dict:
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


# --- 1) Verification View ---
class VerificationView(ui.View):
    """Persistent Verify button that grants a role to the clicking user."""

    def __init__(self, verified_role_name: str = "Verified"):
        super().__init__(timeout=None)
        self.verified_role_name = verified_role_name

    @ui.button(label="Verify Me", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.guild is None:
            await interaction.response.send_message("This verification button only works inside servers.", ephemeral=True)
            return

        role = discord.utils.get(interaction.guild.roles, name=self.verified_role_name)
        if role is None:
            await interaction.response.send_message(
                f"Error: The `{self.verified_role_name}` role does not exist on this server.", ephemeral=True
            )
            return

        # Resolve member
        member: Optional[discord.Member] = None
        if isinstance(interaction.user, discord.Member):
            member = interaction.user
        else:
            member = interaction.guild.get_member(interaction.user.id)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(interaction.user.id)
                except Exception:
                    member = None

        if member is None:
            await interaction.response.send_message("Could not resolve your member object. Try again later.", ephemeral=True)
            return

        me = interaction.guild.me or interaction.guild.get_member(bot.user.id)
        if me is None:
            await interaction.response.send_message("Bot member object unavailable; cannot assign roles.", ephemeral=True)
            return

        if not me.guild_permissions.manage_roles:
            await interaction.response.send_message("I do not have Manage Roles permission. Ask an admin to grant it.", ephemeral=True)
            return

        if role.position >= me.top_role.position:
            await interaction.response.send_message(
                "I cannot assign that role because it is higher or equal to my top role. An admin must adjust role order.",
                ephemeral=True,
            )
            return

        if role in member.roles:
            await interaction.response.send_message("You are already verified!", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason="Self-verification via verify button")
            await interaction.response.send_message(f"Verification successful! You now have **{self.verified_role_name}**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I lack permissions to add that role. Please contact an admin.", ephemeral=True)
        except Exception:
            logger.exception("Failed to add verification role")
            try:
                await interaction.response.send_message("An unexpected error occurred while assigning the role.", ephemeral=True)
            except Exception:
                logger.exception("Failed to acknowledgement verification error")


# --- 2) Post Message Modal ---
class PostMessageModal(ui.Modal, title="Create Custom Post"):
    embed_title = ui.TextInput(label="Embed Title (Optional)", style=discord.TextStyle.short, required=False, max_length=256)
    message_content = ui.TextInput(
        label="Message/Embed Description",
        style=discord.TextStyle.long,
        required=True,
        max_length=2000,
        default="📢 We have an exciting announcement! Read the details below to find out more."
    )
    embed_color = ui.TextInput(label="Embed Color (Optional, Hex Code)", style=discord.TextStyle.short, required=False, max_length=7)
    image_url = ui.TextInput(label="Image URL (Optional)", style=discord.TextStyle.short, required=False, max_length=200)
    footer_text = ui.TextInput(label="Footer Text (Optional)", style=discord.TextStyle.short, required=False, max_length=2048)
    button_data = ui.TextInput(
        label="Link Buttons (Label|URL, Label|URL)",
        style=discord.TextStyle.short,
        required=False,
        max_length=1000,
        placeholder="Website|https://example.com, Support|https://example.com/support"
    )

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.channel is None:
            await interaction.response.send_message("Cannot post because the interaction has no channel context.", ephemeral=True)
            return

        # Parse color
        color_input = self.embed_color.value.strip() if self.embed_color.value else None
        embed_color = discord.Color.blue()
        color_warning = ""
        if color_input:
            hex_code = color_input.lstrip("#")
            if len(hex_code) == 6:
                try:
                    embed_color = discord.Color(int(hex_code, 16))
                except ValueError:
                    color_warning = "⚠️ Invalid hex code provided. Using default blue."
            else:
                color_warning = "⚠️ Color must be a 6-digit hex code (e.g., #FF5733). Using default blue."

        title = self.embed_title.value.strip() if self.embed_title.value else None
        description = self.message_content.value.strip()
        if title:
            title = "✨ " + title
        else:
            description = "🌟 " + description

        embed = discord.Embed(title=title if title else None, description=description, color=embed_color)
        embed.timestamp = discord.utils.utcnow()
        image_url = self.image_url.value.strip() if self.image_url.value else None
        if image_url:
            if not image_url.lower().startswith(("http://", "https://")):
                await interaction.response.send_message("❌ Image URL must start with http:// or https://", ephemeral=True)
                return
            embed.set_image(url=image_url)

        footer_text = self.footer_text.value.strip() if self.footer_text.value else None
        if footer_text:
            embed.set_footer(text=footer_text)

        view = ui.View()
        button_str = self.button_data.value.strip() if self.button_data.value else ""
        if button_str:
            pairs = [p.strip() for p in button_str.split(",") if p.strip()]
            for pair in pairs:
                if "|" not in pair:
                    await interaction.response.send_message("❌ Each button must be in format `Label|URL`.", ephemeral=True)
                    return
                label, url = pair.split("|", 1)
                label = label.strip()
                url = url.strip()
                if not label or not url:
                    await interaction.response.send_message("❌ Button label and URL cannot be empty.", ephemeral=True)
                    return
                if not url.lower().startswith(("http://", "https://")):
                    await interaction.response.send_message(f"❌ Invalid URL for `{label}`. Must start with http(s).", ephemeral=True)
                    return
                view.add_item(ui.Button(label=label, url=url))

        try:
            await interaction.channel.send(embed=embed, view=view if len(view.children) > 0 else None)
        except discord.Forbidden:
            try:
                await interaction.response.send_message("I do not have permission to post in that channel.", ephemeral=True)
            except Exception:
                logger.exception("Failed to send permission error")
            return
        except Exception:
            logger.exception("Failed to send custom post")
            try:
                await interaction.response.send_message("Failed to post message due to an unexpected error.", ephemeral=True)
            except Exception:
                logger.exception("Failed to acknowledge modal failure")
            return

        ack = "✅ Your custom message has been posted!"
        if color_warning:
            ack += f"\n{color_warning}"
        try:
            await interaction.response.send_message(ack, ephemeral=True)
        except Exception:
            logger.exception("Failed to acknowledge modal submit")


# --- 3) Interactive Button Handler (placeholder + dynamic instances) ---
class InteractiveButtonView(ui.View):
    """Placeholder persistent view for interactive actions. Sent/registered dynamic views also work."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Action Button", style=discord.ButtonStyle.secondary, custom_id="INTERACTIVE_ACTION_PLACEHOLDER")
    async def handle_dynamic_action(self, interaction: discord.Interaction, button: ui.Button):
        # button.custom_id will be set to the actual custom_id on the sent view instance
        parts = button.custom_id.split(":")
        if len(parts) < 3 or parts[0] != "INTERACTIVE_ACTION":
            return await interaction.response.send_message("Error: Invalid button configuration.", ephemeral=True)

        action_type = parts[1]
        target_value = ":".join(parts[2:])

        if action_type == "TICKET":
            try:
                category_id = int(target_value)
            except ValueError:
                return await interaction.response.send_message("Error: Ticket category ID is invalid.", ephemeral=True)
            try:
                return await interaction.response.send_modal(TicketModal(category_id=category_id))
            except Exception:
                logger.exception("Failed to open TicketModal from dynamic button")
                return await interaction.response.send_message("Failed to open ticket creation form.", ephemeral=True)

        # ROLE or others
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            await interaction.followup.send("This action can only be used inside a server.", ephemeral=True)
            return

        if action_type == "ROLE":
            role_name = target_value
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            member = interaction.user
            if role is None:
                return await interaction.followup.send(f"Error: Role `{role_name}` not found.", ephemeral=True)

            if not isinstance(member, discord.Member):
                member = interaction.guild.get_member(interaction.user.id)
                if member is None:
                    return await interaction.followup.send("Could not resolve your member object.", ephemeral=True)

            if role in member.roles:
                return await interaction.followup.send(f"You already have the **{role_name}** role.", ephemeral=True)

            me = interaction.guild.me
            if role.position >= me.top_role.position or not me.guild_permissions.manage_roles:
                return await interaction.followup.send("The bot cannot assign that role due to permission hierarchy.", ephemeral=True)

            try:
                await member.add_roles(role, reason="Dynamic role button click")
                await interaction.followup.send(f"You have been granted the **{role_name}** role! 🎉", ephemeral=True)
            except Exception:
                logger.exception("Failed to assign role from dynamic button")
                await interaction.followup.send("Failed to assign role due to an unexpected error.", ephemeral=True)
        else:
            await interaction.followup.send("Error: Unknown button action type.", ephemeral=True)


# --- 4) Ticketing components ---
class TicketCloseView(ui.View):
    def __init__(self, ticket_opener: discord.Member):
        super().__init__(timeout=None)
        self.ticket_opener_id = ticket_opener.id

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_button")
    async def close_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        member = interaction.user
        can_close = (member.id == self.ticket_opener_id) or (
            isinstance(member, discord.Member) and member.guild_permissions.manage_channels
        )
        if not can_close:
            await interaction.response.send_message("Only the staff or the ticket creator can close this ticket.", ephemeral=True)
            return

        try:
            if interaction.response.is_done():
                await interaction.followup.send("Ticket closing in 5 seconds...", ephemeral=True)
            else:
                await interaction.response.send_message("Ticket closing in 5 seconds...", ephemeral=True)
        except Exception:
            logger.debug("Could not send ephemeral confirmation; continuing to close")

        await asyncio.sleep(5)

        if interaction.channel is None:
            logger.warning("Attempted to close a ticket but interaction.channel is None")
            return

        try:
            await interaction.channel.delete(reason=f"Ticket closed by {getattr(member, 'display_name', str(member))}")
        except discord.Forbidden:
            logger.exception("Missing permission to delete ticket channel")
            try:
                await interaction.followup.send("I don't have permission to delete the ticket channel. Ask an admin to remove it.", ephemeral=True)
            except Exception:
                logger.exception("Failed to send followup after Forbidden on channel.delete")
        except Exception:
            logger.exception("Failed to delete ticket channel")


class TicketModal(ui.Modal, title="Open a New Support Ticket"):
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
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.followup.send("This action can only be performed in a server.", ephemeral=True)
            return

        sanitized_name = member.name.lower().replace(" ", "-").replace("_", "-").strip()
        ticket_prefix = f"ticket-{sanitized_name}"
        existing_tickets = [c for c in guild.text_channels if c.name.startswith(ticket_prefix)]
        if existing_tickets:
            try:
                await interaction.followup.send(f"You already have an open ticket: {existing_tickets[0].mention}", ephemeral=True)
            except Exception:
                logger.exception("Failed to notify user about existing ticket")
            return

        category = discord.utils.get(guild.categories, id=self.category_id)
        if category is None:
            await interaction.followup.send(f"Error: The ticket category (ID: `{self.category_id}`) does not exist.", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        staff_role = discord.utils.get(guild.roles, name="Staff")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            random_suffix = secrets.token_hex(4)
            base_name = f"ticket-{sanitized_name}-{random_suffix}"
            channel_name = base_name[:100]
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket opened by {member.display_name} ({member.id}). Reason: {self.ticket_reason.value}",
                reason="New support ticket creation"
            )
        except discord.Forbidden:
            await interaction.followup.send("I do not have permissions to create channels in that category.", ephemeral=True)
            return
        except Exception:
            logger.exception("Failed to create ticket channel")
            await interaction.followup.send("An error occurred while creating the ticket.", ephemeral=True)
            return

        ticket_embed = discord.Embed(
            title=f"Support Ticket for {member.display_name}",
            description=f"**Reason:** {self.ticket_reason.value}\n\nOur support team will be with you shortly.",
            color=discord.Color.gold(),
        )
        ticket_embed.set_footer(text="Click the button below to close this ticket once your issue is resolved.")

        staff_ping = staff_role.mention + ", " if staff_role else ""

        try:
            await ticket_channel.send(content=f"{member.mention} {staff_ping}A new ticket has been opened.", embed=ticket_embed, view=TicketCloseView(ticket_opener=member))
        except Exception:
            logger.exception("Failed to send initial message in ticket channel")

        try:
            await interaction.followup.send(f"✅ Your ticket has been created! Go to: {ticket_channel.mention}", ephemeral=True)
        except Exception:
            logger.exception("Failed to send followup confirming ticket creation")


class TicketPanelView(ui.View):
    """Base persistent view that handles a dynamic TICKET_CREATE:{category_id} custom_id."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Create a Ticket", style=discord.ButtonStyle.primary, custom_id="TICKET_CREATE_PLACEHOLDER")
    async def create_ticket_callback(self, interaction: discord.Interaction, button: ui.Button):
        if not button.custom_id.startswith("TICKET_CREATE:"):
            await interaction.response.send_message("Internal error: Custom ID format incorrect.", ephemeral=True)
            return
        try:
            category_id = int(button.custom_id.split(":", 1)[1])
        except (ValueError, IndexError):
            logger.error(f"Failed to parse category_id from custom_id: {button.custom_id}")
            await interaction.response.send_message("Configuration error: Cannot resolve ticket destination category.", ephemeral=True)
            return
        try:
            await interaction.response.send_modal(TicketModal(category_id=category_id))
        except Exception:
            logger.exception("Failed to open TicketModal")
            try:
                await interaction.response.send_message("Failed to open ticket modal.", ephemeral=True)
            except Exception:
                logger.exception("Failed to send modal error response")


# --- 5) Bot lifecycle: on_ready and registration logic ---
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (id: {bot.user.id})")

    # Register fixed/persistent views
    try:
        bot.add_view(VerificationView())  # static custom_id -> works across restarts while process runs
        bot.add_view(InteractiveButtonView())  # placeholder handler for dynamic interactive buttons
    except Exception:
        logger.exception("Failed to register base persistent views")

    # Re-register ticket panel views from persisted config
    try:
        config = load_ticket_config()  # { "<guild_id>": <category_id> }
        for guild_id_str, category_id in config.items():
            try:
                # create view instance for this persisted category and set the correct custom_id
                view = TicketPanelView()
                if len(view.children) > 0:
                    view.children[0].custom_id = f"TICKET_CREATE:{int(category_id)}"
                    bot.add_view(view)
                    logger.info(f"Re-registered TicketPanelView for guild {guild_id_str} -> category {category_id}")
                else:
                    logger.warning("TicketPanelView had no children when re-registering")
            except Exception:
                logger.exception("Failed to re-register TicketPanelView for guild %s", guild_id_str)
    except Exception:
        logger.exception("Failed to load or re-register ticket panel views from config")

    # Try syncing commands (best effort)
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} commands")
    except Exception:
        logger.exception("Failed to sync application commands on startup")


# --- 6) Slash commands: setup and utilities ---
@bot.tree.command(name="setup_verify", description="Posts the verification message with a button.")
@commands.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    embed = discord.Embed(title="Server Verification", description="Click the **Verify Me** button to gain access.", color=discord.Color.green())
    embed.set_footer(text="Read the rules first.")
    try:
        view = VerificationView()
        bot.add_view(view)
        await interaction.response.send_message(embed=embed, view=view)
    except discord.Forbidden:
        await interaction.response.send_message("I do not have permission to send messages in this channel.", ephemeral=True)


@bot.tree.command(name="post_message", description="Posts a custom embed and optional link buttons.")
@commands.has_permissions(manage_messages=True)
async def post_message_command(interaction: discord.Interaction):
    try:
        await interaction.response.send_modal(PostMessageModal())
    except Exception:
        logger.exception("Failed to open PostMessageModal")
        try:
            await interaction.response.send_message("Could not open the modal.", ephemeral=True)
        except Exception:
            logger.exception("Failed to send modal error response")


@bot.tree.command(name="setup_interactive_button", description="Posts a message with a custom button for roles or tickets.")
@app_commands.describe(
    action="The action this button should perform (role or ticket).",
    label="The text on the button.",
    role_name="[Required for Role] The name of the role to assign (e.g., Member).",
    ticket_category="[Required for Ticket] The category where new ticket channels will be created.",
    message_content="Optional text to display above the button."
)
@commands.has_permissions(administrator=True)
async def setup_interactive_button(
    interaction: discord.Interaction,
    action: str,
    label: str,
    role_name: Optional[str] = None,
    ticket_category: Optional[discord.CategoryChannel] = None,
    message_content: Optional[str] = None,
):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    action = action.lower()

    # Helpful guidance if ticket action missing category
    if action == "ticket" and ticket_category is None:
        example = '/setup_interactive_button action:ticket label:"Open Ticket" ticket_category:#Support message_content:"Click to open a private ticket."'
        help_msg = (
            "❌ When action is `ticket`, the `ticket_category` argument is required.\n\n"
            "How to fix:\n"
            "1. Type `/setup_interactive_button` in chat.\n"
            "2. Set `action` to `ticket`.\n"
            "3. Click the **ticket_category** field and select the Category from the dropdown (e.g., `Support`).\n"
            "4. Fill `label` and optional `message_content`, then send.\n\n"
            f"Example (fill these in the slash UI):\n{example}"
        )
        await interaction.response.send_message(help_msg, ephemeral=True)
        return

    custom_id = None
    target_info = ""
    style = discord.ButtonStyle.secondary
    embed_title = "Interactive Button"

    if action == "role":
        if not role_name:
            await interaction.response.send_message("❌ When action is `role`, the `role_name` argument is required.", ephemeral=True)
            return
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role is None:
            await interaction.response.send_message(f"❌ Role named `{role_name}` not found in this server.", ephemeral=True)
            return
        custom_id = f"INTERACTIVE_ACTION:ROLE:{role_name}"
        target_info = f"Role: {role_name}"
        style = discord.ButtonStyle.green
        embed_title = "Dynamic Role Assignment"

    elif action == "ticket":
        me = interaction.guild.me
        if not me:
            await interaction.response.send_message("Bot member object unavailable.", ephemeral=True)
            return
        category_perms = ticket_category.permissions_for(me)
        if not category_perms.manage_channels:
            await interaction.response.send_message("❌ I must have Manage Channels permission in that category to create tickets.", ephemeral=True)
            return
        custom_id = f"INTERACTIVE_ACTION:TICKET:{ticket_category.id}"
        target_info = f"Category: #{ticket_category.name}"
        style = discord.ButtonStyle.primary
        embed_title = "Dynamic Ticket System"

    else:
        await interaction.response.send_message("❌ Invalid action. Must be `role` or `ticket`.", ephemeral=True)
        return

    view = ui.View(timeout=None)
    action_button = ui.Button(label=label, style=style, custom_id=custom_id)
    view.add_item(action_button)
    content = message_content or f"Click the **{label}** button below to complete the action: {action.capitalize()}."
    embed = discord.Embed(title=embed_title, description=content, color=discord.Color.blurple())
    embed.set_footer(text=f"Action: {action.capitalize()} | Target: {target_info}")

    # Register this exact view instance for this run so interactions are routed to it
    bot.add_view(view)

    try:
        await interaction.response.send_message(embed=embed, view=view)
    except discord.Forbidden:
        await interaction.response.send_message("I do not have permission to send messages in this channel.", ephemeral=True)


@bot.tree.command(name="setup_ticket", description="Posts the ticket creation panel.")
@app_commands.describe(category="The category where new tickets should be created.")
@commands.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction, category: discord.CategoryChannel):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    me = interaction.guild.me or interaction.guild.get_member(bot.user.id)
    if not me:
        await interaction.response.send_message("Bot member object unavailable.", ephemeral=True)
        return

    if not me.guild_permissions.manage_channels:
        await interaction.response.send_message("I must have Manage Channels permission in the server to create tickets.", ephemeral=True)
        return

    category_perms = category.permissions_for(me)
    if not category_perms.manage_channels:
        await interaction.response.send_message("I must have Manage Channels permission in that category to create tickets.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Support & Assistance",
        description="Need help? Click the **Create a Ticket** button below to open a private channel with our staff.",
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Please be patient; we'll respond as soon as possible.")

    # Instantiate view, set dynamic custom_id, register view so interactions for this custom_id are handled
    view = TicketPanelView()
    if len(view.children) == 0:
        await interaction.response.send_message("Internal error: ticket view not configured correctly.", ephemeral=True)
        return

    unique_custom_id = f"TICKET_CREATE:{category.id}"
    view.children[0].custom_id = unique_custom_id
    bot.add_view(view)

    try:
        await interaction.response.send_message(embed=embed, view=view)
    except discord.Forbidden:
        await interaction.response.send_message("I do not have permission to send messages in this channel.", ephemeral=True)
        return

    # Persist mapping so we can re-register the view on restart
    config = load_ticket_config()
    config[str(interaction.guild.id)] = category.id
    save_ticket_config(config)
    logger.info(f"Saved ticket panel category {category.id} for guild {interaction.guild.id}")


@bot.tree.command(name="sync", description="Instantly syncs all application commands for this guild.")
@commands.has_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command must be run inside a guild.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        bot.tree.clear_commands(guild=interaction.guild)
        synced = await bot.tree.sync(guild=interaction.guild)
        await bot.tree.sync()  # best-effort global
        await interaction.followup.send(f"✅ Successfully synced **{len(synced)}** commands to this guild.", ephemeral=True)
    except Exception as e:
        logger.exception("Failed to sync commands via /sync")
        await interaction.followup.send(f"❌ Command synchronization failed: {e}", ephemeral=True)


# --- Error handling for app commands ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        try:
            await interaction.response.send_message("You do not have the required permissions to use this command.", ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send("You do not have the required permissions to use this command.", ephemeral=True)
            except Exception:
                logger.exception("Failed to notify about missing permissions")
        return

    logger.exception("App command error")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"An unexpected error occurred: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"An unexpected error occurred: {error}", ephemeral=True)
    except Exception:
        logger.exception("Failed to respond to interaction error")


# --- Entrypoint ---
if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("Please set the DISCORD_BOT_TOKEN environment variable.")
        print("\nERROR: Please set 'DISCORD_BOT_TOKEN' in your environment (Railway -> Variables).\n")
    else:
        bot.run(BOT_TOKEN)
