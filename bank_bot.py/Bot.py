import os
import discord
from discord import app_commands
from discord.ext import commands
import random
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Configuration files ---
BALANCES_FILE       = "balances.json"
BANK_BALANCE_FILE   = "bank_balance.json"
BUSINESSES_FILE     = "businesses.json"
SETTINGS_FILE       = "settings.json"

DEPOSIT_CHANNEL_ID  = 1422789849446092820
WITHDRAW_CHANNEL_ID = 1422790276967170098
GAMBLING_CHANNEL_ID = 1422790430843469955

# --- Helper I/O ---
def load_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return default
    return default

def save_json(path: str, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

balances   = load_json(BALANCES_FILE, {})
bank       = load_json(BANK_BALANCE_FILE, {"balance": 0})
businesses = load_json(BUSINESSES_FILE, {})
settings   = load_json(SETTINGS_FILE, {"gambling_enabled": True})

def get_balance(user_id: int) -> int:
    return balances.get(str(user_id), 0)

def update_balance(user_id: int, delta: int):
    balances[str(user_id)] = get_balance(user_id) + delta
    save_json(BALANCES_FILE, balances)

def get_bank_balance() -> int:
    return bank.get("balance", 0)

def update_bank_balance(delta: int):
    bank["balance"] = get_bank_balance() + delta
    save_json(BANK_BALANCE_FILE, bank)

def save_businesses():
    save_json(BUSINESSES_FILE, businesses)

def save_settings():
    save_json(SETTINGS_FILE, settings)

# --- Bot ready ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Connected as {bot.user}")

# --- Global error handler for slash commands ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # If we already sent a response or deferred, follow up
    if interaction.response.is_done():
        await interaction.followup.send(
            "❌ An unexpected error occurred. Please try again later.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ An error occurred processing your command.", ephemeral=True
        )
    # Log the error details
    print(f"Error in command '{interaction.command.name}': {error!r}")

# --- /toggle_gambling ---
@bot.tree.command(name="toggle_gambling", description="Enable or disable gambling (staff only)")
async def slash_toggle_gambling(interaction: discord.Interaction):
    if "Bank management board" not in [r.name for r in interaction.user.roles]:
        return await interaction.response.send_message("You do not have permission.", ephemeral=True)

    settings["gambling_enabled"] = not settings["gambling_enabled"]
    save_settings()
    status = "enabled" if settings["gambling_enabled"] else "disabled"
    await interaction.response.send_message(f"Gambling is now {status}.", ephemeral=False)

# --- /create_business ---
@bot.tree.command(name="create_business", description="Open a new business account")
@app_commands.describe(name="Unique business account name")
async def slash_create_business(interaction: discord.Interaction, name: str):
    if name.lower() in businesses:
        return await interaction.response.send_message("A business with that name already exists.", ephemeral=True)

    businesses[name.lower()] = {"owner": interaction.user.id, "members": [], "balance": 0}
    save_businesses()
    await interaction.response.send_message(f"Business '{name}' created. You are the owner.", ephemeral=True)

# --- /business_add_member ---
@bot.tree.command(name="business_add_member", description="Allow a user to operate your business account")
@app_commands.describe(business="Your business name", member="User to add")
async def slash_business_add_member(interaction: discord.Interaction, business: str, member: discord.Member):
    biz = businesses.get(business.lower())
    if not biz or biz["owner"] != interaction.user.id:
        return await interaction.response.send_message("You are not the owner of that business.", ephemeral=True)

    if member.id in biz["members"]:
        return await interaction.response.send_message(f"{member.display_name} is already a member.", ephemeral=True)

    biz["members"].append(member.id)
    save_businesses()
    await interaction.response.send_message(f"{member.mention} can now operate '{business}'.", ephemeral=True)

# --- /business_dashboard ---
@bot.tree.command(name="business_dashboard", description="View details of your business account")
@app_commands.describe(business="Business account name")
async def slash_business_dashboard(interaction: discord.Interaction, business: str):
    # defer early to avoid interaction timeout during fetch_user calls
    await interaction.response.defer(ephemeral=True)

    biz = businesses.get(business.lower())
    allowed = [biz["owner"]] + biz.get("members", []) if biz else []
    if not biz or interaction.user.id not in allowed:
        return await interaction.followup.send("You are not authorized for that business.", ephemeral=True)

    # resolve owner
    owner = bot.get_user(biz["owner"]) or await bot.fetch_user(biz["owner"])
    owner_label = f"{owner.name}#{owner.discriminator}"

    # resolve members
    member_labels = []
    for mid in biz["members"]:
        u = bot.get_user(mid) or await bot.fetch_user(mid)
        member_labels.append(f"{u.name}#{u.discriminator}")

    members_text = ", ".join(member_labels) if member_labels else "None"
    await interaction.followup.send(
        f"Business '{business}' Dashboard\n"
        f"- Owner: {owner_label}\n"
        f"- Members: {members_text}\n"
        f"- Balance: ${biz['balance']}"
    )

# --- /delete_business ---
@bot.tree.command(name="delete_business", description="Delete a business account (staff only)")
@app_commands.describe(business="Name of the business to delete")
async def slash_delete_business(interaction: discord.Interaction, business: str):
    if "Bank management board" not in [r.name for r in interaction.user.roles]:
        return await interaction.response.send_message("You do not have permission.", ephemeral=True)

    if business.lower() not in businesses:
        return await interaction.response.send_message("No such business exists.", ephemeral=True)

    businesses.pop(business.lower())
    save_businesses()
    await interaction.response.send_message(f"Business '{business}' has been deleted.", ephemeral=False)

# --- /check_account ---
@bot.tree.command(
    name="check_account",
    description="Check any personal or business account balance (staff only)"
)
@app_commands.describe(member="User whose personal balance to check", business="Optional business account name")
async def slash_check_account(interaction: discord.Interaction, member: discord.Member, business: str = None):
    if "Bank management board" not in [r.name for r in interaction.user.roles]:
        return await interaction.response.send_message("You do not have permission.", ephemeral=True)

    if business:
        biz = businesses.get(business.lower())
        if not biz:
            return await interaction.response.send_message("No such business exists.", ephemeral=True)
        await interaction.response.send_message(f"Business '{business}' balance: ${biz['balance']}", ephemeral=True)
    else:
        bal = get_balance(member.id)
        await interaction.response.send_message(f"{member.name}#{member.discriminator} personal balance: ${bal}", ephemeral=True)

# --- /balance ---
@bot.tree.command(name="balance", description="Check your personal or business balance")
@app_commands.describe(business="Optional business name")
async def slash_balance(interaction: discord.Interaction, business: str = None):
    if business:
        biz = businesses.get(business.lower())
        allowed = [biz["owner"]] + biz.get("members", []) if biz else []
        if not biz or interaction.user.id not in allowed:
            return await interaction.response.send_message("No access to that business.", ephemeral=True)
        await interaction.response.send_message(f"Business '{business}' balance: ${biz['balance']}", ephemeral=True)
    else:
        bal = get_balance(interaction.user.id)
        await interaction.response.send_message(f"Your personal balance: ${bal}", ephemeral=True)

# --- /deposit ---
@bot.tree.command(name="deposit", description="Request a deposit (proof required)")
@app_commands.describe(
    amount="Amount to deposit",
    proof="Screenshot proof",
    business="Optional business name"
)
async def slash_deposit(interaction: discord.Interaction, amount: int, proof: discord.Attachment, business: str = None):
    if amount <= 0:
        return await interaction.response.send_message("Amount must be greater than 0.", ephemeral=True)

    if business:
        biz = businesses.get(business.lower())
        allowed = [biz["owner"]] + biz.get("members", []) if biz else []
        if not biz or interaction.user.id not in allowed:
            return await interaction.response.send_message("No access to that business.", ephemeral=True)
        owner_id = biz["owner"]
        target_label = business
    else:
        owner_id = interaction.user.id
        target_label = "personal"

    chan = bot.get_channel(DEPOSIT_CHANNEL_ID)
    await chan.send(
        f"Deposit Request: {interaction.user.mention} -> {target_label} ${amount}\nProof: {proof.url}"
    )
    await interaction.response.send_message(f"Deposit request of ${amount} sent to staff.", ephemeral=True)

    if business:
        owner = bot.get_user(owner_id)
        dm = await owner.create_dm()
        await dm.send(f"{interaction.user} requested a deposit of ${amount} to '{business}'.")

# --- /withdraw ---
@bot.tree.command(name="withdraw", description="Request a withdrawal")
@app_commands.describe(
    amount="Amount to withdraw",
    business="Optional business name"
)
async def slash_withdraw(interaction: discord.Interaction, amount: int, business: str = None):
    if amount <= 0:
        return await interaction.response.send_message("Amount must be greater than 0.", ephemeral=True)

    if business:
        biz = businesses.get(business.lower())
        allowed = [biz["owner"]] + biz.get("members", []) if biz else []
        if not biz or interaction.user.id not in allowed:
            return await interaction.response.send_message("No access to that business.", ephemeral=True)
        if biz["balance"] < amount:
            return await interaction.response.send_message("Business has insufficient funds.", ephemeral=True)
        owner_id = biz["owner"]
        target_label = business
    else:
        if get_balance(interaction.user.id) < amount:
            return await interaction.response.send_message("Insufficient personal balance.", ephemeral=True)
        owner_id = interaction.user.id
        target_label = "personal"

    chan = bot.get_channel(WITHDRAW_CHANNEL_ID)
    await chan.send(f"Withdrawal Request: {interaction.user.mention} -> {target_label} ${amount}")
    await interaction.response.send_message(f"Withdrawal request of ${amount} sent to staff.", ephemeral=True)

    if business:
        owner = bot.get_user(owner_id)
        dm = await owner.create_dm()
        await dm.send(f"{interaction.user} requested a withdrawal of ${amount} from '{business}'.")

# --- /approve ---
@bot.tree.command(
    name="approve",
    description="Approve a deposit or withdrawal (staff only)"
)
@app_commands.describe(
    member="User whose request you're approving",
    action="deposit or withdraw",
    amount="Amount to approve",
    business="Optional business name",
    proof="Screenshot proof (required if withdraw)"
)
async def slash_approve(
    interaction: discord.Interaction,
    member: discord.Member,
    action: str,
    amount: int,
    business: str = None,
    proof: discord.Attachment = None
):
    if "Bank management board" not in [r.name for r in interaction.user.roles]:
        return await interaction.response.send_message("You do not have permission.", ephemeral=True)

    action = action.lower()
    if action not in ("deposit", "withdraw") or amount <= 0:
        return await interaction.response.send_message("Invalid action or amount.", ephemeral=True)

    if action == "withdraw" and proof is None:
        return await interaction.response.send_message("You must attach proof for a withdrawal.", ephemeral=True)

    target_label = "personal"
    biz = None
    if business:
        biz = businesses.get(business.lower())
        if not biz:
            return await interaction.response.send_message("No such business.", ephemeral=True)
        target_label = business

    if action == "deposit":
        if biz:
            biz["balance"] += amount
            save_businesses()
        else:
            update_balance(member.id, amount)
    else:
        if biz:
            biz["balance"] -= amount
            save_businesses()
        else:
            update_balance(member.id, -amount)

    await interaction.response.send_message(
        f"Approved {action} of ${amount} for {member.mention} on '{target_label}'.",
        ephemeral=False
    )

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    if biz:
        owner = bot.get_user(biz["owner"])
        dm = await owner.create_dm()
        header = f"Business '{business}' {action} approved"
        body = (
            f"- Who: {member} ({member.id})\n"
            f"- Amount: ${amount}\n"
            f"- When: {ts}"
        )
        if action == "withdraw":
            file = await proof.to_file()
            await dm.send(f"{header}\n{body}", file=file)
        else:
            await dm.send(f"{header}\n{body}")
    else:
        dm = await member.create_dm()
        await dm.send(f"Your {action} of ${amount} has been approved on {ts}.")

# --- /reject ---
@bot.tree.command(name="reject", description="Reject a deposit or withdrawal (staff only)")
@app_commands.describe(
    member="User whose request you're rejecting",
    action="deposit or withdraw",
    business="Optional business name"
)
async def slash_reject(interaction: discord.Interaction, member: discord.Member, action: str, business: str = None):
    if "Bank management board" not in [r.name for r in interaction.user.roles]:
        return await interaction.response.send_message("You do not have permission.", ephemeral=True)

    action = action.lower()
    if action not in ("deposit", "withdraw"):
        return await interaction.response.send_message("Action must be 'deposit' or 'withdraw'.", ephemeral=True)

    target_label = business if business else "personal"
    await interaction.response.send_message(
        f"Rejected {action} request for {member.mention} on '{target_label}'.",
        ephemeral=False
    )

# --- /gamble ---
@bot.tree.command(name="gamble", description="Gamble against the bank")
@app_commands.describe(amount="Amount to gamble")
async def slash_gamble(interaction: discord.Interaction, amount: int):
    if not settings.get("gambling_enabled", True):
        return await interaction.response.send_message("Gambling is currently disabled.", ephemeral=True)
    if amount <= 0:
        return await interaction.response.send_message("Amount must be greater than 0.", ephemeral=True)
    if get_balance(interaction.user.id) < amount:
        return await interaction.response.send_message("You do not have enough balance to gamble.", ephemeral=True)

    bank_bal = get_bank_balance()
    staff_chan = bot.get_channel(GAMBLING_CHANNEL_ID)
    win = random.random() > 0.6

    if win:
        if bank_bal < amount:
            return await interaction.response.send_message("Bank does not have enough funds to pay out this win.", ephemeral=True)
        update_balance(interaction.user.id, amount)
        update_bank_balance(-amount)
        result = f"You won ${amount}. New balance: ${get_balance(interaction.user.id)}"
        log = f"{interaction.user.mention} WON ${amount}"
    else:
        update_balance(interaction.user.id, -amount)
        update_bank_balance(amount)
        result = f"You lost ${amount}. New balance: ${get_balance(interaction.user.id)}"
        log = f"{interaction.user.mention} LOST ${amount}"

    await interaction.response.send_message(result, ephemeral=True)
    if staff_chan:
        await staff_chan.send(log)

# --- /transfer_to_bank ---
@bot.tree.command(name="transfer_to_bank", description="Add funds to the bank (staff only)")
@app_commands.describe(amount="Amount to transfer")
async def slash_transfer_to_bank(interaction: discord.Interaction, amount: int):
    if "Bank management board" not in [r.name for r in interaction.user.roles]:
        return await interaction.response.send_message("You do not have permission.", ephemeral=True)
    if amount <= 0:
        return await interaction.response.send_message("Amount must be greater than 0.", ephemeral=True)

    update_bank_balance(amount)
    await interaction.response.send_message(
        f"Transferred ${amount} to the bank. New bank balance: ${get_bank_balance()}",
        ephemeral=False
    )

# --- Run bot ---
bot.run(TOKEN)
