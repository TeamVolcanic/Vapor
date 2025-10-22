import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
from datetime import datetime
import google.generativeai as genai

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

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

# -------------------- INTERACTION HANDLER --------------------

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data["custom_id"]
    user = interaction.user
    guild = interaction.guild

    if custom_id.startswith("verify_ticket:") or custom_id == "open_ticket":
        now = datetime.utcnow()
        if user.id in cooldowns and (now - cooldowns[user.id]).total_seconds() < 60:
            await interaction.response.send_message("⏳ Please wait before opening another ticket.", ephemeral=True)
            return
        cooldowns[user.id] = now

        gid = guild.id
        ticket_counter.setdefault(gid, 1)
        ticket_number = ticket_counter[gid]
        ticket_counter[gid] += 1

        category_name = "Tickets"
        prefix = "ticket"
        role_id = None

        if custom_id.startswith("verify_ticket:"):
            category_name = "Verification"
            prefix = "verify"
            role_id = int(custom_id.split(":")[1])

        category = discord.utils.get(guild.categories, name=category_name) or await guild.create_category(category_name)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await guild.create_text_channel(f"{prefix}-{ticket_number}", category=category, overwrites=overwrites)
        embed = discord.Embed(
            title=f"🎟️ {prefix.capitalize()} #{ticket_number}",
            description="Thanks for reaching out! A staff member will be with you shortly.",
            color=discord.Color.green()
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Claim Ticket", style=discord.ButtonStyle.secondary, custom_id="claim_ticket"))
        view.add_item(discord.ui.Button(label="Close with Reason", style=discord.ButtonStyle.danger, custom_id=f"close_with_reason:{role_id}" if role_id else "close_with_reason"))
        view.add_item(discord.ui.Button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id=f"close_ticket:{role_id}" if role_id else "close_ticket"))
        await channel.send(content=user.mention, embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

    elif custom_id == "claim_ticket":
        await interaction.response.send_message(f"🎟️ Ticket claimed by {user.mention}. We’ll assist you shortly!", ephemeral=False)

    elif custom_id.startswith("close_ticket"):
        role_id = custom_id.split(":")[1] if ":" in custom_id else None
        role = guild.get_role(int(role_id)) if role_id else None
        user_mentions = [m for m in interaction.channel.members if not m.bot and not m.guild_permissions.administrator]
        for member in user_mentions:
            if role:
                await member.add_roles(role)
            try:
                await member.send("✅ Your ticket has been resolved. Thanks for reaching out!")
            except:
                pass
        await interaction.response.send_message("🔒 Ticket closed.", ephemeral=True)
        await interaction.channel.delete()

    elif custom_id.startswith("close_with_reason"):
        role_id = custom_id.split(":")[1] if ":" in custom_id else None
        await interaction.response.send_modal(CloseReasonModal(role_id))

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

class CloseReasonModal(discord.ui.Modal, title="Close Ticket with Reason"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph)

    def __init__(self, role_id):
        super().__init__()
        self.role_id = role_id

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        channel = interaction.channel
        closer = interaction.user
        role = guild.get_role(int(self.role_id)) if self.role_id else None

        channel._close_reason = self.reason.value
        channel._closer = closer
        channel._role_to_assign = role

        embed = discord.Embed(
            title="❌ Ticket Closure Requested",
            description=f"{closer.mention} wants to close this ticket.\n\n**Reason:** {self.reason.value}",
            color=discord.Color.red()
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Confirm Close", style=discord.ButtonStyle.danger, custom_id="confirm_close"))
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message("🔒 Closure request sent. Awaiting confirmation.", ephemeral=True)
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

# -------------------- GEMINI /prompt COMMAND --------------------

@bot.tree.command(name="prompt")
@app_commands.describe(channel="Channel to post the response", prompt="Your message or question")
async def prompt(interaction: discord.Interaction, channel: discord.TextChannel, prompt: str):
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
    except Exception as e:
        text = f"⚠️ Gemini API error: {e}"

    embed = discord.Embed(
        title="💡 Vapor Insight",
        description=text,
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Generated by Gemini")
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
