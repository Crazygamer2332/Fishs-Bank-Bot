import os
import json
import random
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# keep_alive (Replit/Glitch) to prevent sleep
try:
    from keep_alive import keep_alive
    keep_alive()
except ImportError:
    pass

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ── Config files & channels ──────────────────────────────────────────────────
BALANCES_FILE       = "balances.json"
BANK_BALANCE_FILE   = "bank_balance.json"
BUSINESSES_FILE     = "businesses.json"
SETTINGS_FILE       = "settings.json"
FROZEN_FILE         = "frozen.json"

DEPOSIT_CHANNEL_ID  = 1422789849446092820
WITHDRAW_CHANNEL_ID = 1422790276967170098
GAMBLING_CHANNEL_ID = 1422790430843469955

# ── JSON utils ───────────────────────────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return default
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

balances   = load_json(BALANCES_FILE, {})
bank       = load_json(BANK_BALANCE_FILE, {"balance": 0})
businesses = load_json(BUSINESSES_FILE, {})
settings   = load_json(SETTINGS_FILE, {
    "gambling_enabled": True,
    "deposit_enabled": True,
    "withdraw_enabled": True
})
frozen     = load_json(FROZEN_FILE, {"accounts": [], "businesses": []})

def save_all():
    save_json(BALANCES_FILE, balances)
    save_json(BANK_BALANCE_FILE, bank)
    save_json(BUSINESSES_FILE, businesses)
    save_json(SETTINGS_FILE, settings)
    save_json(FROZEN_FILE, frozen)

# ── Helpers ──────────────────────────────────────────────────────────────────
def is_staff(member):
    return "Bank management board" in [r.name for r in member.roles]

def timestamp():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

def get_balance(user_id):
    return balances.get(str(user_id), 0)

def update_balance(uid, delta):
    balances[str(uid)] = get_balance(uid) + delta
    save_json(BALANCES_FILE, balances)

def get_bank_balance():
    return bank["balance"]

def update_bank_balance(delta):
    bank["balance"] += delta
    save_json(BANK_BALANCE_FILE, bank)

def is_frozen_account(uid):
    return str(uid) in frozen["accounts"]

def is_frozen_business(key):
    return key.lower() in frozen["businesses"]

# ── Events & Error Handler ─────────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Connected as {bot.user}")

@bot.tree.error
async def on_app_command_error(inter, error):
    if inter.response.is_done():
        await inter.followup.send("❌ Error occurred.", ephemeral=True)
    else:
        await inter.response.send_message("❌ Error occurred.", ephemeral=True)
    print(error)

# ── Toggles (staff) ──────────────────────────────────────────────────────────
@bot.tree.command(name="toggle_deposit", description="Toggle deposit requests")
async def toggle_deposit(inter: discord.Interaction):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    settings["deposit_enabled"] = not settings["deposit_enabled"]
    save_json(SETTINGS_FILE, settings)
    await inter.response.send_message(f"Deposit {'enabled' if settings['deposit_enabled'] else 'disabled'}.", ephemeral=False)

@bot.tree.command(name="toggle_withdraw", description="Toggle withdrawal requests")
async def toggle_withdraw(inter: discord.Interaction):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    settings["withdraw_enabled"] = not settings["withdraw_enabled"]
    save_json(SETTINGS_FILE, settings)
    await inter.response.send_message(f"Withdrawals {'enabled' if settings['withdraw_enabled'] else 'disabled'}.", ephemeral=False)

@bot.tree.command(name="toggle_gambling", description="Toggle gambling")
async def toggle_gambling(inter: discord.Interaction):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    settings["gambling_enabled"] = not settings["gambling_enabled"]
    save_json(SETTINGS_FILE, settings)
    await inter.response.send_message(f"Gambling {'enabled' if settings['gambling_enabled'] else 'disabled'}.", ephemeral=False)

