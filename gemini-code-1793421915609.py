"""
⚫⚪  ROBUX STORE BOT  —  discord.py 2.x  (Python 3.10+)
"""
import asyncio
import hmac
import json
import logging
import os
import re
import time
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / "config.env")
load_dotenv(BASE / ".env")
log = logging.getLogger("robux-bot")

# ═════════════════════════ KONFIGURASI ═════════════════════════
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
STORE_NAME = os.getenv("STORE_NAME", "").strip() or "Robux Store"


def env_int(name: str) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value.isdigit() else 0


GUILD_ID = env_int("GUILD_ID")
ORDER_CATEGORY_ID = env_int("ORDER_CATEGORY_ID")
TICKET_CATEGORY_ID = env_int("TICKET_CATEGORY_ID")

if not TOKEN or TOKEN.startswith("isi_") or not ADMIN_PASSWORD:
    raise SystemExit("Isi DISCORD_TOKEN dan ADMIN_PASSWORD di config.env dulu ya.")

# ── Tampilan & harga ──
EMBED_COLOR = 0x111111                 # hitam
SEC = discord.ButtonStyle.secondary    # abu-abu
LOCK = "🔒"                            # penanda tombol khusus atmin
PRICE_PER_ROBUX = 150                  # 100 Robux = Rp15.000
AMOUNTS = range(100, 1001, 100)        # 100 … 1000 Robux

ACTIVE = ("cek_stok", "bayar", "cek_bukti", "proses")
STATUS_LABEL = {
    "cek_stok": "⏳ cek stok",
    "bayar": "💳 menunggu bayar",
    "cek_bukti": "🧾 cek bukti",
    "proses": "🔄 diproses",
    "selesai": "🎉 selesai",
    "batal": "❌ dibatalkan",
}
QRIS_EXT = (".png", ".jpg", ".jpeg", ".webp")
LOGO_EXT = (".png", ".jpg", ".jpeg", ".webp")
HUMAN_PERMS = dict(view_channel=True, send_messages=True, read_message_history=True, attach_files=True)
BOT_PERMS = dict(HUMAN_PERMS, embed_links=True)


# ═════════════════════════ UTIL ═════════════════════════
def rp(n: int) -> str:
    return "Rp" + f"{n:,}".replace(",", ".")


def esc(text) -> str:
    return discord.utils.escape_markdown(str(text))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())[:12] or "user"


def admin_pings() -> str:
    return " ".join(f"<@{uid}>" for uid in db.data["admins"])


def find_qris():
    for ext in QRIS_EXT:
        path = BASE / f"qris{ext}"
        if path.exists():
            return path
    return None


def find_logo():
    for ext in LOGO_EXT:
        path = BASE / f"logo{ext}"
        if path.exists():
            return path
    return None


def card(title, desc=None) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=EMBED_COLOR)
    e.set_footer(text=f"⚫ {STORE_NAME} ⚪")
    return e


def order_card(o, title, desc=None) -> discord.Embed:
    e = card(title, desc)
    e.add_field(name="🧾 Pesanan", value=f"`#{o['id']:04d}`")
    e.add_field(name="💎 Robux", value=f"{o['robux']:,}".replace(",", "."))
    e.add_field(name="💰 Total", value=rp(o["price"]))
    e.add_field(
        name="🎮 Roblox",
        value=f"[{esc(o['rb_name'])}](https://www.roblox.com/users/{o['rb_id']}/profile) • {esc(o['rb_display'])}",
        inline=False,
    )
    if o.get("avatar"):
        e.set_thumbnail(url=o["avatar"])
    return e


def receipt_card(o, admin_mention) -> discord.Embed:
    e = card(f"🧾 BUKTI TRANSAKSI SELESAI #{o['id']:04d}", "Terima kasih telah berbelanja di toko kami! ✨")
    e.add_field(name="💎 Jumlah Robux", value=f"**{o['robux']:,}** Robux".replace(",", "."), inline=True)
    e.add_field(name="💰 Total Bayar", value=f"**{rp(o['price'])}**", inline=True)
    e.add_field(name="👤 Pembeli", value=f"<@{o['user_id']}>", inline=True)
    e.add_field(name="🎮 Akun Roblox", value=f"[{esc(o['rb_name'])}](https://www.roblox.com/users/{o['rb_id']}/profile)", inline=True)
    e.add_field(name="🛡️ Dilayani Oleh", value=admin_mention, inline=True)
    e.add_field(name="🕒 Waktu", value=f"<t:{int(time.time())}:F>", inline=True)
    e.add_field(name="📌 Kebijakan", value="Dana bersifat **non-refundable** (tidak dapat direfund).", inline=False)
    if o.get("avatar"):
        e.set_thumbnail(url=o["avatar"])
    return e


