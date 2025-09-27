"""
Antinuke Discord Bot (example)
- Requires: Python 3.11+ and a modern py-cord / discord.py compatible library
- This is a starter, secure-by-default antinuke bot. Customize as needed.
"""

import asyncio
import json
import os
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

# --- Config / persistence (simple JSON file) ---
DATA_FILE = "data.json"
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        DATA = json.load(f)
else:
    DATA = {"guilds": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(DATA, f, indent=2)

# --- Bot setup ---
intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.members = True
intents.message_content = False  # not required
intents.bans = True
intents.reactions = False
intents.integrations = False
intents.emojis = True
intents.guild_messages = True
intents.presences = False

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# In-memory action logs: {guild_id: {user_id: deque([timestamp,...])}}
action_logs = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))

# Default protections
DEFAULTS = {
    "threshold_count": 3,          # number of destructive actions within window to trigger
    "threshold_window": 10,        # seconds window for threshold
    "auto_ban": True,              # ban the attacker when triggered
    "whitelist_roles": [],         # role ids allowed to perform admin actions
    "whitelist_users": [],         # user ids allowed
    "owner_id": None               # guild owner allowed by default
}

# Utilities
def get_gconfig(guild_id):
    g = DATA["guilds"].setdefault(str(guild_id), {})
    for k,v in DEFAULTS.items():
        g.setdefault(k, v)
    return g

async def is_whitelisted(guild, user_id):
    g = get_gconfig(guild.id)
    if g.get("owner_id") is None:
        g["owner_id"] = guild.owner_id
        save_data()
    if user_id == int(g.get("owner_id")):
        return True
    if str(user_id) in map(str, g.get("whitelist_users", [])):
        return True
    # check roles
    member = guild.get_member(user_id)
    if member:
        wroles = set(map(int, g.get("whitelist_roles", [])))
        for r in member.roles:
            if r.id in wroles:
                return True
    return False

def record_action(guild_id, user_id):
    now = time.time()
    dq = action_logs[guild_id][user_id]
    dq.append(now)
    return dq

def actions_within_window(dq, window):
    if not dq:
        return 0
    now = time.time()
    # count timestamps >= now-window
    return sum(1 for t in dq if t >= now - window)

# --- Protective response ---
async def punish_executor(guild, executor, reason="Antinuke trigger"):
    try:
        # Try to remove all roles (demote) then ban as fallback
        member = guild.get_member(executor.id)
        if member:
            # remove roles we can
            removable = [r for r in member.roles if r != guild.default_role and r < guild.me.top_role]
            for r in removable:
                try:
                    await member.remove_roles(r, reason=reason)
                except Exception:
                    pass
            # final ban if configured
            g = get_gconfig(guild.id)
            if g.get("auto_ban", True):
                try:
                    await guild.ban(member, reason=reason)
                except Exception:
                    try:
                        await guild.kick(member, reason=reason)
                    except Exception:
                        pass
    except Exception:
        pass

# --- Audit helper ---
async def fetch_executor(guild, action):
    # action is discord.AuditLogAction
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            return entry
    except Exception:
        return None

# --- Common handler used for several destructive actions ---
async def handle_danger_action(payload, audit_action: discord.AuditLogAction, description: str):
    guild = payload.guild
    if not guild:
        return
    entry = await fetch_executor(guild, audit_action)
    if not entry or not entry.user:
        return
    executor = entry.user
    if executor.bot:
        return
    if await is_whitelisted(guild, executor.id):
        return

    dq = record_action(guild.id, executor.id)
    g = get_gconfig(guild.id)
    count = actions_within_window(dq, g.get("threshold_window", 10))
    if count >= g.get("threshold_count", 3):
        # Trigger protective measures
        await punish_executor(guild, executor, reason=f"Triggered antinuke: {description}")
        # clear their log
        action_logs[guild.id][executor.id].clear()
        # Notify guild owner or mod log channel (best-effort)
        try:
            owner = guild.owner
            if owner and owner.dm_channel is None:
                await owner.create_dm()
            if owner:
                await owner.send(f"Antinuke triggered in **{guild.name}**. Executor **{executor}** has been punished.")
        except Exception:
            pass

