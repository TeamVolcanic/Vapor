#!/usr/bin/env python3
"""
Vapor Bot - Full Verification & Interactive Ticket System
- Old /setup_interactive_button style
- Verify button creates private tickets with 1-min cooldown
- Ticket owner and admins can close tickets
- Admins can claim/close/close-with-reason
- AI-style embeds with emojis
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

# --- Per-user cooldowns ---
user_cooldowns = {}

# --- AI-style Embed Generator ---
def generate_ai_embed(action: str, label: str, target_info: str):
    action = action.lower()
    color = discord.Color.random()
    if action == "ticket":
        title = "🎫 Need Assistance?"
        description = f"Hey there! 👋\n\nClick **{label}** below to open your private **verification ticket**.\n🕒 Staff will respond shortly!\n💬 Explain your issue clearly."
        color = discord.Color.blue()
    elif action == "verify":
        title = "🛡️ Server Verification"
        description = f"Welcome! 🎉\n\nClick **{label}** to create your verification ticket.\n📜 Read the rules first!\n🤖 This keeps the server secure."
        color = discord.Color.red()
    elif action == "role":
        title = "🎭 Claim Your Role!"
        description = f"Press **{label}** below to get your role instantly.\n✨ Unlock exclusive channels!"
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

        # Cooldown
        if user_id in user_cooldowns and now - user_cooldowns[user_id] < 60:
            await interaction.response.send_message(
                "⏱ You must wait 1 minute before creating another ticket.", ephemeral=True
            )
            return
        user_cooldowns[user_id] = now

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        # Category
        category_name = "━━━━⮩VERIFICATION⮨━━━━"
        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            category = await guild.create_category(name=category_name)

        # Ticket channel
        ticket_number = random.randint(1, 10_000_000_000_000_000_000)
        ticket_name = f"verify-{ticket_number}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
        }
        # Admins
        for member in guild.members:
            if member.guild_permissions.administrator:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)

        ticket_channel = await guild.create_text_channel(name=ticket_name, category=category, overwrites=overwrites)

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

# --- Old /setup_interactive_button ---
@bot.tree.command(name="setup_interactive_button", description="Posts a message with a custom button for roles or tickets.")
@app_commands.describe(
    action="Action: verify, role, ticket",
    label="Button text",
    role_name="[Role] Name",
    ticket_category="[Ticket] Category",
    message_content="Optional text above button"
)
@commands.has_permissions(administrator=True)
async def setup_interactive_button(interaction: discord.Interaction, action: str, label: str,
                                   role_name: Optional[str] = None, ticket_category: Optional[discord.CategoryChannel] = None,
                                   message_content: Optional[str] = None):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ Must be run in a server.", ephemeral=True)
        return

    action = action.lower()
    custom_id = None
    target_info = ""

    if action == "role":
        if not role_name:
            await interaction.response.send_message("❌ Missing role_name.", ephemeral=True)
            return
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            await interaction.response.send_message(f"❌ Role `{role_name}` not found.", ephemeral=True)
            return
        custom_id = f"INTERACTIVE_ACTION:ROLE:{role_name}"
        target_info = f"Role: {role_name}"
    elif action == "ticket":
        if ticket_category is None:
            await interaction.response.send_message("❌ Must select a category.", ephemeral=True)
            return
        custom_id = f"INTERACTIVE_ACTION:TICKET:{ticket_category.id}"
        target_info = f"Category: #{ticket_category.name}"
    elif action == "verify":
