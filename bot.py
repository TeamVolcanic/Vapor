#!/usr/bin/env python3
"""
Vapor Bot (Enhanced Version)
- Keeps Ticket + Role System
- Adds AI-Generated Embed Descriptions with Emojis
- Improved Verification Embed with #━━━━⮩VERIFICATION⮨━━━━ Style
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
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
TICKET_CONFIG_FILE = "ticket_config.json"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vapor-bot")

bot = commands.Bot(command_prefix=None, intents=intents)


# --- Persistence Helpers ---
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


# --- AI-style Embed Generator ---
def generate_ai_embed(action: str, label: str, target_info: str):
    """Creates detailed, emoji-filled embeds based on the action type."""
    action = action.lower()
    color = discord.Color.random()

    if action == "ticket":
        title = "🎫 Need Assistance?"
        description = (
            f"Hey there! 👋\n\n"
            f"If you're facing an issue or have a question, click the **{label}** button below to "
            f"open a **private support ticket**.\n\n"
            "🕒 Our team will respond shortly.\n"
            "💬 Feel free to explain your issue once your ticket opens!"
        )
        color = discord.Color.blue()

    elif action == "role":
        title = "🎭 Claim Your Role!"
        description = (
            f"Ready to stand out? 🌟\n\n"
            f"Press the **{label}** button below to get your role instantly.\n"
            "✨ Show off your group and unlock exclusive channels!"
        )
        color = discord.Color.green()

    elif action == "verify":
        title = "🛡️ Server Verification"
        description = (
            f"Welcome to the community! 🎉\n\n"
            f"To access all channels, click the **{label}** button below to verify.\n\n"
            "📜 Make sure you’ve read the rules before verifying!\n"
            "🤖 Verification helps us keep this server secure and friendly."
        )
        color = discord.Color.red()

    else:
        title = "✨ Interactive System"
        description = f"Click the **{label}** button below to continue."

    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Action: {action.capitalize()} | Target: #━━━━⮩VERIFICATION⮨━━━━ | Info: {target_info}")
    return embed


# --- Verification View ---
class VerificationView(ui.View):
    def __init__(self, verified_role_name: str = "Verified"):
        super().__init__(timeout=None)
        self.verified_role_name = verified_role_name

    @ui.button(label="Verify Me", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.guild is None:
            await interaction.response.send_message("This button only works inside servers.", ephemeral=True)
            return

        role = discord.utils.get(interaction.guild.roles, name=self.verified_role_name)
        if role is None:
            await interaction.response.send_message(f"Error: `{self.verified_role_name}` role does not exist.", ephemeral=True)
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None:
            member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            await interaction.response.send_message("Could not find your member profile.", ephemeral=True)
            return

        if role in member.roles:
            await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason="User verified")
            await interaction.response.send_message(
                f"🛡️ Verification complete! Welcome aboard, {member.mention}! You now have **{self.verified_role_name}** access.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing permission to assign roles.", ephemeral=True)
        except Exception as e:
            logger.exception("Verification role assignment failed: %s", e)
            await interaction.response.send_message("⚠️ Something went wrong while verifying you.", ephemeral=True)


# --- Main Command Upgrades ---
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
    if interaction.guild is None:
        await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        return

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

    # AI-styled embed creation
    embed = generate_ai_embed(action, label, target_info)

    bot.add_view(view)
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to send embeds here.", ephemeral=True)


# --- Verification Setup Command ---
@bot.tree.command(name="setup_verify", description="Posts the verification message with the fancy AI embed.")
@commands.has_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = generate_ai_embed("verify", "Verify Me", "#━━━━⮩VERIFICATION⮨━━━━")
    view = VerificationView()
    bot.add_view(view)
    await interaction.response.send_message(embed=embed, view=view)


# --- Startup Logic ---
@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    bot.add_view(VerificationView())
    logger.info("✅ VerificationView registered.")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} commands successfully.")
    except Exception as e:
        logger.exception("Failed to sync commands: %s", e)


if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("❌ DISCORD_BOT_TOKEN not set in environment.")
        print("Set DISCORD_BOT_TOKEN in your hosting environment.")
    else:
        bot.run(BOT_TOKEN)
