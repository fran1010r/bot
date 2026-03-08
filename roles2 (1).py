import asyncio
import discord
from discord.ext import commands
import json
import os
import sys
import time
import traceback
import logging

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
    # El token puede venir de variable de entorno (Railway) o del config.json
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
#  BASE DE DATOS (puntos.json)
# ─────────────────────────────────────────────────────────────
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
