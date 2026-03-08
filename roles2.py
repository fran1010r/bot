import asyncio
import discord
from discord.ext import commands
import json
import os
import sys
import time
import traceback
import logging
import random
import aiohttp
from datetime import datetime, timezone
from collections import defaultdict

# ─────────────────────────────────────────────────────────────
#  LOGGING — muestra info con fecha/hora en consola y en archivo
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s » %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
log = logging.getLogger("bot")

# ─────────────────────────────────────────────────────────────
#  CARGAR CONFIG.JSON
# ─────────────────────────────────────────────────────────────
CONFIG_FILE = "config.json"

def cargar_config() -> dict:
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    # Token desde variable de entorno (Railway) o desde config.json
    token_env = os.environ.get("DISCORD_TOKEN")
    if token_env:
        cfg["token"] = token_env
    if cfg.get("token") in ("", "TU_TOKEN_AQUÍ", None):
        log.critical("No se encontró token. Ponlo en DISCORD_TOKEN (variable de entorno) o en config.json.")
        sys.exit(1)
    return cfg

CONFIG          = cargar_config()
TOKEN           = CONFIG["token"]
PREFIX          = CONFIG.get("prefix", "!")
PUNTOS_MAX = 7   # máximo de puntos que se pueden dar de una vez
ROLES_STAFF_CFG = CONFIG.get("roles_staff", ["👑 Administración", "🛡️ Moderador"])

# ─────────────────────────────────────────────────────────────
#  BOT
# ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
bot.remove_command("help")

# ─────────────────────────────────────────────────────────────
#  PERMISOS
# ─────────────────────────────────────────────────────────────
def es_admin(ctx) -> bool:
    return ctx.author.guild_permissions.administrator

def es_staff(ctx) -> bool:
    return (
        ctx.author.guild_permissions.administrator
        or ctx.author.guild_permissions.manage_roles
        or any(r.name in ROLES_STAFF_CFG for r in ctx.author.roles)
    )


DB_FILE = "puntos.json"

def cargar_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def get_puntos(user_id: int) -> int:
    return cargar_db().get(str(user_id), {}).get("puntos", 0)

def get_raids(user_id: int) -> int:
    return cargar_db().get(str(user_id), {}).get("raids", 0)

def set_puntos(user_id: int, puntos: int):
    db = cargar_db()
    if str(user_id) not in db:
        db[str(user_id)] = {}
    db[str(user_id)]["puntos"] = max(0, puntos)
    guardar_db(db)

def add_puntos(user_id: int, cantidad: int, contar_raid: bool = False) -> int:
    db = cargar_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = {}
    db[uid]["puntos"] = max(0, db[uid].get("puntos", 0) + cantidad)
    if contar_raid:
        db[uid]["raids"] = db[uid].get("raids", 0) + 1
    guardar_db(db)
    return db[uid]["puntos"]

# ─────────────────────────────────────────────────────────────
#  60 ROLES CON GRADIENTE — de 15 en 15 puntos
#  Formato: (nombre, color1_hex, color2_hex)
#  Rol 1 = 15 pts … Rol 60 = 900 pts
# ─────────────────────────────────────────────────────────────
ROLES_DATA = [
    # Fuego & Infierno (1-15)
    ("Wraith",     0xFF0000, 0xFF6600),
    ("Demon",      0xCC0000, 0xFF2200),
    ("Hellfire",   0xFF2200, 0xFFAA00),
    ("Blaze",      0x990000, 0xFF4400),
    ("Crimson",    0xFF0044, 0xFF6600),
    ("Inferno",    0xFF3300, 0xFFCC00),
    ("Ember",      0xFF4400, 0xFF9900),
    ("Phantom",    0xDD2200, 0xFF7700),
    ("Molten",     0xFF5500, 0xFFDD00),
    ("Lava",       0xBB1100, 0xFF5500),
    ("Pyre",       0xFF6600, 0xFFEE00),
    ("Solar",      0xFF8800, 0xFFFF00),
    ("Amber",      0xFF9900, 0xFFFF44),
    ("Golden",     0xFFAA00, 0xFFFFAA),
    ("Gilded",     0xFFCC00, 0xFFFFDD),
    # Toxico & Veneno (16-30)
    ("Toxic",      0xAAFF00, 0x00FF44),
    ("Acid",       0xCCFF00, 0x00FFAA),
    ("Neon",       0xFFFF00, 0x00FF00),
    ("Viper",      0x88FF00, 0x00CC44),
    ("Venom",      0x66FF00, 0x00FF66),
    ("Slime",      0x44FF00, 0x00FFCC),
    ("Bio",        0x00FF00, 0x00FFFF),
    ("Jungle",     0x00EE00, 0x00AAFF),
    ("Plague",     0x00CC00, 0x008844),
    ("Nova",       0x009900, 0x44FF88),
    ("Emerald",    0x00FF44, 0xAAFF00),
    ("Forest",     0x00BB44, 0x00FFBB),
    ("Serpent",    0x006600, 0x00FF44),
    ("Moss",       0x004400, 0x00CC00),
    ("Swamp",      0x224400, 0x66FF00),
    # Hielo & Abismo (31-45)
    ("Tide",       0x00FFFF, 0x0088FF),
    ("Aqua",       0x00EECC, 0x0044FF),
    ("Ocean",      0x00BBFF, 0x0000CC),
    ("Frost",      0xAAFFFF, 0x0066FF),
    ("Glacier",    0xCCFFFF, 0x0000FF),
    ("Ice",        0xEEFFFF, 0x00AAFF),
    ("Sky",        0x88DDFF, 0x0000BB),
    ("Storm",      0x4499FF, 0x220088),
    ("Thunder",    0x2244FF, 0x000066),
    ("Void",       0x0000FF, 0x220099),
    ("Deep",       0x0000CC, 0x110066),
    ("Abyss",      0x000099, 0x330066),
    ("Midnight",   0x000066, 0x110033),
    ("Dark",       0x000044, 0x220022),
    ("Depth",      0x001133, 0x002244),
    # Arcano & Celestial (46-60)
    ("Specter",    0x4400CC, 0xFF00FF),
    ("Soul",       0x6600DD, 0xFF44FF),
    ("Spirit",     0x8800EE, 0xFFAAFF),
    ("Astral",     0xAA00FF, 0xFF00AA),
    ("Arcane",     0xCC00FF, 0xFF0088),
    ("Mystic",     0xFF00FF, 0xFF0044),
    ("Chaos",      0xDD00CC, 0xFF6600),
    ("Nether",     0xAA0088, 0xFF00FF),
    ("Omen",       0xFF0088, 0xFF88CC),
    ("Cursed",     0xFF0066, 0xFFAADD),
    ("Rose",       0xFF0044, 0xFF8899),
    ("Petal",      0xFF4488, 0xFFCCDD),
    ("Blossom",    0xFF88AA, 0xFFEEFF),
    ("Angel",      0xFFCCDD, 0xFFFFFF),
    ("Celestial",  0xCCAAFF, 0xFFFFFF),
]

COSTO_POR_ROL = 15

def costo_rol(index_0based: int) -> int:
    return (index_0based + 1) * COSTO_POR_ROL

# Convertir ROLES_DATA al formato de RANGOS para compatibilidad
RANGOS = [
    {"nombre": nombre, "puntos": costo_rol(i), "color": f"#{c1:06X}"}
    for i, (nombre, c1, c2) in enumerate(ROLES_DATA)
]

PAGINA_INFO = [
    ("Fuego & Infierno",   0xFF4400),
    ("Toxico & Veneno",    0x66FF00),
    ("Hielo & Abismo",     0x0066FF),
    ("Arcano & Celestial", 0xCC00FF),
]

ROLES_POR_PAGINA = 15

NOMBRES_RANGOS = {r["nombre"] for r in RANGOS}

# ─────────────────────────────────────────────────────────────
#  HELPERS DE RANGOS
# ─────────────────────────────────────────────────────────────
def rango_por_puntos(puntos: int) -> dict | None:
    actual = None
    for r in RANGOS:
        if puntos >= r["puntos"]:
            actual = r
    return actual

def siguiente_rango(puntos: int):
    for r in RANGOS:
        if puntos < r["puntos"]:
            return r
    return None

def obtener_tier(rango: dict) -> str:
    idx = RANGOS.index(rango)
    mapa = [
        (15, "1 — Fuego & Infierno 🔥"),
        (30, "2 — Toxico & Veneno ☠️"),
        (45, "3 — Hielo & Abismo 🧊"),
        (60, "4 — Arcano & Celestial ✨"),
    ]
    for limite, nombre in mapa:
        if idx < limite:
            return nombre
    return "4 — Arcano & Celestial ✨"

async def actualizar_rango_rol(member: discord.Member, puntos: int):
    rango = rango_por_puntos(puntos)
    roles_quitar = [r for r in member.roles if r.name in NOMBRES_RANGOS]
    if roles_quitar:
        try:
            await member.remove_roles(*roles_quitar, reason="Actualización de rango")
        except discord.Forbidden:
            log.warning(f"Sin permisos para quitar roles a {member}")
    if rango is None:
        return  # Sin puntos suficientes, solo se quitaron los roles anteriores
    nuevo_rol = discord.utils.get(member.guild.roles, name=rango["nombre"])
    if nuevo_rol:
        try:
            await member.add_roles(nuevo_rol, reason=f"Rango: {rango['nombre']}")
        except discord.Forbidden:
            log.warning(f"Sin permisos para asignar {rango['nombre']} a {member}")

def barra_progreso(puntos: int, rango: dict, siguiente: dict) -> str:
    if not siguiente:
        return "`████████████████████` 100%"
    rango_range = siguiente["puntos"] - rango["puntos"]
    progreso = (puntos - rango["puntos"]) / rango_range if rango_range else 1
    barras = int(progreso * 20)
    return f"`{'█' * barras}{'░' * (20 - barras)}` {int(progreso * 100)}%"

# ═════════════════════════════════════════════════════════════
#  🎭 ROLEPLAY
# ═════════════════════════════════════════════════════════════

PAREJAS_FILE = "parejas.json"
FAMILIA_FILE  = "familia.json"

