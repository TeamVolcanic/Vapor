import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
# -------------------- REACTION ROLE --------------------

@bot.tree.command(name="reactionrole")
@app_commands.describe(emoji="Emoji to react with", role="Role to assign", prompt="Embed message")
async def reactionrole(interaction: discord.Interaction, emoji: str, role: discord.Role, prompt: str):
    embed = discord.Embed(
        title=f"{emoji} {role.name} Role",
        description=f"{prompt}\n\nReact with {emoji} to get the role!",
        color=discord.Color.purple()
    )
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction(emoji)
    reaction_roles[msg.id] = {emoji: role.id}
    await interaction.response.send_message("Reaction role message posted.", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.message_id in reaction_roles:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        emoji = str(payload.emoji)
        role_id = reaction_roles[payload.message_id].get(emoji)
        if role_id:
            role = guild.get_role(role_id)
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id in reaction_roles:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        emoji = str(payload.emoji)
        role_id = reaction_roles[payload.message_id].get(emoji)
        if role_id:
            role = guild.get_role(role_id)
            await member.remove_roles(role)

# -------------------- DETAIL MESSAGE --------------------

@bot.tree.command(name="detailmessage")
@app_commands.describe(channel="Channel to post the message", prompt="Message content")
async def detailmessage(interaction: discord.Interaction, channel: discord.TextChannel, prompt: str):
    embed = discord.Embed(
        title="📢 Vapor Announcement",
        description=f"{prompt}\n\nLet us know if you have questions or feedback!",
        color=discord.Color.gold()
    )
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Message posted.", ephemeral=True)

# -------------------- PROMPT COMMAND --------------------

@bot.tree.command(name="prompt")
@app_commands.describe(channel="Channel to post the response", prompt="Your message or question")
async def prompt(interaction: discord.Interaction, channel: discord.TextChannel, prompt: str):
    response = f"✨ {prompt}\n\n🔍 Here's what we think:\n{prompt.capitalize()} is a great starting point. Let’s explore it together!"
    embed = discord.Embed(
        title="💡 Vapor Insight",
        description=response,
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Powered by Vapor")
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Insight posted.", ephemeral=True)

# -------------------- BOT READY --------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Vapor is online as {bot.user}")

# -------------------- RUN --------------------

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN missing in .env")
    else:
        bot.run(TOKEN)
