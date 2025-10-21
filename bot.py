#!/usr/bin/env python3
"""
Vapor Bot - Verification Ticket System
- Verify button creates private tickets
- Ticket numbering: 1-10^19
- 1-minute per-user cooldown
- Ticket owner and admins can close tickets
- Admins can claim/close/close-with-reason
- AI-style embeds with emojis
- Global slash command sync
"""

import asyncio
import os
import random
import logging
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands, ui

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vapor-bot")

bot = commands.Bot(command_prefix=None, intents=intents)

# --- Cooldown tracking ---
user_cooldowns = {}

# --- AI-style Embed Generator ---
def generate_ai_embed(action: str, label: str, target_info: str):
    action = action.lower()
    color = discord.Color.random()

    if action == "ticket":
        title = "🎫 Need Assistance?"
        description = (
            f"Hey there! 👋\n\n"
            f"Click **{label}** below to open your private **verification ticket**.\n\n"
            "🕒 Staff will respond shortly!\n💬 Explain your issue clearly."
        )
        color = discord.Color.blue()
    elif action == "verify":
        title = "🛡️ Server Verification"
        description = (
            f"Welcome! 🎉\n\n"
            f"Click **{label}** below to create your verification ticket.\n"
            "📜 Make sure to read the rules first!\n"
            "🤖 This helps us keep the server secure."
        )
        color = discord.Color.red()
    elif action == "role":
        title = "🎭 Claim Your Role!"
        description = (
            f"Press **{label}** below to get your role instantly.\n"
            "✨ Unlock exclusive channels!"
        )
        color = discord.Color.green()
    else:
        title = "✨ Interactive System"
        description = f"Click **{label}** to continue."

    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Action: {action.capitalize()} | Target: {target_info}")
    return embed

# --- Verification Ticket View ---
class VerificationView(ui.View):
    def __init__(self, timeout=None):
        super().__init__(timeout=timeout)

    @ui.button(label="Verify Me", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: ui.Button):
        user_id = interaction.user.id
        now = asyncio.get_event_loop().time()

        # Per-user cooldown
        if user_id in user_cooldowns and now - user_cooldowns[user_id] < 60:
            await interaction.response.send_message(
                "⏱ You must wait 1 minute before creating another ticket.", ephemeral=True
            )
            return
        user_cooldowns[user_id] = now

        # Category
        category_name = "━━━━⮩VERIFICATION⮨━━━━"
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            category = await guild.create_category(name=category_name)

        # Ticket name
        ticket_number = random.randint(1, 10_000_000_000_000_000_000)
        ticket_name = f"verify-{ticket_number}"

        # Permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
        }
        # Admins
        for member in guild.members:
            if member.guild_permissions.administrator:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)

        # Create ticket channel
        ticket_channel = await guild.create_text_channel(name=ticket_name, category=category, overwrites=overwrites)

        # Add buttons (claim/close/close-with-reason)
        view = TicketActionView(ticket_owner=interaction.user)
        embed = generate_ai_embed("ticket", "Ticket Actions", ticket_channel.name)
        await ticket_channel.send(f"{interaction.user.mention} Your verification ticket is created!", embed=embed, view=view)
        await interaction.response.send_message(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

# --- Ticket Action View ---
class TicketActionView(ui.View):
    def __init__(self, ticket_owner: discord.Member, timeout=None):
        super().__init__(timeout=timeout)
        self.ticket_owner = ticket_owner
        self.claimed_by: Optional[discord.Member] = None

    @ui.button(label="Claim Ticket", style=discord.ButtonStyle.blurple, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can claim tickets.", ephemeral=True)
            return
        self.claimed_by = interaction.user
        await interaction.response.send_message(f"🛡️ Ticket claimed by {interaction.user.mention}", ephemeral=False)

    @ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.ticket_owner and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only the ticket owner or admin can close this ticket.", ephemeral=True)
            return
        await interaction.response.send_message("❌ Ticket closing...", ephemeral=False)
        await asyncio.sleep(2)
        await interaction.channel.delete()

    @ui.button(label="Close with Reason", style=discord.ButtonStyle.gray, custom_id="close_reason")
    async def close_reason(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.ticket_owner and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only the ticket owner or admin can close this ticket.", ephemeral=True)
            return

        modal = CloseReasonModal(ticket_channel=interaction.channel)
        await interaction.response.send_modal(modal)

# --- Close Reason Modal ---
class CloseReasonModal(ui.Modal, title="Close Ticket with Reason"):
    reason = ui.TextInput(label="Reason for closing", style=discord.TextStyle.paragraph)

    def __init__(self, ticket_channel: discord.TextChannel):
        super().__init__()
        self.ticket_channel = ticket_channel

    async def on_submit(self, interaction: discord.Interaction):
        await self.ticket_channel.send(f"📝 Ticket closed with reason: {self.reason.value}")
        await interaction.response.send_message("✅ Ticket will be closed shortly.", ephemeral=True)
        await asyncio.sleep(2)
        await self.ticket_channel.delete()

# --- Setup Interactive Button Command (Old Command) ---
@bot.tree.command(name="setup_interactive_button", description="Posts a message with a custom button for roles or tickets.")
@app_commands.describe(
    action="The action this button should perform (verify, role, or ticket).",
    label="The text on the button.",
    role_name="[For Role] The name of the role to assign.",
    ticket_category="[For Ticket] The category where new ticket channels will be created.",
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
    action = action.lower()
    custom_id = None
    target_info = ""

    if action == "role":
        if not role_name:
            await interaction.response.send_message("❌ Missing role_name for role action.", ephemeral=True)
            return
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if not role:
            await interaction.response.send_message(f"❌ Role `{role_name}` not found.", ephemeral=True)
            return
        custom_id = f"INTERACTIVE_ACTION:ROLE:{role_name}"
        target_info = f"Role: {role_name}"

    elif action == "ticket":
        if ticket_category is None:
            await interaction.response.send_message("❌ You must select a category for tickets.", ephemeral=True)
            return
        custom_id = f"INTERACTIVE_ACTION:TICKET:{ticket_category.id}"
        target_info = f"Category: #{ticket_category.name}"

    elif action == "verify":
        custom_id = "verify_button"
        target_info = "#━━━━⮩VERIFICATION⮨━━━━"

    else:
        await interaction.response.send_message("❌ Invalid action. Use `verify`, `role`, or `ticket`.", ephemeral=True)
        return

    view = ui.View(timeout=None)
    view.add_item(ui.Button(label=label, style=discord.ButtonStyle.primary, custom_id=custom_id))

    embed = generate_ai_embed(action, label, target_info)

    bot.add_view(view)
    await interaction.response.send_message(embed=embed, view=view)

# --- Startup ---
@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    bot.add_view(VerificationView())
    try:
        synced = await bot.tree.sync()  # GLOBAL sync
        logger.info(f"Synced {len(synced)} commands globally!")
    except Exception as e:
        logger.exception("Failed to sync commands: %s", e)

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("❌ DISCORD_BOT_TOKEN not set in environment.")
        print("Set DISCORD_BOT_TOKEN in your hosting environment.")
    else:
        bot.run(BOT_TOKEN)