def cargar_parejas() -> dict:
    if os.path.exists(PAREJAS_FILE):
        with open(PAREJAS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_parejas(data: dict):
    with open(PAREJAS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def cargar_familia() -> dict:
    if os.path.exists(FAMILIA_FILE):
        with open(FAMILIA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_familia(data: dict):
    with open(FAMILIA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

propuestas_pendientes = {}

@bot.command(name="casar", aliases=["proponer", "marry"])
async def casar(ctx, member: discord.Member):
    """🎭 Propón matrimonio. Uso: !casar @usuario"""
    if member == ctx.author:
        return await ctx.send("❌ No puedes casarte contigo mismo 😅")
    if member.bot:
        return await ctx.send("❌ Los bots no se casan 🤖")
    parejas = cargar_parejas()
    uid = str(ctx.author.id)
    mid = str(member.id)
    if uid in parejas:
        pareja_actual = parejas[uid]
        return await ctx.send(f"💍 Ya estás casado/a con <@{pareja_actual}>. Usa `!divorcio` primero.")
    if mid in parejas:
        return await ctx.send(f"💔 {member.mention} ya está casado/a con alguien más.")

    propuestas_pendientes[mid] = ctx.author.id
    embed = discord.Embed(
        title="💍 ¡Propuesta de Matrimonio!",
        description=f"{ctx.author.mention} le propone matrimonio a {member.mention} 💕\n\n"
                    f"{member.mention} responde con `!aceptar` o `!rechazar` en los próximos 60 segundos.",
        color=discord.Color.pink()
    )
    await ctx.send(embed=embed)

    await asyncio.sleep(60)
    if propuestas_pendientes.get(mid) == ctx.author.id:
        propuestas_pendientes.pop(mid, None)
        await ctx.send(f"⌛ {member.mention} no respondió a tiempo. La propuesta expiró.")

@bot.command(name="aceptar")
async def aceptar(ctx):
    """🎭 Acepta una propuesta de matrimonio."""
    mid = str(ctx.author.id)
    if ctx.author.id not in propuestas_pendientes:
        return await ctx.send("❌ No tienes ninguna propuesta pendiente.")
    autor_id = propuestas_pendientes.pop(ctx.author.id)
    parejas = cargar_parejas()
    parejas[str(autor_id)] = mid
    parejas[mid] = str(autor_id)
    guardar_parejas(parejas)
    embed = discord.Embed(
        title="💒 ¡Se casaron!",
        description=f"💍 {ctx.author.mention} y <@{autor_id}> ahora están casados. ¡Felicidades! 🎉",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

@bot.command(name="rechazar")
async def rechazar(ctx):
    """🎭 Rechaza una propuesta de matrimonio."""
    if ctx.author.id not in propuestas_pendientes:
        return await ctx.send("❌ No tienes ninguna propuesta pendiente.")
    autor_id = propuestas_pendientes.pop(ctx.author.id)
    await ctx.send(f"💔 {ctx.author.mention} rechazó la propuesta de <@{autor_id}>. Qué triste...")

@bot.command(name="divorcio", aliases=["divorciar"])
async def divorcio(ctx):
    """🎭 Divorciarse de tu pareja."""
    parejas = cargar_parejas()
    uid = str(ctx.author.id)
    if uid not in parejas:
        return await ctx.send("❌ No estás casado/a con nadie.")
    ex_id = parejas.pop(uid)
    parejas.pop(str(ex_id), None)
    guardar_parejas(parejas)
    embed = discord.Embed(
        title="💔 Divorcio",
        description=f"{ctx.author.mention} se divorció de <@{ex_id}>. Fin de una era...",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

@bot.command(name="pareja", aliases=["esposo", "esposa"])
async def ver_pareja(ctx, member: discord.Member = None):
    """🎭 Ver quién es tu pareja."""
    member = member or ctx.author
    parejas = cargar_parejas()
    uid = str(member.id)
    if uid not in parejas:
        return await ctx.send(f"💔 {member.display_name} no está casado/a con nadie.")
    pareja_id = parejas[uid]
    embed = discord.Embed(
        title="💍 Estado Civil",
        description=f"{member.mention} está casado/a con <@{pareja_id}> 💕",
        color=discord.Color.pink()
    )
    await ctx.send(embed=embed)

@bot.command(name="adoptar")
async def adoptar(ctx, member: discord.Member):
    """🎭 Adopta a alguien como hijo/a. Uso: !adoptar @usuario"""
    if member == ctx.author or member.bot:
        return await ctx.send("❌ No puedes adoptarte a ti mismo ni a un bot.")
    familia = cargar_familia()
    uid = str(ctx.author.id)
    mid = str(member.id)
    hijos = familia.get(uid, [])
    if mid in hijos:
        return await ctx.send(f"❌ {member.mention} ya es tu hijo/a.")
    hijos.append(mid)
    familia[uid] = hijos
    guardar_familia(familia)
    embed = discord.Embed(
        title="👨‍👧 ¡Adopción!",
        description=f"{ctx.author.mention} adoptó a {member.mention} 🏠💕",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="familia")
async def ver_familia(ctx, member: discord.Member = None):
    """🎭 Ver tu familia."""
    member = member or ctx.author
    familia = cargar_familia()
    parejas = cargar_parejas()
    uid = str(member.id)
    hijos = familia.get(uid, [])
    pareja = parejas.get(uid)
    embed = discord.Embed(title=f"👨‍👩‍👧 Familia de {member.display_name}", color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="💍 Pareja", value=f"<@{pareja}>" if pareja else "Soltero/a", inline=False)
    embed.add_field(name="👶 Hijos", value="\n".join(f"<@{h}>" for h in hijos) if hijos else "Sin hijos", inline=False)
    await ctx.send(embed=embed)


# ═════════════════════════════════════════════════════════════
#  🔮 HORÓSCOPO Y PERSONALIDAD
# ═════════════════════════════════════════════════════════════

SIGNOS = {
    "aries": ("♈", "21 mar – 19 abr", "Eres una persona valiente, apasionada y directa. Hoy el fuego interior te guía."),
    "tauro": ("♉", "20 abr – 20 may", "Eres leal, paciente y muy determinado. Hoy la estabilidad es tu aliada."),
    "geminis": ("♊", "21 may – 20 jun", "Eres curioso, adaptable y comunicativo. Hoy las palabras son tu poder."),
    "cancer": ("♋", "21 jun – 22 jul", "Eres intuitivo, protector y empático. Hoy el corazón te dice la verdad."),
    "leo": ("♌", "23 jul – 22 ago", "Eres carismático, generoso y líder nato. Hoy el mundo te pertenece."),
    "virgo": ("♍", "23 ago – 22 sep", "Eres analítico, detallista y perfeccionista. Hoy los detalles marcan la diferencia."),
    "libra": ("♎", "23 sep – 22 oct", "Eres justo, diplomático y encantador. Hoy el equilibrio es tu meta."),
    "escorpio": ("♏", "23 oct – 21 nov", "Eres intenso, misterioso y poderoso. Hoy la transformación te espera."),
    "sagitario": ("♐", "22 nov – 21 dic", "Eres aventurero, optimista y filosófico. Hoy la libertad te llama."),
    "capricornio": ("♑", "22 dic – 19 ene", "Eres ambicioso, disciplinado y responsable. Hoy el esfuerzo da frutos."),
    "acuario": ("♒", "20 ene – 18 feb", "Eres innovador, independiente y humanitario. Hoy piensas fuera de la caja."),
    "piscis": ("♓", "19 feb – 20 mar", "Eres compasivo, artístico y soñador. Hoy la intuición es tu brújula."),
}

PREDICCIONES = [
    "🌟 Un encuentro inesperado cambiará tu día.",
    "💰 El dinero fluye hacia ti si actúas con confianza.",
    "❤️ El amor está más cerca de lo que crees.",
    "⚠️ Evita tomar decisiones impulsivas hoy.",
    "🎯 Tu concentración está al máximo, aprovéchala.",
    "🌈 Un buen día para empezar algo nuevo.",
    "🤝 Una amistad te sorprenderá positivamente.",
    "😴 Descansar hoy te dará energía para mañana.",
    "🔥 Tu energía es imparable, úsala sabiamente.",
    "🌙 La noche traerá claridad a tus dudas.",
]

@bot.command(name="horoscopo", aliases=["signo", "zodiac"])
async def horoscopo(ctx, *, signo: str):
    """🔮 Tu horóscopo. Uso: !horoscopo aries"""
    signo = signo.lower().strip()
    if signo not in SIGNOS:
        lista = ", ".join(f"`{s}`" for s in SIGNOS)
        return await ctx.send(f"❌ Signo no válido. Opciones: {lista}")
    emoji, fechas, descripcion = SIGNOS[signo]
    prediccion = random.choice(PREDICCIONES)
    suerte = random.randint(1, 100)
    color_val = random.randint(0x880000, 0xFFFFFF)
    embed = discord.Embed(title=f"{emoji} {signo.capitalize()}", color=color_val)
    embed.add_field(name="📅 Fechas", value=fechas, inline=True)
    embed.add_field(name="🍀 Suerte hoy", value=f"{suerte}%", inline=True)
    embed.add_field(name="✨ Personalidad", value=descripcion, inline=False)
    embed.add_field(name="🔮 Predicción", value=prediccion, inline=False)
    embed.set_footer(text=f"Consultado por {ctx.author.display_name}")
    await ctx.send(embed=embed)

TIPOS_PERSONALIDAD = [
    ("🔥 Alma de Fuego", "Eres intenso/a, apasionado/a y siempre vas al frente sin miedo."),
    ("🌊 Espíritu del Agua", "Eres tranquilo/a, profundo/a y te adaptas a todo con facilidad."),
    ("🌪️ Mente del Viento", "Eres veloz, creativo/a y siempre tienes mil ideas en la cabeza."),
    ("🌍 Corazón de Tierra", "Eres estable, confiable y la roca en la que todos se apoyan."),
    ("⚡ Rayo de Energía", "Tienes una energía inagotable que contagia a todos a tu alrededor."),
    ("🌙 Alma Lunar", "Eres misterioso/a, intuitivo/a y muy conectado/a con tus emociones."),
    ("☀️ Espíritu Solar", "Irradias positividad, carisma y alegría dondequiera que vayas."),
    ("❄️ Mente de Hielo", "Eres frío/a bajo presión, estratégico/a y muy analítico/a."),
]

@bot.command(name="personalidad", aliases=["quiensoy", "tipo"])
async def personalidad(ctx, member: discord.Member = None):
    """🔮 Descubre tu tipo de personalidad."""
    member = member or ctx.author
    seed = member.id + datetime.now(timezone.utc).toordinal()
    random.seed(seed)
    tipo, desc = random.choice(TIPOS_PERSONALIDAD)
    random.seed()
    embed = discord.Embed(title=f"🔮 Personalidad de {member.display_name}", description=f"**{tipo}**\n\n{desc}", color=discord.Color.purple())
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="compatibilidad", aliases=["compat", "shipper"])
async def compatibilidad(ctx, member: discord.Member):
    """🔮 Compatibilidad entre dos personas. Uso: !compatibilidad @usuario"""
    ids = sorted([ctx.author.id, member.id])
    random.seed(ids[0] + ids[1])
    porcentaje = random.randint(1, 100)
    random.seed()
    if porcentaje >= 80:
        estado = "💞 ¡Almas gemelas!"
        color = discord.Color.pink()
    elif porcentaje >= 60:
        estado = "💕 Buena compatibilidad"
        color = discord.Color.magenta()
    elif porcentaje >= 40:
        estado = "🤝 Compatible con esfuerzo"
        color = discord.Color.yellow()
    else:
        estado = "💔 Difícil combinación"
        color = discord.Color.red()
    barra = "█" * (porcentaje // 10) + "░" * (10 - porcentaje // 10)
    embed = discord.Embed(title="💘 Compatibilidad", color=color)
    embed.add_field(name="👫 Pareja", value=f"{ctx.author.mention} & {member.mention}", inline=False)
    embed.add_field(name="📊 Resultado", value=f"`{barra}` **{porcentaje}%**", inline=False)
    embed.add_field(name="💬 Estado", value=estado, inline=False)
    await ctx.send(embed=embed)


# ═════════════════════════════════════════════════════════════
#  🃏 TRIVIA Y ADIVINA EL NÚMERO
# ═════════════════════════════════════════════════════════════

juegos_activos = {}

PREGUNTAS_TRIVIA = [
    {"p": "¿Cuántos lados tiene un hexágono?", "r": "6", "ops": ["4", "5", "6", "8"]},
    {"p": "¿Cuál es la capital de Japón?", "r": "tokio", "ops": ["osaka", "tokio", "beijing", "seul"]},
    {"p": "¿Cuántos planetas tiene el sistema solar?", "r": "8", "ops": ["7", "8", "9", "10"]},
    {"p": "¿En qué año llegó el hombre a la luna?", "r": "1969", "ops": ["1965", "1969", "1971", "1973"]},
    {"p": "¿Cuál es el elemento más abundante en el universo?", "r": "hidrogeno", "ops": ["oxigeno", "helio", "hidrogeno", "carbono"]},
    {"p": "¿Cuántos colores tiene el arcoíris?", "r": "7", "ops": ["5", "6", "7", "8"]},
    {"p": "¿Qué animal es el más rápido del mundo?", "r": "guepardo", "ops": ["leon", "guepardo", "tigre", "aguila"]},
    {"p": "¿Cuál es el océano más grande?", "r": "pacifico", "ops": ["atlantico", "indico", "pacifico", "artico"]},
    {"p": "¿Cuántos huesos tiene el cuerpo humano adulto?", "r": "206", "ops": ["180", "196", "206", "220"]},
    {"p": "¿Cuál es el país más grande del mundo?", "r": "rusia", "ops": ["canada", "china", "rusia", "eeuu"]},
    {"p": "¿Qué planeta es conocido como el planeta rojo?", "r": "marte", "ops": ["venus", "marte", "jupiter", "saturno"]},
    {"p": "¿Cuánto es 15 x 15?", "r": "225", "ops": ["200", "215", "225", "250"]},
    {"p": "¿Cuál es el metal más caro del mundo?", "r": "rodio", "ops": ["oro", "platino", "rodio", "iridio"]},
    {"p": "¿En qué continente está Brasil?", "r": "america del sur", "ops": ["africa", "america central", "america del sur", "europa"]},
    {"p": "¿Cuántos segundos tiene una hora?", "r": "3600", "ops": ["1200", "3000", "3600", "4800"]},
]

@bot.command(name="trivia")
async def trivia(ctx):
    """🃏 Responde una pregunta de trivia."""
    if ctx.channel.id in juegos_activos:
        return await ctx.send("❌ Ya hay una trivia activa en este canal. Espera que termine.")
    pregunta = random.choice(PREGUNTAS_TRIVIA)
    ops = pregunta["ops"].copy()
    random.shuffle(ops)
    numeros = ["1️⃣","2️⃣","3️⃣","4️⃣"]
    desc = "\n".join(f"{numeros[i]} {op.capitalize()}" for i, op in enumerate(ops))
    embed = discord.Embed(title="🃏 Trivia", description=f"**{pregunta['p']}**\n\n{desc}", color=discord.Color.blurple())
    embed.set_footer(text="Responde con el número correcto en 20 segundos")
    msg = await ctx.send(embed=embed)
    for emoji in numeros[:len(ops)]:
        await msg.add_reaction(emoji)
    juegos_activos[ctx.channel.id] = True

    def check(reaction, user):
        return (
            reaction.message.id == msg.id and
            not user.bot and
            str(reaction.emoji) in numeros[:len(ops)]
        )

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=20.0, check=check)
        idx = numeros.index(str(reaction.emoji))
        elegida = ops[idx]
        if elegida.lower() == pregunta["r"].lower():
            await ctx.send(f"✅ ¡{user.mention} acertó! La respuesta era **{pregunta['r'].capitalize()}** 🎉")
        else:
            await ctx.send(f"❌ {user.mention} falló. La respuesta correcta era **{pregunta['r'].capitalize()}**.")
    except asyncio.TimeoutError:
        await ctx.send(f"⌛ Tiempo agotado. La respuesta era **{pregunta['r'].capitalize()}**.")
    finally:
        juegos_activos.pop(ctx.channel.id, None)


@bot.command(name="adivina", aliases=["guess", "numero"])
async def adivina_numero(ctx, maximo: int = 100):
    """🃏 Adivina el número. Uso: !adivina [máximo]"""
    if ctx.channel.id in juegos_activos:
        return await ctx.send("❌ Ya hay un juego activo en este canal.")
    if maximo < 5 or maximo > 1000:
        return await ctx.send("❌ El máximo debe ser entre 5 y 1000.")
    numero = random.randint(1, maximo)
    juegos_activos[ctx.channel.id] = True
    intentos = 0
    max_intentos = 5

    embed = discord.Embed(
        title="🔢 Adivina el Número",
        description=f"Estoy pensando en un número entre **1 y {maximo}**.\nTienes **{max_intentos} intentos**. ¡Escribe tu respuesta!",
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed)

    def check(m):
        return m.channel == ctx.channel and not m.author.bot and m.content.isdigit()

    while intentos < max_intentos:
        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            juegos_activos.pop(ctx.channel.id, None)
            return await ctx.send(f"⌛ Tiempo agotado. El número era **{numero}**.")
        intento = int(msg.content)
        intentos += 1
        restantes = max_intentos - intentos
        if intento == numero:
            juegos_activos.pop(ctx.channel.id, None)
            return await ctx.send(f"🎉 ¡{msg.author.mention} acertó! El número era **{numero}** en {intentos} intento(s)!")
        elif intento < numero:
            pista = "📈 El número es **mayor**."
        else:
            pista = "📉 El número es **menor**."
        if restantes > 0:
            await ctx.send(f"{pista} Te quedan **{restantes}** intento(s).")
        else:
            await ctx.send(f"😢 Sin más intentos. El número era **{numero}**.")
    juegos_activos.pop(ctx.channel.id, None)


# ═════════════════════════════════════════════════════════════
#  💬 FRASES DE PERSONAJES
# ═════════════════════════════════════════════════════════════

FRASES_PERSONAJES = {
    "naruto": [
        "¡No voy a rendirme, ese es mi camino del ninja!",
        "¡Cree en ti mismo! Eso es el verdadero poder del ninja.",
        "¡No me importa lo que digas! ¡Voy a ser Hokage!",
        "El dolor te hace más fuerte. Las lágrimas te hacen más valiente.",
    ],
    "goku": [
        "¡Soy un Saiyan que vive en la Tierra!",
        "¡Kamehameha!",
        "Lo siento, pero no puedo perder. Hay gente que me importa.",
        "Cada límite que rompes te hace más fuerte.",
    ],
    "luffy": [
        "¡Voy a ser el Rey de los Piratas!",
        "No me importa el título. Solo quiero ser libre.",
        "¡Un hombre que no puede proteger a sus amigos no vale nada!",
        "¡Shanks me dio este sombrero. Lo cuidaré con mi vida!",
    ],
    "zoro": [
        "Nada me sucede hasta que yo digo que algo me sucede.",
        "Cuando el mundo haya decidido que voy a morir, yo ya habré decidido vivir.",
        "¡Nunca perderé de nuevo!",
        "Solo hay un camino: hacia adelante.",
    ],
    "eren": [
        "Si no luchas, no puedes ganar.",
        "Seguiré adelante hasta que mis enemigos sean destruidos.",
        "La libertad... es lo único que siempre he querido.",
    ],
    "levi": [
        "La única forma de encontrar la respuesta correcta es elegir y no arrepentirte.",
        "Nadie puede saber cuál será el resultado. Solo sigue hacia adelante.",
        "Tus camaradas confían en ti. Sigue adelante.",
    ],
    "light": [
        "Soy el nuevo dios de este mundo.",
        "El que gana tiene razón, y el que pierde está equivocado.",
        "Este mundo podrido necesita ser cambiado.",
    ],
    "itachi": [
        "Eres débil. ¿Por qué eres débil? Porque te falta odio.",
        "El perdón es la base de la paz.",
        "No importa cuánto crezcas, siempre seré tu hermano mayor.",
    ],
}

@bot.command(name="frase_personaje", aliases=["fp", "anime_quote"])
async def frase_personaje(ctx, *, personaje: str = None):
    """💬 Frase de un personaje. Uso: !fp [personaje]"""
    personajes_disponibles = list(FRASES_PERSONAJES.keys())
    if personaje is None:
        personaje = random.choice(personajes_disponibles)
    personaje = personaje.lower().strip()
    if personaje not in FRASES_PERSONAJES:
        lista = ", ".join(f"`{p}`" for p in personajes_disponibles)
        return await ctx.send(f"❌ Personaje no encontrado. Disponibles: {lista}")
    frase = random.choice(FRASES_PERSONAJES[personaje])
    colores = [discord.Color.red(), discord.Color.blue(), discord.Color.green(),
               discord.Color.purple(), discord.Color.orange(), discord.Color.dark_gold()]
    embed = discord.Embed(
        title=f"💬 {personaje.capitalize()}",
        description=f"*\"{frase}\"*",
        color=random.choice(colores)
    )
    embed.set_footer(text=f"Pedido por {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command(name="personajes_lista", aliases=["pl"])
async def personajes_lista(ctx):
    """💬 Ver personajes disponibles."""
    lista = ", ".join(f"`{p.capitalize()}`" for p in FRASES_PERSONAJES)
    embed = discord.Embed(title="💬 Personajes disponibles", description=lista, color=discord.Color.blurple())
    embed.set_footer(text=f"Usa !fp <personaje> para ver una frase")
    await ctx.send(embed=embed)


# ═════════════════════════════════════════════════════════════
#  🔒 GESTIÓN DE CANALES (Admin)
# ═════════════════════════════════════════════════════════════

@bot.command(name="lock", aliases=["bloquear"])
@commands.check(es_admin)
async def lock(ctx, canal: discord.TextChannel = None, *, razon: str = "Sin razón"):
    """🔒 ADMIN — Bloquea un canal. Uso: !lock [#canal] [razón]"""
    canal = canal or ctx.channel
    overwrite = canal.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await canal.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"[{ctx.author}] {razon}")
    embed = discord.Embed(title="🔒 Canal Bloqueado", description=f"{canal.mention} bloqueado.\n📋 Razón: {razon}", color=discord.Color.red())
    embed.set_footer(text=f"Por {ctx.author.display_name}")
    await canal.send(embed=embed)
    if canal != ctx.channel:
        await ctx.send(f"✅ {canal.mention} bloqueado.")

@bot.command(name="unlock", aliases=["desbloquear"])
@commands.check(es_admin)
async def unlock(ctx, canal: discord.TextChannel = None, *, razon: str = "Sin razón"):
    """🔒 ADMIN — Desbloquea un canal. Uso: !unlock [#canal] [razón]"""
    canal = canal or ctx.channel
    overwrite = canal.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await canal.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"[{ctx.author}] {razon}")
    embed = discord.Embed(title="🔓 Canal Desbloqueado", description=f"{canal.mention} desbloqueado.\n📋 Razón: {razon}", color=discord.Color.green())
    embed.set_footer(text=f"Por {ctx.author.display_name}")
    await canal.send(embed=embed)
    if canal != ctx.channel:
        await ctx.send(f"✅ {canal.mention} desbloqueado.")

@bot.command(name="lockall", aliases=["bloquear_todo"])
@commands.check(es_admin)
async def lockall(ctx, *, razon: str = "Sin razón"):
    """🔒 ADMIN — Bloquea todos los canales."""
    msg = await ctx.send("⏳ Bloqueando todos los canales...")
    count = 0
    for c in ctx.guild.text_channels:
        try:
            ow = c.overwrites_for(ctx.guild.default_role)
            ow.send_messages = False
            await c.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"[LockAll] {ctx.author}")
            count += 1
        except Exception:
            pass
    embed = discord.Embed(title="🔒 Servidor Bloqueado", description=f"**{count}** canales bloqueados.\n📋 Razón: {razon}", color=discord.Color.red())
    embed.set_footer(text=f"Por {ctx.author.display_name}")
    await msg.edit(content=None, embed=embed)

@bot.command(name="unlockall", aliases=["desbloquear_todo"])
@commands.check(es_admin)
async def unlockall(ctx, *, razon: str = "Sin razón"):
    """🔒 ADMIN — Desbloquea todos los canales."""
    msg = await ctx.send("⏳ Desbloqueando todos los canales...")
    count = 0
    for c in ctx.guild.text_channels:
        try:
            ow = c.overwrites_for(ctx.guild.default_role)
            ow.send_messages = None
            await c.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"[UnlockAll] {ctx.author}")
            count += 1
        except Exception:
            pass
    embed = discord.Embed(title="🔓 Servidor Desbloqueado", description=f"**{count}** canales desbloqueados.\n📋 Razón: {razon}", color=discord.Color.green())
    embed.set_footer(text=f"Por {ctx.author.display_name}")
    await msg.edit(content=None, embed=embed)

@bot.command(name="slowmode", aliases=["sm", "modo_lento"])
@commands.check(es_admin)
async def slowmode(ctx, segundos: int = 0, canal: discord.TextChannel = None):
    """🔒 ADMIN — Modo lento. Uso: !slowmode [segundos] [#canal]"""
    canal = canal or ctx.channel
    if segundos < 0 or segundos > 21600:
        return await ctx.send("❌ Valor entre 0 y 21600 segundos.")
    await canal.edit(slowmode_delay=segundos)
    if segundos == 0:
        await ctx.send(f"✅ Modo lento **desactivado** en {canal.mention}.")
    else:
        await ctx.send(f"🐌 Modo lento en {canal.mention}: **{segundos}s** entre mensajes.")

@bot.command(name="hide", aliases=["ocultar"])
@commands.check(es_admin)
async def hide(ctx, canal: discord.TextChannel = None):
    """🔒 ADMIN — Oculta un canal. Uso: !hide [#canal]"""
    canal = canal or ctx.channel
    ow = canal.overwrites_for(ctx.guild.default_role)
    ow.view_channel = False
    await canal.set_permissions(ctx.guild.default_role, overwrite=ow)
    await ctx.send(f"👁️ {canal.mention} ahora está **oculto**.")

@bot.command(name="show", aliases=["mostrar"])
@commands.check(es_admin)
async def show(ctx, canal: discord.TextChannel = None):
    """🔒 ADMIN — Muestra un canal oculto. Uso: !show [#canal]"""
    canal = canal or ctx.channel
    ow = canal.overwrites_for(ctx.guild.default_role)
    ow.view_channel = None
    await canal.set_permissions(ctx.guild.default_role, overwrite=ow)
    await ctx.send(f"👁️ {canal.mention} ahora está **visible**.")

@bot.command(name="topic", aliases=["tema"])
@commands.check(es_admin)
async def topic(ctx, *, texto: str):
    """🔒 ADMIN — Cambia el tema del canal. Uso: !topic texto"""
    await ctx.channel.edit(topic=texto)
    await ctx.send(f"✅ Tema actualizado: **{texto}**")

@bot.command(name="rename_canal", aliases=["rc"])
@commands.check(es_admin)
async def rename_canal(ctx, *, nombre: str):
    """🔒 ADMIN — Renombra el canal actual. Uso: !rc nuevo-nombre"""
    nombre = nombre.lower().replace(" ", "-")
    viejo = ctx.channel.name
    await ctx.channel.edit(name=nombre)
    await ctx.send(f"✅ Canal: **#{viejo}** → **#{nombre}**")

@bot.command(name="crear_canal", aliases=["cc"])
@commands.check(es_admin)
async def crear_canal(ctx, *, nombre: str):
    """🔒 ADMIN — Crea un canal de texto. Uso: !cc nombre"""
    nombre = nombre.lower().replace(" ", "-")
    c = await ctx.guild.create_text_channel(nombre, reason=f"Creado por {ctx.author}")
    await ctx.send(f"✅ Canal creado: {c.mention}")

@bot.command(name="eliminar_canal", aliases=["ec"])
@commands.check(es_admin)
async def eliminar_canal(ctx, canal: discord.TextChannel = None):
    """🔒 ADMIN — Elimina un canal. Uso: !ec [#canal]"""
    canal = canal or ctx.channel
    nombre = canal.name
    await canal.delete(reason=f"Eliminado por {ctx.author}")
    if canal != ctx.channel:
        await ctx.send(f"🗑️ Canal **#{nombre}** eliminado.")

@bot.command(name="clonar_canal", aliases=["clone"])
@commands.check(es_admin)
async def clonar_canal(ctx, canal: discord.TextChannel = None):
    """🔒 ADMIN — Clona un canal. Uso: !clone [#canal]"""
    canal = canal or ctx.channel
    nuevo = await canal.clone(reason=f"Clonado por {ctx.author}")
    await ctx.send(f"✅ Canal clonado: {nuevo.mention}")

@bot.command(name="nsfw")
@commands.check(es_admin)
async def nsfw_toggle(ctx, canal: discord.TextChannel = None):
    """🔒 ADMIN — Activa/desactiva NSFW. Uso: !nsfw [#canal]"""
    canal = canal or ctx.channel
    nuevo = not canal.is_nsfw()
    await canal.edit(nsfw=nuevo)
    estado = "activado 🔞" if nuevo else "desactivado ✅"
    await ctx.send(f"NSFW **{estado}** en {canal.mention}.")

@bot.command(name="slowmode_reset", aliases=["smr"])
@commands.check(es_admin)
async def slowmode_reset(ctx):
    """🔒 ADMIN — Resetea el modo lento del canal actual."""
    await ctx.channel.edit(slowmode_delay=0)
    await ctx.send("✅ Modo lento **desactivado** en este canal.")

# ═════════════════════════════════════════════════════════════
#  🎭 GESTIÓN DE ROLES (Admin)
# ═════════════════════════════════════════════════════════════

@bot.command(name="dar_rol", aliases=["dr"])
@commands.check(es_admin)
async def dar_rol(ctx, member: discord.Member, *, nombre_rol: str):
    """🔒 ADMIN — Da un rol. Uso: !dr @usuario Nombre Rol"""
    rol = discord.utils.get(ctx.guild.roles, name=nombre_rol)
    if not rol:
        return await ctx.send(f"❌ No encontré el rol `{nombre_rol}`.")
    if rol in member.roles:
        return await ctx.send(f"⚠️ {member.mention} ya tiene **{rol.name}**.")
    try:
        await member.add_roles(rol, reason=f"Dado por {ctx.author}")
        await ctx.send(f"✅ Rol **{rol.name}** dado a {member.mention}.")
    except discord.Forbidden:
        await ctx.send("❌ Sin permisos para dar ese rol.")

@bot.command(name="quitar_rol", aliases=["qr"])
@commands.check(es_admin)
async def quitar_rol(ctx, member: discord.Member, *, nombre_rol: str):
    """🔒 ADMIN — Quita un rol. Uso: !qr @usuario Nombre Rol"""
    rol = discord.utils.get(ctx.guild.roles, name=nombre_rol)
    if not rol:
        return await ctx.send(f"❌ No encontré el rol `{nombre_rol}`.")
    if rol not in member.roles:
        return await ctx.send(f"⚠️ {member.mention} no tiene **{rol.name}**.")
    try:
        await member.remove_roles(rol, reason=f"Quitado por {ctx.author}")
        await ctx.send(f"✅ Rol **{rol.name}** quitado a {member.mention}.")
    except discord.Forbidden:
        await ctx.send("❌ Sin permisos para quitar ese rol.")

@bot.command(name="crear_rol", aliases=["cr"])
@commands.check(es_admin)
async def crear_rol(ctx, color: str = "#99AAB5", *, nombre: str):
    """🔒 ADMIN — Crea un rol. Uso: !cr #FF0000 Nombre"""
    try:
        color_obj = discord.Color.from_str(color)
    except Exception:
        return await ctx.send("❌ Color inválido. Usa `#RRGGBB`.")
    rol = await ctx.guild.create_role(name=nombre, color=color_obj, reason=f"Creado por {ctx.author}")
    await ctx.send(f"✅ Rol {rol.mention} creado.")

@bot.command(name="eliminar_rol", aliases=["er"])
@commands.check(es_admin)
async def eliminar_rol(ctx, *, nombre_rol: str):
    """🔒 ADMIN — Elimina un rol. Uso: !er Nombre Rol"""
    rol = discord.utils.get(ctx.guild.roles, name=nombre_rol)
    if not rol:
        return await ctx.send(f"❌ No encontré el rol `{nombre_rol}`.")
    try:
        await rol.delete(reason=f"Eliminado por {ctx.author}")
        await ctx.send(f"🗑️ Rol **{nombre_rol}** eliminado.")
    except discord.Forbidden:
        await ctx.send("❌ Sin permisos para eliminar ese rol.")

@bot.command(name="roles_usuario", aliases=["ru"])
@commands.check(es_admin)
async def roles_usuario(ctx, member: discord.Member = None):
    """🔒 ADMIN — Lista roles de un usuario. Uso: !ru [@usuario]"""
    member = member or ctx.author
    roles = [r.mention for r in reversed(member.roles) if r != ctx.guild.default_role]
    embed = discord.Embed(title=f"🎭 Roles de {member.display_name}", color=member.color)
    embed.description = " ".join(roles) if roles else "Sin roles"
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="anuncio", aliases=["ann"])
@commands.check(es_admin)
async def anuncio(ctx, canal: discord.TextChannel = None, *, mensaje: str):
    """🔒 ADMIN — Envía un anuncio. Uso: !ann [#canal] mensaje"""
    canal = canal or ctx.channel
    embed = discord.Embed(title="📢 Anuncio", description=mensaje, color=discord.Color.gold(), timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=f"Por {ctx.author.display_name}")
    await canal.send("@everyone", embed=embed)
    if canal != ctx.channel:
        await ctx.send(f"✅ Anuncio enviado en {canal.mention}.")

@bot.command(name="embed_msg", aliases=["emb"])
@commands.check(es_admin)
async def embed_msg(ctx, canal: discord.TextChannel = None, titulo: str = "Mensaje", *, mensaje: str):
    """🔒 ADMIN — Envía un embed. Uso: !emb [#canal] "Titulo" mensaje"""
    canal = canal or ctx.channel
    embed = discord.Embed(title=titulo, description=mensaje, color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=f"Por {ctx.author.display_name}")
    await canal.send(embed=embed)
    if canal != ctx.channel:
        await ctx.send(f"✅ Embed enviado en {canal.mention}.")


ANTINUKE_FILE = "antinuke.json"

ANTINUKE_DEFAULT = {
    "activo": True,
    "whitelist": [],          # IDs de usuarios de confianza (no se les aplica)
    "owner_id": None,         # ID del propietario del servidor
    "limites": {
        "ban": 3,             # máx bans en ventana de tiempo
        "kick": 3,
        "roles": 3,
        "canales": 3,
        "webhooks": 3,
    },
    "ventana": 10,            # segundos para contar acciones
    "accion": "ban",          # qué hacer con el nuke: ban | kick | quitar_roles
    "log_channel": None,      # ID del canal de logs
}

def cargar_antinuke() -> dict:
    if os.path.exists(ANTINUKE_FILE):
        with open(ANTINUKE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Asegurar que tenga todas las claves
        for k, v in ANTINUKE_DEFAULT.items():
            if k not in data:
                data[k] = v
        return data
    return dict(ANTINUKE_DEFAULT)

def guardar_antinuke(cfg: dict):
    with open(ANTINUKE_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# Contadores de acciones por usuario { user_id: [(timestamp, accion), ...] }
_acciones = defaultdict(list)

def registrar_accion(user_id: int, tipo: str) -> int:
    """Registra una acción y devuelve cuántas hizo en la ventana."""
    cfg = cargar_antinuke()
    ventana = cfg.get("ventana", 10)
    ahora = time.time()
    _acciones[user_id] = [
        (t, a) for t, a in _acciones[user_id]
        if ahora - t <= ventana
    ]
    _acciones[user_id].append((ahora, tipo))
    return sum(1 for _, a in _acciones[user_id] if a == tipo)

def es_seguro(user_id: int, guild: discord.Guild) -> bool:
    """Retorna True si el usuario está en whitelist o es owner."""
    cfg = cargar_antinuke()
    if guild.owner_id == user_id:
        return True
    owner = cfg.get("owner_id")
    if owner and user_id == int(owner):
        return True
    return user_id in [int(x) for x in cfg.get("whitelist", [])]

async def ejecutar_castigo(guild: discord.Guild, member: discord.Member, razon: str):
    cfg = cargar_antinuke()
    accion = cfg.get("accion", "ban")
    try:
        if accion == "ban":
            await guild.ban(member, reason=f"[AntiNuke] {razon}", delete_message_days=0)
        elif accion == "kick":
            await guild.kick(member, reason=f"[AntiNuke] {razon}")
        elif accion == "quitar_roles":
            roles = [r for r in member.roles if r != guild.default_role and not r.managed]
            if roles:
                await member.remove_roles(*roles, reason=f"[AntiNuke] {razon}")
        log.warning(f"[AntiNuke] {accion.upper()} a {member} — {razon}")
    except Exception as e:
        log.error(f"[AntiNuke] No pude aplicar castigo a {member}: {e}")

async def log_antinuke(guild: discord.Guild, titulo: str, desc: str, color=0xFF0000):
    cfg = cargar_antinuke()
    canal_id = cfg.get("log_channel")
    if not canal_id:
        return
    canal = guild.get_channel(int(canal_id))
    if canal:
        embed = discord.Embed(title=f"🛡️ AntiNuke — {titulo}", description=desc, color=color, timestamp=datetime.now(timezone.utc))
        try:
            await canal.send(embed=embed)
        except Exception:
            pass

def es_owner(ctx) -> bool:
    cfg = cargar_antinuke()
    owner = cfg.get("owner_id")
    return (
        ctx.author.id == ctx.guild.owner_id or
        (owner and ctx.author.id == int(owner))
    )

def es_owner_o_admin(ctx) -> bool:
    return es_owner(ctx) or ctx.author.guild_permissions.administrator

# ─────────────────────────────────────────────────────────────
#  EVENTOS ANTINUKE
# ─────────────────────────────────────────────────────────────

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    cfg = cargar_antinuke()
    if not cfg.get("activo"):
        return
    try:
        entry = await guild.audit_logs(limit=1, action=discord.AuditLogAction.ban).next()
        autor = entry.user
        if autor.bot or es_seguro(autor.id, guild):
            return
        count = registrar_accion(autor.id, "ban")
        if count >= cfg["limites"]["ban"]:
            member = guild.get_member(autor.id)
            if member:
                await ejecutar_castigo(guild, member, f"Ban masivo ({count} bans)")
                await log_antinuke(guild, "Ban Masivo Detectado",
                    f"**Usuario:** {autor.mention} (`{autor.id}`)\n**Bans:** {count}\n**Acción:** {cfg['accion']}")
    except Exception as e:
        log.error(f"[AntiNuke] on_member_ban error: {e}")

@bot.event
async def on_member_remove(member: discord.Member):
    cfg = cargar_antinuke()
    if not cfg.get("activo"):
        return
    try:
        entry = await member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick).next()
        autor = entry.user
        if autor.bot or es_seguro(autor.id, member.guild):
            return
        if entry.target.id == member.id:
            count = registrar_accion(autor.id, "kick")
            if count >= cfg["limites"]["kick"]:
                m = member.guild.get_member(autor.id)
                if m:
                    await ejecutar_castigo(member.guild, m, f"Kick masivo ({count} kicks)")
                    await log_antinuke(member.guild, "Kick Masivo Detectado",
                        f"**Usuario:** {autor.mention}\n**Kicks:** {count}\n**Acción:** {cfg['accion']}")
    except Exception as e:
        pass

@bot.event
async def on_guild_role_delete(role: discord.Role):
    cfg = cargar_antinuke()
    if not cfg.get("activo"):
        return
    try:
        entry = await role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete).next()
        autor = entry.user
        if autor.bot or es_seguro(autor.id, role.guild):
            return
        count = registrar_accion(autor.id, "roles")
        if count >= cfg["limites"]["roles"]:
            m = role.guild.get_member(autor.id)
            if m:
                await ejecutar_castigo(role.guild, m, f"Borrado masivo de roles ({count})")
                await log_antinuke(role.guild, "Borrado de Roles Detectado",
                    f"**Usuario:** {autor.mention}\n**Roles borrados:** {count}\n**Acción:** {cfg['accion']}")
    except Exception as e:
        pass

@bot.event
async def on_guild_channel_delete(channel):
    cfg = cargar_antinuke()
    if not cfg.get("activo"):
        return
    try:
        entry = await channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete).next()
        autor = entry.user
        if autor.bot or es_seguro(autor.id, channel.guild):
            return
        count = registrar_accion(autor.id, "canales")
        if count >= cfg["limites"]["canales"]:
            m = channel.guild.get_member(autor.id)
            if m:
                await ejecutar_castigo(channel.guild, m, f"Borrado masivo de canales ({count})")
                await log_antinuke(channel.guild, "Borrado de Canales Detectado",
                    f"**Usuario:** {autor.mention}\n**Canales borrados:** {count}\n**Acción:** {cfg['accion']}")
    except Exception as e:
        pass

