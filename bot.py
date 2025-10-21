@bot.tree.command(name="setup_interactive_button", description="Posts a message with a custom button for roles or tickets.")
@app_commands.describe(
    action="The action this button should perform (verify, role, or ticket).",
    label="Text on the button",
    role_name="[Role] Name of role",
    ticket_category="[Ticket] Category for new tickets",
    message_content="Optional text above the button"
)
@commands.has_permissions(administrator=True)
async def setup_interactive_button(
    interaction: discord.Interaction,
    action: str,
    label: str,
    role_name: Optional[str] = None,
    ticket_category: Optional[discord.CategoryChannel] = None,
    message_content: Optional[str] = None
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ This must be run in a server.", ephemeral=True)
        return

    action = action.lower()
    target_info = ""

    # Set up button and target info
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
        if not ticket_category:
            await interaction.response.send_message("❌ Must select a category.", ephemeral=True)
            return
        custom_id = f"INTERACTIVE_ACTION:TICKET:{ticket_category.id}"
        target_info = f"Category: #{ticket_category.name}"

    elif action == "verify":
        custom_id = "verify_button"
        target_info = "#━━━━⮩VERIFICATION⮨━━━━"

    else:
        await interaction.response.send_message("❌ Invalid action. Use `verify`, `role`, or `ticket`.", ephemeral=True)
        return

    # Create view and button
    view = ui.View(timeout=None)
    view.add_item(ui.Button(label=label, style=discord.ButtonStyle.primary, custom_id=custom_id))

    # AI embed
    embed = generate_ai_embed(action, label, target_info)
    if message_content:
        embed.description = f"{message_content}\n\n{embed.description}"

    bot.add_view(view)
    await interaction.response.send_message(embed=embed, view=view)
