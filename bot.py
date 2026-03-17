import discord
from discord.ext import commands
from datetime import datetime, timezone
import json, os

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

DATA_FILE = "nxt_data.json"

def default_data():
    return {
        "roster": {},
        "championships": {
            "NXT Championship":                {"holder": None, "since": None},
            "NXT Women's Championship":        {"holder": None, "since": None},
            "NXT Tag Team Championship":       {"holder": None, "since": None},
            "NXT North American Championship": {"holder": None, "since": None},
        },
        "shows": [],
        "promo_sessions": {},
        "leaderboard": {},
    }

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return default_data()

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

data = load_data()

def lb_add(user_id: str, field: str, amount: int = 1):
    if user_id not in data["leaderboard"]:
        data["leaderboard"][user_id] = {"wins": 0, "titles": 0, "promos": 0}
    data["leaderboard"][user_id][field] = data["leaderboard"][user_id].get(field, 0) + amount

def days_since(iso_str):
    if not iso_str:
        return 0
    since = datetime.fromisoformat(iso_str)
    return (datetime.now(timezone.utc) - since).days

def find_roster_member(name_or_id: str):
    for uid, dname in data["roster"].items():
        if uid == name_or_id or dname.lower() == name_or_id.lower():
            return uid, dname
    return None, None

# ═══════════════════════════════════════════════════════════════════
#  .addroster / .removeroster
# ═══════════════════════════════════════════════════════════════════

@bot.command(name="addroster")
async def addroster(ctx, member: discord.Member):
    uid = str(member.id)
    if uid in data["roster"]:
        await ctx.send(f"⚠️ **{member.display_name}** is already on the NXT roster.")
        return
    data["roster"][uid] = member.display_name
    lb_add(uid, "wins", 0)
    save_data()
    embed = discord.Embed(
        title="✅ Signed to NXT!",
        description=f"**{member.display_name}** has joined the NXT roster!",
        color=0xFFD700
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="removeroster")
async def removeroster(ctx, member: discord.Member):
    uid = str(member.id)
    if uid not in data["roster"]:
        await ctx.send(f"⚠️ **{member.display_name}** is not on the roster.")
        return
    for title, info in data["championships"].items():
        if info["holder"] == data["roster"][uid]:
            data["championships"][title] = {"holder": None, "since": None}
            await ctx.send(f"⚠️ **{title}** has been **VACATED**.")
    del data["roster"][uid]
    save_data()
    await ctx.send(f"✅ **{member.display_name}** has been released from NXT.")

# ═══════════════════════════════════════════════════════════════════
#  .roster
# ═══════════════════════════════════════════════════════════════════

@bot.command(name="roster")
async def show_roster(ctx):
    if not data["roster"]:
        await ctx.send("The NXT roster is currently empty.")
        return
    embed = discord.Embed(title="🎤 NXT Roster", color=0x1a1a2e)
    lines = []
    for uid, name in data["roster"].items():
        lb    = data["leaderboard"].get(uid, {})
        wins  = lb.get("wins", 0)
        titles = lb.get("titles", 0)
        is_champ = any(info["holder"] == name for info in data["championships"].values())
        badge = " 🏆" if is_champ else ""
        lines.append(f"**{name}**{badge} — Wins: {wins} | Title reigns: {titles}")
    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{len(data['roster'])} superstars on the NXT roster")
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════
#  .settitleholder
# ═══════════════════════════════════════════════════════════════════

class TitleSelect(discord.ui.Select):
    def __init__(self, winner_name, winner_id):
        self.winner_name = winner_name
        self.winner_id   = winner_id
        options = [
            discord.SelectOption(label=t, emoji="🏆")
            for t in data["championships"].keys()
        ]
        super().__init__(placeholder="Choose a title...", options=options)

    async def callback(self, interaction: discord.Interaction):
        title = self.values[0]
        old   = data["championships"][title]["holder"]
        data["championships"][title] = {
            "holder": self.winner_name,
            "since":  datetime.now(timezone.utc).isoformat(),
        }
        lb_add(self.winner_id, "titles")
        save_data()
        embed = discord.Embed(
            title="🏆 NEW CHAMPION!",
            description=f"**{self.winner_name}** is the NEW **{title}**!",
            color=0xFFD700
        )
        if old:
            embed.add_field(name="Previous Champion", value=old)
        await interaction.response.edit_message(embed=embed, view=None)