def panel_card() -> discord.Embed:
    status = "🟢 **BUKA**" if db.data["open"] else "🔴 **TUTUP**"
    prices = "\n".join(f"`{a:>4}` Robux  ➜  **{rp(a * PRICE_PER_ROBUX)}**" for a in AMOUNTS)
    e = card(
        f"⚫ {STORE_NAME} ⚪",
        f"Status toko: {status}\n\n{prices}\n\n"
        "**Cara beli:** pilih jumlah di menu bawah → isi username Roblox → bayar QRIS → kirim bukti.\n\n"
        "⚠️ **Kebijakan Toko:** Dengan melanjutkan pembelian & pembayaran, uang yang sudah dibayar **tidak dapat direfund (non-refundable)**.\n\n"
        "🔐 Atmin tidak pernah meminta password akun Roblox kamu.",
    )
    logo = find_logo()
    if logo:
        e.set_image(url=f"attachment://{logo.name}")
    else:
        e.set_image(url="https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=60")
    return e


def admin_card() -> discord.Embed:
    orders = db.data["orders"].values()
    done = [o for o in orders if o["status"] == "selesai"]
    active = [o for o in orders if o["status"] in ACTIVE]
    
    channels = db.data.get("autoreact_channels", [])
    ch_list = ", ".join(f"<#{cid}>" for cid in channels) if channels else "Tidak ada (Mati)"
    
    e = card(f"{LOCK} Panel Atmin")
    e.add_field(name="Toko", value="🟢 Buka" if db.data["open"] else "🔴 Tutup")
    e.add_field(name="Pesanan aktif", value=str(len(active)))
    e.add_field(name="Selesai", value=f"{len(done)} • {rp(sum(o['price'] for o in done))}")
    e.add_field(name="QRIS", value="✅ Sudah diatur" if find_qris() else "⚠️ Belum — pakai `/setqris`")
    e.add_field(name="Logo Banner", value="✅ Sudah diatur" if find_logo() else "⚠️ Belum — pakai `/setlogo`")
    e.add_field(name="Atmin aktif", value=str(len(db.data["admins"])))
    e.add_field(name="Auto-React Channel", value=ch_list, inline=False)
    return e


# ═════════════════════════ DATA (data.json) ═════════════════════════
class DB:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"open": True, "admins": [], "counter": 0, "orders": {}, "tickets": {}, "panels": [], "autoreact_channels": []}
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def is_admin(self, uid: int) -> bool:
        return uid in self.data["admins"]

    def order_in(self, channel_id: int):
        return next((o for o in self.data["orders"].values() if o["channel_id"] == channel_id), None)

    def active_order_of(self, uid: int):
        return next(
            (o for o in self.data["orders"].values() if o["user_id"] == uid and o["status"] in ACTIVE), None
        )


db = DB(BASE / "data.json")


# ═════════════════════════ ROBLOX API ═════════════════════════
class RobloxError(Exception):
    pass


async def roblox_lookup(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", name):
        return None
    try:
        async with bot.web.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [name], "excludeBannedUsers": True},
        ) as resp:
            if resp.status != 200:
                raise RobloxError(f"HTTP {resp.status}")
            data = (await resp.json())["data"]
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as exc:
        raise RobloxError(str(exc)) from exc
    return data[0] if data else None


async def roblox_avatar(user_id: int):
    try:
        async with bot.web.get(
            "https://thumbnails.roblox.com/v1/users/avatar-headshot",
            params={"userIds": user_id, "size": "150x150", "format": "Png", "isCircular": "false"},
        ) as resp:
            data = (await resp.json())["data"]
            return data[0].get("imageUrl") if data else None
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError):
        return None


