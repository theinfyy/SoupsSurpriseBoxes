import discord
from discord.ext import commands
from discord import app_commands
import config
import db
import asyncio

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

async def update_stock_display():
    channel = bot.get_channel(config.STOCK_CHANNEL_ID)
    if channel is None:
        print("Stock channel not found.")
        return

    stock = db.get_all_stock()
    content = (
        f"📦 **Current Stock:**\n"
        f"1mil: {stock.get('1mil', 0)}\n"
        f"10mil: {stock.get('10mil', 0)}\n"
        f"25mil: {stock.get('25mil', 0)}"
    )

    message_id = db.get_stock_message_id()
    message = None

    try:
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(content=content)
            except discord.NotFound:
                message = await channel.send(content)
                db.set_stock_message_id(message.id)
        else:
            message = await channel.send(content)
            db.set_stock_message_id(message.id)
    except Exception as e:
        print(f"Error updating stock message: {e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=config.GUILD_ID))
        print(f"Synced {len(synced)} commands to guild {config.GUILD_ID}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    await update_stock_display()

@bot.tree.command(name="buybox", description="Buy a box", guild=discord.Object(id=config.GUILD_ID))
@app_commands.describe(box_type="1mil, 10mil, or 25mil", quantity="How many boxes (max 5)")
async def buybox(interaction: discord.Interaction, box_type: str, quantity: int):
    if not db.get_shop_status():
        await interaction.response.send_message("❌ The shop is currently closed. Please try again later.", ephemeral=True)
        return

    box_type = box_type.lower()
    if box_type not in ["1mil", "10mil", "25mil"]:
        await interaction.response.send_message("Invalid box type.", ephemeral=True)
        return

    if quantity < 1 or quantity > 5:
        await interaction.response.send_message("You can only buy between 1 and 5 boxes at a time.", ephemeral=True)
        return

    remaining = db.get_user_limit(interaction.user.id, box_type)
    if remaining < quantity:
        await interaction.response.send_message(
            f"You can only buy {remaining} more {box_type} boxes in the next 24h.", ephemeral=True)
        return

    if db.get_stock(box_type) < quantity:
        await interaction.response.send_message("Not enough stock.", ephemeral=True)
        return

    db.reduce_stock(box_type, quantity)
    db.log_purchase(interaction.user.id, box_type, quantity)

    await interaction.response.send_message(f"You bought {quantity}x {box_type} box(es)!", ephemeral=True)

    # Notify admin channel (not DM)
    try:
        admin_channel = bot.get_channel(config.ADMIN_ORDER_LOG_CHANNEL_ID)
        if admin_channel:
            await admin_channel.send(f"📦 {interaction.user.name} bought {quantity}x {box_type} box.")
    except Exception as e:
        print(f"Failed to send admin notification: {e}")

    await update_stock_display()

@bot.tree.command(name="restock", description="Admin restocks boxes", guild=discord.Object(id=config.GUILD_ID))
@app_commands.describe(box_type="1mil, 10mil, or 25mil", amount="Amount to add")
async def restock(interaction: discord.Interaction, box_type: str, amount: int):
    if interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message("You don't have permission to do this.", ephemeral=True)
        return

    box_type = box_type.lower()
    if box_type not in ["1mil", "10mil", "25mil"]:
        await interaction.response.send_message("Invalid box type.", ephemeral=True)
        return

    if amount < 1:
        await interaction.response.send_message("Amount must be positive.", ephemeral=True)
        return

    db.add_stock(box_type, amount)
    await interaction.response.send_message(f"Restocked {amount}x {box_type} boxes.", ephemeral=True)
    await update_stock_display()

@bot.tree.command(name="stock", description="View current stock", guild=discord.Object(id=config.GUILD_ID))
async def stock(interaction: discord.Interaction):
    stock = db.get_all_stock()
    content = (
        f"📦 **Current Stock:**\n"
        f"1mil: {stock.get('1mil', 0)}\n"
        f"10mil: {stock.get('10mil', 0)}\n"
        f"25mil: {stock.get('25mil', 0)}"
    )
    await interaction.response.send_message(content, ephemeral=True)

@bot.tree.command(name="cooldown", description="Check your box purchase cooldowns", guild=discord.Object(id=config.GUILD_ID))
async def cooldown(interaction: discord.Interaction):
    cooldowns = db.get_user_cooldowns(interaction.user.id)
    messages = []
    for box_type in ["1mil", "10mil", "25mil"]:
        bought = cooldowns.get(box_type, 0)
        remaining = db.get_remaining_cooldown(interaction.user.id, box_type)
        messages.append(f"{box_type}: {bought} bought in last 24h, cooldown remaining: {remaining}")
    await interaction.response.send_message("\n".join(messages), ephemeral=True)

@bot.tree.command(name="cdreset", description="Reset all cooldowns (admin only)", guild=discord.Object(id=config.GUILD_ID))
async def cdreset(interaction: discord.Interaction):
    if interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message("You don't have permission to do this.", ephemeral=True)
        return

    db.reset_cooldowns()
    await interaction.response.send_message("✅ All cooldowns have been reset.", ephemeral=True)

@bot.tree.command(name="clearorders", description="Clear all messages from the orders channel (admin only)", guild=discord.Object(id=config.GUILD_ID))
async def clearorders(interaction: discord.Interaction):
    if interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message("You don't have permission to do this.", ephemeral=True)
        return

    channel = bot.get_channel(config.ADMIN_ORDER_LOG_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message("Orders channel not found.", ephemeral=True)
        return

    deleted = []
    async for message in channel.history(limit=100):
        try:
            await message.delete()
            deleted.append(message)
        except Exception as e:
            print(f"Failed to delete message: {e}")

    await interaction.response.send_message(f"✅ Deleted {len(deleted)} messages from orders channel.", ephemeral=True)

@bot.tree.command(name="open", description="Open or close the shop (admin only)", guild=discord.Object(id=config.GUILD_ID))
@app_commands.describe(state="true to open, false to close")
async def open_shop(interaction: discord.Interaction, state: bool):
    if interaction.user.id != config.ADMIN_USER_ID:
        await interaction.response.send_message("You don't have permission to do this.", ephemeral=True)
        return

    db.set_shop_status(state)
    status_text = "open" if state else "closed"
    await interaction.response.send_message(f"Shop is now {status_text}.", ephemeral=True)

async def main():
    await bot.start(config.TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