class TitleView(discord.ui.View):
    def __init__(self, winner_name, winner_id):
        super().__init__(timeout=60)
        self.add_item(TitleSelect(winner_name, winner_id))

@bot.command(name="settitleholder")
async def settitleholder(ctx, member: discord.Member):
    uid  = str(member.id)
    name = data["roster"].get(uid, member.display_name)
    embed = discord.Embed(
        title="🏆 Assign Title",
        description=f"Select which title to give **{name}**:",
        color=0xFFD700
    )
    await ctx.send(embed=embed, view=TitleView(name, uid))

# ═══════════════════════════════════════════════════════════════════
#  .winner
# ═══════════════════════════════════════════════════════════════════

class WinnerSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, value=uid)
            for uid, name in list(data["roster"].items())[:25]
        ]
        super().__init__(placeholder="Select the winner...", options=options)

    async def callback(self, interaction: discord.Interaction):
        uid  = self.values[0]
        name = data["roster"].get(uid, "Unknown")
        lb_add(uid, "wins")
        save_data()
        embed = discord.Embed(
            title="🎉 Match Result Recorded",
            description=f"**{name}** wins! 🙌",
            color=0x00ff88
        )
        await interaction.response.edit_message(embed=embed, view=None)

class WinnerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(WinnerSelect())

@bot.command(name="winner")
async def winner(ctx):
    if not data["roster"]:
        await ctx.send("No roster members found. Use `.addroster` first.")
        return
    embed = discord.Embed(
        title="🎯 Record Match Winner",
        description="Tap the name of the superstar who won:",
        color=0x00ff88
    )
    await ctx.send(embed=embed, view=WinnerView())

# ═══════════════════════════════════════════════════════════════════
#  .titledays
# ═══════════════════════════════════════════════════════════════════

class TitleDaysSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=t, emoji="📅")
            for t in data["championships"].keys()
        ]
        super().__init__(placeholder="Select a title...", options=options)

    async def callback(self, interaction: discord.Interaction):
        title = self.values[0]
        info  = data["championships"][title]
        if not info["holder"]:
            embed = discord.Embed(
                title=f"📅 {title}",
                description="This title is currently **VACANT**.",
                color=0x888888
            )
        else:
            days = days_since(info["since"])
            embed = discord.Embed(
                title=f"📅 {title}",
                description=f"**{info['holder']}** has held this title for **{days} day(s)**.",
                color=0xFFD700
            )
        await interaction.response.edit_message(embed=embed, view=None)

class TitleDaysView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(TitleDaysSelect())

@bot.command(name="titledays")
async def titledays(ctx):
    embed = discord.Embed(
        title="📅 Title Reign Length",
        description="Select a title to check days held:",
        color=0xFFD700
    )
    await ctx.send(embed=embed, view=TitleDaysView())

# ═══════════════════════════════════════════════════════════════════
#  .book
# ═══════════════════════════════════════════════════════════════════

SHOW_NAMES = ["NXT TakeOver", "NXT Weekly", "NXT Deadline", "NXT Battleground", "NXT Halloween Havoc"]
STIPS      = ["Standard", "Ladder Match", "Steel Cage", "Last Man Standing", "No DQ", "Iron Man", "TLC"]

class ShowNameSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=s, emoji="📺") for s in SHOW_NAMES]
        super().__init__(placeholder="Pick a show...", options=options)

    async def callback(self, interaction: discord.Interaction):
        show_name = self.values[0]
        embed = discord.Embed(
            title=f"📺 Booking: {show_name}",
            description="Now select **Superstar 1**:",
            color=0x1a1a2e
        )
        await interaction.response.edit_message(embed=embed, view=Participant1View(show_name))

