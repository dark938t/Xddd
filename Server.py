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
OWNER_ID = int(os.getenv("OWNER_ID", 0))
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "ravex123")
WEB_PORT = int(os.getenv("PORT", 10000))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO") 

# STOK DOSYALARI (Normal artık stok.json kullanıyor)
FILES = {
    "normal": "stok.json",
    "premium": "Premiumstok.json",
    "exclusive": "Exclusivestok.json"
}

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
github_lock = asyncio.Lock()

# ==================== GITHUB VERİTABANI ====================
async def github_get_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

async def read_github_stock(plan_type):
    filename = FILES.get(plan_type.lower(), FILES["normal"])
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=await github_get_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                return json.loads(content), data['sha']
            return {"steam": [], "netflix": [], "used": []}, None

async def write_github_stock(plan_type, stock_data, sha):
    filename = FILES.get(plan_type.lower(), FILES["normal"])
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    content = base64.b64encode(json.dumps(stock_data, indent=2).encode('utf-8')).decode('utf-8')
    payload = {"message": "Bot stok guncellemesi", "content": content}
    if sha: payload["sha"] = sha
        
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=await github_get_headers(), json=payload) as resp:
            if resp.status not in [200, 201]:
                print(f"GitHub Save Error: {await resp.text()}")
                return False
            return True

async def add_stock_safely(plan_type, service, new_accounts):
    async with github_lock:
        for _ in range(3):
            stock, sha = await read_github_stock(plan_type)
            if service.lower() == "steam": stock["steam"].extend(new_accounts)
            else: stock["netflix"].extend(new_accounts)
            if await write_github_stock(plan_type, stock, sha): return True
            await asyncio.sleep(1)
        return False

async def get_available_account(plan_type, service):
    async with github_lock:
        stock, sha = await read_github_stock(plan_type)
        if service == "steam":
            lines = stock.get("steam", [])
            for i in range(0, len(lines), 2):
                if i+1 < len(lines):
                    acc = f"{lines[i]}\n{lines[i+1]}"
                    if acc not in stock.get("used", []):
                        stock["used"].append(acc)
                        await write_github_stock(plan_type, stock, sha)
                        return acc
        elif service == "netflix":
            lines = stock.get("netflix", [])
            for line in lines:
                if line not in stock.get("used", []):
                    stock["used"].append(line)
                    await write_github_stock(plan_type, stock, sha)
                    return line
        return None

async def count_stock(plan_type, service):
    stock, _ = await read_github_stock(plan_type)
    used = stock.get("used", [])
    if service == "steam":
        lines = stock.get("steam", [])
        return sum(1 for i in range(0, len(lines), 2) if i+1 < len(lines) and f"{lines[i]}\n{lines[i+1]}" not in used)
    return sum(1 for line in stock.get("netflix", []) if line not in used)
# =========================================================

# ==================== WEB SİTESİ (FLASK) ====================
web_app = Flask(__name__)
HTML_PAGE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Ravex Panel</title><style>body{font-family:sans-serif;background:#121212;color:#fff;padding:20px}.container{max-width:600px;margin:auto;background:#1e1e1e;padding:20px;border-radius:10px}input,select,textarea{width:100%;padding:10px;margin:5px 0;background:#2b2b2b;color:white;border:1px solid #333;box-sizing:border-box}button{width:100%;padding:10px;background:#7289da;color:white;border:none;margin-top:10px;cursor:pointer}.msg{margin-top:10px;text-align:center}</style></head><body><div class="container"><h2 style="text-align:center;">📦 Ravex Panel</h2><form method="POST"><label>Password</label><input type="password" name="password" required><label>Plan Türü</label><select name="plan"><option value="normal">Normal</option><option value="premium">Premium</option><option value="exclusive">Exclusive</option></select><label>Service</label><select name="service"><option value="steam">Steam</option><option value="netflix">Netflix</option></select><label>Accounts (One per line)</label><textarea name="accounts" rows="8" required></textarea><button type="submit">Add Stock</button></form>{% if message %}<div class="msg" style="color:{% if success %}lightgreen{% else %}red{% endif %};">{{ message }}</div>{% endif %}</div></body></html>"""

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@web_app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if request.form.get('password') != WEB_PASSWORD:
            return render_template_string(HTML_PAGE, message="Incorrect password!", success=False)
        plan_type, service, accounts_raw = request.form.get('plan'), request.form.get('service'), request.form.get('accounts')
        if not accounts_raw.strip(): return render_template_string(HTML_PAGE, message="Empty!", success=False)
        lines = [line.strip() for line in accounts_raw.split("\n") if line.strip()]
        success = run_async(add_stock_safely(plan_type, service, lines))
        return render_template_string(HTML_PAGE, message=f"Added to {plan_type.capitalize()}!" if success else "GitHub save failed!", success=success)
    return render_template_string(HTML_PAGE)

def run_web_server():
    web_app.run(host='0.0.0.0', port=WEB_PORT)
# =========================================================

# ==================== TICKET VE MENÜLER ====================
class TicketSelectMenu(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Support", emoji="🎧", value="Support"), discord.SelectOption(label="General", emoji="💬", value="General"), discord.SelectOption(label="Another", emoji="❓", value="Another")]
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options, custom_id="ticket_menu")
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
        if not any(r.id in STAFF_ROLES for r in interaction.user.roles): return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        button.disabled = True; button.label = f"Claimed by {interaction.user.name}"
        await interaction.message.edit(view=self); await interaction.response.send_message(f"✅ {interaction.user.mention} claimed.", ephemeral=False)
    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="t_close")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id in STAFF_ROLES for r in interaction.user.roles): return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        await interaction.response.send_message("🔒 Closing in 5s..."); await asyncio.sleep(5); await interaction.channel.delete()