# ═════════════════════════ BOT ═════════════════════════
class RobuxBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.web = None

    async def setup_hook(self):
        self.web = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10), headers={"User-Agent": "RobuxStoreBot/1.0"}
        )
        for view in (PanelView(), StockView(), PayView(), ProofView(), ProcessView(), CloseView(), TicketView()):
            self.add_view(view)
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self):
        if self.web:
            await self.web.close()
        await super().close()

    async def on_ready(self):
        print(f"✅ Login sebagai {self.user} (id {self.user.id})")
        await self.change_presence(activity=discord.Game("Jual Robux ⚫⚪"))

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        
        # Auto-react hanya jika channel saat ini didaftarkan di autoreact_channels
        channels = db.data.get("autoreact_channels", [])
        if message.channel.id in channels:
            try:
                await message.add_reaction("👍")
            except discord.HTTPException:
                pass

        order = db.order_in(message.channel.id)
        if not order or order["status"] != "bayar" or message.author.id != order["user_id"]:
            return
        if not any((a.content_type or "").startswith("image/") for a in message.attachments):
            return
        order["status"] = "cek_bukti"
        db.save()
        await message.channel.send(
            content=admin_pings(),
            embed=order_card(order, "🧾 Bukti pembayaran diterima", "Atmin lagi cek pembayaranmu, sabar ya 🙏"),
            view=ProofView(),
        )


bot = RobuxBot()


async def get_member(guild: discord.Guild, uid: int):
    member = guild.get_member(uid)
    if member is None:
        try:
            member = await guild.fetch_member(uid)
        except discord.HTTPException:
            return None
    return member


async def private_overwrites(guild: discord.Guild, owner: discord.Member):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(**BOT_PERMS),
        owner: discord.PermissionOverwrite(**HUMAN_PERMS),
    }
    for uid in db.data["admins"]:
        member = await get_member(guild, uid)
        if member is not None:
            overwrites[member] = discord.PermissionOverwrite(**HUMAN_PERMS)
    return overwrites


def category_of(guild: discord.Guild, category_id: int):
    channel = guild.get_channel(category_id) if category_id else None
    return channel if isinstance(channel, discord.CategoryChannel) else None


async def admin_only(interaction: discord.Interaction, order=None) -> bool:
    if db.is_admin(interaction.user.id):
        return True
    if order is None:
        order = db.order_in(interaction.channel_id)
    
    if order and interaction.user.id == order["user_id"]:
        await interaction.response.send_message(
            "❌ Eits! Tombol ini khusus untuk **Atmin**. Kamu adalah **pembeli**, silakan tunggu atmin mengecek atau kirim bukti pembayaran di chat ini ya!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"{LOCK} Tombol ini khusus atmin. Masuk lewat `/admin` dulu ya.", ephemeral=True
        )
    return False


async def get_order(interaction: discord.Interaction, *statuses):
    order = db.order_in(interaction.channel_id)
    if order is None:
        await interaction.response.send_message("Pesanan tidak ditemukan di channel ini.", ephemeral=True)
        return None
    if order["status"] not in statuses:
        if order["status"] in ("batal", "selesai"):
            try:
                await interaction.response.edit_message(view=None)
            except discord.HTTPException:
                pass
            await interaction.followup.send("⚠️ Pesanan ini sudah ditutup/dibatalkan.", ephemeral=True)
            return None
            
        current_label = STATUS_LABEL.get(order["status"], order["status"])
        await interaction.response.send_message(
            f"⚠️ Pesanan ini sedang berada di tahap **{current_label}**, tombol ini tidak bisa digunakan pada tahap ini.",
            ephemeral=True
        )
        return None
    return order


async def cancel_order(interaction: discord.Interaction):
    order = db.order_in(interaction.channel_id)
    if order is None:
        await interaction.response.send_message("Pesanan tidak ditemukan.", ephemeral=True)
        return
    if order["status"] in ("batal", "selesai"):
        await interaction.response.send_message("Pesanan ini sudah selesai atau dibatalkan sebelumnya.", ephemeral=True)
        return
    if interaction.user.id != order["user_id"] and not db.is_admin(interaction.user.id):
        await interaction.response.send_message("Hanya pembeli atau atmin yang bisa membatalkan.", ephemeral=True)
        return
        
    order["status"] = "batal"
    db.save()
    try:
        await interaction.response.edit_message(view=None)
    except discord.HTTPException:
        pass
    await interaction.channel.send(
        embed=card("✖️ Pesanan dibatalkan", f"Dibatalkan oleh {interaction.user.mention}."), view=CloseView()
    )