# ── Business Commands ────────────────────────────────────────────────────────
@bot.tree.command(name="create_business", description="Create a business account")
@app_commands.describe(name="Unique name")
async def create_business(inter, name: str):
    key = name.lower()
    if key in businesses:
        return await inter.response.send_message("Already exists.", ephemeral=True)
    businesses[key] = {"owner": inter.user.id, "members": [], "balance": 0}
    save_json(BUSINESSES_FILE, businesses)
    await inter.response.send_message(f"Business '{name}' created.", ephemeral=True)

@bot.tree.command(name="business_add_member", description="Add member to business")
@app_commands.describe(business="Name", member="User")
async def add_member(inter, business: str, member: discord.Member):
    biz = businesses.get(business.lower())
    if not biz or biz["owner"] != inter.user.id:
        return await inter.response.send_message("Not owner.", ephemeral=True)
    if member.id in biz["members"]:
        return await inter.response.send_message("Already a member.", ephemeral=True)
    biz["members"].append(member.id)
    save_json(BUSINESSES_FILE, businesses)
    await inter.response.send_message(f"{member.mention} added.", ephemeral=True)

@bot.tree.command(name="business_remove_member", description="Remove member from business")
@app_commands.describe(business="Name", member="User")
async def remove_member(inter, business: str, member: discord.Member):
    biz = businesses.get(business.lower())
    if not biz or biz["owner"] != inter.user.id:
        return await inter.response.send_message("Not owner.", ephemeral=True)
    if member.id not in biz["members"]:
        return await inter.response.send_message("Not a member.", ephemeral=True)
    biz["members"].remove(member.id)
    save_json(BUSINESSES_FILE, businesses)
    await inter.response.send_message(f"{member.mention} removed.", ephemeral=True)

# ── Freeze / Unfreeze ───────────────────────────────────────────────────────
@bot.tree.command(name="freeze_account", description="Freeze a personal account")
@app_commands.describe(member="User to freeze")
async def freeze_acct(inter, member: discord.Member):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    frozen["accounts"].append(str(member.id))
    save_json(FROZEN_FILE, frozen)
    await inter.response.send_message(f"{member.mention} frozen.", ephemeral=False)

@bot.tree.command(name="unfreeze_account", description="Unfreeze a personal account")
@app_commands.describe(member="User to unfreeze")
async def unfreeze_acct(inter, member: discord.Member):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    frozen["accounts"].remove(str(member.id))
    save_json(FROZEN_FILE, frozen)
    await inter.response.send_message(f"{member.mention} unfrozen.", ephemeral=False)

@bot.tree.command(name="freeze_business", description="Freeze a business account")
@app_commands.describe(business="Name")
async def freeze_biz(inter, business: str):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    frozen["businesses"].append(business.lower())
    save_json(FROZEN_FILE, frozen)
    await inter.response.send_message(f"Business '{business}' frozen.", ephemeral=False)

@bot.tree.command(name="unfreeze_business", description="Unfreeze a business account")
@app_commands.describe(business="Name")
async def unfreeze_biz(inter, business: str):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    frozen["businesses"].remove(business.lower())
    save_json(FROZEN_FILE, frozen)
    await inter.response.send_message(f"Business '{business}' unfrozen.", ephemeral=False)

# ── Prune zero-balance data ───────────────────────────────────────────────────
@bot.tree.command(name="prune_zero", description="Prune zero-balance accounts/businesses")
@app_commands.describe(target="accounts | businesses")
async def prune_zero(inter, target: str):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    if target == "accounts":
        removed = [uid for uid, bal in balances.items() if bal == 0]
        for uid in removed:
            del balances[uid]
    elif target == "businesses":
        removed = [k for k,v in businesses.items() if v["balance"] == 0]
        for k in removed:
            del businesses[k]
    else:
        return await inter.response.send_message("Use 'accounts' or 'businesses'.", ephemeral=True)
    save_all()
    await inter.response.send_message(f"Pruned {len(removed)} {target}.", ephemeral=False)