class GiveawayView(discord.ui.View):
    def __init__(self, prize, winners, end_time, host_id):
        super().__init__(timeout=end_time - time.time())
        self.prize, self.winners_count, self.end_time, self.host_id, self.entries = prize, winners, end_time, host_id, set()
    def get_embed(self):
        embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"**Prize:** {self.prize}\n**Winners:** {self.winners_count}\n**Ends:** <t:{int(self.end_time)}:R>", color=discord.Color.gold())
        embed.add_field(name="Entries", value=f"👥 **{len(self.entries)}**"); return embed
    @discord.ui.button(label="Join", emoji="🎉", style=discord.ButtonStyle.success, custom_id="g_join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.entries: return await interaction.response.send_message("❌ Already joined!", ephemeral=True)
        self.entries.add(interaction.user.id); await interaction.message.edit(embed=self.get_embed()); await interaction.response.send_message("✅ Joined!", ephemeral=True)
    @discord.ui.button(label="Leave", emoji="🚪", style=discord.ButtonStyle.danger, custom_id="g_leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.entries: return await interaction.response.send_message("❌ Not in giveaway!", ephemeral=True)
        self.entries.remove(interaction.user.id); await interaction.message.edit(embed=self.get_embed()); await interaction.response.send_message("✅ Left.", ephemeral=True)

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

    async def on_ready(self):
        print(f"[+] Logged in as {self.user.name}")
        await self.change_presence(activity=discord.Game(name="Made By kaptan9021_2"))
        if not any(t.name == "WebServerThread" for t in threading.enumerate()):
            threading.Thread(target=run_web_server, daemon=True, name="WebServerThread").start()

    async def on_member_join(self, member):
        role = member.guild.get_role(JOIN_ROLE)
        if role:
            try: await member.add_roles(role)
            except: pass

bot = MyBot()

# ==================== YARDIMCI FONKSİYONLAR ====================
def get_ticket_number(guild): return len([c for c in guild.channels if c.name.startswith("ticket-")]) + 1

async def create_ticket(interaction: discord.Interaction, category: str):
    guild = interaction.guild
    staff_roles = [guild.get_role(r) for r in STAFF_ROLES]
    overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False), interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
    for role in staff_roles:
        if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    t_num = get_ticket_number(guild)
    try:
        channel = await guild.create_text_channel(name=f"ticket-{t_num}", overwrites=overwrites)
        embed = discord.Embed(title=f"Ticket #{t_num}", description=f"Category: **{category}**\nOpened by: {interaction.user.mention}", color=discord.Color.blue())
        await channel.send(content=" ".join([r.mention for r in staff_roles if r]), embed=embed, view=TicketControlView())
        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

def check_limit(user_id, type_):
    if user_id not in bot.cooldowns: bot.cooldowns[user_id] = {}
    if type_ in bot.cooldowns[user_id]:
        elapsed = time.time() - bot.cooldowns[user_id][type_]
        if elapsed < 86400: return False, int(86400 - elapsed)
    return True, 0

def set_limit(user_id, type_):
    if user_id not in bot.cooldowns: bot.cooldowns[user_id] = {}
    bot.cooldowns[user_id][type_] = time.time()

# ==================== SLASH KOMUTLARI ====================
@bot.tree.command(name="ticket", description="Open a ticket")
async def ticket_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=discord.Embed(title="🎟️ Support", description="Select category.", color=discord.Color.blurple()), view=TicketMenuView())