async def send_qris(channel, order):
    e = card(
        "💳 Pembayaran QRIS & Ketentuan",
        f"Stok **ada** ✅\nScan QRIS di bawah dan bayar tepat **{rp(order['price'])}**.\n\n"
        "⚠️ **Perhatian:** Dana yang sudah ditransfer **tidak dapat direfund (non-refundable)** dalam kondisi apapun.\n\n"
        "📎 Setelah bayar, **kirim bukti pembayaran (screenshot)** di channel ini.",
    )
    qris = find_qris()
    file = None
    if qris:
        file = discord.File(qris, filename=qris.name)
        e.set_image(url=f"attachment://{qris.name}")
    else:
        e.add_field(name="⚠️ QRIS belum diatur", value="Tunggu atmin kirim QRIS-nya ya.")
    await channel.send(content=f"<@{order['user_id']}>", embed=e, file=file, view=PayView())


class StockView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ada", emoji=LOCK, style=SEC, custom_id="order:ada")
    async def ada(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = db.order_in(interaction.channel_id)
        if not await admin_only(interaction, order):
            return
        order = await get_order(interaction, "cek_stok")
        if order is None:
            return
        order["status"] = "bayar"
        db.save()
        await interaction.response.edit_message(
            embed=order_card(order, "✅ Stok tersedia", f"Dikonfirmasi oleh {interaction.user.mention}"), view=None
        )
        await send_qris(interaction.channel, order)

    @discord.ui.button(label="Tidak Ada", emoji=LOCK, style=SEC, custom_id="order:kosong")
    async def kosong(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = db.order_in(interaction.channel_id)
        if not await admin_only(interaction, order):
            return
        order = await get_order(interaction, "cek_stok")
        if order is None:
            return
        order["status"] = "batal"
        db.save()
        await interaction.response.edit_message(view=None)
        await interaction.channel.send(
            content=f"<@{order['user_id']}>",
            embed=card("😔 Stok kosong", "Maaf, stok lagi kosong jadi pesanan dibatalkan. Coba lagi nanti ya!"),
            view=CloseView(),
        )

    @discord.ui.button(label="Batalkan", emoji="✖️", style=SEC, custom_id="order:batal1")
    async def batal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await cancel_order(interaction)


class PayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Batalkan Pesanan", emoji="✖️", style=SEC, custom_id="order:batal2")
    async def batal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await cancel_order(interaction)


class ProofView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Konfirmasi Pembayaran", emoji=LOCK, style=SEC, custom_id="order:bayar_ok")
    async def ok(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = db.order_in(interaction.channel_id)
        if not await admin_only(interaction, order):
            return
        order = await get_order(interaction, "cek_bukti")
        if order is None:
            return
        order["status"] = "proses"
        db.save()
        await interaction.response.edit_message(
            embed=order_card(order, "🧾 Pembayaran dikonfirmasi ✅", f"Dicek oleh {interaction.user.mention}"),
            view=None,
        )
        await interaction.channel.send(
            content=f"<@{order['user_id']}>",
            embed=order_card(
                order,
                "🔄 Pesanan sedang diproses",
                "Pembayaran sudah dikonfirmasi. Robux kamu lagi diproses atmin, mohon ditunggu ya!",
            ),
            view=ProcessView(),
        )

    @discord.ui.button(label="Bukti Tidak Valid", emoji=LOCK, style=SEC, custom_id="order:bayar_no")
    async def tolak(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = db.order_in(interaction.channel_id)
        if not await admin_only(interaction, order):
            return
        order = await get_order(interaction, "cek_bukti")
        if order is None:
            return
        order["status"] = "bayar"
        db.save()
        await interaction.response.edit_message(view=None)
        await interaction.channel.send(
            content=f"<@{order['user_id']}>",
            embed=card(
                "❌ Bukti belum valid",
                "Atmin belum bisa memverifikasi pembayaranmu. Kirim ulang bukti yang jelas ya.",
            ),
        )


class ProcessView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Selesai (Serah)", emoji=LOCK, style=SEC, custom_id="order:selesai")
    async def selesai(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = db.order_in(interaction.channel_id)
        if not await admin_only(interaction, order):
            return
        order = await get_order(interaction, "proses")
        if order is None:
            return
        order["status"] = "selesai"
        order["done"] = int(time.time())
        db.save()
        
        await interaction.response.edit_message(
            embed=order_card(order, "🎉 Pesanan selesai", f"Diselesaikan oleh {interaction.user.mention}"),
            view=None,
        )
        
        receipt = receipt_card(order, interaction.user.mention)
        
        await interaction.channel.send(
            content=f"<@{order['user_id']}>",
            embed=card(
                "🎉 Pesanan Selesai & Dikirim!",
                "Robux kamu sudah dikirim/diserahkan ✅ Terima kasih sudah belanja di toko kami!\n"
                "📩 **Bukti resi transaksi resmi telah dikirim ke pesan pribadi (DM) kamu.**\n\n"
                "⏳ **Channel ini akan otomatis tertutup sendiri dalam waktu 5 menit ke depan.**"
            ),
        )
        
        try:
            buyer = await bot.fetch_user(order["user_id"])
            await buyer.send(embed=receipt)
        except discord.HTTPException:
            pass
        
        await asyncio.sleep(300)
        try:
            await interaction.channel.delete(reason="Pesanan selesai dan waktu 5 menit habis.")
        except discord.HTTPException:
            pass


class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Tutup Channel", emoji="✖️", style=SEC, custom_id="order:tutup")
    async def tutup(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = db.order_in(interaction.channel_id)
        if order and interaction.user.id == order["user_id"]:
            pass
        elif not await admin_only(interaction):
            return
            
        await interaction.response.send_message("🔒 Channel ditutup dalam 5 detik…")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ditutup oleh {interaction.user}")
        except discord.HTTPException:
            pass


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        custom_id="panel:amount",
        placeholder="⚫ Pilih jumlah Robux…",
        options=[
            discord.SelectOption(
                label=f"{a} Robux", description=rp(a * PRICE_PER_ROBUX), value=str(a), emoji="🪙"
            )
            for a in AMOUNTS
        ],
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.Select):
        robux = int(interaction.data["values"][0])
        if not db.data["open"]:
            await interaction.response.send_message("🔴 Toko lagi **tutup**.", ephemeral=True)
        elif db.active_order_of(interaction.user.id):
            await interaction.response.send_message("Kamu masih punya pesanan aktif.", ephemeral=True)
        else:
            await interaction.response.send_modal(UsernameModal(robux))
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Tiket", emoji="🎫", style=SEC, custom_id="panel:ticket")
    async def ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_ticket(interaction)


class UsernameModal(discord.ui.Modal, title="Username Roblox"):
    username = discord.ui.TextInput(
        label="Username Roblox kamu", placeholder="contoh: Builderman", min_length=3, max_length=20
    )

    def __init__(self, robux: int):
        super().__init__()
        self.robux = robux

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        name = self.username.value.strip()
        try:
            rb = await roblox_lookup(name)
        except RobloxError:
            log.warning("Roblox API bermasalah", exc_info=True)
            await interaction.followup.send(
                embed=card("⚠️ Roblox lagi susah dihubungi", "Coba lagi sebentar ya."),
                view=RetryView(self.robux),
                ephemeral=True,
            )
            return
        if rb is None:
            await interaction.followup.send(
                embed=card("🔎 Username tidak ditemukan", f"**{esc(name)}** tidak ketemu di Roblox 😕"),
                view=RetryView(self.robux),
                ephemeral=True,
            )
            return
        avatar = await roblox_avatar(rb["id"])
        e = card("🔎 Apakah ini akunmu?", f"Pesanan: **{self.robux} Robux** • {rp(self.robux * PRICE_PER_ROBUX)}")
        e.add_field(name="Username", value=esc(rb["name"]))
        e.add_field(name="Display name", value=esc(rb["displayName"]))
        e.add_field(name="ID", value=str(rb["id"]))
        e.add_field(
            name="⚠️ Kebijakan Non-Refund", 
            value="Dengan mengklik **Iya**, pesanan akan dilanjutkan dan dana bersifat **non-refundable (tidak dapat direfund)**.", 
            inline=False
        )
        if avatar:
            e.set_thumbnail(url=avatar)
        await interaction.followup.send(embed=e, view=ConfirmView(self.robux, rb, avatar), ephemeral=True)


class ConfirmView(discord.ui.View):
    def __init__(self, robux: int, rb: dict, avatar):
        super().__init__(timeout=300)
        self.robux, self.rb, self.avatar = robux, rb, avatar

    @discord.ui.button(label="Iya", emoji="✅", style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_order(interaction, self.robux, self.rb, self.avatar)

    @discord.ui.button(label="Tidak", emoji="❌", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=card("✏️ Oke, tulis ulang", "Klik tombol di bawah untuk memasukkan username yang benar."),
            view=RetryView(self.robux),
        )


class RetryView(discord.ui.View):
    def __init__(self, robux: int):
        super().__init__(timeout=300)
        self.robux = robux

    @discord.ui.button(label="Tulis Ulang", emoji="✏️", style=SEC)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UsernameModal(self.robux))

    @discord.ui.button(label="Batal", emoji="✖️", style=SEC)
    async def abort(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=card("Dibatalkan", "Pilih lagi dari menu kapan saja ya."), view=None)


async def create_order(interaction: discord.Interaction, robux: int, rb: dict, avatar):
    user, guild = interaction.user, interaction.guild
    await interaction.response.edit_message(embed=card("⏳ Membuat pesanan…"), view=None)

    async def say(title, desc):
        await interaction.edit_original_response(embed=card(title, desc), view=None)

    if not db.data["open"]:
        return await say("🔴 Toko tutup", "Toko baru saja ditutup.")
    if db.active_order_of(user.id):
        return await say("Pesanan masih aktif", "Selesaikan atau batalkan pesananmu dulu.")
    if not db.data["admins"]:
        return await say("⚠️ Toko belum siap", "Belum ada atmin yang aktif.")

    oid = db.data["counter"] + 1
    try:
        channel = await guild.create_text_channel(
            f"pesanan-{oid:04d}-{slug(user.name)}",
            category=category_of(guild, ORDER_CATEGORY_ID),
            overwrites=await private_overwrites(guild, user),
            topic=f"Pesanan #{oid:04d} • {user} • {robux} Robux",
            reason=f"Pesanan baru dari {user}",
        )
    except discord.HTTPException:
        log.exception("Gagal membuat channel pesanan")
        return await say("⚠️ Gagal membuat pesanan", "Bot belum punya izin **Manage Channels**.")

    order = {
        "id": oid,
        "user_id": user.id,
        "channel_id": channel.id,
        "robux": robux,
        "price": robux * PRICE_PER_ROBUX,
        "rb_id": rb["id"],
        "rb_name": rb["name"],
        "rb_display": rb["displayName"],
        "avatar": avatar,
        "status": "cek_stok",
        "created": int(time.time()),
    }
    db.data["counter"] = oid
    db.data["orders"][str(oid)] = order
    db.save()

    await channel.send(
        content=f"{user.mention} {admin_pings()}",
        embed=order_card(order, "⏳ Menunggu cek stok", "Tunggu ya, atmin lagi cek stok… 🙏"),
        view=StockView(),
    )
    await say("✅ Pesanan dibuat", f"Lanjut di {channel.mention} ya!")


async def open_ticket(interaction: discord.Interaction):
    guild, user = interaction.guild, interaction.user
    for cid, uid in list(db.data["tickets"].items()):
        if uid == user.id:
            existing = guild.get_channel(int(cid))
            if existing:
                await interaction.response.send_message(f"Kamu masih punya tiket aktif: {existing.mention}", ephemeral=True)
                return
            db.data["tickets"].pop(cid)
    await interaction.response.defer(ephemeral=True)
    try:
        channel = await guild.create_text_channel(
            f"tiket-{slug(user.name)}",
            category=category_of(guild, TICKET_CATEGORY_ID),
            overwrites=await private_overwrites(guild, user),
            topic=f"Tiket {user} ({user.id})",
            reason=f"Tiket dari {user}",
        )
    except discord.HTTPException:
        log.exception("Gagal membuat channel tiket")
        await interaction.followup.send("⚠️ Gagal membuat tiket.", ephemeral=True)
        return
    db.data["tickets"][str(channel.id)] = user.id
    db.save()
    await channel.send(
        content=f"{user.mention} {admin_pings()}",
        embed=card("🎫 Tiket dibuka", "Jelaskan kendala atau pertanyaanmu di sini."),
        view=TicketView(),
    )
    await interaction.followup.send(f"🎫 Tiket kamu sudah dibuat: {channel.mention}", ephemeral=True)


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Tutup Tiket", emoji="✖️", style=SEC, custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        owner = db.data["tickets"].get(str(interaction.channel_id))
        if interaction.user.id != owner and not db.is_admin(interaction.user.id):
            await interaction.response.send_message("Hanya pemilik tiket atau atmin yang bisa menutup tiket ini.", ephemeral=True)
            return
        db.data["tickets"].pop(str(interaction.channel_id), None)
        db.save()
        await interaction.response.send_message("✖️ Tiket ditutup. Channel dihapus dalam 5 detik…")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Tiket ditutup oleh {interaction.user}")
        except discord.HTTPException:
            pass


FAILS: dict = {}


def lockout_seconds(uid: int) -> int:
    now = time.time()
    recent = [t for t in FAILS.get(uid, []) if now - t < 600]
    FAILS[uid] = recent
    return int(600 - (now - recent[0])) if len(recent) >= 5 else 0


async def refresh_panels():
    keep = []
    logo = find_logo()
    for cid, mid in db.data["panels"]:
        try:
            channel = bot.get_partial_messageable(cid)
            file = discord.File(logo, filename=logo.name) if logo else None
            await channel.get_partial_message(mid).edit(embed=panel_card(), attachments=[file] if file else [])
            keep.append([cid, mid])
        except discord.NotFound:
            continue
        except discord.HTTPException:
            keep.append([cid, mid])
    db.data["panels"] = keep
    db.save()


class PasswordModal(discord.ui.Modal, title="Login Atmin 🔒"):
    password = discord.ui.TextInput(label="Password atmin", placeholder="Masukkan password", max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        wait = lockout_seconds(uid)
        if wait:
            await interaction.response.send_message(f"🔒 Terlalu banyak percobaan. Coba lagi nanti.", ephemeral=True)
            return
        if not hmac.compare_digest(self.password.value.strip().encode(), ADMIN_PASSWORD.encode()):
            FAILS.setdefault(uid, []).append(time.time())
            await interaction.response.send_message("❌ Password salah.", ephemeral=True)
            return
        FAILS.pop(uid, None)
        
        if uid not in db.data["admins"]:
            db.data["admins"].append(uid)
            db.save()
            
        await interaction.response.send_message("🔓 Berhasil masuk sebagai atmin! (Akses permanen tersimpan)", embed=admin_card(), view=AdminView(), ephemeral=True)


class AdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await admin_only(interaction)

    @discord.ui.button(label="Buka / Tutup Toko", emoji=LOCK, style=SEC, row=0)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        db.data["open"] = not db.data["open"]
        db.save()
        await interaction.response.edit_message(embed=admin_card(), view=self)
        await refresh_panels()

    @discord.ui.button(label="Pesanan Aktif", emoji=LOCK, style=SEC, row=0)
    async def active(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = [
            f"`#{o['id']:04d}` <#{o['channel_id']}> • {o['robux']} R$ • {STATUS_LABEL[o['status']]}"
            for o in db.data["orders"].values()
            if o["status"] in ACTIVE
        ]
        desc = "\n".join(rows[:20]) or "Belum ada pesanan aktif."
        await interaction.response.send_message(embed=card("📋 Pesanan Aktif", desc), ephemeral=True)

    @discord.ui.button(label="Kirim Panel Toko", emoji=LOCK, style=SEC, row=1)
    async def post_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        logo = find_logo()
        file = discord.File(logo, filename=logo.name) if logo else None
        try:
            msg = await interaction.channel.send(embed=panel_card(), file=file, view=PanelView())
        except discord.HTTPException:
            await interaction.response.send_message("Bot tidak bisa kirim pesan di channel ini.", ephemeral=True)
            return
        db.data["panels"].append([msg.channel.id, msg.id])
        db.save()
        await interaction.response.send_message("✅ Panel toko terkirim di channel ini.", ephemeral=True)

    @discord.ui.button(label="Keluar Atmin", emoji=LOCK, style=SEC, row=1)
    async def logout(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in db.data["admins"]:
            db.data["admins"].remove(interaction.user.id)
            db.save()
        await interaction.response.edit_message(embed=card("🔓 Keluar dari mode atmin", "Akses atmin dicabut."), view=None)


@bot.tree.command(name="admin", description="Masuk ke panel atmin (butuh password)")
@app_commands.guild_only()
async def admin_cmd(interaction: discord.Interaction):
    if db.is_admin(interaction.user.id):
        await interaction.response.send_message(embed=admin_card(), view=AdminView(), ephemeral=True)
    else:
        await interaction.response.send_modal(PasswordModal())


@bot.tree.command(name="autoreact", description="🔒 Atur auto-react jempol untuk channel tertentu (khusus atmin)")
@app_commands.describe(aksi="Pilih tambah atau hapus", channel="Channel teks yang dituju")
@app_commands.choices(aksi=[
    app_commands.Choice(name="Tambah Channel", value="add"),
    app_commands.Choice(name="Hapus Channel", value="remove")
])
@app_commands.guild_only()
async def autoreact_cmd(interaction: discord.Interaction, aksi: str, channel: discord.TextChannel):
    if not await admin_only(interaction):
        return
    
    channels = db.data.setdefault("autoreact_channels", [])
    
    if aksi == "add":
        if channel.id in channels:
            await interaction.response.send_message(f"⚠️ Channel {channel.mention} sudah ada dalam daftar auto-react.", ephemeral=True)
        else:
            channels.append(channel.id)
            db.save()
            await interaction.response.send_message(f"✅ Berhasil menambahkan {channel.mention} ke daftar auto-react.", ephemeral=True)
    elif aksi == "remove":
        if channel.id in channels:
            channels.remove(channel.id)
            db.save()
            await interaction.response.send_message(f"✅ Berhasil menghapus {channel.mention} dari daftar auto-react.", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Channel {channel.mention} memang tidak ada di daftar auto-react.", ephemeral=True)


@bot.tree.command(name="setqris", description="🔒 Upload gambar QRIS toko (khusus atmin)")
@app_commands.describe(gambar="Gambar QRIS (png / jpg / webp)")
@app_commands.guild_only()
async def setqris(interaction: discord.Interaction, gambar: discord.Attachment):
    await interaction.response.defer(ephemeral=True, thinking=True)
    if not await admin_only(interaction):
        return
    ext = Path(gambar.filename).suffix.lower()
    if ext not in QRIS_EXT:
        await interaction.followup.send("File harus gambar (png / jpg / jpeg / webp).", ephemeral=True)
        return
    for old in QRIS_EXT:
        (BASE / f"qris{old}").unlink(missing_ok=True)
    await gambar.save(BASE / f"qris{ext}")
    await interaction.followup.send("✅ QRIS tersimpan.", ephemeral=True)


@bot.tree.command(name="setlogo", description="🔒 Upload gambar logo/banner panel toko (khusus atmin)")
@app_commands.describe(gambar="Gambar logo (png / jpg / webp)")
@app_commands.guild_only()
async def setlogo(interaction: discord.Interaction, gambar: discord.Attachment):
    await interaction.response.defer(ephemeral=True, thinking=True)
    if not await admin_only(interaction):
        return
    ext = Path(gambar.filename).suffix.lower()
    if ext not in LOGO_EXT:
        await interaction.followup.send("File harus gambar (png / jpg / jpeg / webp).", ephemeral=True)
        return
    for old in LOGO_EXT:
        (BASE / f"logo{old}").unlink(missing_ok=True)
    await gambar.save(BASE / f"logo{old}")
    await interaction.followup.send("✅ Logo panel toko berhasil tersimpan! Ketik `/admin` lalu klik **Kirim Panel Toko** untuk melihat perubahannya.", ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN)