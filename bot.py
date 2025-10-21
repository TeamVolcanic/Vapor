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
            "Hey there! 👋\n\n"
            "If you're facing an issue or have a question, click the **{label}** button below to "
            "open a **private support ticket**.\n\n"
            "🕒 Our team will respond shortly.\n"
            "💬 Feel free to explain your issue once your ticket opens!"
        ).format(label=label)
        color = discord.Color.blue()

    elif action == "role":
        title = "🎭 Claim Your Role!"
        description = (
            "Ready to stand out? 🌟\n\n"
            "Press the **{label}** button below to get your role instantly.\n"
            "✨ Show off your group and unlock exclusive channels!"
        ).format(label=label)
        color = discord.Color.green()

    elif action == "veri