@bot.tree.command(name="stock", description="Check stock")
async def stock_cmd(interaction: discord.Interaction):
    await interaction.response.defer() 
    try:
        nf_n = await count_stock("normal", "netflix"); st_n = await count_stock("normal", "steam")
        nf_p = await count_stock("premium", "netflix"); st_p = await count_stock("premium", "steam")
        nf_e = await count_stock("exclusive", "netflix"); st_e = await count_stock("exclusive", "steam")
        
        embed = discord.Embed(title="📦 Current Stock", color=discord.Color.green())
        embed.add_field(name="💎 Premium", value=f"Netflix: **{nf_p}** | Steam: **{st_p}**", inline=False)
        embed.add_field(name="👑 Exclusive", value=f"Steam: **{st_e}** | Netflix: **{nf_e}**", inline=False)
        embed.add_field(name="🟢 Normal", value=f"Steam: **{st_n}** | Netflix: **{nf_n}**", inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e: await interaction.followup.send(f"❌ Error: {e}")

@bot.tree.command(name="generate", description="Generate account")
@app_commands.choices(service=[app_commands.Choice(name="Netflix", value="netflix"), app_commands.Choice(name="Steam", value="steam")], plan=[app_commands.Choice(name="Normal", value="normal"), app_commands.Choice(name="Premium", value="premium"), app_commands.Choice(name="Exclusive", value="exclusive")])
async def generate_cmd(interaction: discord.Interaction, service: app_commands.Choice[str], plan: app_commands.Choice[str]):
    user_roles, svc, pln = [r.id for r in interaction.user.roles], service.value, plan.value
    if pln in ["premium", "exclusive"] and interaction.channel_id != PREMIUM_EXCLUSIVE_CHANNEL: return await interaction.response.send_message(f"❌ Use in <#{PREMIUM_EXCLUSIVE_CHANNEL}>.", ephemeral=True)
    if pln == "premium" and PREMIUM_ROLE not in user_roles: return await interaction.response.send_message("❌ No Premium role.", ephemeral=True)
    if pln == "exclusive" and EXCLUSIVE_ROLE not in user_roles: return await interaction.response.send_message("❌ No Exclusive role.", ephemeral=True)
    
    await interaction.response.defer() 
    try:
        limit_ok, t_left = check_limit(interaction.user.id, f"{svc}_{pln}")
        if not limit_ok: return await interaction.followup.send(f"❌ Limit reached. Wait {t_left//3600}h.", ephemeral=True)
        
        acc = await get_available_account(pln, svc)
        if not acc: return await interaction.followup.send(f"❌ {pln.capitalize()} out of stock for {svc}!", ephemeral=True)
        
        set_limit(interaction.user.id, f"{svc}_{pln}")
        limit_max = 100 if pln == "exclusive" else (10 if pln == "premium" else 3)
        
        if svc == "steam":
            await interaction.user.send(f"🎁 **Steam ({pln.capitalize()})**\n\n```\n{acc}\n```\n\n*Limit: 1/{limit_max}*")
            await interaction.followup.send(f"Generated, Check DMs and Vouch <#{VOUCH_CHANNEL}>")
        else:
            pending_netflix[interaction.user.id] = acc
            await interaction.followup.send(f"✅ Generated, Wait 20 minutes.")
            owner = await bot.fetch_user(OWNER_ID)
            if owner:
                embed = discord.Embed(title=f"🎬 Netflix Request ({pln.capitalize()})", color=discord.Color.red())
                embed.add_field(name="User", value=f"{interaction.user.mention}", inline=False); embed.add_field(name="Acc", value=f"```{acc}```", inline=False)
                embed.set_footer(text="Reply: .okey @user"); await owner.send(embed=embed)
    except discord.Forbidden: await interaction.followup.send("❌ DMs closed.", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="delete", description="Delete messages")
async def delete_cmd(interaction: discord.Interaction, amount: int, empty_only: bool = True):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        if empty_only:
            cnt = 0
            async for msg in interaction.channel.history(limit=amount):
                if not msg.content.strip() or not msg.content.isprintable():
                    try: await msg.delete(); cnt += 1
                    except: pass
            await interaction.followup.send(f"✅ Deleted {cnt} empty messages.", ephemeral=True)
        else: await interaction.channel.purge(limit=amount); await interaction.followup.send(f"✅ Deleted {amount} messages.", ephemeral=True)
    except Exception as e: await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="giveaway", description="Start giveaway")
async def giveaway_cmd(interaction: discord.Interaction, channel: discord.TextChannel, prize: str, duration: str, winners: int):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        sec = int(duration[:-1]) * (60 if duration.endswith("m") else 3600 if duration.endswith("h") else 86400 if duration.endswith("d") else 1)
        view = GiveawayView(prize, winners, time.time() + sec, interaction.user.id)
        msg = await channel.send(embed=view.get_embed(), view=view); bot.active_giveaways[msg.id] = view
        await interaction.followup.send(f"✅ Giveaway started in {channel.mention}", ephemeral=True)
        await asyncio.sleep(sec)
        if msg.id in bot.active_giveaways:
            g = bot.active_giveaways.pop(msg.id); g.stop()
            if not g.entries: await channel.send(f"❌ No participants for {prize}.")
            else:
                wins = random.sample(list(g.entries), min(winners, len(g.entries)))
                await channel.send(f"🎉 **Ended!**\nPrize: **{prize}**\nWinners: {', '.join([f'<@{w}>' for w in wins])}")
    except Exception as e: await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="unlocklimit", description="Reset limit")