# ── List data ────────────────────────────────────────────────────────────────
@bot.tree.command(name="list", description="List accounts/businesses/frozen")
@app_commands.describe(
    category="accounts | businesses | frozen_accounts | frozen_businesses"
)
async def list_data(inter, category: str):
    cat = category.lower()
    if cat == "accounts":
        items = [f"<@{uid}>: ${bal}" for uid, bal in balances.items()]
    elif cat == "businesses":
        items = [f"{k}: ${v['balance']}" for k,v in businesses.items()]
    elif cat == "frozen_accounts":
        items = [f"<@{uid}>" for uid in frozen["accounts"]]
    elif cat == "frozen_businesses":
        items = frozen["businesses"]
    else:
        return await inter.response.send_message("Invalid category.", ephemeral=True)

    text = "\n".join(items) if items else "None"
    await inter.response.send_message(f"**{category}**\n{text}", ephemeral=True)

# ── Transfer between personal/business ───────────────────────────────────────
@bot.tree.command(name="transfer", description="Transfer funds between you/business")
@app_commands.describe(
    amount="Amount",
    from_acc="personal or business name",
    to_acc="personal or business name"
)
async def transfer(inter, amount: int, from_acc: str, to_acc: str):
    if amount <= 0:
        return await inter.response.send_message("Amount > 0 required.", ephemeral=True)

    # Resolve from
    if from_acc.lower() == "personal":
        if get_balance(inter.user.id) < amount:
            return await inter.response.send_message("Not enough personal funds.", ephemeral=True)
        update_balance(inter.user.id, -amount)
    else:
        biz = businesses.get(from_acc.lower())
        if not biz or inter.user.id not in [biz["owner"]] + biz["members"]:
            return await inter.response.send_message("No access to source business.", ephemeral=True)
        if biz["balance"] < amount:
            return await inter.response.send_message("Business has insufficient funds.", ephemeral=True)
        biz["balance"] -= amount
        save_businesses()

    # Resolve to
    if to_acc.lower() == "personal":
        update_balance(inter.user.id, amount)
    else:
        biz2 = businesses.get(to_acc.lower())
        if not biz2:
            return await inter.response.send_message("Destination business not found.", ephemeral=True)
        biz2["balance"] += amount
        save_businesses()

    await inter.response.send_message(f"Transferred ${amount} from {from_acc} to {to_acc}.", ephemeral=False)

# ── Deposit, Withdraw, Approve, Reject, Gamble ────────────────────────────────
@bot.tree.command(name="deposit", description="Request deposit")
@app_commands.describe(amount="Amount", proof="Screenshot", business="Optional")
async def deposit(inter, amount: int, proof: discord.Attachment, business: str = None):
    if amount <= 0 or not settings["deposit_enabled"]:
        return await inter.response.send_message("Invalid or disabled.", ephemeral=True)
    target = business.lower() if business else None
    chan = bot.get_channel(DEPOSIT_CHANNEL_ID)
    chan.send(f"Deposit: {inter.user.mention} -> {business or 'personal'} ${amount}\nProof: {proof.url}")
    await inter.response.send_message("Sent to staff.", ephemeral=True)

@bot.tree.command(name="withdraw", description="Request withdrawal")
@app_commands.describe(amount="Amount", business="Optional")
async def withdraw(inter, amount: int, business: str = None):
    if amount <= 0 or not settings["withdraw_enabled"]:
        return await inter.response.send_message("Invalid or disabled.", ephemeral=True)
    target = business.lower() if business else None
    chan = bot.get_channel(WITHDRAW_CHANNEL_ID)
    chan.send(f"Withdraw: {inter.user.mention} -> {business or 'personal'} ${amount}")
    await inter.response.send_message("Sent to staff.", ephemeral=True)