@bot.event
async def on_webhooks_update(channel):
    cfg = cargar_antinuke()
    if not cfg.get("activo"):
        return
    try:
        entry = await channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create).next()
        autor = entry.user
        if autor.bot or es_seguro(autor.id, channel.guild):
            return
        count = registrar_accion(autor.id, "webhooks")
        if count >= cfg["limites"]["webhooks"]:
            m = channel.guild.get_member(autor.id)
            if m:
                await ejecutar_castigo(channel.guild, m, f"Creación masiva de webhooks ({count})")
                await log_antinuke(channel.guild, "Webhooks Masivos Detectados",
                    f"**Usuario:** {autor.mention}\n**Webhooks:** {count}\n**Acción:** {cfg['accion']}")
    except Exception as e:
        pass

# ═════════════════════════════════════════════════════════════
#  🛡️ COMANDOS ANTINUKE (solo Owner)
# ═════════════════════════════════════════════════════════════

@bot.command(name="antinuke")
@commands.check(es_owner)
async def antinuke_status(ctx):
    """👑 OWNER — Ver estado del antinuke."""
    cfg = cargar_antinuke()
    estado = "✅ Activo" if cfg["activo"] else "❌ Desactivado"
    wl = cfg.get("whitelist", [])
    wl_txt = ", ".join(f"<@{uid}>" for uid in wl) if wl else "Nadie"
    embed = discord.Embed(title="🛡️ AntiNuke — Estado", color=0x00FF88 if cfg["activo"] else 0xFF0000)
    embed.add_field(name="Estado", value=estado, inline=True)
    embed.add_field(name="Acción", value=cfg.get("accion", "ban").upper(), inline=True)
    embed.add_field(name="Ventana", value=f"{cfg.get('ventana', 10)}s", inline=True)
    limites = cfg.get("limites", {})
    embed.add_field(name="Límites", value="\n".join(f"`{k}`: {v}" for k, v in limites.items()), inline=True)
    embed.add_field(name="Whitelist", value=wl_txt, inline=False)
    log_ch = cfg.get("log_channel")
    embed.add_field(name="Canal de logs", value=f"<#{log_ch}>" if log_ch else "No configurado", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="an_activar")
@commands.check(es_owner)
async def an_activar(ctx):
    """👑 OWNER — Activa el antinuke."""
    cfg = cargar_antinuke()
    cfg["activo"] = True
    guardar_antinuke(cfg)
    await ctx.send("✅ AntiNuke **activado**.")

@bot.command(name="an_desactivar")
@commands.check(es_owner)
async def an_desactivar(ctx):
    """👑 OWNER — Desactiva el antinuke."""
    cfg = cargar_antinuke()
    cfg["activo"] = False
    guardar_antinuke(cfg)
    await ctx.send("⚠️ AntiNuke **desactivado**. El servidor queda sin protección.")

@bot.command(name="an_whitelist")
@commands.check(es_owner)
async def an_whitelist(ctx, member: discord.Member):
    """👑 OWNER — Añade/quita un usuario de la whitelist. Uso: !an_whitelist @user"""
    cfg = cargar_antinuke()
    wl = cfg.get("whitelist", [])
    uid = str(member.id)
    if uid in wl:
        wl.remove(uid)
        cfg["whitelist"] = wl
        guardar_antinuke(cfg)
        await ctx.send(f"🗑️ {member.mention} **quitado** de la whitelist.")
    else:
        wl.append(uid)
        cfg["whitelist"] = wl
        guardar_antinuke(cfg)
        await ctx.send(f"✅ {member.mention} **añadido** a la whitelist.")

@bot.command(name="an_accion")
@commands.check(es_owner)
async def an_accion(ctx, accion: str):
    """👑 OWNER — Cambia la acción ante un nuke. Uso: !an_accion ban|kick|quitar_roles"""
    accion = accion.lower()
    if accion not in ("ban", "kick", "quitar_roles"):
        return await ctx.send("❌ Opciones válidas: `ban`, `kick`, `quitar_roles`")
    cfg = cargar_antinuke()
    cfg["accion"] = accion
    guardar_antinuke(cfg)
    await ctx.send(f"✅ Acción cambiada a **{accion.upper()}**.")

@bot.command(name="an_limite")
@commands.check(es_owner)
async def an_limite(ctx, tipo: str, cantidad: int):
    """👑 OWNER — Cambia un límite. Uso: !an_limite ban 3"""
    tipos = ["ban", "kick", "roles", "canales", "webhooks"]
    if tipo not in tipos:
        return await ctx.send(f"❌ Tipos válidos: {', '.join(f'`{t}`' for t in tipos)}")
    if cantidad < 1 or cantidad > 20:
        return await ctx.send("❌ El límite debe ser entre 1 y 20.")
    cfg = cargar_antinuke()
    cfg["limites"][tipo] = cantidad
    guardar_antinuke(cfg)
    await ctx.send(f"✅ Límite de `{tipo}` cambiado a **{cantidad}**.")

@bot.command(name="an_logs")
@commands.check(es_owner)
async def an_logs(ctx, canal: discord.TextChannel = None):
    """👑 OWNER — Configura el canal de logs. Uso: !an_logs #canal"""
    cfg = cargar_antinuke()
    if canal is None:
        cfg["log_channel"] = None
        guardar_antinuke(cfg)
        return await ctx.send("🗑️ Canal de logs **eliminado**.")
    cfg["log_channel"] = str(canal.id)
    guardar_antinuke(cfg)
    await ctx.send(f"✅ Canal de logs configurado en {canal.mention}.")

@bot.command(name="an_owner")
@commands.check(lambda ctx: ctx.author.id == ctx.guild.owner_id)
async def an_owner(ctx, member: discord.Member):
    """👑 Solo dueño del servidor — Asigna un owner del antinuke. Uso: !an_owner @user"""
    cfg = cargar_antinuke()
    cfg["owner_id"] = str(member.id)
    guardar_antinuke(cfg)
    await ctx.send(f"✅ {member.mention} es ahora el **owner del AntiNuke**.")

# ═════════════════════════════════════════════════════════════
#  🔒 COMANDOS SOLO ADMIN (moderación extra)
# ═════════════════════════════════════════════════════════════

@bot.command(name="ban")
@commands.check(es_admin)
async def ban_cmd(ctx, member: discord.Member, *, razon: str = "Sin razón"):
    """🔒 ADMIN — Banea a un usuario. Uso: !ban @usuario [razón]"""
    if member == ctx.author:
        return await ctx.send("❌ No puedes banearte a ti mismo.")
    if member.guild_permissions.administrator:
        return await ctx.send("❌ No puedes banear a un administrador.")
    await guild_ban_safe(ctx.guild, member, razon, ctx.author)
    embed = discord.Embed(title="🔨 Usuario Baneado", color=discord.Color.red())
    embed.add_field(name="👤 Usuario", value=f"{member} (`{member.id}`)", inline=True)
    embed.add_field(name="📋 Razón", value=razon, inline=True)
    embed.add_field(name="👮 Por", value=ctx.author.display_name, inline=True)
    await ctx.send(embed=embed)

async def guild_ban_safe(guild, member, razon, autor):
    try:
        await guild.ban(member, reason=f"[{autor}] {razon}", delete_message_days=0)
    except discord.Forbidden:
        pass

@bot.command(name="kick")
@commands.check(es_admin)
async def kick_cmd(ctx, member: discord.Member, *, razon: str = "Sin razón"):
    """🔒 ADMIN — Expulsa a un usuario. Uso: !kick @usuario [razón]"""
    if member == ctx.author:
        return await ctx.send("❌ No puedes kickearte a ti mismo.")
    try:
        await ctx.guild.kick(member, reason=f"[{ctx.author}] {razon}")
    except discord.Forbidden:
        return await ctx.send("❌ No tengo permisos para kickear a ese usuario.")
    embed = discord.Embed(title="👢 Usuario Expulsado", color=discord.Color.orange())
    embed.add_field(name="👤 Usuario", value=f"{member}", inline=True)
    embed.add_field(name="📋 Razón", value=razon, inline=True)
    embed.add_field(name="👮 Por", value=ctx.author.display_name, inline=True)
    await ctx.send(embed=embed)

@bot.command(name="mute")
@commands.check(es_admin)
async def mute_cmd(ctx, member: discord.Member, minutos: int = 10, *, razon: str = "Sin razón"):
    """🔒 ADMIN — Mutea a un usuario. Uso: !mute @usuario [minutos] [razón]"""
    import datetime as dt
    if minutos < 1 or minutos > 40320:
        return await ctx.send("❌ Los minutos deben ser entre 1 y 40320 (28 días).")
    try:
        until = discord.utils.utcnow() + dt.timedelta(minutes=minutos)
        await member.timeout(until, reason=f"[{ctx.author}] {razon}")
    except discord.Forbidden:
        return await ctx.send("❌ No tengo permisos para mutear a ese usuario.")
    embed = discord.Embed(title="🔇 Usuario Muteado", color=discord.Color.dark_grey())
    embed.add_field(name="👤 Usuario", value=member.mention, inline=True)
    embed.add_field(name="⏰ Duración", value=f"{minutos} minutos", inline=True)
    embed.add_field(name="📋 Razón", value=razon, inline=True)
    embed.add_field(name="👮 Por", value=ctx.author.display_name, inline=True)
    await ctx.send(embed=embed)

@bot.command(name="unmute")
@commands.check(es_admin)
async def unmute_cmd(ctx, member: discord.Member):
    """🔒 ADMIN — Desmutea a un usuario. Uso: !unmute @usuario"""
    try:
        await member.timeout(None)
    except discord.Forbidden:
        return await ctx.send("❌ No tengo permisos para desmutear a ese usuario.")
    await ctx.send(f"✅ {member.mention} ha sido **desmuteado**.")

@bot.command(name="limpiar", aliases=["clear", "purge"])
@commands.check(es_admin)
async def limpiar(ctx, cantidad: int = 10):
    """🔒 ADMIN — Borra mensajes. Uso: !limpiar [cantidad]"""
    if cantidad < 1 or cantidad > 100:
        return await ctx.send("❌ Debes indicar entre 1 y 100 mensajes.")
    borrados = await ctx.channel.purge(limit=cantidad + 1)
    msg = await ctx.send(f"🗑️ **{len(borrados)-1}** mensajes borrados.")
    await asyncio.sleep(3)
    await msg.delete()

