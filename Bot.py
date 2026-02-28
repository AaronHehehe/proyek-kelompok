import discord
from discord.ext import commands
import sqlite3
import random
import datetime
import asyncio

STARTER_POKEMON = ["charmander", "bulbasaur", "squirtle"]
STARTER_LEVEL = 5
trade_requests = {}
MAX_POKEMON = 30
MAX_LEVEL = 120 
pvp_requests = {}
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
TYPE_EFFECTIVENESS = {
    ("Fire", "Grass"): 2,
    ("Fire", "Water"): 0.5,
    ("Water", "Fire"): 2,
    ("Water", "Grass"): 0.5,
    ("Grass", "Water"): 2,
    ("Grass", "Fire"): 0.5,
}

def has_pokemon(user_id):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM user_pokemon
        WHERE user_id=?
    """, (str(user_id),))

    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

def init_money_table():
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_money (
            user_id TEXT PRIMARY KEY,
            money INTEGER DEFAULT 500
        )
    """)
    conn.commit()
    conn.close()

init_money_table()

def get_money(user_id):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO user_money (user_id) VALUES (?)",
        (str(user_id),)
    )
    cursor.execute(
        "SELECT money FROM user_money WHERE user_id=?",
        (str(user_id),)
    )
    money = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return money

def calculate_sell_price(level):
    return 50 + (level * 10)

@bot.command()
async def sell(ctx, index: int):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, pokemon_name, level
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
    """, (str(ctx.author.id),))

    rows = cursor.fetchall()

    if not rows:
        await ctx.send("📭 Kamu tidak punya Pokémon.")
        conn.close()
        return

    if index < 1 or index > len(rows):
        await ctx.send("❌ Nomor Pokémon tidak valid.")
        conn.close()
        return

    pokemon_id, name, level = rows[index - 1]
    price = calculate_sell_price(level)

    # hapus pokemon
    cursor.execute(
        "DELETE FROM user_pokemon WHERE id=?",
        (pokemon_id,)
    )
    conn.commit()
    conn.close()

    # tambah uang
    current_money = get_money(ctx.author.id)
    update_money(ctx.author.id, current_money + price)

    await ctx.send(
        f"💰 **{name} (Lv.{level}) berhasil dijual!**\n"
        f"🪙 Harga: {price}\n"
        f"💼 Saldo sekarang: {get_money(ctx.author.id)}"
    )

def update_money(user_id, amount):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_money SET money=? WHERE user_id=?",
        (amount, str(user_id))
    )
    conn.commit()
    conn.close()

def battle_engine(p1, p2, allow_heal=False):
    log = []

    turn_p1 = p1["speed"] >= p2["speed"]

    for _ in range(20):  # max 20 turn
        if p1["hp"] <= 0 or p2["hp"] <= 0:
            break

        attacker = p1 if turn_p1 else p2
        defender = p2 if turn_p1 else p1

        # heal (opsional)
        if (
            allow_heal
            and attacker.get("heal_used") is False
            and attacker["hp"] < attacker["max_hp"] * 0.3
        ):
            heal = int(attacker["max_hp"] * 0.25)
            attacker["hp"] += heal
            attacker["heal_used"] = True
            log.append(f"💉 {attacker['name']} heal (+{heal} HP)")
        else:
            dmg, info = calculate_damage(attacker, defender)
            defender["hp"] -= dmg
            log.append(
                f"⚔️ {attacker['name']} menyerang (-{dmg} HP){info}"
            )

        turn_p1 = not turn_p1

    winner = p1 if p1["hp"] > 0 else p2
    return log, winner

def get_pokemon_type(name):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Type1
        FROM Pokemon
        WHERE LOWER(Name)=?
    """, (name.lower(),))

    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Normal"

