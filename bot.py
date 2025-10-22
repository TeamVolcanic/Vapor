import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

reaction_roles = {}

@bot.tree.command(name="purge", description="Delete messages from the channel")
@app_commands.describe(
    amount="Number of messages to delete (default: 50, max: 100)",
    user="User whose messages to delete (optional)"
)
async def purge(
    interaction: discord.Interaction, 
    amount: int = 50, 
    user: discord.Member = None
):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ You need the 'Manage Messages' permission to use this command.",
            ephemeral=True
        )
        return
    
    if amount < 1:
        await interaction.response.send_message(
            "❌ Amount must be at least 1.",
            ephemeral=True
        )
        return
    
    if amount > 100:
        amount = 100
        await interaction.response.send_message(
            "⚠️ Discord limits bulk deletion to 100 messages. Proceeding with 100...",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"🗑️ Deleting messages...",
            ephemeral=True
        )
    
    try:
        if user:
            def check_user(message):
                return message.author.id == user.id
            
            deleted = await interaction.channel.purge(limit=amount * 2, check=check_user)
            deleted_count = len(deleted)
            
            await interaction.followup.send(
                f"✅ Deleted {deleted_count} message(s) from {user.mention}.",
                ephemeral=True
            )
        else:
            deleted = await interaction.channel.purge(limit=amount)
            deleted_count = len(deleted)
            
            await interaction.followup.send(
                f"✅ Deleted {deleted_count} message(s).",
                ephemeral=True
            )
    
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ I don't have permission to delete messages in this channel.",
            ephemeral=True
        )
    except discord.HTTPException as e:
        await interaction.followup.send(
            f"❌ An error occurred: {e}",
            ephemeral=True
        )

@bot.tree.command(name="embedbutton", description="Send an embed with a clickable button")
@app_commands.describe(channel="Channel to post the embed", title="Embed title", message="Embed message")
async def embedbutton(interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str):
    class ButtonView(discord.ui.View):
        @discord.ui.button(label="🔗 Click Me", style=discord.ButtonStyle.green)
        async def button_click(self, button: discord.ui.Button, interaction: discord.Interaction):
            await interaction.response.send_message("✅ You clicked the button!", ephemeral=True)

    embed = discord.Embed(title=title, description=message, color=discord.Color.green())
    await channel.send(embed=embed, view=ButtonView())
    await interaction.response.send_message("✅ Embed with button sent.", ephemeral=True)

@bot.tree.command(name="reactionrole", description="Create a reaction role message")
@app_commands.describe(channel="Channel to post message", emoji="Emoji to react with", role="Role to assign")
async def reactionrole(interaction: discord.Interaction, channel: discord.TextChannel, emoji: str, role: discord.Role):
    message = await channel.send(
        embed=discord.Embed(
            title="🎭 Reaction Role",
            description=f"React with {emoji} to get the {role.mention} role.",
            color=discord.Color.orange()
        )
    )
    await message.add_reaction(emoji)
    reaction_roles[message.id] = {"emoji": emoji, "role_id": role.id}
    await interaction.response.send_message("✅ Reaction role set.", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.message_id in reaction_roles:
        data = reaction_roles[payload.message_id]
        if str(payload.emoji) == data["emoji"]:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(data["role_id"])
            member = guild.get_member(payload.user_id)
            if member and role:
                await member.add_roles(role)
                print(f"✅ Added {role.name} to {member.display_name}")

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id in reaction_roles:
        data = reaction_roles[payload.message_id]
        if str(payload.emoji) == data["emoji"]:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(data["role_id"])
            member = guild.get_member(payload.user_id)
            if member and role:
                await member.remove_roles(role)
                print(f"❌ Removed {role.name} from {member.display_name}")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user} | Ready on {len(bot.guilds)} servers.")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN missing in .env")
    else:
        bot.run(TOKEN)