@bot.tree.command(name="approve", description="Approve request (staff)")
@app_commands.describe(
    member="User",
    action="deposit|withdraw",
    amount="Amount",
    business="Optional",
    proof="Proof for withdraw"
)
async def approve(inter, member: discord.Member, action: str, amount: int, business: str = None, proof: discord.Attachment = None):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    act = action.lower()
    biz = businesses.get(business.lower()) if business else None

    # Update balances
    if act == "deposit":
        if biz:
            biz["balance"] += amount; save_businesses()
        else:
            update_balance(member.id, amount)
    else:  # withdraw
        if biz:
            biz["balance"] -= amount; save_businesses()
        else:
            update_balance(member.id, -amount)

    # DM owner or member
    ts = timestamp()
    if biz:
        owner = await bot.fetch_user(biz["owner"])
        dm = await owner.create_dm()
        header = f"Business '{business}' {act} approved"
        body = f"- Who: {member}\n- Amount: ${amount}\n- When: {ts}"
        if proof:
            file = await proof.to_file(); await dm.send(f"{header}\n{body}", file=file)
        else:
            await dm.send(f"{header}\n{body}")
    else:
        dm = await member.create_dm()
        await dm.send(f"Your {act} of ${amount} was approved on {ts}.")

    await inter.response.send_message(f"Approved {act}.", ephemeral=False)

# … (le code précédent)

@bot.tree.command(
    name="reject",
    description="Reject a deposit or withdrawal (staff only)"
)
@app_commands.describe(
    member="User whose request you're rejecting",
    action="deposit or withdraw",
    business="Optional business name"
)
async def reject(
    inter: discord.Interaction,
    member: discord.Member,
    action: str,
    business: str = None
):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)

    action = action.lower()
    if action not in ("deposit", "withdraw"):
        return await inter.response.send_message("Action must be 'deposit' or 'withdraw'.", ephemeral=True)

    biz = businesses.get(business.lower()) if business else None
    ts = timestamp()

    # Notify staff channel
    await inter.response.send_message(
        f"Rejected {action} request for {member.mention} "
        f"{'on ' + business if business else 'on personal account'}.",
        ephemeral=False
    )

    # DM to owner or member
    if biz:
        owner = await bot.fetch_user(biz["owner"])
        dm = await owner.create_dm()
        await dm.send(
            f"Your business '{business}' {action} request for ${amount} was rejected on {ts}."
        )
    else:
        dm = await member.create_dm()
        await dm.send(
            f"Your personal {action} request for ${amount} was rejected on {ts}."
        )

@bot.tree.command(name="gamble", description="Gamble against the bank")
@app_commands.describe(amount="Amount to gamble")
async def gamble(inter: discord.Interaction, amount: int):
    if not settings.get("gambling_enabled", True):
        return await inter.response.send_message("Gambling is currently disabled.", ephemeral=True)
    if amount <= 0:
        return await inter.response.send_message("Amount must be greater than 0.", ephemeral=True)
    if get_balance(inter.user.id) < amount:
        return await inter.response.send_message("Insufficient personal balance.", ephemeral=True)

    bank_bal = get_bank_balance()
    win = random.random() > 0.6

    if win:
        if bank_bal < amount:
            return await inter.response.send_message("Bank has insufficient funds.", ephemeral=True)
        update_balance(inter.user.id, amount)
        update_bank_balance(-amount)
        result = f"You won ${amount}! New balance: ${get_balance(inter.user.id)}"
    else:
        update_balance(inter.user.id, -amount)
        update_bank_balance(amount)
        result = f"You lost ${amount}. New balance: ${get_balance(inter.user.id)}"

    staff_chan = bot.get_channel(GAMBLING_CHANNEL_ID)
    if staff_chan:
        await staff_chan.send(f"{inter.user.mention} {'WON' if win else 'LOST'} ${amount}")
    await inter.response.send_message(result, ephemeral=True)

@bot.tree.command(
    name="transfer_to_bank",
    description="Add funds to the bank (staff only)"
)
@app_commands.describe(amount="Amount to transfer")
async def transfer_to_bank(inter: discord.Interaction, amount: int):
    if not is_staff(inter.user):
        return await inter.response.send_message("No permission.", ephemeral=True)
    if amount <= 0:
        return await inter.response.send_message("Amount must be > 0.", ephemeral=True)

    update_bank_balance(amount)
    await inter.response.send_message(
        f"Transferred ${amount} to the bank. Bank balance: ${get_bank_balance()}",
        ephemeral=False
    )

# ── Lancement du bot ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(TOKEN)