def calculate_damage(attacker, defender):
    base = max(1, attacker["atk"] - defender["def"] // 2)

    # type advantage
    multiplier = TYPE_EFFECTIVENESS.get(
        (attacker["type"], defender["type"]),
        1
    )

    # critical hit (10%)
    crit = random.randint(1, 100) <= 10
    if crit:
        multiplier *= 1.5

    damage = int(base * multiplier)

    info = ""
    if multiplier > 1:
        info += " 🔥 Super Effective!"
    elif multiplier < 1:
        info += " 🪨 Not Very Effective..."
    if crit:
        info += " 💥 CRITICAL!"

    return damage, info

def exp_to_next(level):
    return 100 + (level * 50)

def get_player(user_id):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO player (user_id) VALUES (?)",
        (str(user_id),)
    )
    cursor.execute(
        "SELECT level, exp FROM player WHERE user_id=?",
        (str(user_id),)
    )

    data = cursor.fetchone()
    conn.commit()
    conn.close()
    return data  # (level, exp)

def add_exp(user_id, amount):
    level, exp = get_player(user_id)
    exp += amount

    leveled_up = False

    while exp >= exp_to_next(level):
        exp -= exp_to_next(level)
        level += 1
        leveled_up = True

        # 🎁 reward level up
        update_money(user_id, get_money(user_id) + 100)

    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE player SET level=?, exp=? WHERE user_id=?",
        (level, exp, str(user_id))
    )
    conn.commit()
    conn.close()

    return leveled_up, level, exp

def get_first_user_pokemon(user_id):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pokemon_name, level,
               bonus_hp, bonus_atk, bonus_def, bonus_speed
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
        LIMIT 1
    """, (str(user_id),))

    result = cursor.fetchone()
    conn.close()
    return result

def simulate_battle(p1, p2):
    log = []

    turn_p1 = p1["speed"] >= p2["speed"]

    while p1["hp"] > 0 and p2["hp"] > 0:
        if turn_p1:
            dmg = max(1, p1["atk"] - p2["def"] // 2)
            p2["hp"] -= dmg
            log.append(f"👤 {p1['name']} menyerang (-{dmg} HP)")
        else:
            dmg = max(1, p2["atk"] - p1["def"] // 2)
            p1["hp"] -= dmg
            log.append(f"👤 {p2['name']} menyerang (-{dmg} HP)")

        turn_p1 = not turn_p1

        if len(log) >= 10:
            break

    winner = p1 if p1["hp"] > 0 else p2
    return log, winner

def create_ai_pokemon():
    name = get_random_pokemon()
    level = random.randint(10, 50)
    bonus = level // 10

    stats = get_pokemon_stats(name, (bonus, bonus, bonus, bonus))
    ptype = get_pokemon_type(name)

    return {
        "name": name,
        "level": level,
        "hp": stats["hp"],
        "max_hp": stats["hp"],
        "atk": stats["atk"],
        "def": stats["def"],
        "speed": stats["speed"],
        "type": ptype,
        "heal_used": False
    }

def get_pokemon(name):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT Name, Type1, Type2, HP, Attack, Defense, SpAtk, SpDef, Speed "
        "FROM Pokemon WHERE LOWER(Name)=?",
        (name.lower(),)
    )

    result = cursor.fetchone()
    conn.close()
    return result

def count_user_pokemon(user_id):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM user_pokemon
        WHERE user_id=?
    """, (str(user_id),))

    count = cursor.fetchone()[0]
    conn.close()
    return count

def set_active_pokemon(user_id, pokemon_id):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    # nonaktifkan semua
    cursor.execute("""
        UPDATE user_pokemon
        SET is_active=0
        WHERE user_id=?
    """, (str(user_id),))

    # aktifkan satu
    cursor.execute("""
        UPDATE user_pokemon
        SET is_active=1
        WHERE id=? AND user_id=?
    """, (pokemon_id, str(user_id)))

    conn.commit()
    conn.close()


def get_active_pokemon(user_id):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    # coba ambil aktif
    cursor.execute("""
        SELECT pokemon_name, level,
               bonus_hp, bonus_atk, bonus_def, bonus_speed
        FROM user_pokemon
        WHERE user_id=? AND is_active=1
        LIMIT 1
    """, (str(user_id),))

    result = cursor.fetchone()

    # fallback: pokemon pertama
    if not result:
        cursor.execute("""
            SELECT pokemon_name, level,
                   bonus_hp, bonus_atk, bonus_def, bonus_speed
            FROM user_pokemon
            WHERE user_id=?
            ORDER BY id
            LIMIT 1
        """, (str(user_id),))
        result = cursor.fetchone()

    conn.close()
    return result

