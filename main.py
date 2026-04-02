import json
import os
import asyncio
import io
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
GUILD_CONFIG_FILE = "guild_config.json"

# Legge il token prima dalla variabile d'ambiente (Railway),
# poi dal config.json locale (PC di casa)
TOKEN = os.environ.get("TOKEN")

if not TOKEN:
    CONFIG_FILE = "config.json"
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            main_config = json.load(f)
        TOKEN = main_config.get("token")

if not TOKEN:
    raise ValueError("Token non trovato! Imposta la variabile TOKEN su Railway oppure crea config.json.")

# Colore azzurro AtlatiMC
ATLATI_BLUE = 0x00BFFF   # DeepSkyBlue
SERVER_NAME = "AtlatiMC"

# ─────────────────────────────────────────────
#  GUILD CONFIG  (load / save / get)
# ─────────────────────────────────────────────
def load_guild_config():
    if not os.path.exists(GUILD_CONFIG_FILE):
        return {}
    with open(GUILD_CONFIG_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            backup = GUILD_CONFIG_FILE + ".backup"
            if os.path.exists(backup):
                print("⚠️  Config corrotto, carico backup...")
                with open(backup, "r", encoding="utf-8") as bf:
                    return json.load(bf)
            return {}

def save_guild_config(data: dict):
    if os.path.exists(GUILD_CONFIG_FILE):
        backup = GUILD_CONFIG_FILE + ".backup"
        try:
            with open(GUILD_CONFIG_FILE, "r", encoding="utf-8") as f:
                old = f.read()
            with open(backup, "w", encoding="utf-8") as bf:
                bf.write(old)
        except Exception:
            pass
    with open(GUILD_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"💾 Config salvata.")

guild_config = load_guild_config()

def get_guild_entry(guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in guild_config:
        guild_config[gid] = {
            # Benvenuto
            "welcome_channel_id":    None,
            "welcome_role_id":       None,

            # Ticket
            "ticket_panel_channel":         None,
            "ticket_logs_channel_id":       None,
            "ticket_transcript_channel_id": None,
            "ticket_support_category":      None,
            "ticket_report_category":       None,
            "ticket_bug_category":          None,
            "ticket_ban_category":          None,
            "ticket_candidature_category":  None,
            "ticket_partnership_category":  None,
            "staff_role_id":                None,
        }
        save_guild_config(guild_config)
    return guild_config[gid]

# ─────────────────────────────────────────────
#  UTILITY
# ─────────────────────────────────────────────
def is_ticket_channel(ch) -> bool:
    return isinstance(ch, discord.TextChannel) and ch.name.startswith("ticket-")

def is_staff_member(member: discord.Member, data: dict) -> bool:
    staff_role_id = data.get("staff_role_id")
    return bool(staff_role_id and staff_role_id in [r.id for r in member.roles])

def sanitize_channel_name(name: str) -> str:
    name = name.strip().lower().replace(" ", "-")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    cleaned = "".join(c for c in name if c in allowed).strip("-_")
    return cleaned[:90] if cleaned else "ticket"

async def generate_transcript(channel: discord.TextChannel) -> io.BytesIO:
    buf = io.StringIO()
    buf.write("=" * 60 + "\n")
    buf.write(f"TRANSCRIPT TICKET: {channel.name}\n")
    buf.write(f"Server: {channel.guild.name}\n")
    buf.write(f"Data chiusura: {datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S')} UTC\n")
    buf.write("=" * 60 + "\n\n")

    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(msg)

    for msg in messages:
        ts     = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
        author = msg.author.name if msg.author.discriminator == "0" else f"{msg.author.name}#{msg.author.discriminator}"
        buf.write(f"[{ts}] {author}:\n")
        if msg.content:
            buf.write(f"{msg.content}\n")
        if msg.embeds:
            for e in msg.embeds:
                buf.write("--- EMBED ---\n")
                if e.title:       buf.write(f"Titolo: {e.title}\n")
                if e.description: buf.write(f"Desc: {e.description}\n")
                for field in e.fields:
                    buf.write(f"{field.name}: {field.value}\n")
                buf.write("--- FINE EMBED ---\n")
        if msg.attachments:
            for att in msg.attachments:
                buf.write(f"  [allegato] {att.filename} → {att.url}\n")
        buf.write("\n")

    buf.write("=" * 60 + "\nFINE TRANSCRIPT\n" + "=" * 60 + "\n")
    out = io.BytesIO(buf.getvalue().encode("utf-8"))
    out.seek(0)
    return out

# ─────────────────────────────────────────────
#  BOT
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.members         = True
intents.guilds          = True
intents.messages        = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ─────────────────────────────────────────────
#  ON READY
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Loggato come {bot.user} (ID: {bot.user.id})")
    try:
        await bot.tree.sync()
        print("🌐 Slash commands sincronizzati.")
    except Exception as e:
        print(f"Errore sync: {e}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{SERVER_NAME} 🌐"
        )
    )

# ═══════════════════════════════════════════════════════════════
#  SISTEMA DI BENVENUTO
# ═══════════════════════════════════════════════════════════════
@bot.event
async def on_member_join(member: discord.Member):
    data = get_guild_entry(member.guild.id)

    # — Ruolo automatico al join —
    role_id = data.get("welcome_role_id")
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role)
                print(f"✅ Ruolo '{role.name}' assegnato a {member.name}")
            except Exception as e:
                print(f"❌ Errore assegnando ruolo: {e}")

    # — Messaggio di benvenuto —
    welcome_ch_id = data.get("welcome_channel_id")
    if not welcome_ch_id:
        return

    channel = member.guild.get_channel(welcome_ch_id)
    if not channel:
        return

    embed = discord.Embed(
        title=f"👋 Benvenuto su {SERVER_NAME}!",
        description=(
            f"Ciao {member.mention}, siamo felici di averti con noi! 🎉\n\n"
            f"🌐 **Server:** {member.guild.name}\n"
            f"👥 **Membro numero:** `{member.guild.member_count}`\n\n"
            "📖 Leggi le **regole** e buon divertimento!\n"
            "🎫 Per assistenza apri un **ticket**."
        ),
        color=ATLATI_BLUE,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} • Sistema Benvenuto", icon_url=member.guild.icon.url if member.guild.icon else None)

    await channel.send(content=member.mention, embed=embed)

