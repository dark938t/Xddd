# language: Python 3.11, file: Server.py
import discord
from discord import app_commands
from discord.ext import commands
import time
import os
import asyncio
import random
import json
import base64
import aiohttp
from flask import Flask, request, render_template_string
import threading
from dotenv import load_dotenv

load_dotenv()

# ==================== AYARLAR ====================
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "ravex123")
WEB_PORT = int(os.getenv("PORT", 8080))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO") 
GITHUB_FILE = "stok.json" 

STAFF_ROLES = [1566432003560181891, 1560996761659515003]
EXCLUSIVE_ROLE = 1560688907199184986
PREMIUM_ROLE = 1560316365951475852
JOIN_ROLE = 1560292397982810173
TICKET_LOG_CHANNEL = 1566423675480186951
VOUCH_CHANNEL = 1566423691301093437
PREMIUM_EXCLUSIVE_CHANNEL = 1566423682371420273
# =================================================

pending_netflix = {} 
approved_netflix = {}

# ==================== GITHUB VERİTABANI VE HAFIZA ====================
STOK_DATA = {"steam": [], "netflix": [], "used": []}
STOK_SHA = None
STOK_LOCK = asyncio.Lock() # Aynı anda işlem yapmayı engeller

async def github_get_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

async def read_github_stock():
    global STOK_DATA, STOK_SHA
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=await github_get_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                STOK_DATA = json.loads(content)
                STOK_SHA = data['sha']
            else:
                STOK_DATA = {"steam": [], "netflix": [], "used": []}
                STOK_SHA = None

async def write_github_stock():
    global STOK_SHA
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    content = base64.b64encode(json.dumps(STOK_DATA, indent=2).encode('utf-8')).decode('utf-8')
    payload = {
        "message": "Bot stok güncellemesi",
        "content": content
    }
    if STOK_SHA:
        payload["sha"] = STOK_SHA
        
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=await github_get_headers(), json=payload) as resp:
            if resp.status in [200, 201]:
                new_data = await resp.json()
                STOK_SHA = new_data['content']['sha']
                return True
            print(f"GitHub Error: {await resp.text()}")
            return False

# Uygulama başlarken GitHub'dan stokları çek
asyncio.run(read_github_stock())
# =========================================================

