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
cooldowns = {}
ticket_counter = {}
reaction_roles = {}

# -------------------- TICKET PANEL --------------------

class TicketView(discord.ui.View):
    def __init__(self, embed_text, button_label):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label=button_label, style=discord.ButtonStyle.primary, custom_id="open_ticket"))

@bot.tree.command(name="ticketpanel")
@app_commands.describe(channel="Channel to post the panel", embed_text="Embed message", button_label="Button label")
async def ticketpanel(interaction: discord.Interaction, channel: discord.TextChannel, embed_text: str, button_label: str):
    embed = discord.Embed(
        title="🎫 Vapor Ticket Panel",
        description=f"{embed_text}\n\nNeed help? Tap the button below and we’ll get you sorted.",
        color=discord.Color.blue()
    )
    view = TicketView(embed_text, button_label)
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message("Ticket panel created.", ephemeral=True)

# -------------------- VERIFICATION PANEL --------------------

class VerificationView(discord.ui.View):
    def __init__(self, embed_text, button_label, role_id):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label=button_label, style=discord.ButtonStyle.success, custom_id=f"verify_ticket:{role_id}"))

@bot.tree.command(name="verificationpanel")
@app_commands.describe(channel="Channel to post the panel", embed_text="Embed message", button_label="Button label", role="Role to assign when verified")
async def verificationpanel(interaction: discord.Interaction, channel: discord.TextChannel, embed_text: str, button_label: str, role: discord.Role):
    embed = discord.Embed(
        title="✅ Vapor Verification",
        description=f"{embed_text}\n\nClick below to confirm your access and unlock your role.",
        color=discord.Color.green()
    )
    view = VerificationView(embed_text, button_label, role.id)
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message("Verification panel created.", ephemeral=True)
    # -------------------- INTERACTION CONTINUED --------------------

    elif custom_id == "confirm_close":
        channel = interaction.channel
        reason = getattr(channel, "_close_reason", "No reason provided.")
        closer = getattr(channel, "_closer", interaction.user)
        role = getattr(channel, "_role_to_assign", None)
        user_mentions = [m for m in channel.members if not m.bot and not m.guild_permissions.administrator]

        for member in user_mentions:
            if role:
                await member.add_roles(role)
            try:
                await member.send(
                    f"🔒 Your ticket was closed by {closer.name}.\n**Reason:** {reason}"
                )
            except:
                pass

        await interaction.response.send_message("✅ Ticket closed and channel will be deleted.", ephemeral=True)
        await channel.delete()

# -------------------- ADMIN RENAME --------------------

@bot.tree.command(name="rename_ticket")
@app_commands.describe(new_name="New channel name")
async def rename_ticket(interaction: discord.Interaction, new_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await interaction.channel.edit(name=new_name)
    await interaction.response.send_message(f"Channel renamed to {new_name}", ephemeral=True)

# -------------------- VERIFY COMMANDS --------------------

@bot.tree.command(name="verify")
@app_commands.describe(role="Role to assign when verified")
async def verify(interaction: discord.Interaction, role: discord.Role):
    await interaction.user.add_roles(role)
    embed = discord.Embed(
        title="✅ Verified",
        description=f"You now have access to the **{role.name}** role. Welcome aboard!",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="mverify")
@app_commands.describe(user="User to verify", role="Role to assign")
async def mverify(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await user.add_roles(role)
    embed_admin = discord.Embed(
        title="✅ Verification Complete",
        description=f"{user.mention} has been granted the **{role.name}** role.",
        color=discord.Color.green()
    )
    embed_user = discord.Embed(
        title="🎉 You're In!",
        description=f"You’ve been verified and assigned the **{role.name}** role by {interaction.user.mention}.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed_admin, ephemeral=True)
    try:
        await user.send(embed=embed_user)
    except:
        pass

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