class ShowNameView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ShowNameSelect())

class Participant1Select(discord.ui.Select):
    def __init__(self, show_name):
        self.show_name = show_name
        options = [
            discord.SelectOption(label=name, value=uid)
            for uid, name in list(data["roster"].items())[:25]
        ]
        super().__init__(placeholder="Select Superstar 1...", options=options)

    async def callback(self, interaction: discord.Interaction):
        uid1  = self.values[0]
        name1 = data["roster"].get(uid1, "Unknown")
        embed = discord.Embed(
            title=f"📺 Booking: {self.show_name}",
            description=f"**{name1}** vs ❓\nNow select **Superstar 2**:",
            color=0x1a1a2e
        )
        await interaction.response.edit_message(embed=embed, view=Participant2View(self.show_name, uid1, name1))

class Participant1View(discord.ui.View):
    def __init__(self, show_name):
        super().__init__(timeout=120)
        self.add_item(Participant1Select(show_name))

class Participant2Select(discord.ui.Select):
    def __init__(self, show_name, uid1, name1):
        self.show_name = show_name
        self.uid1      = uid1
        self.name1     = name1
        options = [
            discord.SelectOption(label=name, value=uid)
            for uid, name in list(data["roster"].items())[:25]
            if uid != uid1
        ]
        super().__init__(placeholder="Select Superstar 2...", options=options)

    async def callback(self, interaction: discord.Interaction):
        uid2  = self.values[0]
        name2 = data["roster"].get(uid2, "Unknown")
        embed = discord.Embed(
            title=f"📺 Booking: {self.show_name}",
            description=f"**{self.name1}** vs **{name2}**\nAdd a stipulation?",
            color=0x1a1a2e
        )
        await interaction.response.edit_message(
            embed=embed,
            view=StipulationView(self.show_name, self.uid1, self.name1, uid2, name2)
        )

class Participant2View(discord.ui.View):
    def __init__(self, show_name, uid1, name1):
        super().__init__(timeout=120)
        self.add_item(Participant2Select(show_name, uid1, name1))

class StipulationSelect(discord.ui.Select):
    def __init__(self, show_name, uid1, name1, uid2, name2):
        self.show_name = show_name
        self.uid1, self.name1 = uid1, name1
        self.uid2, self.name2 = uid2, name2
        options = [discord.SelectOption(label=s) for s in STIPS]
        super().__init__(placeholder="Select stipulation...", options=options)

    async def callback(self, interaction: discord.Interaction):
        stip = self.values[0]
        show = {
            "show":   self.show_name,
            "s1":     self.name1,
            "s2":     self.name2,
            "stip":   stip,
            "title":  None,
            "result": None,
        }
        data["shows"].append(show)
        save_data()
        embed = discord.Embed(title="✅ Match Booked!", color=0xFFD700)
        embed.add_field(name="Show",        value=self.show_name, inline=True)
        embed.add_field(name="Match",       value=f"{self.name1} vs {self.name2}", inline=True)
        embed.add_field(name="Stipulation", value=stip, inline=True)
        await interaction.response.edit_message(embed=embed, view=None)

class StipulationView(discord.ui.View):
    def __init__(self, show_name, uid1, name1, uid2, name2):
        super().__init__(timeout=120)
        self.add_item(StipulationSelect(show_name, uid1, name1, uid2, name2))

@bot.command(name="book")
async def book_show(ctx):
    if not data["roster"]:
        await ctx.send("No roster members. Use `.addroster` first.")
        return
    embed = discord.Embed(
        title="📺 Book a Match",
        description="Step 1: Choose the show",
        color=0x1a1a2e
    )
    await ctx.send(embed=embed, view=ShowNameView())

# ═══════════════════════════════════════════════════════════════════
#  .lb
# ═══════════════════════════════════════════════════════════════════