# — Setup canale benvenuto —
@bot.tree.command(name="setup-welcome", description="Imposta il canale di benvenuto.")
@app_commands.describe(canale="Canale dove inviare il messaggio di benvenuto")
async def setup_welcome(interaction: discord.Interaction, canale: discord.TextChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["welcome_channel_id"] = canale.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Canale benvenuto impostato su {canale.mention}", ephemeral=True)

# — Setup ruolo automatico —
@bot.tree.command(name="setup-welcome-role", description="Imposta il ruolo da assegnare automaticamente ai nuovi membri.")
@app_commands.describe(ruolo="Ruolo da assegnare al join")
async def setup_welcome_role(interaction: discord.Interaction, ruolo: discord.Role):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["welcome_role_id"] = ruolo.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Ruolo automatico impostato su **{ruolo.name}**", ephemeral=True)

# — Test benvenuto manuale —
@bot.tree.command(name="test-welcome", description="Testa il messaggio di benvenuto (solo admin).")
async def test_welcome(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)

    # Simula on_member_join con l'utente che esegue il comando
    member = interaction.user
    data = get_guild_entry(interaction.guild_id)
    welcome_ch_id = data.get("welcome_channel_id")

    if not welcome_ch_id:
        return await interaction.response.send_message("❌ Canale benvenuto non configurato. Usa `/setup-welcome`.", ephemeral=True)

    channel = interaction.guild.get_channel(welcome_ch_id)
    if not channel:
        return await interaction.response.send_message("❌ Canale non trovato.", ephemeral=True)

    embed = discord.Embed(
        title=f"👋 Benvenuto su {SERVER_NAME}!",
        description=(
            f"Ciao {member.mention}, siamo felici di averti con noi! 🎉\n\n"
            f"🌐 **Server:** {interaction.guild.name}\n"
            f"👥 **Membro numero:** `{interaction.guild.member_count}`\n\n"
            "📖 Leggi le **regole** e buon divertimento!\n"
            "🎫 Per assistenza apri un **ticket**."
        ),
        color=ATLATI_BLUE,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{SERVER_NAME} • Sistema Benvenuto", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

    await channel.send(content=f"🔧 *[TEST]* {member.mention}", embed=embed)
    await interaction.response.send_message(f"✅ Test benvenuto inviato in {channel.mention}", ephemeral=True)

# ═══════════════════════════════════════════════════════════════
#  SISTEMA TICKET  –  Views / Modals
# ═══════════════════════════════════════════════════════════════

class ConfirmCloseView(discord.ui.View):
    def __init__(self, original_user: discord.Member):
        super().__init__(timeout=60)
        self.original_user = original_user
        self.value = None

    @discord.ui.button(label="✅ Conferma", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_user.id:
            return await interaction.response.send_message("❌ Solo chi ha richiesto la chiusura può confermare.", ephemeral=True)
        self.value = True
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="✅ **Chiusura confermata!** Generazione transcript...", view=self)

    @discord.ui.button(label="❌ Annulla", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_user.id:
            return await interaction.response.send_message("❌ Solo chi ha richiesto la chiusura può annullare.", ephemeral=True)
        self.value = False
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ **Chiusura annullata.** Il ticket rimane aperto.", view=self)

    async def on_timeout(self):
        self.value = False
        self.stop()


class TicketControlView(discord.ui.View):
    def __init__(self, opener: discord.Member):
        super().__init__(timeout=None)
        self.opener      = opener
        self.claimed_by  = None

    @discord.ui.button(label="👮 Claim", style=discord.ButtonStyle.primary)
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = get_guild_entry(interaction.guild.id)
        if not is_staff_member(interaction.user, data):
            return await interaction.response.send_message("❌ Solo lo **staff** può claimare il ticket.", ephemeral=True)
        if self.claimed_by:
            return await interaction.response.send_message(f"⚠️ Già claimato da {self.claimed_by.mention}", ephemeral=True)
        self.claimed_by = interaction.user
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"👮 **Ticket claimato da:** {interaction.user.mention}")

    @discord.ui.button(label="🔒 Chiudi", style=discord.ButtonStyle.red)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = get_guild_entry(interaction.guild.id)
        if not is_staff_member(interaction.user, data):
            return await interaction.response.send_message("❌ Solo lo **staff** può chiudere il ticket.", ephemeral=True)
        await _do_close_ticket(interaction)


async def _do_close_ticket(interaction: discord.Interaction):
    """Logica condivisa di chiusura ticket."""
    data = get_guild_entry(interaction.guild.id)

    embed = discord.Embed(
        title="⚠️ Conferma Chiusura Ticket",
        description=(
            f"**{interaction.user.mention}**, sei sicuro di voler chiudere questo ticket?\n\n"
            "🔹 Verrà generato un transcript completo\n"
            "🔹 Il canale verrà eliminato definitivamente\n\n"
            "**Premi un pulsante per confermare o annullare:**"
        ),
        color=discord.Color.orange()
    )
    confirm_view = ConfirmCloseView(interaction.user)
    await interaction.response.send_message(embed=embed, view=confirm_view)
    await confirm_view.wait()

    if not confirm_view.value:
        return

    channel = interaction.channel

    # Transcript
    transcript_ch_id = data.get("ticket_transcript_channel_id")
    if transcript_ch_id:
        tch = interaction.guild.get_channel(transcript_ch_id)
        if tch:
            try:
                file_bytes = await generate_transcript(channel)
                filename   = f"transcript-{channel.name}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
                t_embed = discord.Embed(
                    title="📄 Transcript Ticket",
                    description=f"**Ticket:** {channel.name}\n**Chiuso da:** {interaction.user.mention}",
                    color=ATLATI_BLUE,
                    timestamp=discord.utils.utcnow()
                )
                await tch.send(embed=t_embed, file=discord.File(file_bytes, filename=filename))
            except Exception as e:
                print(f"❌ Errore transcript: {e}")

    # Log
    log_id = data.get("ticket_logs_channel_id")
    if log_id:
        lch = interaction.guild.get_channel(log_id)
        if lch:
            await lch.send(f"🔒 Ticket `{channel.name}` chiuso da {interaction.user.mention}")

    await asyncio.sleep(5)
    await channel.delete(reason=f"Ticket chiuso da {interaction.user}")


# — Modali —
class BaseTicketModal(discord.ui.Modal):
    def __init__(self, categoria: str, title: str):
        super().__init__(title=title)
        self.categoria = categoria
        self.add_item(discord.ui.TextInput(label="Il tuo nickname", style=discord.TextStyle.short, required=True))

    async def on_submit(self, interaction: discord.Interaction):
        nickname       = self.children[0].value
        extra          = "\n".join(f"**{c.label}:** {c.value}" for c in self.children[1:])
        await create_ticket(interaction, self.categoria, nickname, extra)


class SupportoModal(BaseTicketModal):
    def __init__(self):
        super().__init__("supporto", "🎫 Ticket Supporto")
        self.add_item(discord.ui.TextInput(label="Descrivi il tuo problema", style=discord.TextStyle.paragraph, required=True))

class ReportModal(BaseTicketModal):
    def __init__(self):
        super().__init__("report", "🚨 Ticket Report Player")
        self.add_item(discord.ui.TextInput(label="Nickname da reportare", style=discord.TextStyle.short, required=True))
        self.add_item(discord.ui.TextInput(label="Prove (link imgur / screenshot)", style=discord.TextStyle.short, required=True))
        self.add_item(discord.ui.TextInput(label="Motivazione del report", style=discord.TextStyle.paragraph, required=True))

class BugModal(BaseTicketModal):
    def __init__(self):
        super().__init__("bug", "🐛 Ticket Bug")
        self.add_item(discord.ui.TextInput(label="Descrivi il bug", style=discord.TextStyle.paragraph, required=True))

class BanModal(BaseTicketModal):
    def __init__(self):
        super().__init__("ban", "🔨 Ticket Appello Ban")
        self.add_item(discord.ui.TextInput(label="Motivazione del ban (se conosci)", style=discord.TextStyle.paragraph, required=True))
        self.add_item(discord.ui.TextInput(label="Perché dovresti essere sbannato?", style=discord.TextStyle.paragraph, required=True))

class CandidaturaModal(BaseTicketModal):
    def __init__(self):
        super().__init__("candidatura", "📋 Ticket Candidatura Staff")
        self.add_item(discord.ui.TextInput(label="Ruolo a cui ti candidi (es. Helper)", style=discord.TextStyle.short, required=True))
        self.add_item(discord.ui.TextInput(label="Quante ore al giorno puoi dedicare?", style=discord.TextStyle.short, required=True))
        self.add_item(discord.ui.TextInput(label="Perché vuoi entrare nello staff?", style=discord.TextStyle.paragraph, required=True))

class AltroModal(BaseTicketModal):
    def __init__(self):
        super().__init__("altro", "❓ Ticket Altro")
        self.add_item(discord.ui.TextInput(label="Spiegaci il problema", style=discord.TextStyle.paragraph, required=True))


async def create_ticket(interaction: discord.Interaction, categoria: str, nickname: str, extra: str):
    guild  = interaction.guild
    utente = interaction.user
    data   = get_guild_entry(guild.id)

    safe_nick    = sanitize_channel_name(utente.nick or utente.name)
    channel_name = f"ticket-{categoria}-{safe_nick}"

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        utente: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }

    staff_role = None
    staff_role_id = data.get("staff_role_id")
    if staff_role_id:
        staff_role = guild.get_role(staff_role_id)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    category_map = {
        "supporto":    data.get("ticket_support_category"),
        "report":      data.get("ticket_report_category"),
        "bug":         data.get("ticket_bug_category") or data.get("ticket_report_category"),
        "ban":         data.get("ticket_ban_category")  or data.get("ticket_support_category"),
        "candidatura": data.get("ticket_candidature_category"),
        "altro":       data.get("ticket_support_category"),
    }
    cat_id   = category_map.get(categoria)
    category = guild.get_channel(cat_id) if cat_id else None

    ticket_ch = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        reason=f"Ticket {categoria} aperto da {utente}"
    )

    embed = discord.Embed(
        title="🎫 Ticket Aperto",
        description=(
            f"👤 **Utente:** {utente.mention}\n"
            f"🏷️ **Nickname:** {nickname}\n"
            f"📂 **Categoria:** {categoria.capitalize()}\n\n"
            f"{extra}\n\n"
            "⏳ Uno staffer ti risponderà al più presto.\n"
            "🔒 Usa il pulsante **Chiudi** per chiudere il ticket."
        ),
        color=ATLATI_BLUE,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"{SERVER_NAME} • Sistema Ticket")

    mention_content = utente.mention + (f" | {staff_role.mention}" if staff_role else "")
    await ticket_ch.send(content=mention_content, embed=embed, view=TicketControlView(utente))
    await interaction.response.send_message(f"✅ Ticket creato: {ticket_ch.mention}", ephemeral=True)

    log_id = data.get("ticket_logs_channel_id")
    if log_id:
        lch = guild.get_channel(log_id)
        if lch:
            await lch.send(f"🆕 **Nuovo ticket** ({categoria}) → {ticket_ch.mention} | {utente.mention}")