async def unlocklimit_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    if user.id in bot.cooldowns: bot.cooldowns[user.id].clear()
    await interaction.followup.send(f"✅ Reset for {user.mention}.", ephemeral=True)

@bot.tree.command(name="premium", description="Give Premium")
async def premium_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    role = interaction.guild.get_role(PREMIUM_ROLE)
    if role:
        try: await user.add_roles(role); await interaction.followup.send("✅ Done.")
        except: await interaction.followup.send("❌ Role Error.")

@bot.tree.command(name="exclusive", description="Give Exclusive")
async def exclusive_cmd(interaction: discord.Interaction, user: discord.Member):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    role = interaction.guild.get_role(EXCLUSIVE_ROLE)
    if role:
        try: await user.add_roles(role); await interaction.followup.send("✅ Done.")
        except: await interaction.followup.send("❌ Role Error.")

@bot.tree.command(name="ban", description="Ban member")
async def ban_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "None"):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True); await member.ban(reason=reason); await interaction.followup.send(f"🔨 Banned {member.mention}.", ephemeral=True)

@bot.tree.command(name="kick", description="Kick member")
async def kick_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "None"):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True); await member.kick(reason=reason); await interaction.followup.send(f"👢 Kicked {member.mention}.", ephemeral=True)

@bot.tree.command(name="mute", description="Mute member")
async def mute_cmd(interaction: discord.Interaction, member: discord.Member, duration: int):
    if not any(r.id in STAFF_ROLES for r in interaction.user.roles) and interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True); await member.timeout(discord.utils.utcnow() + discord.timedelta(minutes=duration)); await interaction.followup.send(f"🔇 Muted {member.mention}.", ephemeral=True)

@bot.tree.command(name="unblacklist", description="Remove BL")
async def unblacklist_cmd(interaction: discord.Interaction, user: discord.Member, duration: str):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
    await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"✅ Removed {user.mention}.", ephemeral=True)

# ==================== OWNER DM KOMUTLARI ====================
@bot.event
async def on_message(message):
    if message.author.bot or not isinstance(message.channel, discord.DMChannel) or message.author.id != OWNER_ID: return
    content = message.content.lower().strip()
    
    parts = message.content.split("<@")
    if len(parts) > 1:
        user_id_str = parts[1].split(">")[0].replace("!", "")
        try: user_id = int(user_id_str)
        except ValueError: return await message.reply("❌ Geçersiz kullanıcı etiketi.")
    else:
        return await message.reply("❌ Kullanım: `.okey @kullanıcı` veya `.send @kullanıcı`")

    if content.startswith(".okey"):
        if user_id in pending_netflix:
            acc = pending_netflix.pop(user_id)
            approved_netflix[user_id] = acc
            user = await bot.fetch_user(user_id)
            await message.reply(f"✅ Okeylendi: **{user.name}**\n`.send @{user.name}`")
        else: await message.reply("❌ Bu kullanıcı için bekleyen Netflix isteği yok.")
            
    elif content.startswith(".send"):
        if user_id in approved_netflix:
            acc = approved_netflix.pop(user_id)
            user = await bot.fetch_user(user_id)
            try:
                await user.send(f"🎬 **Netflix:**\n```\n{acc}\n```\n\n**Do Vouch or Blacklist in 2h.**\nVouch: <#{VOUCH_CHANNEL}> write `Ravex`")
                await message.reply(f"✅ Sent to **{user.name}**.")
                async def check_vouch():
                    await asyncio.sleep(7200)
                    vch = bot.get_channel(VOUCH_CHANNEL)
                    if vch:
                        async for msg in vch.history(limit=100):
                            if msg.author.id == user_id and "ravex" in msg.content.lower():
                                try: await msg.add_reaction("✅")
                                except: pass
                                return
                        log = bot.get_channel(TICKET_LOG_CHANNEL)
                        if log: await log.send(f"⚠️ **Blacklist:** {user.mention} vouch atmadı.")
                asyncio.create_task(check_vouch())
            except discord.Forbidden: await message.reply("❌ User DMs closed.")
        else: await message.reply("❌ Bu kullanıcı okeylenmemiş. Önce `.okey` yaz.")
    await bot.process_commands(message)

if __name__ == "__main__":
    if not TOKEN or not OWNER_ID or not GITHUB_TOKEN or not GITHUB_REPO:
        print("❌ Eksik Environment değişkeni!")
        exit()
    bot.run(TOKEN)