# ==================== WEB SİTESİ (FLASK) ====================
web_app = Flask(__name__)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ravex Stock Panel</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #fff; margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: auto; background: #1e1e1e; padding: 20px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.5); }
        h2 { text-align: center; color: #7289da; }
        label { display: block; margin-top: 15px; font-weight: bold; }
        input[type="text"], input[type="password"], select, textarea { width: 100%; padding: 10px; margin-top: 5px; border-radius: 5px; border: 1px solid #333; background: #2b2b2b; color: white; box-sizing: border-box; }
        button { margin-top: 20px; width: 100%; padding: 12px; background: #7289da; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; }
        button:hover { background: #5b6eae; }
        .success { color: #4caf50; text-align: center; margin-top: 15px; }
        .error { color: #f44336; text-align: center; margin-top: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>📦 Ravex Stock Panel</h2>
        <form method="POST">
            <label>Password</label>
            <input type="password" name="password" required>
            
            <label>Service</label>
            <select name="service">
                <option value="steam">Steam</option>
                <option value="netflix">Netflix</option>
            </select>
            
            <label>Accounts (One per line. For Steam use 2 lines)</label>
            <textarea name="accounts" rows="8" required placeholder="Steam Name: ornek
Steam Password: 12345"></textarea>
            
            <button type="submit">Add Stock</button>
        </form>
        {% if message %}
            <div class="{{ 'success' if success else 'error' }}">{{ message }}</div>
        {% endif %}
    </div>
</body>
</html>"""

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@web_app.route('/', methods=['GET', 'POST'])
def index():
    global STOK_DATA
    if request.method == 'POST':
        if request.form.get('password') != WEB_PASSWORD:
            return render_template_string(HTML_PAGE, message="Incorrect password!", success=False)
        
        service = request.form.get('service')
        accounts_raw = request.form.get('accounts')
        
        if not accounts_raw.strip():
            return render_template_string(HTML_PAGE, message="Accounts cannot be empty!", success=False)
            
        lines = [line.strip() for line in accounts_raw.split("\n") if line.strip()]
        
        if service.lower() == "steam":
            STOK_DATA["steam"].extend(lines)
        else:
            STOK_DATA["netflix"].extend(lines)
            
        success = run_async(write_github_stock())
        
        if success:
            return render_template_string(HTML_PAGE, message=f"Successfully added stock to {service}!", success=True)
        else:
            return render_template_string(HTML_PAGE, message="GitHub save failed! Check Token.", success=False)

    return render_template_string(HTML_PAGE)

def run_web_server():
    web_app.run(host='0.0.0.0', port=WEB_PORT)
# =========================================================

# ==================== TICKET VE MENÜLER ====================
class TicketSelectMenu(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Support", emoji="🎧", description="Open a ticket for support issues", value="Support"),
            discord.SelectOption(label="General", emoji="💬", description="Ask general questions", value="General"),
            discord.SelectOption(label="Another", emoji="❓", description="For any other issues", value="Another")
        ]
        super().__init__(placeholder="Select a category to open a ticket...", min_values=1, max_values=1, options=options, custom_id="ticket_menu")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await create_ticket(interaction, self.values[0])

class TicketMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelectMenu())

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", emoji="🙋‍♂️", style=discord.ButtonStyle.success, custom_id="t_claim")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id in STAFF_ROLES for r in interaction.user.roles):
            return await interaction.response.send_message("❌ You don't have the staff role to claim this.", ephemeral=True)
        button.disabled = True
        button.label = f"Claimed by {interaction.user.name}"
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"✅ {interaction.user.mention} has claimed this ticket.", ephemeral=False)

    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="t_close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id in STAFF_ROLES for r in interaction.user.roles):
            return await interaction.response.send_message("❌ You don't have the staff role to close this.", ephemeral=True)
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class GiveawayView(discord.ui.View):
    def __init__(self, prize, winners, end_time, host_id):
        super().__init__(timeout=end_time - time.time())
        self.prize = prize
        self.winners_count = winners
        self.end_time = end_time
        self.host_id = host_id
        self.entries = set()

    def get_embed(self):
        embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"**Prize:** {self.prize}\n**Winners:** {self.winners_count}\n**Ends:** <t:{int(self.end_time)}:R>", color=discord.Color.gold())
        embed.add_field(name="Entries", value=f"👥 **{len(self.entries)}**")
        return embed

    @discord.ui.button(label="Join", emoji="🎉", style=discord.ButtonStyle.success, custom_id="g_join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.entries:
            return await interaction.response.send_message("❌ You are already in this giveaway!", ephemeral=True)
        self.entries.add(interaction.user.id)
        await interaction.message.edit(embed=self.get_embed())
        await interaction.response.send_message("✅ You joined the giveaway!", ephemeral=True)

    @discord.ui.button(label="Leave", emoji="🚪", style=discord.ButtonStyle.danger, custom_id="g_leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.entries:
            return await interaction.response.send_message("❌ You are not in this giveaway!", ephemeral=True)
        self.entries.remove(interaction.user.id)
        await interaction.message.edit(embed=self.get_embed())
        await interaction.response.send_message("✅ You left the giveaway.", ephemeral=True)

# ==================== BOT CLASS ====================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=".", intents=intents)
        self.active_giveaways = {}
        self.cooldowns = {} 

    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(TicketMenuView())
        self.add_view(TicketControlView())
        print("[+] Slash commands synced.")

    async def on_ready(self):
        print(f"[+] Logged in as {self.user.name} | Made By kaptan9021_2")
        await self.change_presence(activity=discord.Game(name="Made By kaptan9021_2"))
        threading.Thread(target=run_web_server, daemon=True).start()

    async def on_member_join(self, member):
        role = member.guild.get_role(JOIN_ROLE)
        if role:
            try: await member.add_roles(role)
            except: pass

bot = MyBot()

# ==================== YARDIMCI FONKSİYONLAR ====================

def get_ticket_number(guild):
    count = len([c for c in guild.channels if c.name.startswith("ticket-")])
    return count + 1

async def create_ticket(interaction: discord.Interaction, category: str):
    guild = interaction.guild
    staff_roles = [guild.get_role(r) for r in STAFF_ROLES]
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    for role in staff_roles:
        if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    t_num = get_ticket_number(guild)
    try:
        channel = await guild.create_text_channel(name=f"ticket-{t_num}", overwrites=overwrites, category=None)
        embed = discord.Embed(title=f"Ticket #{t_num}", description=f"Category: **{category}**\nOpened by: {interaction.user.mention}\n\nStaff will be with you shortly.", color=discord.Color.blue())
        mention_str = " ".join([r.mention for r in staff_roles if r])
        
        await channel.send(content=mention_str, embed=embed, view=TicketControlView())
        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error creating ticket: {e}", ephemeral=True)

def check_limit(user_id, type_):
    if user_id not in bot.cooldowns: bot.cooldowns[user_id] = {}
    if type_ in bot.cooldowns[user_id]:
        elapsed = time.time() - bot.cooldowns[user_id][type_]
        if elapsed < 86400: return False, int(86400 - elapsed)
    return True, 0

def set_limit(user_id, type_):
    if user_id not in bot.cooldowns: bot.cooldowns[user_id] = {}
    bot.cooldowns[user_id][type_] = time.time()

async def get_available_account(service):
    global STOK_DATA
    async with STOK_LOCK:
        if service == "steam":
            lines = STOK_DATA.get("steam", [])
            for i in range(0, len(lines), 2):
                if i+1 < len(lines):
                    acc = f"{lines[i]}\n{lines[i+1]}"
                    if acc not in STOK_DATA.get("used", []):
                        STOK_DATA["used"].append(acc)
                        await write_github_stock()
                        return acc
        elif service == "netflix":
            lines = STOK_DATA.get("netflix", [])
            for line in lines:
                if line not in STOK_DATA.get("used", []):
                    STOK_DATA["used"].append(line)
                    await write_github_stock()
                    return line
    return None

async def count_stock(service):
    async with STOK_LOCK:
        used = STOK_DATA.get("used", [])
        if service == "steam":
            lines = STOK_DATA.get("steam", [])
            count = 0
            for i in range(0, len(lines), 2):
                if i+1 < len(lines) and f"{lines[i]}\n{lines[i+1]}" not in used:
                    count += 1
            return count
        elif service == "netflix":
            return sum(1 for line in STOK_DATA.get("netflix", []) if line not in used)
    return 0

# ==================== SLASH KOMUTLARI ====================

@bot.tree.command(name="ticket", description="Open a support ticket menu")
async def ticket_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🎟️ Support Tickets", description="Please select a category from the menu below to open a ticket.", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, view=TicketMenuView())

@bot.tree.command(name="stock", description="Check available stock")
async def stock_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    nf_count = await count_stock("netflix")
    st_count = await count_stock("steam")
    embed = discord.Embed(title="📦 Current Stock", color=discord.Color.green())
    embed.add_field(name="Netflix", value=f"**{nf_count}** accounts", inline=True)
    embed.add_field(name="Steam", value=f"**{st_count}** accounts", inline=True)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="generate", description="Generate an account")
@app_commands.describe(service="Select service", plan="Select plan")
@app_commands.choices(
    service=[app_commands.Choice(name="Netflix", value="netflix"), app_commands.Choice(name="Steam", value="steam")],
    plan=[app_commands.Choice(name="Normal", value="normal"), app_commands.Choice(name="Premium", value="premium"), app_commands.Choice(name="Exclusive", value="exclusive")]
)
async def generate_cmd(interaction: discord.Interaction, service: app_commands.Choice[str], plan: app_commands.Choice[str]):
    user_roles = [r.id for r in interaction.user.roles]
    service_val = service.value
    plan_val = plan.value
    
    if plan_val in ["premium", "exclusive"] and interaction.channel_id != PREMIUM_EXCLUSIVE_CHANNEL:
        return await interaction.response.send_message(f"❌ You can only use this plan in <#{PREMIUM_EXCLUSIVE_CHANNEL}>.", ephemeral=True)

    if plan_val == "premium" and PREMIUM_ROLE not in user_roles:
        return await interaction.response.send_message("❌ You don't have the Premium role.", ephemeral=True)
    if plan_val == "exclusive" and EXCLUSIVE_ROLE not in user_roles:
        return await interaction.response.send_message("❌ You don't have the Exclusive role.", ephemeral=True)

    await interaction.response.defer()

    if service_val == "steam":
        limit_ok, time_left = check_limit(interaction.user.id, f"steam_{plan_val}")
        if not limit_ok: return await interaction.followup.send(f"❌ Limit reached. Try again in {time_left//3600}h.", ephemeral=True)
        
        acc = await get_available_account("steam")
        if not acc: return await interaction.followup.send("❌ Out of stock!", ephemeral=True)
        
        set_limit(interaction.user.id, f"steam_{plan_val}")
        limit_max = 100 if plan_val == "exclusive" else (10 if plan_val == "premium" else 3)
        
        try:
            await interaction.user.send(f"🎁 **Steam Account ({plan_val.capitalize()})**\n\n```\n{acc}\n```\n\n*Limit: 1/{limit_max}*")
            await interaction.followup.send(f"Generated, Check Your DMs and Vouch <#{VOUCH_CHANNEL}> - Legit Ravex write")
        except:
            await interaction.followup.send("❌ DMs closed.", ephemeral=True)

    elif service_val == "netflix":
        limit_ok, time_left = check_limit(interaction.user.id, "netflix")
        if not limit_ok: return await interaction.followup.send(f"❌ Limit reached. Try again in {time_left//3600}h.", ephemeral=True)
        
        acc = await get_available_account("netflix")
        if not acc: return await interaction.followup.send("❌ Out of stock!", ephemeral=True)

        set_limit(interaction.user.id, "netflix")
        pending_netflix[interaction.user.id] = acc
        
        await interaction.followup.send(f"✅ Generated, Check Your DMs and Vouch <#{VOUCH_CHANNEL}> - Legit Ravex write (Wait 20 minutes)")
        
        owner = await bot.fetch_user(OWNER_ID)
        if owner:
            embed = discord.Embed(title="🎬 New Netflix Request", color=discord.Color.red())
            embed.add_field(name="User", value=f"{interaction.user.mention} (ID: {interaction.user.id})", inline=False)
            embed.add_field(name="Account Info", value=f"```{acc}```", inline=False)
            embed.set_footer(text="Reply with: .okey @user")
            await owner.send(embed=embed)

@bot.tree.command(name="delete", description="Delete messages")
@app_commands.describe(amount="Number of messages to scan and delete", empty_only="Sadece boş mesajları sil (True/False)")
async def delete_cmd(interaction: discord.Interaction, amount: int, empty_only: bool = True):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        if empty_only:
            deleted_count = 0
            async for message in interaction.channel.history(limit=amount):
                if not message.content.strip() or not message.content.isprintable():
                    try:
                        await message.delete()
                        deleted_count += 1
                    except:
                        pass
            await interaction.followup.send(f"✅ **{amount}** mesaj tarandı, **{deleted_count}** boş mesaj silindi.", ephemeral=True)
        else:
            await interaction.channel.purge(limit=amount)
            await interaction.followup.send(f"✅ **{amount}** mesaj silindi.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Hata: {e}", ephemeral=True)

@bot.tree.command(name="giveaway", description="Start a giveaway")
@app_commands.describe(channel="Channel", prize="Prize", duration="Duration (e.g. 10m, 1h, 1d)", winners="Number of winners")
async def giveaway_cmd(interaction: discord.Interaction, channel: discord.TextChannel, prize: str, duration: str, winners: int):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    
    seconds = 0
    if duration.endswith("s"): seconds = int(duration[:-1])
    elif duration.endswith("m"): seconds = int(duration[:-1]) * 60
    elif duration.endswith("h"): seconds = int(duration[:-1]) * 3600
    elif duration.endswith("d"): seconds = int(duration[:-1]) * 86400
    
    end_time = time.time() + seconds
    view = GiveawayView(prize, winners, end_time, interaction.user.id)
    try:
        msg = await channel.send(embed=view.get_embed(), view=view)
        bot.active_giveaways[msg.id] = view
        await interaction.followup.send(f"✅ Giveaway started in {channel.mention}", ephemeral=True)
    except Exception as e:
        return await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    await asyncio.sleep(seconds)
    if msg.id in bot.active_giveaways:
        g_view = bot.active_giveaways.pop(msg.id)
        g_view.stop()
        if not g_view.entries:
            await channel.send(f"❌ Giveaway for **{prize}** ended with no participants.")
        else:
            winners_list = random.sample(list(g_view.entries), min(winners, len(g_view.entries)))
            mentions = ", ".join([f"<@{w}>" for w in winners_list])
            await channel.send(f"🎉 **Giveaway Ended!**\nPrize: **{prize}**\nWinners: {mentions}\n\n*Congratulations! Open a ticket to claim your prize.*")

@bot.tree.command(name="unlocklimit", description="Reset a user's limit (Staff Only)")
async def unlocklimit_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    if user.id in bot.cooldowns: bot.cooldowns[user.id].clear()
    await interaction.followup.send(f"✅ Limits reset for {user.mention}.", ephemeral=True)

@bot.tree.command(name="premium", description="Give premium role (Staff Only)")
async def premium_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    role = interaction.guild.get_role(PREMIUM_ROLE)
    if not role:
        return await interaction.followup.send("❌ Premium role not found on this server.", ephemeral=True)
    
    try:
        await user.add_roles(role)
        await interaction.followup.send(f"✅ Gave {role.name} to {user.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to give this role (Check role hierarchy).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="exclusive", description="Give exclusive role (Staff Only)")
async def exclusive_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    role = interaction.guild.get_role(EXCLUSIVE_ROLE)
    if not role:
        return await interaction.followup.send("❌ Exclusive role not found on this server.", ephemeral=True)
        
    try:
        await user.add_roles(role)
        await interaction.followup.send(f"✅ Gave {role.name} to {user.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to give this role (Check role hierarchy).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a member")
async def ban_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        await member.ban(reason=reason)
        await interaction.followup.send(f"🔨 Banned {member.mention}. Reason: {reason}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="kick", description="Kick a member")
async def kick_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        await member.kick(reason=reason)
        await interaction.followup.send(f"👢 Kicked {member.mention}. Reason: {reason}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Mute a member (Timeout)")
async def mute_cmd(interaction: discord.Interaction, member: discord.Member, duration: int):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        await member.timeout(discord.utils.utcnow() + discord.timedelta(minutes=duration))
        await interaction.followup.send(f"🔇 Muted {member.mention} for {duration} minutes.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="unblacklist", description="Remove user from blacklist (Owner Only)")
async def unblacklist_cmd(interaction: discord.Interaction, user: discord.Member, duration: str):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(f"✅ {user.mention} has been removed from the blacklist.", ephemeral=True)

# ==================== OWNER DM KOMUTLARI ====================

@bot.event
async def on_message(message):
    if message.author.bot: return
    if not isinstance(message.channel, discord.DMChannel): return
    if message.author.id != OWNER_ID: return

    content = message.content.lower()
    
    if content.startswith(".okey"):
        try:
            user_id = int(message.content.split("<@")[1].split(">")[0].replace("!", ""))
            if user_id in pending_netflix:
                acc = pending_netflix.pop(user_id)
                approved_netflix[user_id] = acc
                user = await bot.fetch_user(user_id)
                await message.reply(f"✅ Okeylendi: **{user.name}**\nŞimdi hesabı göndermek için: `.send @{user.name}`")
            else:
                await message.reply("❌ Bu kullanıcı için bekleyen Netflix isteği yok.")
        except:
            await message.reply("❌ Kullanım: `.okey @kullanıcı`")
            
    elif content.startswith(".send"):
        try:
            user_id = int(message.content.split("<@")[1].split(">")[0].replace("!", ""))
            if user_id in approved_netflix:
                acc = approved_netflix.pop(user_id)
                user = await bot.fetch_user(user_id)
                
                try:
                    await user.send(f"🎬 **Generated Netflix:**\n```\n{acc}\n```\n\n**Do Vouch or You get blacklist in 2 hours.**\nVouch here: <#{VOUCH_CHANNEL}> and type `Ravex`")
                    await message.reply(f"✅ Hesap **{user.name}** kişisine DM'den gönderildi ve Vouch uyarısı yapıldı.")
                    
                    async def check_vouch():
                        await asyncio.sleep(7200)
                        vouch_channel = bot.get_channel(VOUCH_CHANNEL)
                        if vouch_channel:
                            async for msg in vouch_channel.history(limit=100):
                                if msg.author.id == user_id and "ravex" in msg.content.lower():
                                    try: await msg.add_reaction("✅")
                                    except: pass
                                    return
                            log_channel = bot.get_channel(TICKET_LOG_CHANNEL)
                            if log_channel:
                                await log_channel.send(f"⚠️ **Blacklist:** {user.mention} vouch atmadı.")
                    asyncio.create_task(check_vouch())
                    
                except discord.Forbidden:
                    await message.reply("❌ Kullanıcının DM'leri kapalı, gönderilemedi.")
            else:
                await message.reply("❌ Bu kullanıcı okeylenmemiş. Önce `.okey @kullanıcı` yaz.")
        except:
            await message.reply("❌ Kullanım: `.send @kullanıcı`")

    await bot.process_commands(message)

# ==================== ÇALIŞTIR ====================
if __name__ == "__main__":
    if not TOKEN or not OWNER_ID or not WEB_PASSWORD or not GITHUB_TOKEN or not GITHUB_REPO:
        print("❌ HATA: Eksik Çevre Değişkenleri! (DISCORD_TOKEN, OWNER_ID, WEB_PASSWORD, GITHUB_TOKEN, GITHUB_REPO)")