def get_random_pokemon():
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("SELECT Name FROM Pokemon ORDER BY RANDOM() LIMIT 1")
    result = cursor.fetchone()

    conn.close()
    return result[0]

def get_bonus_from_level(level):
    return level // 10

def get_pokemon_stats(name, bonus):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT HP, Attack, Defense, Speed
        FROM Pokemon
        WHERE LOWER(Name)=?
    """, (name.lower(),))

    base = cursor.fetchone()
    conn.close()

    if not base:
        return None

    hp = int(base[0])
    atk = int(base[1])
    deff = int(base[2])
    speed = int(base[3])

    bonus_hp, bonus_atk, bonus_def, bonus_speed = bonus

    return {
        "hp": hp + bonus_hp,
        "atk": atk + bonus_atk,
        "def": deff + bonus_def,
        "speed": speed + bonus_speed
    }

@bot.event
async def on_ready():
    print(f"Bot login sebagai {bot.user}")

@bot.command()
async def select(ctx, index: int):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, pokemon_name, level
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
    """, (str(ctx.author.id),))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await ctx.send("📭 Kamu tidak punya Pokémon.")
        return

    if index < 1 or index > len(rows):
        await ctx.send("❌ Nomor Pokémon tidak valid.")
        return

    pokemon_id, name, level = rows[index - 1]

    set_active_pokemon(ctx.author.id, pokemon_id)

    await ctx.send(
        f"✅ **{name} (Lv.{level}) dipilih sebagai Pokémon aktif!**\n"
        f"Digunakan untuk `!battle` dan `!pvp`"
    )

@bot.command()
async def profile(ctx):
    level, exp = get_player(ctx.author.id)
    need = exp_to_next(level)

    await ctx.send(
        f"👤 **Profil {ctx.author.name}**\n"
        f"⭐ Level: {level}\n"
        f"📈 EXP: {exp}/{need}\n"
        f"💰 Uang: {get_money(ctx.author.id)}"
    )