@bot.command(name="lb")
async def leaderboard(ctx):
    lb = data["leaderboard"]
    if not lb:
        await ctx.send("No leaderboard data yet.")
        return
    sorted_lb = sorted(lb.items(), key=lambda x: (x[1].get("titles", 0), x[1].get("wins", 0)), reverse=True)
    embed = discord.Embed(title="🏅 NXT Leaderboard", color=0xFFD700)
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, stats) in enumerate(sorted_lb[:10]):
        name   = data["roster"].get(uid, f"<@{uid}>")
        medal  = medals[i] if i < 3 else f"#{i+1}"
        wins   = stats.get("wins", 0)
        titles = stats.get("titles", 0)
        promos = stats.get("promos", 0)
        embed.add_field(
            name=f"{medal} {name}",
            value=f"Wins: **{wins}** | Title Reigns: **{titles}** | Promos: **{promos}**",
            inline=False
        )
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════
#  .promo
# ═══════════════════════════════════════════════════════════════════

PROMO_TYPES = {
    "Challenge":     "🎯 Calling out your opponent for a match",
    "Trash Talk":    "🗣️ Going off on your opponent ruthlessly",
    "Hype":          "🔥 Building yourself up before a big match",
    "Heel Turn":     "😈 Turning on someone / betrayal promo",
    "Face Comeback": "💪 Emotional fired-up baby face promo",
}