# — Ticket Panel (Select Menu) —
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Supporto",          emoji="🎫", value="supporto",    description="Hai bisogno di aiuto?"),
            discord.SelectOption(label="Report Player",     emoji="🚨", value="report",      description="Segnala un giocatore"),
            discord.SelectOption(label="Bug",               emoji="🐛", value="bug",         description="Hai trovato un bug?"),
            discord.SelectOption(label="Appello Ban",       emoji="🔨", value="ban",         description="Sei stato bannato ingiustamente?"),
            discord.SelectOption(label="Candidatura Staff", emoji="📋", value="candidatura", description="Vuoi entrare nello staff?"),
            discord.SelectOption(label="Altro",             emoji="❓", value="altro",       description="Qualcos'altro"),
        ]
        super().__init__(placeholder="📩 Seleziona il motivo del ticket…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        modal_map = {
            "supporto":    SupportoModal,
            "report":      ReportModal,
            "bug":         BugModal,
            "ban":         BanModal,
            "candidatura": CandidaturaModal,
            "altro":       AltroModal,
        }
        modal_cls = modal_map.get(self.values[0])
        if modal_cls:
            await interaction.response.send_modal(modal_cls())


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ═══════════════════════════════════════════════════════════════
#  SLASH COMMANDS – SETUP TICKET
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="setup-ticket-panel", description="Invia il panel ticket nel canale corrente.")
async def setup_ticket_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)

    data = get_guild_entry(interaction.guild_id)
    data["ticket_panel_channel"] = interaction.channel_id
    save_guild_config(guild_config)

    embed = discord.Embed(
        title=f"🎫 Supporto {SERVER_NAME}",
        description=(
            "Hai bisogno di aiuto? Seleziona una categoria dal menu qui sotto\n"
            "e apri un ticket. Il nostro staff ti risponderà il prima possibile!\n\n"
            "🎫 Supporto generale\n"
            "🚨 Report player\n"
            "🐛 Segnalazione bug\n"
            "🔨 Appello ban\n"
            "📋 Candidatura staff\n"
            "❓ Altro"
        ),
        color=ATLATI_BLUE
    )
    embed.set_footer(text=f"{SERVER_NAME} • Sistema Ticket")
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("✅ Panel ticket inviato!", ephemeral=True)