@bot.command()
async def starter(ctx, choice: str):
    choice = choice.lower()

    if choice not in STARTER_POKEMON:
        await ctx.send("❌ Pilihan: charmander / bulbasaur / squirtle")
        return

    if has_pokemon(ctx.author.id):
        await ctx.send("❌ Kamu sudah punya Pokémon.")
        return

    level = STARTER_LEVEL
    bonus = level // 10

    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    # nonaktifkan semua pokemon dulu
    cursor.execute("""
        UPDATE user_pokemon SET is_active=0 WHERE user_id=?
    """, (str(ctx.author.id),))

    # insert starter sebagai aktif
    cursor.execute("""
        INSERT INTO user_pokemon (
            user_id, pokemon_name, level,
            bonus_hp, bonus_atk, bonus_def, bonus_speed,
            caught_at, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        str(ctx.author.id),
        choice.capitalize(),
        level,
        bonus, bonus, bonus, bonus,
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    await ctx.send(
        f"⭐ **Starter dipilih!**\n"
        f"{choice.capitalize()} Lv.{level} sekarang AKTIF"
    )


@bot.command()
async def starterinfo(ctx):
    await ctx.send(
        "🎒 **Pilih Starter Pokémon:**\n"
        "🔥 Charmander\n"
        "🌱 Bulbasaur\n"
        "💧 Squirtle\n\n"
        "Gunakan: `!starter <nama>`"
    )

@bot.command()
async def trade(ctx, target: discord.Member, my_index: int, their_index: int):
    if target.bot or target.id == ctx.author.id:
        await ctx.send("❌ Trade tidak valid.")
        return

    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    # ambil pokemon pengirim
    cursor.execute("""
        SELECT id, pokemon_name, level,
               bonus_hp, bonus_atk, bonus_def, bonus_speed
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
    """, (str(ctx.author.id),))
    my_pokes = cursor.fetchall()

    # ambil pokemon target
    cursor.execute("""
        SELECT id, pokemon_name, level,
               bonus_hp, bonus_atk, bonus_def, bonus_speed
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
    """, (str(target.id),))
    their_pokes = cursor.fetchall()

    conn.close()

    if not my_pokes or not their_pokes:
        await ctx.send("❌ Salah satu player tidak punya Pokémon.")
        return

    if my_index < 1 or my_index > len(my_pokes):
        await ctx.send("❌ Pokémon kamu tidak valid.")
        return

    if their_index < 1 or their_index > len(their_pokes):
        await ctx.send("❌ Pokémon target tidak valid.")
        return

    trade_requests[target.id] = {
        "from": ctx.author,
        "my_pokemon": my_pokes[my_index - 1],
        "their_pokemon": their_pokes[their_index - 1]
    }

    await ctx.send(
        f"🔄 **TRADE REQUEST**\n"
        f"👤 {ctx.author.name} menawarkan trade ke {target.mention}\n\n"
        f"📦 {ctx.author.name}: {my_pokes[my_index-1][1]} (Lv.{my_pokes[my_index-1][2]})\n"
        f"📦 {target.name}: {their_pokes[their_index-1][1]} (Lv.{their_pokes[their_index-1][2]})\n\n"
        f"{target.mention}, ketik `!accepttrade` atau `!declinetrade`"
    )

@bot.command()
async def accepttrade(ctx):
    if ctx.author.id not in trade_requests:
        await ctx.send("❌ Tidak ada trade request.")
        return

    trade = trade_requests.pop(ctx.author.id)

    sender = trade["from"]
    my_poke = trade["their_pokemon"]
    their_poke = trade["my_pokemon"]

    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    # tukar owner
    cursor.execute(
        "UPDATE user_pokemon SET user_id=? WHERE id=?",
        (str(ctx.author.id), their_poke[0])
    )
    cursor.execute(
        "UPDATE user_pokemon SET user_id=? WHERE id=?",
        (str(sender.id), my_poke[0])
    )

    conn.commit()
    conn.close()

    await ctx.send(
        f"🔄 **TRADE BERHASIL!**\n"
        f"{sender.name} ⇄ {ctx.author.name}"
    )

@bot.command()
async def viewpokemon(ctx, target: discord.Member):
    if target.bot:
        await ctx.send("❌ Tidak bisa melihat Pokémon bot.")
        return

    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pokemon_name, level,
               bonus_hp, bonus_atk, bonus_def, bonus_speed
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
    """, (str(target.id),))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await ctx.send(f"📭 {target.name} belum punya Pokémon.")
        return

    embed = discord.Embed(
        title=f"🎒 Pokémon milik {target.name}",
        color=0x5865F2
    )

    for i, (name, level, bhp, batk, bdef, bspd) in enumerate(rows, start=1):
        stats = get_pokemon_stats(name, (bhp, batk, bdef, bspd))
        embed.add_field(
            name=f"{i}. {name} (Lv.{level}/{MAX_LEVEL})",
            value=(
                f"❤️ HP: {stats['hp']}\n"
                f"⚔️ ATK: {stats['atk']}\n"
                f"🛡️ DEF: {stats['def']}\n"
                f"⚡ SPEED: {stats['speed']}"
            ),
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command()
async def declinetrade(ctx):
    if ctx.author.id in trade_requests:
        trade_requests.pop(ctx.author.id)
        await ctx.send("❌ Trade ditolak.")
    else:
        await ctx.send("❌ Tidak ada trade request.")

@bot.command()
async def pvp(ctx, opponent: discord.Member, bet: int = 0):
    if opponent.bot or opponent.id == ctx.author.id:
        await ctx.send("❌ PvP tidak valid.")
        return

    if bet < 0:
        await ctx.send("❌ Bet tidak boleh negatif.")
        return

    money1 = get_money(ctx.author.id)
    money2 = get_money(opponent.id)

    if money1 < bet:
        await ctx.send("❌ Uang kamu tidak cukup.")
        return
    if money2 < bet:
        await ctx.send(f"❌ {opponent.name} tidak punya uang cukup.")
        return

    pvp_requests[opponent.id] = {
        "challenger": ctx.author,
        "bet": bet
    }

    await ctx.send(
        f"⚔️ **PvP Challenge!**\n"
        f"👤 {ctx.author.name} menantang {opponent.mention}\n"
        f"💰 Bet: {bet}\n\n"
        f"{opponent.mention}, ketik `!accept` atau `!decline`"
    )

@bot.command()
async def accept(ctx):
    if ctx.author.id not in pvp_requests:
        await ctx.send("❌ Tidak ada PvP challenge.")
        return

    req = pvp_requests.pop(ctx.author.id)
    challenger = req["challenger"]
    bet = req["bet"]

    # ===== AMBIL POKEMON (SAMA SEPERTI SEBELUMNYA) =====
    p1_data = get_active_pokemon(challenger.id)
    p2_data = get_active_pokemon(ctx.author.id)


    if not p1_data or not p2_data:
        await ctx.send("❌ Salah satu pemain tidak punya Pokémon.")
        return

    def build_player(data):
        name, level, bhp, batk, bdef, bspd = data
        s = get_pokemon_stats(name, (bhp, batk, bdef, bspd))
        return {
            "name": name,
            "level": level,
            "hp": s["hp"],
            "max_hp": s["hp"],
            "atk": s["atk"],
            "def": s["def"],
            "speed": s["speed"],
            "type": get_pokemon_type(name),
            "heal_used": False
        }

    p1 = build_player(p1_data)
    p2 = build_player(p2_data)

    log, winner = battle_engine(p1, p2, allow_heal=False)

    # ===== REWARD =====
    if winner["name"] == p1["name"]:
        update_money(challenger.id, get_money(challenger.id) + bet)
        update_money(ctx.author.id, get_money(ctx.author.id) - bet)
        winner_name = challenger.name
    else:
        update_money(ctx.author.id, get_money(ctx.author.id) + bet)
        update_money(challenger.id, get_money(challenger.id) - bet)
        winner_name = ctx.author.name

    text = (
        f"⚔️ **PvP BATTLE**\n"
        f"👤 {challenger.name} vs {ctx.author.name}\n"
        f"💰 Bet: {bet}\n\n"
        + "\n".join(log[:12]) +
        f"\n\n🏆 **Pemenang: {winner_name}**"
    )
    if winner["name"] == p1["name"]:
        add_exp(challenger.id, 70)
    else:
        add_exp(ctx.author.id, 70)

    await ctx.send(text)

@bot.command()
async def decline(ctx):
    if ctx.author.id in pvp_requests:
        pvp_requests.pop(ctx.author.id)
        await ctx.send("❌ PvP challenge ditolak.")
    else:
        await ctx.send("❌ Tidak ada PvP challenge.")

@bot.command()
async def money(ctx):
    await ctx.send(f"💰 Uang kamu: {get_money(ctx.author.id)}")

@bot.command()
async def battle(ctx):
    player = get_active_pokemon(ctx.author.id)
    if not player:
        await ctx.send("❌ Kamu tidak punya Pokémon.")
        return

    name, level, bhp, batk, bdef, bspd = player
    p_stats = get_pokemon_stats(name, (bhp, batk, bdef, bspd))
    ptype = get_pokemon_type(name)

    player_pokemon = {
        "name": name,
        "level": level,
        "hp": p_stats["hp"],
        "max_hp": p_stats["hp"],
        "atk": p_stats["atk"],
        "def": p_stats["def"],
        "speed": p_stats["speed"],
        "type": ptype
    }

    ai = create_ai_pokemon()

    log = [
        f"⚔️ **BATTLE DIMULAI**",
        f"👤 {player_pokemon['name']} (Lv.{player_pokemon['level']} | {player_pokemon['type']})",
        f"🧠 {ai['name']} (Lv.{ai['level']} | {ai['type']})",
        ""
    ]

    player_turn = player_pokemon["speed"] >= ai["speed"]

    for turn in range(1, 21):
        if player_pokemon["hp"] <= 0 or ai["hp"] <= 0:
            break

        if player_turn:
            dmg, info = calculate_damage(player_pokemon, ai)
            ai["hp"] -= dmg
            log.append(
                f"👤 {player_pokemon['name']} menyerang (-{dmg} HP){info}"
            )
        else:
            # AI heal logic
            if ai["hp"] < ai["max_hp"] * 0.3 and not ai["heal_used"]:
                heal = int(ai["max_hp"] * 0.25)
                ai["hp"] += heal
                ai["heal_used"] = True
                log.append(f"🧠 {ai['name']} menggunakan HEAL (+{heal} HP)")
            else:
                dmg, info = calculate_damage(ai, player_pokemon)
                player_pokemon["hp"] -= dmg
                log.append(
                    f"🧠 {ai['name']} menyerang (-{dmg} HP){info}"
                )

        player_turn = not player_turn

    if player_pokemon["hp"] > 0 and ai["hp"] <= 0:
        log.append("\n🏆 **KAMU MENANG!**")
    elif ai["hp"] > 0 and player_pokemon["hp"] <= 0:
        log.append("\n💀 **KAMU KALAH...**")
    else:
        log.append("\n⏳ **BATTLE SERI**")

    await ctx.send("\n".join(log[:15]))

    # ===== EXP HANYA JIKA MENANG =====
    if player_pokemon["hp"] > 0 and ai["hp"] <= 0:
        leveled, lvl, exp = add_exp(ctx.author.id, 50)
        if leveled:
            await ctx.send(f"🆙 Player naik ke Level {lvl}!")
    else:
        await ctx.send("💀 Kamu kalah. Tidak mendapatkan EXP.")


@bot.command()
async def pokedex(ctx, *, name):
    pokemon = get_pokemon(name)

    if not pokemon:
        await ctx.send("❌ Pokémon tidak ditemukan!")
        return

    name, type1, type2, hp, atk, defn, spatk, spdef, speed = pokemon

    embed = discord.Embed(
        title=name,
        color=0xE3350D
    )
    embed.add_field(name="Type", value=f"{type1} / {type2 or '-'}", inline=False)
    embed.add_field(name="HP", value=hp)
    embed.add_field(name="Attack", value=atk)
    embed.add_field(name="Defense", value=defn)
    embed.add_field(name="Sp. Attack", value=spatk)
    embed.add_field(name="Sp. Defense", value=spdef)
    embed.add_field(name="Speed", value=speed)

    await ctx.send(embed=embed)


@bot.command()
async def catch(ctx):
    # 🔒 cek limit
    total = count_user_pokemon(ctx.author.id)
    if total >= MAX_POKEMON:
        await ctx.send(
            f"🎒 Pokémon kamu sudah penuh!\n"
            f"📦 Maksimal: {MAX_POKEMON}\n"
            f"🗑️ Gunakan `!release` untuk membuang Pokémon."
        )
        return

    name = get_random_pokemon()

    # 🎯 chance gagal
    if random.randint(1, 100) > 70:
        await ctx.send("❌ Pokémon kabur!")
        return

    level = random.randint(1, 50)
    bonus = level // 10

    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    # ⭐ NONAKTIFKAN POKÉMON AKTIF LAMA
    cursor.execute("""
        UPDATE user_pokemon
        SET is_active = 0
        WHERE user_id = ?
    """, (str(ctx.author.id),))

    # ➕ INSERT POKÉMON BARU (AKTIF)
    cursor.execute("""
        INSERT INTO user_pokemon (
            user_id, pokemon_name, level,
            bonus_hp, bonus_atk, bonus_def, bonus_speed,
            caught_at, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        str(ctx.author.id),
        name,
        level,
        bonus, bonus, bonus, bonus,
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    stats = get_pokemon_stats(
        name,
        (bonus, bonus, bonus, bonus)
    )

    await ctx.send(
        f"🎉 **Kamu menangkap {name}!** ⭐\n"
        f"🔥 Pokémon ini sekarang **AKTIF**\n\n"
        f"⭐ Level: {level}\n"
        f"❤️ HP: {stats['hp']}\n"
        f"⚔️ ATK: {stats['atk']}\n"
        f"🛡️ DEF: {stats['def']}\n"
        f"⚡ SPEED: {stats['speed']}\n\n"
        f"📦 Slot: {total + 1}/{MAX_POKEMON}"
    )

    # 🎓 EXP PLAYER
    leveled, lvl, exp = add_exp(ctx.author.id, 20)
    if leveled:
        await ctx.send(f"🆙 **Player naik ke Level {lvl}!**")

@bot.command()
async def mypokemon(ctx):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pokemon_name, level,
               bonus_hp, bonus_atk, bonus_def, bonus_speed, is_active
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
    """, (str(ctx.author.id),))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await ctx.send("📭 Kamu belum punya Pokémon.")
        return

    embed = discord.Embed(
        title=f"🎒 Pokémon {ctx.author.name}",
        color=0x3B4CCA
    )

    for i, (name, level, bhp, batk, bdef, bspd, is_active) in enumerate(rows, start=1):
        stats = get_pokemon_stats(name, (bhp, batk, bdef, bspd))
        active = " ⭐ AKTIF" if is_active else ""

        embed.add_field(
            name=f"{i}. {name} (Lv.{level}/{MAX_LEVEL}){active}",
            value=(
                f"❤️ HP: {stats['hp']}\n"
                f"⚔️ ATK: {stats['atk']}\n"
                f"🛡️ DEF: {stats['def']}\n"
                f"⚡ SPEED: {stats['speed']}"
            ),
            inline=False
        )

    total = len(rows)
    embed.description = f"📦 Slot Pokémon: {total}/{MAX_POKEMON}"

    await ctx.send(embed=embed)


@bot.command()
async def release(ctx, index: int):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    # Ambil Pokémon berdasarkan urutan
    cursor.execute("""
        SELECT id, pokemon_name, level
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
    """, (str(ctx.author.id),))

    rows = cursor.fetchall()

    if not rows:
        await ctx.send("📭 Kamu tidak punya Pokémon.")
        conn.close()
        return

    if index < 1 or index > len(rows):
        await ctx.send("❌ Nomor Pokémon tidak valid.")
        conn.close()
        return

    pokemon_id, name, level = rows[index - 1]

    cursor.execute(
        "DELETE FROM user_pokemon WHERE id=?",
        (pokemon_id,)
    )

    conn.commit()
    conn.close()

    await ctx.send(
        f"🗑️ **{name} (Lv.{level})** berhasil dibuang."
    )

@bot.command()
async def feed(ctx, index: int):
    conn = sqlite3.connect("pokemon.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, pokemon_name, level,
               bonus_hp, bonus_atk, bonus_def,
               bonus_spatk, bonus_spdef, bonus_speed
        FROM user_pokemon
        WHERE user_id=?
        ORDER BY id
    """, (str(ctx.author.id),))

    rows = cursor.fetchall()

    if not rows:
        await ctx.send("📭 Kamu tidak punya Pokémon.")
        conn.close()
        return

    if index < 1 or index > len(rows):
        await ctx.send("❌ Nomor Pokémon tidak valid.")
        conn.close()
        return

    (pid, name, level,
     bhp, batk, bdef, bsa, bsd, bspd) = rows[index - 1]

    if level >= MAX_LEVEL:
        await ctx.send(f"🧢 **{name}** sudah level maksimal ({MAX_LEVEL}).")
        conn.close()
        return

    new_level = level + 1

    # cek bonus lama & baru
    old_bonus = level // 10
    new_bonus = new_level // 10
    gained = new_bonus - old_bonus

    if gained > 0:
        bhp += gained
        batk += gained
        bdef += gained
        bsa += gained
        bsd += gained
        bspd += gained

    cursor.execute("""
        UPDATE user_pokemon
        SET level=?, bonus_hp=?, bonus_atk=?, bonus_def=?,
            bonus_spatk=?, bonus_spdef=?, bonus_speed=?
        WHERE id=?
    """, (new_level, bhp, batk, bdef, bsa, bsd, bspd, pid))

    conn.commit()
    conn.close()

    msg = f"🍖 **{name}** naik level!\n⬆️ {level} → {new_level}"

    if gained > 0:
        msg += "\n✨ **BONUS STAT +1 KE SEMUA!**"

    await ctx.send(msg)


bot.run("")