@bot.command(name="userinfo", aliases=["ui", "whois"])
@commands.check(es_admin)
async def userinfo(ctx, member: discord.Member = None):
    """🔒 ADMIN — Info de un usuario. Uso: !userinfo [@usuario]"""
    member = member or ctx.author
    roles = [r.mention for r in member.roles if r != ctx.guild.default_role]
    embed = discord.Embed(title=f"👤 Info de {member}", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🆔 ID", value=member.id, inline=True)
    embed.add_field(name="📅 Cuenta creada", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="📥 Se unió", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="🏆 Roles", value=" ".join(roles) if roles else "Sin roles", inline=False)
    embed.add_field(name="🤖 Bot", value="Sí" if member.bot else "No", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="serverinfo", aliases=["si", "servidor"])
@commands.check(es_admin)
async def serverinfo(ctx):
    """🔒 ADMIN — Info del servidor."""
    g = ctx.guild
    embed = discord.Embed(title=f"🏠 {g.name}", color=discord.Color.blurple())
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="🆔 ID", value=g.id, inline=True)
    embed.add_field(name="👑 Dueño", value=g.owner.mention, inline=True)
    embed.add_field(name="👥 Miembros", value=g.member_count, inline=True)
    embed.add_field(name="💬 Canales", value=len(g.channels), inline=True)
    embed.add_field(name="🎭 Roles", value=len(g.roles), inline=True)
    embed.add_field(name="📅 Creado", value=g.created_at.strftime("%d/%m/%Y"), inline=True)
    await ctx.send(embed=embed)


# ─────────────────────────────────────────────────────────────
#  EVENTOS
# ─────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    log.info(f"Bot conectado como {bot.user} (ID: {bot.user.id})")
    log.info(f"{len(RANGOS)} rangos | puntos por acción: 1–{PUNTOS_MAX} | Prefix: {PREFIX}")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name=f"{PREFIX}ayuda | Raids")
    )

@bot.event
async def on_member_join(member: discord.Member):
    rol = discord.utils.get(member.guild.roles, name="Wraith")
    if rol:
        try:
            await member.add_roles(rol)
            log.info(f"Wraith asignado a {member} al entrar")
        except discord.Forbidden:
            log.warning(f"Sin permisos para asignar rol a {member}")

# ═════════════════════════════════════════════════════════════
#  🔒 COMANDOS SOLO ADMIN
# ═════════════════════════════════════════════════════════════

@bot.command(name="setup_rangos")
@commands.check(es_admin)
async def setup_rangos(ctx):
    """🔒 ADMIN — Crea los 60 roles de gradiente en el servidor."""
    import aiohttp
    DISCORD_API = "https://discord.com/api/v10"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

    msg = await ctx.send(f"⏳ Creando {len(ROLES_DATA)} roles con gradiente...")
    creados = existentes = errores = 0

    async with aiohttp.ClientSession() as session:
        for nombre, c1, c2 in ROLES_DATA:
            existe = discord.utils.get(ctx.guild.roles, name=nombre)
            if existe:
                # Actualizar colores
                async with session.patch(
                    f"{DISCORD_API}/guilds/{ctx.guild.id}/roles/{existe.id}",
                    headers=headers, json={"colors": [c1, c2]}
                ) as resp:
                    existentes += 1
            else:
                payload = {"name": nombre, "colors": [c1, c2], "hoist": False, "mentionable": False}
                async with session.post(
                    f"{DISCORD_API}/guilds/{ctx.guild.id}/roles",
                    headers=headers, json=payload
                ) as resp:
                    if resp.status in (200, 201):
                        creados += 1
                    else:
                        log.warning(f"Error creando {nombre}: {resp.status}")
                        errores += 1

    log.info(f"setup_rangos: {creados} creados, {existentes} ya existían, {errores} errores")
    embed = discord.Embed(title="✅ Roles Listos!", color=0x00FF88)
    embed.add_field(name="✨ Creados",      value=str(creados),      inline=True)
    embed.add_field(name="🔄 Actualizados", value=str(existentes),   inline=True)
    embed.add_field(name="❌ Errores",      value=str(errores),       inline=True)
    embed.set_footer(text=f"60 roles con gradiente | Usa {PREFIX}raid @usuario para empezar")
    await msg.edit(content=None, embed=embed)


@bot.command(name="setup_staff")
@commands.check(es_admin)
async def setup_staff(ctx):
    """🔒 ADMIN — Crea los roles de staff."""
    roles_staff = [
        {"nombre": "👑 Administración", "color": "#FF0000", "perms": discord.Permissions(administrator=True)},
        {"nombre": "🛡️ Moderador",      "color": "#FF6600", "perms": discord.Permissions(kick_members=True, ban_members=True, manage_messages=True, mute_members=True)},
        {"nombre": "🤝 Helper",          "color": "#00AAFF", "perms": discord.Permissions(manage_messages=True)},
    ]
    creados = []
    for r in roles_staff:
        if not discord.utils.get(ctx.guild.roles, name=r["nombre"]):
            await ctx.guild.create_role(
                name=r["nombre"], color=discord.Color.from_str(r["color"]),
                hoist=True, mentionable=True, permissions=r["perms"], reason="Setup staff"
            )
            creados.append(r["nombre"])
    if creados:
        await ctx.send(f"✅ Roles creados: {', '.join(f'**{n}**' for n in creados)}")
    else:
        await ctx.send("ℹ️ Los roles de staff ya existían.")


@bot.command(name="set_puntos", aliases=["sp"])
@commands.check(es_admin)
async def set_puntos_cmd(ctx, member: discord.Member, cantidad: int):
    """🔒 ADMIN — Fija los puntos exactos. Uso: !set_puntos @usuario 300"""
    if cantidad < 0:
        return await ctx.send("❌ La cantidad debe ser positiva.")
    set_puntos(member.id, cantidad)
    await actualizar_rango_rol(member, cantidad)
    rango = rango_por_puntos(cantidad)
    nombre_rango = rango["nombre"] if rango else "Sin rango aún"
    log.info(f"set_puntos: {ctx.author} → {member} = {cantidad} pts ({nombre_rango})")
    await ctx.send(f"✅ {member.mention} ahora tiene **{cantidad} pts** → **{nombre_rango}**")


@bot.command(name="resetear", aliases=["reset"])
@commands.check(es_admin)
async def resetear(ctx, member: discord.Member):
    """🔒 ADMIN — Resetea los puntos a 0. Uso: !resetear @usuario"""
    rango_antes = rango_por_puntos(get_puntos(member.id))
    set_puntos(member.id, 0)
    await actualizar_rango_rol(member, 0)
    log.info(f"resetear: {ctx.author} reseteó a {member} (era {rango_antes['nombre']})")
    await ctx.send(f"🔄 {member.mention} reseteado a **0 pts** (era **{rango_antes['nombre']}**).")


@bot.command(name="borrar_rangos")
@commands.check(es_admin)
async def borrar_rangos(ctx):
    """🔒 ADMIN — Elimina todos los roles de rango."""
    msg = await ctx.send("⏳ Eliminando roles de rango...")
    eliminados = 0
    for role in ctx.guild.roles:
        if role.name in NOMBRES_RANGOS:
            try:
                await role.delete(reason="Borrado por admin")
                eliminados += 1
            except Exception as e:
                log.warning(f"No pude eliminar {role.name}: {e}")
    log.info(f"borrar_rangos: {ctx.author} eliminó {eliminados} roles")
    await msg.edit(content=f"🗑️ {eliminados} roles de rango eliminados.")


# ═════════════════════════════════════════════════════════════
#  🔑 COMANDOS STAFF (Admin + Mod)
# ═════════════════════════════════════════════════════════════