# --- Events to monitor ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    # ensure data default updated for guilds
    for g in bot.guilds:
        get_gconfig(g.id)
    save_data()

@bot.event
async def on_guild_channel_delete(channel):
    # payload is channel; create synthetic small payload object for handle
    class P: pass
    p = P(); p.guild = channel.guild; p.channel = channel
    await handle_danger_action(p, discord.AuditLogAction.channel_delete, "Channel Deletion")

@bot.event
async def on_guild_channel_create(channel):
    class P: pass
    p = P(); p.guild = channel.guild; p.channel = channel
    await handle_danger_action(p, discord.AuditLogAction.channel_create, "Channel Creation")

@bot.event
async def on_guild_role_delete(role):
    class P: pass
    p = P(); p.guild = role.guild; p.role = role
    await handle_danger_action(p, discord.AuditLogAction.role_delete, "Role Deletion")

@bot.event
async def on_guild_role_create(role):
    class P: pass
    p = P(); p.guild = role.guild; p.role = role
    await handle_danger_action(p, discord.AuditLogAction.role_create, "Role Creation")

@bot.event
async def on_member_ban(guild, user):
    class P: pass
    p = P(); p.guild = guild; p.user = user
    await handle_danger_action(p, discord.AuditLogAction.ban, "Member Ban")

# --- Commands: manage whitelist and config ---
@bot.group(invoke_without_command=True)
@commands.has_guild_permissions(administrator=True)
async def antinuke(ctx):
    """Show antinuke status"""
    g = get_gconfig(ctx.guild.id)
    txt = f"Threshold: {g['threshold_count']} actions / {g['threshold_window']}s | Auto-ban: {g['auto_ban']}\n"
    txt += f"Whitelisted users: {g['whitelist_users']}\nWhitelisted roles: {g['whitelist_roles']}\n"
    await ctx.send(txt)

@antinuke.command()
@commands.has_guild_permissions(administrator=True)
async def whitelist_add(ctx, member: discord.Member):
    g = get_gconfig(ctx.guild.id)
    if str(member.id) not in map(str, g["whitelist_users"]):
        g["whitelist_users"].append(str(member.id))
        save_data()
    await ctx.send(f"Added {member} to whitelist.")

@antinuke.command()
@commands.has_guild_permissions(administrator=True)
async def whitelist_remove(ctx, member: discord.Member):
    g = get_gconfig(ctx.guild.id)
    g["whitelist_users"] = [u for u in g["whitelist_users"] if str(u) != str(member.id)]
    save_data()
    await ctx.send(f"Removed {member} from whitelist.")

@antinuke.command()
@commands.has_guild_permissions(administrator=True)
async def set_threshold(ctx, count: int, window: int):
    g = get_gconfig(ctx.guild.id)
    g["threshold_count"] = max(1, int(count))
    g["threshold_window"] = max(1, int(window))
    save_data()
    await ctx.send(f"Set threshold to {g['threshold_count']} actions / {g['threshold_window']}s")

@antinuke.command()
@commands.has_guild_permissions(administrator=True)
async def toggle_autoban(ctx, value: str):
    g = get_gconfig(ctx.guild.id)
    g["auto_ban"] = value.lower() in ("1","true","yes","on")
    save_data()
    await ctx.send(f"Auto-ban set to {g['auto_ban']}")

# --- Small safety check: ensure bot has Manage Roles & Ban Members before taking action ---
@bot.check
def bot_has_permissions(ctx):
    me = ctx.guild.me
    if not me.guild_permissions.ban_members or not me.guild_permissions.manage_roles:
        # don't block commands, just warn
        return True
    return True

# --- Run ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("Please set DISCORD_BOT_TOKEN environment variable, or edit the README to add a token.")
    else:
        bot.run(token)