@bot.tree.command(name="setup-staff-role", description="Imposta il ruolo staff.")
@app_commands.describe(ruolo="Ruolo staff")
async def setup_staff_role(interaction: discord.Interaction, ruolo: discord.Role):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["staff_role_id"] = ruolo.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Ruolo staff impostato: **{ruolo.name}**", ephemeral=True)


@bot.tree.command(name="setup-ticket-logs", description="Imposta il canale log ticket.")
@app_commands.describe(canale="Canale log")
async def setup_ticket_logs(interaction: discord.Interaction, canale: discord.TextChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["ticket_logs_channel_id"] = canale.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Log ticket impostato: {canale.mention}", ephemeral=True)


@bot.tree.command(name="setup-ticket-transcript", description="Imposta il canale per i transcript.")
@app_commands.describe(canale="Canale transcript")
async def setup_ticket_transcript(interaction: discord.Interaction, canale: discord.TextChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["ticket_transcript_channel_id"] = canale.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Canale transcript impostato: {canale.mention}", ephemeral=True)


@bot.tree.command(name="setup-ticket-supporto", description="Imposta la categoria per i ticket di supporto.")
@app_commands.describe(categoria="Categoria Discord")
async def setup_ticket_supporto(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["ticket_support_category"] = categoria.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Categoria supporto: **{categoria.name}**", ephemeral=True)


@bot.tree.command(name="setup-ticket-report", description="Imposta la categoria per i ticket report.")
@app_commands.describe(categoria="Categoria Discord")
async def setup_ticket_report(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["ticket_report_category"] = categoria.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Categoria report: **{categoria.name}**", ephemeral=True)


@bot.tree.command(name="setup-ticket-bug", description="Imposta la categoria per i ticket bug.")
@app_commands.describe(categoria="Categoria Discord")
async def setup_ticket_bug(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["ticket_bug_category"] = categoria.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Categoria bug: **{categoria.name}**", ephemeral=True)


@bot.tree.command(name="setup-ticket-ban", description="Imposta la categoria per gli appelli ban.")
@app_commands.describe(categoria="Categoria Discord")
async def setup_ticket_ban(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["ticket_ban_category"] = categoria.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Categoria ban: **{categoria.name}**", ephemeral=True)


@bot.tree.command(name="setup-ticket-candidature", description="Imposta la categoria per le candidature staff.")
@app_commands.describe(categoria="Categoria Discord")
async def setup_ticket_candidature(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)
    data = get_guild_entry(interaction.guild_id)
    data["ticket_candidature_category"] = categoria.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Categoria candidature: **{categoria.name}**", ephemeral=True)


# ═══════════════════════════════════════════════════════════════
#  SLASH COMMANDS – GESTIONE TICKET (staff)
# ═══════════════════════════════════════════════════════════════

@bot.tree.command(name="chiudi", description="Chiude il ticket attuale.")
async def chiudi(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Solo server.", ephemeral=True)
    data = get_guild_entry(interaction.guild.id)
    if not is_staff_member(interaction.user, data):
        return await interaction.response.send_message("❌ Solo lo **staff** può chiudere i ticket.", ephemeral=True)
    if not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("❌ Usa questo comando solo in un canale ticket.", ephemeral=True)
    await _do_close_ticket(interaction)


@bot.tree.command(name="claim", description="Claima il ticket (solo staff).")
async def claim_cmd(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Solo server.", ephemeral=True)
    data = get_guild_entry(interaction.guild.id)
    if not is_staff_member(interaction.user, data):
        return await interaction.response.send_message("❌ Solo staff.", ephemeral=True)
    if not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("❌ Solo nei ticket.", ephemeral=True)
    await interaction.channel.send(f"👮 **Ticket claimato da:** {interaction.user.mention}")
    await interaction.response.send_message("✅ Claim effettuato.", ephemeral=True)


@bot.tree.command(name="add", description="Aggiunge un utente al ticket.")
@app_commands.describe(utente="Utente da aggiungere")
async def add_user(interaction: discord.Interaction, utente: discord.Member):
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Solo server.", ephemeral=True)
    data = get_guild_entry(interaction.guild.id)
    if not is_staff_member(interaction.user, data):
        return await interaction.response.send_message("❌ Solo staff.", ephemeral=True)
    if not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("❌ Solo nei ticket.", ephemeral=True)
    await interaction.channel.set_permissions(utente, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"✅ Aggiunto {utente.mention}", ephemeral=True)
    await interaction.channel.send(f"➕ **Aggiunto al ticket:** {utente.mention} (da {interaction.user.mention})")


@bot.tree.command(name="remove", description="Rimuove un utente dal ticket.")
@app_commands.describe(utente="Utente da rimuovere")
async def remove_user(interaction: discord.Interaction, utente: discord.Member):
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Solo server.", ephemeral=True)
    data = get_guild_entry(interaction.guild.id)
    if not is_staff_member(interaction.user, data):
        return await interaction.response.send_message("❌ Solo staff.", ephemeral=True)
    if not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("❌ Solo nei ticket.", ephemeral=True)
    await interaction.channel.set_permissions(utente, overwrite=None)
    await interaction.response.send_message(f"✅ Rimosso {utente.mention}", ephemeral=True)
    await interaction.channel.send(f"➖ **Rimosso dal ticket:** {utente.mention} (da {interaction.user.mention})")


@bot.tree.command(name="assegna", description="Assegna il ticket a un membro dello staff.")
@app_commands.describe(utente="Membro staff")
async def assegna(interaction: discord.Interaction, utente: discord.Member):
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Solo server.", ephemeral=True)
    data = get_guild_entry(interaction.guild.id)
    if not is_staff_member(interaction.user, data):
        return await interaction.response.send_message("❌ Solo staff.", ephemeral=True)
    if not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("❌ Solo nei ticket.", ephemeral=True)
    await interaction.channel.set_permissions(utente, view_channel=True, send_messages=True, read_message_history=True)
    data["ticket_assigned_to_id"] = utente.id
    save_guild_config(guild_config)
    await interaction.response.send_message(f"✅ Ticket assegnato a {utente.mention}", ephemeral=True)
    await interaction.channel.send(f"📌 **Ticket assegnato a:** {utente.mention} (da {interaction.user.mention})")

    log_id = data.get("ticket_logs_channel_id")
    if log_id:
        lch = interaction.guild.get_channel(log_id)
        if lch:
            await lch.send(f"📌 **ASSEGNA** → {interaction.channel.mention} assegnato a {utente.mention} (da {interaction.user.mention})")


@bot.tree.command(name="renameticket", description="Rinomina il canale del ticket.")
@app_commands.describe(nuovo_nome="Nuovo nome")
async def renameticket(interaction: discord.Interaction, nuovo_nome: str):
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Solo server.", ephemeral=True)
    data = get_guild_entry(interaction.guild.id)
    if not is_staff_member(interaction.user, data):
        return await interaction.response.send_message("❌ Solo staff.", ephemeral=True)
    if not is_ticket_channel(interaction.channel):
        return await interaction.response.send_message("❌ Solo nei ticket.", ephemeral=True)
    old  = interaction.channel.name
    name = sanitize_channel_name(nuovo_nome)
    await interaction.channel.edit(name=name, reason=f"Rinominato da {interaction.user}")
    await interaction.response.send_message(f"✅ Rinominato in **{name}**", ephemeral=True)
    await interaction.channel.send(f"✏️ **Ticket rinominato**: `{old}` → `{name}` (da {interaction.user.mention})")


# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────
bot.run(TOKEN)