class PromoTypeSelect(discord.ui.Select):
    def __init__(self, channel_id, starter_id, starter_name, opponent_id, opponent_name):
        self.channel_id    = str(channel_id)
        self.starter_id    = str(starter_id)
        self.starter_name  = starter_name
        self.opponent_id   = str(opponent_id)
        self.opponent_name = opponent_name
        options = [
            discord.SelectOption(label=ptype, description=desc[:50])
            for ptype, desc in PROMO_TYPES.items()
        ]
        super().__init__(placeholder="Pick the promo type...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.starter_id:
            await interaction.response.send_message("Only the promo starter can pick the type!", ephemeral=True)
            return
        ptype = self.values[0]
        session = {
            "type":         ptype,
            "participants": [self.starter_id, self.opponent_id],
            "names":        {self.starter_id: self.starter_name, self.opponent_id: self.opponent_name},
            "turn":         0,
            "round":        1,
            "max_rounds":   3,
            "cuts":         [],
        }
        data["promo_sessions"][self.channel_id] = session
        save_data()
        embed = discord.Embed(
            title=f"🎤 PROMO BATTLE — {ptype}",
            description=(
                f"**{self.starter_name}** vs **{self.opponent_name}**\n\n"
                f"📋 *{PROMO_TYPES[ptype]}*\n\n"
                f"**{self.starter_name}**, you're up first!\n"
                f"Use `.promo cut <your promo text>` to cut your promo."
            ),
            color=0xFF4500
        )
        embed.set_footer(text=f"Round 1 of 3 | Turn: {self.starter_name}")
        await interaction.response.edit_message(embed=embed, view=None)

class PromoTypeView(discord.ui.View):
    def __init__(self, channel_id, starter_id, starter_name, opponent_id, opponent_name):
        super().__init__(timeout=120)
        self.add_item(PromoTypeSelect(channel_id, starter_id, starter_name, opponent_id, opponent_name))

class PromoOpponentSelect(discord.ui.Select):
    def __init__(self, ctx):
        self.ctx = ctx
        options = [
            discord.SelectOption(label=name, value=uid)
            for uid, name in list(data["roster"].items())[:25]
            if uid != str(ctx.author.id)
        ]
        super().__init__(placeholder="Select your opponent...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.ctx.author.id):
            await interaction.response.send_message("Only the promo starter can pick!", ephemeral=True)
            return
        opp_id       = self.values[0]
        opp_name     = data["roster"].get(opp_id, "Unknown")
        starter_id   = str(self.ctx.author.id)
        starter_name = data["roster"].get(starter_id, self.ctx.author.display_name)
        embed = discord.Embed(
            title="🎤 Promo Battle",
            description=f"**{starter_name}** vs **{opp_name}**\n\nChoose the **promo type**:",
            color=0xFF4500
        )
        await interaction.response.edit_message(
            embed=embed,
            view=PromoTypeView(self.ctx.channel.id, starter_id, starter_name, opp_id, opp_name)
        )

class PromoOpponentView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=120)
        self.add_item(PromoOpponentSelect(ctx))

@bot.command(name="promo")
async def promo(ctx, subcommand: str = None, *, text: str = None):
    channel_id = str(ctx.channel.id)

    if subcommand is None or subcommand.lower() == "start":
        uid = str(ctx.author.id)
        if uid not in data["roster"]:
            await ctx.send("You must be on the NXT roster! Ask a GM to `.addroster` you.")
            return
        if channel_id in data["promo_sessions"]:
            await ctx.send("⚠️ A promo battle is already running here! Finish it first.")
            return
        embed = discord.Embed(
            title="🎤 Starting a Promo Battle",
            description=f"**{ctx.author.display_name}** wants to cut a promo!\nSelect your opponent:",
            color=0xFF4500
        )
        await ctx.send(embed=embed, view=PromoOpponentView(ctx))
        return

    if subcommand.lower() == "cut":
        if channel_id not in data["promo_sessions"]:
            await ctx.send("No promo session active. Use `.promo` to start one.")
            return
        session       = data["promo_sessions"][channel_id]
        whose_turn_id = session["participants"][session["turn"]]
        if str(ctx.author.id) != whose_turn_id:
            whose_turn_name = session["names"][whose_turn_id]
            await ctx.send(f"⚠️ It's **{whose_turn_name}'s** turn!", delete_after=5)
            return
        if not text:
            await ctx.send("Add your promo text: `.promo cut <your words here>`")
            return
        cutter_name = session["names"][whose_turn_id]
        session["cuts"].append({"name": cutter_name, "text": text})
        lb_add(whose_turn_id, "promos")
        session["turn"] = 1 - session["turn"]
        next_id   = session["participants"][session["turn"]]
        next_name = session["names"][next_id]
        embed = discord.Embed(
            title=f"🎤 {cutter_name} cuts a promo!",
            description=f'*"{text}"*',
            color=0xFF4500
        )
        embed.set_footer(text=f"Round {session['round']} | Type: {session['type']}")
        if len(session["cuts"]) % 2 == 0:
            session["round"] += 1
            if session["round"] > session["max_rounds"]:
                del data["promo_sessions"][channel_id]
                save_data()
                summary = "\n\n".join([f"**{c['name']}:** *\"{c['text']}\"*" for c in session["cuts"]])
                end_embed = discord.Embed(
                    title=f"🎤 Promo Battle Over! — {session['type']}",
                    description=summary,
                    color=0xFFD700
                )
                end_embed.set_footer(text="React with 🏆 to vote for your favourite!")
                await ctx.send(embed=embed)
                msg = await ctx.send(embed=end_embed)
                await msg.add_reaction("🏆")
                return
            else:
                embed.add_field(name=f"Round {session['round']} begins!", value=f"**{next_name}**, fire back!", inline=False)
        else:
            embed.add_field(name="Your turn!", value=f"**{next_name}**, use `.promo cut <words>`", inline=False)
        save_data()
        await ctx.send(embed=embed)
        return

    if subcommand.lower() == "end":
        if channel_id in data["promo_sessions"]:
            del data["promo_sessions"][channel_id]
            save_data()
            await ctx.send("🎤 Promo session ended.")
        else:
            await ctx.send("No active promo session.")
        return

    await ctx.send("Usage: `.promo` to start | `.promo cut <text>` for your turn | `.promo end` to cancel")

# ═══════════════════════════════════════════════════════════════════
#  READY
# ═══════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f"✅ NXT Bot online as {bot.user}")

bot.run(TOKEN)