@bot.command(name="raid")
@commands.check(es_staff)
async def registrar_raid(ctx, *miembros: discord.Member):
    """🔑 STAFF — Registra una raid (+15 pts). Uso: !raid @u1 @u2 ..."""
    if not miembros:
        return await ctx.send(f"❌ Menciona al menos un miembro. Ej: `{PREFIX}raid @user1 @user2`")

    resultados, subidas = [], []

    for member in miembros:
        antes       = get_puntos(member.id)
        rango_antes = rango_por_puntos(antes)
        nuevos      = add_puntos(member.id, PUNTOS_MAX, contar_raid=True)
        await actualizar_rango_rol(member, nuevos)
        rango_nuevo = rango_por_puntos(nuevos)
        nombre_nuevo = rango_nuevo["nombre"] if rango_nuevo else "Sin rango aún"
        nombre_antes = rango_antes["nombre"] if rango_antes else "Sin rango"
        resultados.append(f"{member.mention} → **{nuevos} pts** | {nombre_nuevo}")
        if nombre_nuevo != nombre_antes:
            subidas.append(f"🎉 {member.mention} subió a **{nombre_nuevo}**!")

    log.info(f"raid: {ctx.author} registró raid para {[str(m) for m in miembros]}")
    embed = discord.Embed(title=f"⚔️ Raid Registrada (+{PUNTOS_MAX} pts)", color=discord.Color.green())
    embed.add_field(name="Participantes", value="\n".join(resultados), inline=False)
    if subidas:
        embed.add_field(name="🏆 ¡Subida de Rango!", value="\n".join(subidas), inline=False)
    embed.set_footer(text=f"Registrado por {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="dar", aliases=["d"])
@commands.check(es_staff)
async def dar_puntos(ctx, member: discord.Member, raids: int):
    """🔑 STAFF — Da raids a un miembro (1-7). Uso: !dar @usuario 3"""
    if raids < 1 or raids > 7:
        return await ctx.send(
            "❌ Solo puedes dar entre **1 y 7** raids a la vez.\n"
            "Ejemplo: `!dar @usuario 3` da 3 raids (45 pts)"
        )

    cantidad    = raids
    antes       = get_puntos(member.id)
    rango_antes = rango_por_puntos(antes)
    nuevos      = add_puntos(member.id, cantidad, contar_raid=True)
    await actualizar_rango_rol(member, nuevos)
    rango_nuevo = rango_por_puntos(nuevos)
    siguiente   = siguiente_rango(nuevos)

    nombre_rango = rango_nuevo["nombre"] if rango_nuevo else "Sin rango aún"
    color_rango  = discord.Color.from_str(rango_nuevo["color"]) if rango_nuevo else discord.Color.greyple()

    log.info(f"dar: {ctx.author} → {member} +{raids} raids (+{cantidad} pts) = {nuevos} ({nombre_rango})")
    embed = discord.Embed(title="➕ Raids Añadidas", color=color_rango)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Miembro",    value=member.mention,                    inline=True)
    embed.add_field(name="⚔️ Puntos",     value=f"+{raids} pt(s)",                 inline=True)
    embed.add_field(name="✅ Registrado", value=f"Por {ctx.author.display_name}",   inline=True)
    embed.add_field(name="💰 Total",      value=f"{nuevos} pts ({get_raids(member.id)} raids)",   inline=True)
    embed.add_field(name="🏆 Rango",      value=nombre_rango,                       inline=True)
    nombre_antes = rango_antes["nombre"] if rango_antes else "Sin rango"
    if nombre_rango != nombre_antes:
        embed.add_field(name="🎉 ¡SUBIÓ!", value=f"{nombre_antes} → **{nombre_rango}**", inline=False)
    if siguiente:
        raids_faltan = siguiente["puntos"] - nuevos
        embed.add_field(name="📈 Siguiente", value=f"{siguiente['nombre']} — **{raids_faltan} pts más**", inline=False)
    elif rango_nuevo:
        embed.add_field(name="👑 MÁXIMO", value="Ha llegado al **Celestial**.", inline=False)
    embed.set_footer(text=f"Registrado por {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="quitar_puntos", aliases=["qp"])
@commands.check(es_staff)
async def quitar_puntos(ctx, member: discord.Member, cantidad: int):
    """🔑 STAFF — Quita puntos. Uso: !quitar_puntos @usuario 30"""
    if cantidad <= 0:
        return await ctx.send("❌ La cantidad debe ser positiva.")
    antes  = get_puntos(member.id)
    nuevos = max(0, antes - cantidad)
    set_puntos(member.id, nuevos)
    await actualizar_rango_rol(member, nuevos)
    rango = rango_por_puntos(nuevos)
    log.info(f"quitar_puntos: {ctx.author} → {member} -{cantidad} pts = {nuevos}")
    embed = discord.Embed(title="📉 Puntos Removidos", color=discord.Color.red())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Miembro",  value=member.mention,     inline=True)
    embed.add_field(name="➖ Quitados", value=f"-{cantidad} pts",  inline=True)
    embed.add_field(name="💰 Total",    value=f"{nuevos} pts",     inline=True)
    embed.add_field(name="🏆 Rango", value=rango["nombre"] if rango else "Sin rango", inline=True)
    await ctx.send(embed=embed)


# ═════════════════════════════════════════════════════════════
#  🌐 COMANDOS GENERALES
# ═════════════════════════════════════════════════════════════

@bot.command(name="perfil", aliases=["puntos", "rank", "p"])
async def ver_puntos(ctx, member: discord.Member = None):
    """🌐 GENERAL — Perfil de raids. Uso: !perfil [@usuario]"""
    member    = member or ctx.author
    puntos    = get_puntos(member.id)
    rango     = rango_por_puntos(puntos)
    siguiente = siguiente_rango(puntos)

    barra = barra_progreso(puntos, rango, siguiente) if rango else "`░░░░░░░░░░░░░░░░░░░░` 0%"
    siguiente_txt = (
        f"{siguiente['nombre']} — **{siguiente['puntos'] - puntos} pts más**"
        if siguiente else "👑 ¡Eres el **Celestial**! Rango máximo."
    )

    color = discord.Color.from_str(rango["color"]) if rango else discord.Color.greyple()
    embed = discord.Embed(
        title=f"🏆 Perfil de Raids — {member.display_name}",
        color=color
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🎖️ Rango",         value=rango["nombre"] if rango else "Sin rango", inline=True)
    embed.add_field(name="💰 Puntos",         value=f"{puntos} pts",                            inline=True)
    embed.add_field(name="⚔️ Raids totales",  value=str(get_raids(member.id)), inline=True)
    if rango:
        embed.add_field(name="📊 Tier",       value=obtener_tier(rango),  inline=False)
    embed.add_field(name="📈 Progreso",        value=barra,                inline=False)
    embed.add_field(name="🎯 Siguiente rango", value=siguiente_txt,        inline=False)
    embed.set_footer(text=f"ID: {member.id}")
    await ctx.send(embed=embed)


@bot.command(name="top", aliases=["leaderboard", "lb"])
async def top_rangos(ctx, cantidad: int = 10):
    """🌐 GENERAL — Top jugadores. Uso: !top [cantidad, máx 20]"""
    cantidad = min(max(cantidad, 3), 20)
    db = cargar_db()
    ranking = sorted(db.items(), key=lambda x: x[1].get("puntos", 0), reverse=True)[:cantidad]
    if not ranking:
        return await ctx.send("❌ Nadie en el ranking todavía.")

    embed    = discord.Embed(title=f"🏆 Top {cantidad} — Puntos de Raid", color=discord.Color.gold())
    medallas = ["🥇", "🥈", "🥉"] + ["🔹"] * 17

    for i, (uid, data) in enumerate(ranking):
        puntos = data.get("puntos", 0)
        rango  = rango_por_puntos(puntos)
        try:
            member = await ctx.guild.fetch_member(int(uid))
            nombre = member.display_name
        except Exception:
            nombre = "Usuario desconocido"
        embed.add_field(
            name=f"{medallas[i]} #{i+1} — {nombre}",
            value=f"{rango['nombre'] if rango else 'Sin rango'} | **{puntos} pts** | {data.get('raids', 0)} raids",
            inline=False
        )
    await ctx.send(embed=embed)


@bot.command(name="rangos", aliases=["rl", "rangos_lista"])
async def rangos_lista(ctx):
    """🌐 GENERAL — Lista los 60 roles con gradiente paginados."""
    view = RolesView()
    view.sync_btns()
    await ctx.send(embed=view.build_embed(), view=view)


class RolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.pagina = 0
        self.total = len(ROLES_DATA) // ROLES_POR_PAGINA

    def build_embed(self):
        ini = self.pagina * ROLES_POR_PAGINA
        fin = ini + ROLES_POR_PAGINA
        titulo, color = PAGINA_INFO[self.pagina]
        em = discord.Embed(
            title=f"☠️  Roles — {titulo}",
            description=f"> Página **{self.pagina+1}/{self.total}**\n> Los roles se desbloquean acumulando puntos.\n\u200b",
            color=color
        )
        lista = ""
        for i, (nombre, c1, c2) in enumerate(ROLES_DATA[ini:fin], start=ini):
            lista += f"`{i+1:02d}.` **{nombre}**  `#{c1:06X}`→`#{c2:06X}`  ⭐`{costo_rol(i)} pts`\n"
        em.add_field(name=f"Roles {ini+1}–{fin}:", value=lista, inline=False)
        nav = "  ".join(["◆" if j == self.pagina else "◇" for j in range(self.total)])
        em.set_footer(text=f"{nav}  |  Rol 1=15pts … Rol 60=900pts")
        return em

    def sync_btns(self):
        self.prev.disabled = (self.pagina == 0)
        self.nxt.disabled  = (self.pagina == self.total - 1)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction, button):
        if self.pagina > 0: self.pagina -= 1
        self.sync_btns()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def nxt(self, interaction, button):
        if self.pagina < self.total - 1: self.pagina += 1
        self.sync_btns()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="✖", style=discord.ButtonStyle.danger)
    async def close(self, interaction, button):
        await interaction.response.defer()
        await interaction.delete_original_response()


@bot.command(name="ayuda", aliases=["help", "h", "comandos"])
async def ayuda(ctx):
    """🌐 GENERAL — Muestra todos los comandos."""
    p = PREFIX
    embed = discord.Embed(
        title="📖 Comandos del Bot de Raids",
        description=f"Prefix: `{p}` — Da entre 1 y 7 puntos por raid | 60 roles con gradiente",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="🌐 Generales (todos)",
        value=(
            f"`{p}perfil [@user]` — Tu perfil o el de alguien\n"
            f"`{p}top [n]` — Leaderboard top 3–20\n"
            f"`{p}rangos` — Ver los 60 roles paginados (◀▶)\n"
            f"`{p}ayuda` — Este menú"
        ),
        inline=False
    )
    embed.add_field(
        name="🔑 Staff (Admin + Mod)",
        value=(
            f"`{p}raid @u1 @u2 ...` — Registrar raid (+{PUNTOS_MAX} pts)\n"
            f"`{p}dar @user <1-7>` — Dar entre 1 y 7 puntos directamente\n"
            f"`{p}quitar_puntos @user <pts>` — Quitar puntos"
        ),
        inline=False
    )
    embed.add_field(
        name="🔒 Solo Admin",
        value=(
            f"`{p}setup_rangos` — Crear los 60 roles con gradiente\n"
            f"`{p}setup_staff` — Crear roles Admin/Mod/Helper\n"
            f"`{p}set_puntos @user <pts>` — Fijar puntos exactos\n"
            f"`{p}resetear @user` — Resetear a 0\n"
            f"`{p}borrar_rangos` — Eliminar todos los roles de rango\n"
            f"`{p}v @user` — Dar el rol **arn** a un usuario"
        ),
        inline=False
    )
    embed.add_field(
        name="🎭 Roleplay",
        value=(
            f"`{p}casar @user` — Proponer matrimonio\n"
            f"`{p}aceptar` / `{p}rechazar` — Responder propuesta\n"
            f"`{p}divorcio` — Divorciarse\n"
            f"`{p}pareja [@user]` — Ver pareja\n"
            f"`{p}adoptar @user` — Adoptar a alguien\n"
            f"`{p}familia [@user]` — Ver árbol familiar"
        ),
        inline=False
    )
    embed.add_field(
        name="🔮 Horóscopo y Personalidad",
        value=(
            f"`{p}horoscopo <signo>` — Tu horóscopo del día\n"
            f"`{p}personalidad [@user]` — Tipo de personalidad\n"
            f"`{p}compatibilidad @user` — % de compatibilidad"
        ),
        inline=False
    )
    embed.add_field(
        name="🃏 Juegos de Chat",
        value=(
            f"`{p}trivia` — Pregunta de trivia con reacciones\n"
            f"`{p}adivina [máximo]` — Adivina el número (5 intentos)"
        ),
        inline=False
    )
    embed.add_field(
        name="💬 Frases de Personajes",
        value=(
            f"`{p}fp [personaje]` — Frase de Naruto, Goku, Luffy, Zoro, Eren, Levi, Light, Itachi\n"
            f"`{p}pl` — Ver todos los personajes disponibles"
        ),
        inline=False
    )
    embed.add_field(
        name="🎰 Minijuegos",
        value=(
            f"`{p}dado [lados]` — Tira un dado\n"
            f"`{p}moneda` — Cara o sello\n"
            f"`{p}ruleta op1 op2...` — Elige una opción random\n"
            f"`{p}8ball <pregunta>` — La bola mágica\n"
            f"`{p}piedra` — Piedra papel tijera"
        ),
        inline=False
    )
    embed.add_field(
        name="🐱 Anime",
        value=(
            f"`{p}abrazar @user` `{p}pat @user` `{p}slap @user`\n"
            f"`{p}kiss @user` `{p}poke @user` `{p}cuddle @user`\n"
            f"`{p}bite @user` `{p}wave @user` `{p}dance @user` `{p}cry`"
        ),
        inline=False
    )
    embed.add_field(
        name="😂 Memes y Frases",
        value=(
            f"`{p}meme` — Meme random de Reddit\n"
            f"`{p}chiste` — Chiste random\n"
            f"`{p}frase` — Frase motivacional"
        ),
        inline=False
    )
    embed.add_field(
        name="🔒 Canales (Admin)",
        value=(
            f"`{p}lock` / `{p}unlock` [#canal] — Bloquear/desbloquear\n"
            f"`{p}lockall` / `{p}unlockall` — Todo el servidor\n"
            f"`{p}hide` / `{p}show` [#canal] — Ocultar/mostrar\n"
            f"`{p}slowmode [seg]` — Modo lento\n"
            f"`{p}topic <texto>` — Cambiar tema\n"
            f"`{p}rc <nombre>` — Renombrar canal\n"
            f"`{p}cc <nombre>` — Crear canal\n"
            f"`{p}ec [#canal]` — Eliminar canal\n"
            f"`{p}clone [#canal]` — Clonar canal\n"
            f"`{p}nsfw [#canal]` — Toggle NSFW"
        ),
        inline=False
    )
    embed.add_field(
        name="🎭 Roles (Admin)",
        value=(
            f"`{p}dr @user <rol>` — Dar rol\n"
            f"`{p}qr @user <rol>` — Quitar rol\n"
            f"`{p}cr #color <nombre>` — Crear rol\n"
            f"`{p}er <nombre>` — Eliminar rol\n"
            f"`{p}ru [@user]` — Ver roles de usuario\n"
            f"`{p}ann [#canal] <msg>` — Anuncio con @everyone\n"
            f"`{p}emb [#canal] \"Titulo\" <msg>` — Enviar embed"
        ),
        inline=False
    )
    embed.add_field(
        name="🔒 Moderación (Admin)",
        value=(
            f"`{p}ban @user [razón]` — Banear usuario\n"
            f"`{p}kick @user [razón]` — Expulsar usuario\n"
            f"`{p}mute @user [min] [razón]` — Mutear usuario\n"
            f"`{p}unmute @user` — Desmutear usuario\n"
            f"`{p}limpiar [cantidad]` — Borrar mensajes (máx 100)\n"
            f"`{p}userinfo [@user]` — Info de usuario\n"
            f"`{p}serverinfo` — Info del servidor"
        ),
        inline=False
    )
    embed.add_field(
        name="🌐 Generales Extra",
        value=(
            f"`{p}ping` — Latencia del bot\n"
            f"`{p}avatar [@user]` — Ver avatar\n"
            f"`{p}banner [@user]` — Ver banner\n"
            f"`{p}stats` — Estadísticas del servidor\n"
            f"`{p}botinfo` — Info del bot\n"
            f"`{p}calc <expr>` — Calculadora\n"
            f"`{p}color <hex>` — Info de color\n"
            f"`{p}clima <ciudad>` — Clima actual\n"
            f"`{p}tr <idioma> <texto>` — Traducir texto\n"
            f"`{p}dp [n] [lados]` — Dados múltiples\n"
            f"`{p}sugerencia [#canal] <txt>` — Sugerencia\n"
            f"`{p}reporte @user <razón>` — Reportar usuario\n"
            f"`{p}invitar` — Link de invitación del bot"
        ),
        inline=False
    )
    embed.add_field(
        name="🎂 Cumpleaños",
        value=(
            f"`{p}cumple DD/MM` — Registrar tu cumpleaños\n"
            f"`{p}cumple_ver [@user]` — Ver cumpleaños\n"
            f"`{p}cumples_lista` — Próximos cumpleaños"
        ),
        inline=False
    )
    embed.add_field(
        name="⏰ Recordatorios",
        value=f"`{p}recordar <tiempo> <msg>` — Ej: `!recordar 10m Ir al gym` (s/m/h)",
        inline=False
    )
    embed.add_field(
        name="⚙️ Configuración (Owner/Admin)",
        value=f"`{p}setprefix <nuevo>` — Cambiar prefijo del bot",
        inline=False
    )
    embed.set_footer(text="Wraith → Celestial | 900 puntos al máximo | 60 roles con gradiente")
    await ctx.send(embed=embed)


# ═════════════════════════════════════════════════════════════
#  🔒 COMANDO !v — DAR ROL ARN (Solo Admin)
# ═════════════════════════════════════════════════════════════

ROL_ARN_ID        = 1473493514770972922   # ID del rol /arn
ROL_SIN_ACCESO_ID = 1479630235283624049   # ID del rol sin acceso

@bot.command(name="v")
@commands.check(es_admin)
async def dar_rol_arn(ctx, member: discord.Member):
    """🔒 ADMIN — Da /arn y quita sin acceso. Uso: !v @usuario"""
    rol_arn        = ctx.guild.get_role(ROL_ARN_ID)
    rol_sin_acceso = ctx.guild.get_role(ROL_SIN_ACCESO_ID)

    if rol_arn is None:
        return await ctx.send("❌ No encontré el rol /arn. Verifica el ID.")

    # Quitar rol sin acceso si lo tiene
    if rol_sin_acceso and rol_sin_acceso in member.roles:
        try:
            await member.remove_roles(rol_sin_acceso, reason=f"!v usado por {ctx.author}")
            log.info(f"dar_rol_arn: se quitó sin acceso a {member}")
        except discord.Forbidden:
            await ctx.send("⚠️ No pude quitar el rol sin acceso (jerarquía). Continúo con /arn...")

    # Dar rol /arn
    if rol_arn in member.roles:
        return await ctx.send(f"⚠️ {member.mention} ya tiene el rol **{rol_arn.name}**.")

    try:
        await member.add_roles(rol_arn, reason=f"Asignado por {ctx.author} con !v")
        log.info(f"dar_rol_arn: {ctx.author} → {member} recibió el rol '{rol_arn.name}'")
    except discord.Forbidden:
        return await ctx.send("❌ No pude asignar /arn. Sube el rol del bot en la jerarquía.")

    embed = discord.Embed(title="✅ Acceso Concedido", color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Miembro",    value=member.mention,              inline=True)
    embed.add_field(name="✅ Rol dado",   value=f"**{rol_arn.name}**",        inline=True)
    embed.add_field(name="🗑️ Rol quitado", value="**sin acceso**" if rol_sin_acceso else "No tenía", inline=True)
    embed.add_field(name="✍️ Por",         value=ctx.author.display_name,    inline=True)
    msg = await ctx.send(embed=embed)
    await asyncio.sleep(10)
    await msg.delete()


@dar_rol_arn.error
async def dar_rol_arn_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Debes mencionar a un usuario. Uso: `{PREFIX}v @usuario`")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Usuario no encontrado. Menciónalo con @.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("🔒 Solo los **administradores** pueden usar este comando.")


# ─────────────────────────────────────────────────────────────
#  MANEJO DE ERRORES
# ─────────────────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("🔒 No tienes permisos para ese comando.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Miembro no encontrado. Menciónalo con @.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Argumento inválido. Usa `{PREFIX}ayuda` para ver el uso correcto.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Falta un argumento. Usa `{PREFIX}ayuda` para ver cómo usarlo.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        log.error(f"Error en '{ctx.command}': {error}\n{traceback.format_exc()}")
        await ctx.send(f"⚠️ Error: `{error}`")


# ═════════════════════════════════════════════════════════════
#  🎰 JUEGOS
# ═════════════════════════════════════════════════════════════

@bot.command(name="dado", aliases=["dice", "d6"])
async def dado(ctx, lados: int = 6):
    """🎰 Tira un dado. Uso: !dado [lados]"""
    if lados < 2 or lados > 100:
        return await ctx.send("❌ El dado debe tener entre 2 y 100 lados.")
    resultado = random.randint(1, lados)
    embed = discord.Embed(title="🎲 Dado", color=discord.Color.blurple())
    embed.add_field(name=f"D{lados}", value=f"**{resultado}**", inline=True)
    embed.set_footer(text=f"Tirado por {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="moneda", aliases=["coin", "flip"])
async def moneda(ctx):
    """🎰 Tira una moneda."""
    resultado = random.choice(["🪙 Cara", "🪙 Sello"])
    embed = discord.Embed(title="🪙 Moneda", description=f"**{resultado}**", color=discord.Color.gold())
    embed.set_footer(text=f"Lanzada por {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="ruleta", aliases=["roulette"])
async def ruleta(ctx, *opciones):
    """🎰 Elige una opción random. Uso: !ruleta op1 op2 op3"""
    if len(opciones) < 2:
        return await ctx.send("❌ Debes poner al menos 2 opciones. Ej: `!ruleta pizza hamburguesa sushi`")
    elegida = random.choice(opciones)
    embed = discord.Embed(title="🎡 Ruleta", color=discord.Color.red())
    embed.add_field(name="Opciones", value=" | ".join(f"`{o}`" for o in opciones), inline=False)
    embed.add_field(name="🏆 Elegida", value=f"**{elegida}**", inline=False)
    embed.set_footer(text=f"Girada por {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="8ball", aliases=["bola8"])
async def bola_ocho(ctx, *, pregunta: str):
    """🎰 La bola mágica responde. Uso: !8ball ¿pregunta?"""
    respuestas = [
        "✅ Sí, definitivamente.", "✅ Todo indica que sí.", "✅ Sin duda.",
        "✅ Puedes contar con ello.", "✅ Las señales dicen que sí.",
        "🤔 Respuesta confusa, intenta de nuevo.", "🤔 No está claro ahora.",
        "🤔 Mejor no te digo ahora.", "🤔 Concéntrate y pregunta de nuevo.",
        "❌ No cuentes con ello.", "❌ Mi respuesta es no.", "❌ Las señales dicen que no.",
        "❌ Muy dudoso.", "❌ Definitivamente no."
    ]
    embed = discord.Embed(title="🎱 Bola Mágica", color=discord.Color.dark_purple())
    embed.add_field(name="❓ Pregunta", value=pregunta, inline=False)
    embed.add_field(name="🔮 Respuesta", value=random.choice(respuestas), inline=False)
    embed.set_footer(text=f"Preguntado por {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="piedra", aliases=["rps"])
async def piedra_papel_tijera(ctx, eleccion: str):
    """🎰 Piedra, papel o tijera. Uso: !piedra / !rps papel"""
    opciones = ["piedra", "papel", "tijera"]
    eleccion = eleccion.lower()
    if eleccion not in opciones:
        return await ctx.send("❌ Elige: `piedra`, `papel` o `tijera`")
    bot_eleccion = random.choice(opciones)
    emojis = {"piedra": "🪨", "papel": "📄", "tijera": "✂️"}
    if eleccion == bot_eleccion:
        resultado = "🤝 ¡Empate!"
        color = discord.Color.yellow()
    elif (eleccion == "piedra" and bot_eleccion == "tijera") or \
         (eleccion == "papel" and bot_eleccion == "piedra") or \
         (eleccion == "tijera" and bot_eleccion == "papel"):
        resultado = "🏆 ¡Ganaste!"
        color = discord.Color.green()
    else:
        resultado = "😈 ¡Perdiste!"
        color = discord.Color.red()
    embed = discord.Embed(title="🎮 Piedra Papel Tijera", description=resultado, color=color)
    embed.add_field(name="Tu elección", value=emojis[eleccion], inline=True)
    embed.add_field(name="Mi elección", value=emojis[bot_eleccion], inline=True)
    await ctx.send(embed=embed)


# ═════════════════════════════════════════════════════════════
#  🐱 ANIME (hug, pat, slap, kiss, etc.)
# ═════════════════════════════════════════════════════════════

ANIME_ACCIONES = {
    "abrazar":  {"emoji": "🤗", "gif_tag": "hug",    "msg": "{a} abraza a {b} 🤗",               "boton": "Abrazar de vuelta 🤗"},
    "pat":      {"emoji": "👋", "gif_tag": "pat",     "msg": "{a} le da palmaditas a {b} 👋",      "boton": "Dar palmaditas 👋"},
    "slap":     {"emoji": "😤", "gif_tag": "slap",    "msg": "{a} le da una cachetada a {b} 😤",   "boton": "Devolver cachetada 😤"},
    "kiss":     {"emoji": "💋", "gif_tag": "kiss",    "msg": "{a} le da un beso a {b} 💋",         "boton": "Besar de vuelta 💋"},
    "cry":      {"emoji": "😢", "gif_tag": "cry",     "msg": "{a} está llorando 😢",               "boton": "Consolar 🫂"},
    "poke":     {"emoji": "👉", "gif_tag": "poke",    "msg": "{a} le da un toque a {b} 👉",        "boton": "Devolver toque 👉"},
    "cuddle":   {"emoji": "🥰", "gif_tag": "cuddle",  "msg": "{a} acurruca a {b} 🥰",              "boton": "Acurrucarse 🥰"},
    "bite":     {"emoji": "😬", "gif_tag": "bite",    "msg": "{a} muerde a {b} 😬",               "boton": "Morder de vuelta 😬"},
    "wave":     {"emoji": "👋", "gif_tag": "wave",    "msg": "{a} le saluda a {b} 👋",             "boton": "Saludar de vuelta 👋"},
    "dance":    {"emoji": "💃", "gif_tag": "dance",   "msg": "{a} baila con {b} 💃",               "boton": "Bailar juntos 💃"},
}

# Contador de interacciones por pareja
_contadores_anime = {}

def get_contador(uid1: int, uid2: int, accion: str) -> int:
    key = f"{min(uid1,uid2)}-{max(uid1,uid2)}-{accion}"
    _contadores_anime[key] = _contadores_anime.get(key, 0) + 1
    return _contadores_anime[key]

async def obtener_gif_anime(tag: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://nekos.best/api/v2/{tag}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["results"][0]["url"]
    except Exception:
        pass
    return None

class AnimeView(discord.ui.View):
    def __init__(self, autor: discord.Member, target: discord.Member, accion: str, info: dict):
        super().__init__(timeout=60)
        self.autor   = autor
        self.target  = target
        self.accion  = accion
        self.info    = info

        btn_responder = discord.ui.Button(
            label=info["boton"],
            style=discord.ButtonStyle.primary,
            emoji=None
        )
        btn_rechazar = discord.ui.Button(
            label="Rechazar ✖",
            style=discord.ButtonStyle.danger
        )

        async def responder_cb(interaction: discord.Interaction):
            if interaction.user.id != self.target.id:
                return await interaction.response.send_message("❌ Este botón no es para ti.", ephemeral=True)
            contador = get_contador(self.autor.id, self.target.id, self.accion)
            gif = await obtener_gif_anime(self.info["gif_tag"])
            msg_vuelta = self.info["msg"].format(a=self.target.display_name, b=self.autor.display_name)
            embed = discord.Embed(description=msg_vuelta, color=discord.Color.pink())
            embed.set_footer(text=f"{self.autor.display_name} y {self.target.display_name} se han {self.accion}ado {contador} veces.")
            if gif:
                embed.set_image(url=gif)
            await interaction.response.send_message(embed=embed)
            self.stop()

        async def rechazar_cb(interaction: discord.Interaction):
            if interaction.user.id != self.target.id:
                return await interaction.response.send_message("❌ Este botón no es para ti.", ephemeral=True)
            await interaction.response.send_message(
                f"💔 **{self.target.display_name}** rechazó a **{self.autor.display_name}**."
            )
            self.stop()

        btn_responder.callback = responder_cb
        btn_rechazar.callback  = rechazar_cb
        self.add_item(btn_responder)
        self.add_item(btn_rechazar)


def make_anime_cmd(accion: str, info: dict):
    @bot.command(name=accion)
    async def _cmd(ctx, member: discord.Member = None):
        nombre_a = ctx.author.display_name
        nombre_b = member.display_name if member else "todos"
        contador = get_contador(ctx.author.id, member.id if member else 0, accion)
        msg = info["msg"].format(a=nombre_a, b=nombre_b)
        gif = await obtener_gif_anime(info["gif_tag"])
        embed = discord.Embed(description=f"**{msg}**", color=discord.Color.pink())
        if gif:
            embed.set_image(url=gif)
            # Intentar sacar el anime del gif
        if member and member != ctx.author:
            embed.set_footer(text=f"{nombre_a} y {nombre_b} se han {accion}ado {contador} veces.")
            view = AnimeView(ctx.author, member, accion, info)
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)
    _cmd.__name__ = accion
    return _cmd

for _accion, _info in ANIME_ACCIONES.items():
    make_anime_cmd(_accion, _info)



# ═════════════════════════════════════════════════════════════
#  😂 MEMES Y FRASES RANDOM
# ═════════════════════════════════════════════════════════════

FRASES_MOTIVACION = [
    "El éxito no es definitivo, el fracaso no es fatal. — Churchill",
    "Cree en ti mismo y todo lo demás vendrá solo.",
    "Cada día es una nueva oportunidad para cambiar tu vida.",
    "No cuentes los días, haz que los días cuenten. — Ali",
    "El único modo de hacer un gran trabajo es amar lo que haces. — Jobs",
    "La vida es 10% lo que te sucede y 90% cómo reaccionas. — Swindoll",
    "Rodéate de personas que te empujen más alto. — Winfrey",
    "El futuro pertenece a quienes creen en la belleza de sus sueños. — Roosevelt",
    "No esperes oportunidades extraordinarias. Aprovecha las ordinarias.",
    "Sé el cambio que quieres ver en el mundo. — Gandhi",
]

CHISTES = [
    "¿Por qué los pájaros vuelan hacia el sur? Porque caminar es muy lejos 🐦",
    "¿Qué le dijo el 0 al 8? Bonito cinturón 😂",
    "¿Cómo se llama el campeón de buceo de Japón? Tokofondo 🤿",
    "¿Por qué el libro de matemáticas estaba triste? Porque tenía muchos problemas 📚",
    "¿Qué hace una abeja en el gimnasio? ¡Zum-ba! 🐝",
    "¿Cómo llamas a un perro sin patas? No importa, no va a venir 🐶",
    "¿Qué le dijo un techo a otro techo? Nada, los techos no hablan 🏠",
    "¿Por qué los esqueletos no pelean entre sí? No tienen agallas 💀",
]

@bot.command(name="frase", aliases=["motivacion", "quote"])
async def frase_random(ctx):
    """😂 Frase motivacional random."""
    embed = discord.Embed(
        title="💬 Frase del día",
        description=f"*{random.choice(FRASES_MOTIVACION)}*",
        color=discord.Color.teal()
    )
    embed.set_footer(text=f"Para {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="chiste", aliases=["joke"])
async def chiste_random(ctx):
    """😂 Chiste random."""
    embed = discord.Embed(
        title="😂 Chiste",
        description=random.choice(CHISTES),
        color=discord.Color.yellow()
    )
    embed.set_footer(text=f"Para {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command(name="meme")
async def meme_random(ctx):
    """😂 Meme random de Reddit."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://meme-api.com/gimme") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embed = discord.Embed(title=data["title"], color=discord.Color.orange())
                    embed.set_image(url=data["url"])
                    embed.set_footer(text=f"r/{data['subreddit']} | 👍 {data['ups']}")
                    return await ctx.send(embed=embed)
    except Exception:
        pass
    await ctx.send("❌ No pude obtener un meme ahora. Intenta más tarde.")


# ═════════════════════════════════════════════════════════════
#  🎁 SORTEOS Y ENCUESTAS
# ═════════════════════════════════════════════════════════════

sorteos_activos = {}

@bot.command(name="sorteo", aliases=["giveaway"])
@commands.check(es_staff)
async def sorteo(ctx, segundos: int, *, premio: str):
    """🎁 STAFF — Inicia un sorteo. Uso: !sorteo 60 Premio"""
    if segundos < 10 or segundos > 86400:
        return await ctx.send("❌ El tiempo debe ser entre 10 segundos y 24 horas.")
    embed = discord.Embed(
        title="🎁 ¡SORTEO!",
        description=f"**Premio:** {premio}\n\nReacciona con 🎉 para participar!\n\n⏰ Termina en **{segundos}** segundos.",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Organizado por {ctx.author.display_name}")
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")
    sorteos_activos[msg.id] = {"premio": premio, "organizador": ctx.author.display_name}
    await asyncio.sleep(segundos)
    msg = await ctx.channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    participantes = []
    async for user in reaction.users():
        if not user.bot:
            participantes.append(user)
    if not participantes:
        embed_fin = discord.Embed(title="🎁 Sorteo terminado", description="No hubo participantes 😢", color=discord.Color.red())
    else:
        ganador = random.choice(participantes)
        embed_fin = discord.Embed(
            title="🎉 ¡Tenemos ganador!",
            description=f"**Premio:** {premio}\n\n🏆 Ganador: {ganador.mention} ¡Felicidades!",
            color=discord.Color.gold()
        )
    await ctx.send(embed=embed_fin)
    sorteos_activos.pop(msg.id, None)


@bot.command(name="encuesta", aliases=["poll"])
async def encuesta(ctx, *, texto: str):
    """🎁 Crea una encuesta. Uso: !encuesta ¿Pregunta? | op1 | op2 | op3"""
    partes = [p.strip() for p in texto.split("|")]
    if len(partes) < 2:
        return await ctx.send("❌ Formato: `!encuesta ¿Pregunta? | opción1 | opción2`")
    pregunta = partes[0]
    opciones = partes[1:]
    if len(opciones) > 9:
        return await ctx.send("❌ Máximo 9 opciones.")
    numeros = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    desc = "\n".join(f"{numeros[i]} {op}" for i, op in enumerate(opciones))
    embed = discord.Embed(title=f"📊 {pregunta}", description=desc, color=discord.Color.blurple())
    embed.set_footer(text=f"Encuesta de {ctx.author.display_name}")
    msg = await ctx.send(embed=embed)
    for i in range(len(opciones)):
        await msg.add_reaction(numeros[i])


        await msg.add_reaction(numeros[i])


# ═════════════════════════════════════════════════════════════
#  ⚙️ CONFIGURACIÓN DEL BOT (Owner/Admin)
# ═════════════════════════════════════════════════════════════

BOTCONFIG_FILE = "botconfig.json"

def cargar_botconfig() -> dict:
    if os.path.exists(BOTCONFIG_FILE):
        with open(BOTCONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"prefix": PREFIX}

def guardar_botconfig(cfg: dict):
    with open(BOTCONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

@bot.command(name="setprefix", aliases=["prefix", "cambiar_prefijo"])
@commands.check(es_owner_o_admin)
async def setprefix(ctx, nuevo: str):
    """👑 OWNER/ADMIN — Cambia el prefijo. Uso: !setprefix ?"""
    if len(nuevo) > 3:
        return await ctx.send("❌ El prefijo no puede tener más de 3 caracteres.")
    cfg = cargar_botconfig()
    viejo = bot.command_prefix
    cfg["prefix"] = nuevo
    guardar_botconfig(cfg)
    bot.command_prefix = nuevo
    await ctx.send(f"✅ Prefijo cambiado de `{viejo}` a `{nuevo}`")
    log.info(f"Prefijo cambiado a '{nuevo}' por {ctx.author}")


# ═════════════════════════════════════════════════════════════
#  🌐 COMANDOS GENERALES EXTRA
# ═════════════════════════════════════════════════════════════

# ── Estadísticas ──────────────────────────────────────────────

@bot.command(name="stats", aliases=["estadisticas", "estadísticas"])
async def stats(ctx):
    """🌐 Estadísticas del servidor."""
    g = ctx.guild
    total     = g.member_count
    bots      = sum(1 for m in g.members if m.bot)
    humanos   = total - bots
    en_linea  = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
    canales   = len(g.text_channels)
    voz       = len(g.voice_channels)
    roles     = len(g.roles)
    emojis    = len(g.emojis)
    embed = discord.Embed(title=f"📊 Estadísticas — {g.name}", color=discord.Color.blurple())
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="👥 Total miembros", value=total,    inline=True)
    embed.add_field(name="🧑 Humanos",        value=humanos,  inline=True)
    embed.add_field(name="🤖 Bots",           value=bots,     inline=True)
    embed.add_field(name="🟢 En línea",       value=en_linea, inline=True)
    embed.add_field(name="💬 Canales texto",  value=canales,  inline=True)
    embed.add_field(name="🔊 Canales voz",    value=voz,      inline=True)
    embed.add_field(name="🎭 Roles",          value=roles,    inline=True)
    embed.add_field(name="😄 Emojis",         value=emojis,   inline=True)
    embed.add_field(name="📅 Creado",         value=g.created_at.strftime("%d/%m/%Y"), inline=True)
    await ctx.send(embed=embed)


@bot.command(name="botinfo", aliases=["bot_info", "info_bot"])
async def botinfo(ctx):
    """🌐 Info del bot."""
    import platform
    embed = discord.Embed(title="🤖 Info del Bot", color=discord.Color.blurple())
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="🏷️ Nombre",      value=str(bot.user),                   inline=True)
    embed.add_field(name="🆔 ID",           value=bot.user.id,                     inline=True)
    embed.add_field(name="🖥️ Python",       value=platform.python_version(),       inline=True)
    embed.add_field(name="📚 discord.py",   value=discord.__version__,             inline=True)
    embed.add_field(name="🏠 Servidores",   value=len(bot.guilds),                 inline=True)
    embed.add_field(name="👥 Usuarios",     value=len(bot.users),                  inline=True)
    embed.add_field(name="📜 Comandos",     value=len(bot.commands),               inline=True)
    embed.add_field(name="⚙️ Prefijo",      value=f"`{bot.command_prefix}`",       inline=True)
    await ctx.send(embed=embed)


# ── Cumpleaños ────────────────────────────────────────────────

CUMPLE_FILE = "cumpleanos.json"

def cargar_cumples() -> dict:
    if os.path.exists(CUMPLE_FILE):
        with open(CUMPLE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_cumples(data: dict):
    with open(CUMPLE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

@bot.command(name="cumple", aliases=["birthday", "nacimiento"])
async def cumple(ctx, fecha: str = None):
    """🎂 Registra tu cumpleaños. Uso: !cumple DD/MM"""
    if fecha is None:
        cumples = cargar_cumples()
        uid = str(ctx.author.id)
        if uid in cumples:
            return await ctx.send(f"🎂 Tu cumpleaños registrado es el **{cumples[uid]}**. Usa `!cumple DD/MM` para cambiarlo.")
        return await ctx.send("❌ No tienes cumpleaños registrado. Usa `!cumple DD/MM`.")
    try:
        dia, mes = fecha.split("/")
        dia, mes = int(dia), int(mes)
        if not (1 <= dia <= 31 and 1 <= mes <= 12):
            raise ValueError
    except Exception:
        return await ctx.send("❌ Formato inválido. Usa `!cumple DD/MM`. Ej: `!cumple 25/12`")
    cumples = cargar_cumples()
    cumples[str(ctx.author.id)] = f"{dia:02d}/{mes:02d}"
    guardar_cumples(cumples)
    await ctx.send(f"🎂 Cumpleaños registrado: **{dia:02d}/{mes:02d}** ¡Anotado!")

@bot.command(name="cumple_ver", aliases=["ver_cumple", "cumpleaños"])
async def cumple_ver(ctx, member: discord.Member = None):
    """🎂 Ver el cumpleaños de alguien. Uso: !cumple_ver [@usuario]"""
    member = member or ctx.author
    cumples = cargar_cumples()
    uid = str(member.id)
    if uid not in cumples:
        return await ctx.send(f"❌ {member.display_name} no tiene cumpleaños registrado.")
    fecha = cumples[uid]
    dia, mes = map(int, fecha.split("/"))
    hoy = datetime.now(timezone.utc)
    este_anio = datetime(hoy.year, mes, dia, tzinfo=timezone.utc)
    if este_anio < hoy:
        este_anio = datetime(hoy.year + 1, mes, dia, tzinfo=timezone.utc)
    dias_faltan = (este_anio - hoy).days
    embed = discord.Embed(title=f"🎂 Cumpleaños de {member.display_name}", color=discord.Color.gold())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="📅 Fecha", value=fecha, inline=True)
    embed.add_field(name="⏰ Faltan", value=f"**{dias_faltan}** días", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="cumples_lista", aliases=["lista_cumples"])
async def cumples_lista(ctx):
    """🎂 Ver todos los cumpleaños del servidor."""
    cumples = cargar_cumples()
    if not cumples:
        return await ctx.send("❌ Nadie ha registrado su cumpleaños.")
    hoy = datetime.now(timezone.utc)
    lista = []
    for uid, fecha in cumples.items():
        try:
            dia, mes = map(int, fecha.split("/"))
            este = datetime(hoy.year, mes, dia, tzinfo=timezone.utc)
            if este < hoy:
                este = datetime(hoy.year + 1, mes, dia, tzinfo=timezone.utc)
            dias = (este - hoy).days
            lista.append((dias, uid, fecha))
        except Exception:
            pass
    lista.sort()
    embed = discord.Embed(title="🎂 Próximos Cumpleaños", color=discord.Color.gold())
    for dias, uid, fecha in lista[:10]:
        try:
            member = ctx.guild.get_member(int(uid))
            nombre = member.display_name if member else f"<@{uid}>"
        except Exception:
            nombre = f"<@{uid}>"
        embed.add_field(name=f"🎉 {nombre}", value=f"**{fecha}** — en {dias} días", inline=False)
    await ctx.send(embed=embed)


# ── Recordatorios ─────────────────────────────────────────────

@bot.command(name="recordar", aliases=["remind", "reminder"])
async def recordar(ctx, tiempo: str, *, mensaje: str):
    """⏰ Recordatorio personal. Uso: !recordar 10m Ir al gym
    Unidades: s=segundos, m=minutos, h=horas"""
    unidades = {"s": 1, "m": 60, "h": 3600}
    try:
        unidad = tiempo[-1].lower()
        cantidad = int(tiempo[:-1])
        if unidad not in unidades or cantidad < 1 or cantidad > 86400:
            raise ValueError
    except Exception:
        return await ctx.send("❌ Formato inválido. Ej: `!recordar 10m Ir al gym` (s/m/h, máx 24h)")
    segundos = cantidad * unidades[unidad]
    nombres = {"s": "segundo(s)", "m": "minuto(s)", "h": "hora(s)"}
    await ctx.send(f"⏰ Te recordaré en **{cantidad} {nombres[unidad]}**: *{mensaje}*")
    await asyncio.sleep(segundos)
    try:
        embed = discord.Embed(
            title="⏰ ¡Recordatorio!",
            description=mensaje,
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
        await ctx.author.send(embed=embed)
        await ctx.send(f"⏰ {ctx.author.mention} ¡Tu recordatorio! **{mensaje}**")
    except Exception:
        await ctx.send(f"⏰ {ctx.author.mention} ¡Tu recordatorio! **{mensaje}**")


# ── Invitación y avatar ───────────────────────────────────────

@bot.command(name="invitar", aliases=["invite", "invitacion"])
async def invitar(ctx):
    """🔗 Link de invitación del bot."""
    url = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot"
    embed = discord.Embed(title="🔗 Invitar el Bot", description=f"[Haz click aquí para invitarme]({url})", color=discord.Color.blurple())
    await ctx.send(embed=embed)

@bot.command(name="avatar", aliases=["av", "foto"])
async def avatar(ctx, member: discord.Member = None):
    """🖼️ Ver el avatar de alguien. Uso: !avatar [@usuario]"""
    member = member or ctx.author
    embed = discord.Embed(title=f"🖼️ Avatar de {member.display_name}", color=member.color)
    embed.set_image(url=member.display_avatar.url)
    embed.add_field(name="🔗 Link", value=f"[Descargar]({member.display_avatar.url})", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="banner")
async def banner(ctx, member: discord.Member = None):
    """🖼️ Ver el banner de alguien. Uso: !banner [@usuario]"""
    member = member or ctx.author
    user = await bot.fetch_user(member.id)
    if not user.banner:
        return await ctx.send(f"❌ {member.display_name} no tiene banner.")
    embed = discord.Embed(title=f"🖼️ Banner de {member.display_name}", color=member.color)
    embed.set_image(url=user.banner.url)
    await ctx.send(embed=embed)

@bot.command(name="ping")
async def ping(ctx):
    """🏓 Latencia del bot."""
    latencia = round(bot.latency * 1000)
    color = discord.Color.green() if latencia < 100 else discord.Color.yellow() if latencia < 200 else discord.Color.red()
    embed = discord.Embed(title="🏓 Pong!", description=f"Latencia: **{latencia}ms**", color=color)
    await ctx.send(embed=embed)

@bot.command(name="clima", aliases=["weather", "tiempo"])
async def clima(ctx, *, ciudad: str):
    """🌤️ Clima de una ciudad. Uso: !clima Madrid"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://wttr.in/{ciudad.replace(' ', '+')}?format=j1"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await ctx.send("❌ Ciudad no encontrada.")
                data = await resp.json()
                actual = data["current_condition"][0]
                temp_c  = actual["temp_C"]
                sensa   = actual["FeelsLikeC"]
                humedad = actual["humidity"]
                desc    = actual["weatherDesc"][0]["value"]
                viento  = actual["windspeedKmph"]
                embed = discord.Embed(title=f"🌤️ Clima en {ciudad.title()}", color=discord.Color.blue())
                embed.add_field(name="🌡️ Temperatura", value=f"{temp_c}°C", inline=True)
                embed.add_field(name="🤔 Sensación",   value=f"{sensa}°C",  inline=True)
                embed.add_field(name="💧 Humedad",     value=f"{humedad}%", inline=True)
                embed.add_field(name="💨 Viento",      value=f"{viento} km/h", inline=True)
                embed.add_field(name="☁️ Descripción", value=desc,          inline=True)
                embed.set_footer(text="Datos de wttr.in")
                await ctx.send(embed=embed)
    except Exception:
        await ctx.send("❌ No pude obtener el clima. Intenta de nuevo.")

@bot.command(name="traducir", aliases=["translate", "tr"])
async def traducir(ctx, idioma: str, *, texto: str):
    """🌍 Traduce texto. Uso: !tr en Hola mundo"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.mymemory.translated.net/get?q={texto}&langpair=es|{idioma}"
            async with session.get(url) as resp:
                data = await resp.json()
                traduccion = data["responseData"]["translatedText"]
                embed = discord.Embed(title="🌍 Traducción", color=discord.Color.teal())
                embed.add_field(name="📝 Original",    value=texto,       inline=False)
                embed.add_field(name="✅ Traducido",   value=traduccion,  inline=False)
                embed.add_field(name="🌐 Idioma",      value=idioma,      inline=True)
                await ctx.send(embed=embed)
    except Exception:
        await ctx.send("❌ No pude traducir. Usa códigos como `en`, `pt`, `fr`, `de`, `ja`.")

@bot.command(name="calcular", aliases=["calc", "matematica"])
async def calcular(ctx, *, expresion: str):
    """🧮 Calculadora. Uso: !calc 2+2*5"""
    try:
        permitidos = set("0123456789+-*/.() ")
        if not all(c in permitidos for c in expresion):
            return await ctx.send("❌ Solo se permiten números y operadores `+ - * / ( )`.")
        resultado = eval(expresion)
        embed = discord.Embed(title="🧮 Calculadora", color=discord.Color.green())
        embed.add_field(name="📝 Expresión", value=f"`{expresion}`",  inline=False)
        embed.add_field(name="✅ Resultado", value=f"**{resultado}**", inline=False)
        await ctx.send(embed=embed)
    except ZeroDivisionError:
        await ctx.send("❌ No se puede dividir entre cero.")
    except Exception:
        await ctx.send("❌ Expresión inválida.")

@bot.command(name="color")
async def color_cmd(ctx, *, hex_color: str):
    """🎨 Info de un color hex. Uso: !color #FF0000"""
    hex_color = hex_color.strip("#")
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except Exception:
        return await ctx.send("❌ Color inválido. Usa formato hex: `!color FF0000`")
    color_int = int(hex_color, 16)
    embed = discord.Embed(title=f"🎨 Color #{hex_color.upper()}", color=color_int)
    embed.add_field(name="🔴 R", value=r, inline=True)
    embed.add_field(name="🟢 G", value=g, inline=True)
    embed.add_field(name="🔵 B", value=b, inline=True)
    embed.add_field(name="🔢 Decimal", value=color_int, inline=True)
    embed.set_thumbnail(url=f"https://singlecolorimage.com/get/{hex_color}/100x100")
    await ctx.send(embed=embed)

@bot.command(name="sugerencia", aliases=["suggest"])
async def sugerencia(ctx, canal: discord.TextChannel = None, *, texto: str):
    """💡 Envía una sugerencia. Uso: !sugerencia [#canal] texto"""
    canal = canal or ctx.channel
    embed = discord.Embed(
        title="💡 Nueva Sugerencia",
        description=texto,
        color=discord.Color.yellow(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    embed.set_footer(text=f"ID: {ctx.author.id}")
    msg = await canal.send(embed=embed)
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")
    if canal != ctx.channel:
        await ctx.send(f"✅ Sugerencia enviada en {canal.mention}.")

@bot.command(name="reporte", aliases=["report"])
async def reporte(ctx, member: discord.Member, *, razon: str):
    """🚨 Reporta a un usuario. Uso: !reporte @usuario razón"""
    if member == ctx.author:
        return await ctx.send("❌ No puedes reportarte a ti mismo.")
    embed = discord.Embed(
        title="🚨 Nuevo Reporte",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 Reportado",  value=f"{member.mention} (`{member.id}`)", inline=False)
    embed.add_field(name="📋 Razón",      value=razon,                               inline=False)
    embed.add_field(name="📩 Reportado por", value=ctx.author.mention,               inline=False)
    embed.add_field(name="📍 Canal",      value=ctx.channel.mention,                 inline=False)
    # Buscar canal de logs del antinuke o enviar al canal actual
    cfg = cargar_antinuke()
    log_ch_id = cfg.get("log_channel")
    canal_destino = ctx.guild.get_channel(int(log_ch_id)) if log_ch_id else ctx.channel
    await canal_destino.send(embed=embed)
    await ctx.message.delete()
    await ctx.author.send(f"✅ Tu reporte sobre **{member.display_name}** fue enviado.")

@bot.command(name="dado_personalizado", aliases=["dp"])
async def dado_personalizado(ctx, cantidad: int = 1, lados: int = 6):
    """🎲 Tira múltiples dados. Uso: !dp 3 6 (3 dados de 6 lados)"""
    if cantidad < 1 or cantidad > 20:
        return await ctx.send("❌ Entre 1 y 20 dados.")
    if lados < 2 or lados > 1000:
        return await ctx.send("❌ Entre 2 y 1000 lados.")
    resultados = [random.randint(1, lados) for _ in range(cantidad)]
    total = sum(resultados)
    embed = discord.Embed(title=f"🎲 {cantidad}d{lados}", color=discord.Color.blurple())
    embed.add_field(name="Resultados", value=" + ".join(f"`{r}`" for r in resultados), inline=False)
    embed.add_field(name="Total", value=f"**{total}**", inline=True)
    if cantidad > 1:
        embed.add_field(name="Promedio", value=f"**{total/cantidad:.1f}**", inline=True)
    await ctx.send(embed=embed)


# ─────────────────────────────────────────────────────────────
#  INICIO CON RECONEXIÓN AUTOMÁTICA
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    while True:
        try:
            log.info("Iniciando bot...")
            bot.run(TOKEN, reconnect=True)
        except discord.LoginFailure:
            log.critical("TOKEN INVÁLIDO — revisa el token en config.json")
            sys.exit(1)
        except KeyboardInterrupt:
            log.info("Bot detenido manualmente.")
            sys.exit(0)
        except Exception:
            log.error(f"Error inesperado:\n{traceback.format_exc()}")
            log.info("Reiniciando en 5 segundos...")
            time.sleep(5)
