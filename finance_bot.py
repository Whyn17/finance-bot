"""
Bot Telegram: Personal Finance Tracker
Fitur: Keuangan, Investasi (Emas/Saham/Crypto/Valas) + Harga Realtime, Hutang & Piutang, Grafik, Pengingat

API KEYS yang dibutuhkan (gratis):
- GOLD_API_KEY : daftar di https://www.goldapi.io (gratis)
- FX_API_KEY   : daftar di https://www.exchangerate-api.com (gratis)
- Crypto       : CoinGecko (GRATIS, tanpa key)
"""

import json, os, io, asyncio, aiohttp
from datetime import datetime, date, time, timedelta
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN       = os.environ.get("BOT_TOKEN")
GOLD_API    = os.environ.get("GOLD_API_KEY", "")     # goldapi.io
FX_API      = os.environ.get("FX_API_KEY", "")       # exchangerate-api.com
DATA_FILE   = "keuangan.json"

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_ud(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"transaksi":[], "budget":{}, "reminder":None,
                     "investasi":[], "hutang":[], "piutang":[]}
    for k in ["investasi","hutang","piutang"]:
        if k not in data[uid]: data[uid][k] = []
    if "reminder" not in data[uid]: data[uid]["reminder"] = None
    return data[uid]

def rp(v):
    if v >= 1_000_000_000: return f"Rp {v/1_000_000_000:.2f}M"
    if v >= 1_000_000:     return f"Rp {v/1_000_000:.2f}jt"
    if v >= 1_000:         return f"Rp {v/1_000:.0f}rb"
    return f"Rp {v:.0f}"

def rp_full(v):
    return f"Rp {v:,.0f}".replace(",",".")

def pct_str(v):
    arrow = "🔺" if v >= 0 else "🔻"
    return f"{arrow} {abs(v):.2f}%"

# ══════════════════════════════════════════════════════════════════════════════
# REALTIME PRICE APIs
# ══════════════════════════════════════════════════════════════════════════════

CRYPTO_IDS = {
    "bitcoin":  "BTC",
    "ethereum": "ETH",
    "solana":   "SOL",
    "tether":   "USDT",
    "usd-coin": "USDC",
}

VALAS_LIST = ["USD","EUR","SGD","MYR","JPY","AUD","GBP","CNY","SAR","HKD"]

async def get_idr_rate() -> float:
    """Ambil kurs USD/IDR dari exchangerate-api"""
    try:
        url = f"https://v6.exchangerate-api.com/v6/{FX_API}/latest/USD"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                d = await r.json()
                return float(d["conversion_rates"]["IDR"])
    except:
        return 16250.0   # fallback

async def get_crypto_prices() -> dict:
    """Harga crypto dalam IDR via CoinGecko (gratis, tanpa key)"""
    ids = ",".join(CRYPTO_IDS.keys())
    url = (f"https://api.coingecko.com/api/v3/simple/price"
           f"?ids={ids}&vs_currencies=idr&include_24hr_change=true")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                raw = await r.json()
        result = {}
        for coin_id, ticker in CRYPTO_IDS.items():
            if coin_id in raw:
                result[ticker] = {
                    "price": raw[coin_id].get("idr", 0),
                    "change": raw[coin_id].get("idr_24h_change", 0),
                }
        return result
    except:
        return {}

async def get_gold_price_idr() -> dict:
    """Harga emas (XAU) dalam IDR via goldapi.io"""
    try:
        idr_rate = await get_idr_rate()
        headers  = {"x-access-token": GOLD_API, "Content-Type": "application/json"}
        url      = "https://www.goldapi.io/api/XAU/USD"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as r:
                d = await r.json()
        price_usd_per_oz = d.get("price", 0)
        change_pct       = d.get("ch_24h", d.get("chp", 0))
        # konversi: 1 troy oz = 31.1035 gram
        price_per_gram_idr = (price_usd_per_oz / 31.1035) * idr_rate
        return {
            "price_gram": price_per_gram_idr,
            "price_oz":   price_usd_per_oz * idr_rate,
            "change":     change_pct,
            "idr_rate":   idr_rate,
        }
    except:
        return {}

async def get_valas_prices() -> dict:
    """Kurs valas ke IDR via exchangerate-api.com"""
    try:
        url = f"https://v6.exchangerate-api.com/v6/{FX_API}/latest/IDR"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                d = await r.json()
        rates = d.get("conversion_rates", {})
        result = {}
        for cur in VALAS_LIST:
            if cur in rates and rates[cur] > 0:
                result[cur] = 1.0 / rates[cur]   # IDR per 1 unit valas
        return result
    except:
        return {}

# ══════════════════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nama = update.effective_user.first_name
    teks = (
        f"👋 Halo, *{nama}*! Finance Tracker Bot 💰\n\n"
        "💸 *Pengeluaran & Pemasukan:*\n"
        "`/keluar 50000 makan siang`\n"
        "`/masuk 3000000 gaji`\n"
        "`/ringkasan` | `/laporan` | `/riwayat`\n"
        "`/budget makan 1500000` | `/cek_budget`\n\n"

        "📈 *Investasi:*\n"
        "`/inv_emas beli 5` — beli 5 gram emas\n"
        "`/inv_emas jual 2` — jual 2 gram emas\n"
        "`/inv_crypto beli BTC 500000` — beli BTC senilai Rp500rb\n"
        "`/inv_crypto jual ETH 200000` — jual ETH senilai Rp200rb\n"
        "`/inv_saham beli BBCA 1000000` — beli saham BBCA\n"
        "`/inv_saham jual BBCA 1200000` — jual saham BBCA\n"
        "`/inv_valas beli USD 500000` — beli USD senilai Rp500rb\n"
        "`/inv_valas jual USD 300000` — jual USD\n"
        "`/inv_list` — lihat portofolio lengkap\n\n"

        "💹 *Harga Realtime:*\n"
        "`/harga_crypto` — BTC, ETH, SOL, USDT, USDC\n"
        "`/harga_emas` — harga emas per gram & oz\n"
        "`/harga_valas` — kurs USD, EUR, SGD, dll\n\n"

        "🤝 *Hutang & Piutang:*\n"
        "`/hutang 200000 Budi beli makan`\n"
        "`/piutang 150000 Ani pinjam`\n"
        "`/hutang_list` | `/piutang_list`\n"
        "`/bayar_hutang 1` | `/terima_piutang 1`\n\n"

        "📊 `/grafik` | ⏰ `/reminder 20:00` | 🗑 `/reset`"
    )
    await update.message.reply_text(teks, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# HARGA REALTIME
# ══════════════════════════════════════════════════════════════════════════════

async def harga_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Mengambil harga crypto...")
    prices = await get_crypto_prices()
    if not prices:
        await msg.edit_text("❌ Gagal mengambil data. Coba lagi nanti.")
        return

    teks = f"🪙 *Harga Crypto Realtime*\n_{datetime.now().strftime('%d/%m/%Y %H:%M')} WIB_\n\n"
    icons = {"BTC":"₿","ETH":"Ξ","SOL":"◎","USDT":"💵","USDC":"💵"}
    for ticker, d in prices.items():
        icon = icons.get(ticker, "🔸")
        teks += f"{icon} *{ticker}*\n"
        teks += f"  Harga: *{rp_full(d['price'])}*\n"
        teks += f"  24h: {pct_str(d['change'])}\n\n"

    await msg.edit_text(teks, parse_mode="Markdown")

async def harga_emas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GOLD_API:
        await update.message.reply_text(
            "⚠️ *GOLD\\_API\\_KEY belum diset!*\n\n"
            "Cara dapatkan API key gratis:\n"
            "1. Daftar di https://www.goldapi.io\n"
            "2. Copy API key\n"
            "3. Tambah di Railway Variables:\n"
            "   Key: `GOLD_API_KEY`\n"
            "   Value: api key kamu",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text("⏳ Mengambil harga emas...")
    d = await get_gold_price_idr()
    if not d:
        await msg.edit_text("❌ Gagal mengambil data emas. Coba lagi nanti.")
        return

    teks = (
        f"🥇 *Harga Emas Realtime*\n"
        f"_{datetime.now().strftime('%d/%m/%Y %H:%M')} WIB_\n\n"
        f"💛 Per Gram: *{rp_full(d['price_gram'])}*\n"
        f"📦 Per Troy Oz: *{rp_full(d['price_oz'])}*\n"
        f"24h: {pct_str(d['change'])}\n\n"
        f"💱 Kurs USD/IDR: {rp_full(d['idr_rate'])}"
    )
    await msg.edit_text(teks, parse_mode="Markdown")

async def harga_valas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not FX_API:
        await update.message.reply_text(
            "⚠️ *FX\\_API\\_KEY belum diset!*\n\n"
            "Cara dapatkan API key gratis:\n"
            "1. Daftar di https://www.exchangerate-api.com\n"
            "2. Copy API key\n"
            "3. Tambah di Railway Variables:\n"
            "   Key: `FX_API_KEY`\n"
            "   Value: api key kamu",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text("⏳ Mengambil kurs valas...")
    rates = await get_valas_prices()
    if not rates:
        await msg.edit_text("❌ Gagal mengambil data valas. Coba lagi nanti.")
        return

    teks = f"💱 *Kurs Valas ke IDR*\n_{datetime.now().strftime('%d/%m/%Y %H:%M')} WIB_\n\n"
    flags = {"USD":"🇺🇸","EUR":"🇪🇺","SGD":"🇸🇬","MYR":"🇲🇾","JPY":"🇯🇵",
             "AUD":"🇦🇺","GBP":"🇬🇧","CNY":"🇨🇳","SAR":"🇸🇦","HKD":"🇭🇰"}
    for cur, idr_per_unit in rates.items():
        flag = flags.get(cur, "🏳")
        teks += f"{flag} *1 {cur}* = {rp_full(idr_per_unit)}\n"

    await msg.edit_text(teks, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# INVESTASI — EMAS
# ══════════════════════════════════════════════════════════════════════════════

async def inv_emas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /inv_emas beli 5       → beli 5 gram emas (harga otomatis realtime)
    /inv_emas jual 2       → jual 2 gram emas
    /inv_emas beli 5 manual 1600000  → input harga manual per gram
    """
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Format:\n"
            "`/inv_emas beli [gram]` — harga otomatis realtime\n"
            "`/inv_emas jual [gram]`\n"
            "`/inv_emas beli [gram] manual [harga/gram]` — input manual\n\n"
            "Contoh: `/inv_emas beli 5`",
            parse_mode="Markdown"
        )
        return

    aksi = args[0].lower()
    try:
        gram = float(args[1].replace(",","."))
    except:
        await update.message.reply_text("❌ Jumlah gram tidak valid.")
        return

    # Harga manual atau realtime
    if len(args) >= 4 and args[2].lower() == "manual":
        try:
            harga_per_gram = float(args[3].replace(".","").replace(",",""))
            sumber = "manual"
        except:
            await update.message.reply_text("❌ Harga manual tidak valid.")
            return
    else:
        if not GOLD_API:
            await update.message.reply_text("⚠️ GOLD_API_KEY belum diset. Gunakan harga manual:\n`/inv_emas beli 5 manual 1600000`", parse_mode="Markdown")
            return
        msg = await update.message.reply_text("⏳ Mengambil harga emas realtime...")
        d = await get_gold_price_idr()
        if not d:
            await msg.edit_text("❌ Gagal ambil harga. Gunakan: `/inv_emas beli 5 manual 1600000`", parse_mode="Markdown")
            return
        harga_per_gram = d["price_gram"]
        sumber = "realtime"
        await msg.delete()

    total = gram * harga_per_gram
    data = load_data()
    ud   = get_ud(data, update.effective_user.id)
    ud["investasi"].append({
        "jenis": "emas", "tipe": aksi,
        "gram": gram, "harga_per_gram": harga_per_gram,
        "jumlah": total, "sumber_harga": sumber,
        "tanggal": datetime.now().isoformat()
    })
    save_data(data)

    emoji = "📈" if aksi == "beli" else "📉"
    await update.message.reply_text(
        f"{emoji} *Investasi Emas Dicatat!*\n\n"
        f"Aksi: *{aksi.upper()}*\n"
        f"Jumlah: *{gram} gram*\n"
        f"Harga/gram: {rp_full(harga_per_gram)} ({sumber})\n"
        f"Total: *{rp_full(total)}*",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════════════════
# INVESTASI — CRYPTO
# ══════════════════════════════════════════════════════════════════════════════

async def inv_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /inv_crypto beli BTC 500000   → beli BTC senilai Rp500rb (harga realtime)
    /inv_crypto jual ETH 200000
    /inv_crypto beli SOL 300000 manual 2000000  → harga SOL manual
    Supported: BTC, ETH, SOL, USDT, USDC
    """
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "❌ Format:\n"
            "`/inv_crypto beli [coin] [jumlah_rupiah]`\n"
            "`/inv_crypto jual [coin] [jumlah_rupiah]`\n\n"
            "Coin: BTC, ETH, SOL, USDT, USDC\n"
            "Contoh: `/inv_crypto beli BTC 500000`",
            parse_mode="Markdown"
        )
        return

    aksi  = args[0].lower()
    coin  = args[1].upper()
    try:
        jumlah = float(args[2].replace(".","").replace(",",""))
    except:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return

    valid_coins = list(CRYPTO_IDS.values())
    if coin not in valid_coins:
        await update.message.reply_text(f"❌ Coin tidak didukung. Pilih: {', '.join(valid_coins)}")
        return

    # Harga manual atau realtime
    if len(args) >= 5 and args[3].lower() == "manual":
        try:
            harga_per_coin = float(args[4].replace(".","").replace(",",""))
            sumber = "manual"
        except:
            await update.message.reply_text("❌ Harga manual tidak valid.")
            return
        coin_qty = jumlah / harga_per_coin
    else:
        msg = await update.message.reply_text(f"⏳ Mengambil harga {coin}...")
        prices = await get_crypto_prices()
        if not prices or coin not in prices:
            await msg.edit_text(f"❌ Gagal ambil harga {coin}. Gunakan harga manual:\n`/inv_crypto {aksi} {coin} {int(jumlah)} manual [harga_per_coin]`", parse_mode="Markdown")
            return
        harga_per_coin = prices[coin]["price"]
        sumber = "realtime"
        coin_qty = jumlah / harga_per_coin
        await msg.delete()

    data = load_data()
    ud   = get_ud(data, update.effective_user.id)
    ud["investasi"].append({
        "jenis": "crypto", "coin": coin, "tipe": aksi,
        "jumlah": jumlah, "harga_per_coin": harga_per_coin,
        "coin_qty": coin_qty, "sumber_harga": sumber,
        "tanggal": datetime.now().isoformat()
    })
    save_data(data)

    emoji = "📈" if aksi == "beli" else "📉"
    await update.message.reply_text(
        f"{emoji} *Investasi Crypto Dicatat!*\n\n"
        f"Aksi: *{aksi.upper()} {coin}*\n"
        f"Nilai: *{rp_full(jumlah)}*\n"
        f"Harga/{coin}: {rp_full(harga_per_coin)} ({sumber})\n"
        f"Qty: ≈ {coin_qty:.6f} {coin}",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════════════════
# INVESTASI — SAHAM
# ══════════════════════════════════════════════════════════════════════════════

async def inv_saham(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /inv_saham beli BBCA 1000000
    /inv_saham jual BBCA 1200000
    """
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "❌ Format:\n"
            "`/inv_saham beli [kode] [jumlah_rupiah]`\n"
            "`/inv_saham jual [kode] [jumlah_rupiah]`\n\n"
            "Contoh: `/inv_saham beli BBCA 1000000`",
            parse_mode="Markdown"
        )
        return

    aksi  = args[0].lower()
    kode  = args[1].upper()
    try:
        jumlah = float(args[2].replace(".","").replace(",",""))
    except:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return

    catatan = " ".join(args[3:]) if len(args) > 3 else "-"
    data    = load_data()
    ud      = get_ud(data, update.effective_user.id)
    ud["investasi"].append({
        "jenis": "saham", "kode": kode, "tipe": aksi,
        "jumlah": jumlah, "catatan": catatan,
        "tanggal": datetime.now().isoformat()
    })
    save_data(data)

    emoji = "📊" if aksi == "beli" else "💹"
    await update.message.reply_text(
        f"{emoji} *Investasi Saham Dicatat!*\n\n"
        f"Aksi: *{aksi.upper()} {kode}*\n"
        f"Nilai: *{rp_full(jumlah)}*\n"
        f"Catatan: {catatan}",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════════════════
# INVESTASI — VALAS
# ══════════════════════════════════════════════════════════════════════════════

async def inv_valas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /inv_valas beli USD 500000   → beli USD senilai Rp500rb (kurs realtime)
    /inv_valas jual USD 300000
    /inv_valas beli USD 500000 manual 16000  → kurs manual
    """
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "❌ Format:\n"
            "`/inv_valas beli [mata_uang] [jumlah_rupiah]`\n"
            "`/inv_valas jual [mata_uang] [jumlah_rupiah]`\n\n"
            f"Mata uang: {', '.join(VALAS_LIST)}\n"
            "Contoh: `/inv_valas beli USD 500000`",
            parse_mode="Markdown"
        )
        return

    aksi  = args[0].lower()
    cur   = args[1].upper()
    try:
        jumlah = float(args[2].replace(".","").replace(",",""))
    except:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return

    if cur not in VALAS_LIST:
        await update.message.reply_text(f"❌ Mata uang tidak didukung.\nPilih: {', '.join(VALAS_LIST)}")
        return

    # Kurs manual atau realtime
    if len(args) >= 5 and args[3].lower() == "manual":
        try:
            kurs = float(args[4].replace(".","").replace(",",""))
            sumber = "manual"
        except:
            await update.message.reply_text("❌ Kurs manual tidak valid.")
            return
    elif FX_API:
        msg = await update.message.reply_text(f"⏳ Mengambil kurs {cur}...")
        rates = await get_valas_prices()
        if not rates or cur not in rates:
            await msg.edit_text(f"❌ Gagal ambil kurs. Gunakan manual:\n`/inv_valas {aksi} {cur} {int(jumlah)} manual [kurs]`", parse_mode="Markdown")
            return
        kurs = rates[cur]
        sumber = "realtime"
        await msg.delete()
    else:
        await update.message.reply_text(
            "⚠️ FX_API_KEY belum diset. Gunakan kurs manual:\n"
            f"`/inv_valas {aksi} {cur} {int(jumlah)} manual [kurs_per_{cur}]`\n"
            "Contoh: `/inv_valas beli USD 500000 manual 16200`",
            parse_mode="Markdown"
        )
        return

    unit_beli = jumlah / kurs
    data = load_data()
    ud   = get_ud(data, update.effective_user.id)
    ud["investasi"].append({
        "jenis": "valas", "mata_uang": cur, "tipe": aksi,
        "jumlah": jumlah, "kurs": kurs, "unit": unit_beli,
        "sumber_harga": sumber, "tanggal": datetime.now().isoformat()
    })
    save_data(data)

    emoji = "💱" if aksi == "beli" else "💵"
    await update.message.reply_text(
        f"{emoji} *Investasi Valas Dicatat!*\n\n"
        f"Aksi: *{aksi.upper()} {cur}*\n"
        f"Nilai: *{rp_full(jumlah)}*\n"
        f"Kurs: 1 {cur} = {rp_full(kurs)} ({sumber})\n"
        f"Qty: ≈ {unit_beli:.4f} {cur}",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════════════════
# /inv_list — Portofolio lengkap + valuasi realtime
# ══════════════════════════════════════════════════════════════════════════════

async def inv_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud   = get_ud(data, update.effective_user.id)
    inv  = ud["investasi"]

    if not inv:
        await update.message.reply_text("_Belum ada investasi._", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("⏳ Mengambil harga realtime untuk valuasi...")

    # Ambil semua harga sekaligus
    crypto_prices, gold_data, valas_rates = await asyncio.gather(
        get_crypto_prices(),
        get_gold_price_idr() if GOLD_API else asyncio.coroutine(lambda: {})(),
        get_valas_prices()   if FX_API   else asyncio.coroutine(lambda: {})(),
    )

    teks = "📈 *Portofolio Investasi*\n\n"
    total_modal = 0
    total_nilai_kini = 0

    # ── EMAS ─────────────────────────────────────────────────────────────────
    emas_items = [i for i in inv if i["jenis"] == "emas"]
    if emas_items:
        gram_beli = sum(i["gram"] for i in emas_items if i["tipe"] == "beli")
        gram_jual = sum(i["gram"] for i in emas_items if i["tipe"] == "jual")
        modal     = sum(i["jumlah"] for i in emas_items if i["tipe"] == "beli")
        hasil_jual= sum(i["jumlah"] for i in emas_items if i["tipe"] == "jual")
        gram_aktif= gram_beli - gram_jual
        total_modal += modal

        teks += "🥇 *EMAS*\n"
        teks += f"  Modal beli: {rp_full(modal)} ({gram_beli}g)\n"
        if gram_jual > 0:
            teks += f"  Sudah dijual: {gram_jual}g ({rp_full(hasil_jual)})\n"
        teks += f"  Aktif: *{gram_aktif:.2f} gram*\n"
        if gold_data and gram_aktif > 0:
            harga_kini = gold_data["price_gram"]
            nilai_kini = gram_aktif * harga_kini
            total_nilai_kini += nilai_kini
            untung = nilai_kini - (modal - hasil_jual)
            teks += f"  Harga kini: {rp_full(harga_kini)}/gram\n"
            teks += f"  Nilai kini: *{rp_full(nilai_kini)}*\n"
            teks += f"  {'🟢 Untung' if untung >= 0 else '🔴 Rugi'}: {rp_full(abs(untung))}\n"
        teks += "\n"

    # ── CRYPTO ────────────────────────────────────────────────────────────────
    crypto_items = [i for i in inv if i["jenis"] == "crypto"]
    if crypto_items:
        teks += "🪙 *CRYPTO*\n"
        per_coin = defaultdict(lambda: {"beli":0,"jual":0,"qty_beli":0,"qty_jual":0})
        for i in crypto_items:
            per_coin[i["coin"]][i["tipe"]] += i["jumlah"]
            per_coin[i["coin"]][f"qty_{i['tipe']}"] += i.get("coin_qty", 0)

        for coin, d in per_coin.items():
            modal_coin = d["beli"]
            total_modal += modal_coin
            qty_aktif  = d["qty_beli"] - d["qty_jual"]
            teks += f"  ₿ *{coin}*\n"
            teks += f"    Modal: {rp_full(modal_coin)} | Qty aktif: {qty_aktif:.6f}\n"
            if crypto_prices and coin in crypto_prices and qty_aktif > 0:
                harga_kini = crypto_prices[coin]["price"]
                nilai_kini = qty_aktif * harga_kini
                total_nilai_kini += nilai_kini
                untung = nilai_kini - (modal_coin - d["jual"])
                teks += f"    Harga kini: {rp_full(harga_kini)}\n"
                teks += f"    Nilai kini: *{rp_full(nilai_kini)}* {pct_str(crypto_prices[coin]['change'])}\n"
                teks += f"    {'🟢' if untung >= 0 else '🔴'} {rp_full(abs(untung))}\n"
        teks += "\n"

    # ── SAHAM ─────────────────────────────────────────────────────────────────
    saham_items = [i for i in inv if i["jenis"] == "saham"]
    if saham_items:
        teks += "📊 *SAHAM*\n"
        per_kode = defaultdict(lambda: {"beli":0,"jual":0})
        for i in saham_items:
            per_kode[i["kode"]][i["tipe"]] += i["jumlah"]
        for kode, d in per_kode.items():
            modal_saham = d["beli"]
            total_modal += modal_saham
            aktif = modal_saham - d["jual"]
            teks += f"  📈 *{kode}*: Modal {rp_full(modal_saham)} | Aktif {rp_full(aktif)}\n"
            if d["jual"] > 0:
                rl = d["jual"] - modal_saham
                teks += f"    {'🟢' if rl >= 0 else '🔴'} Realized: {rp_full(abs(rl))}\n"
        teks += "  _(Harga saham Indonesia tidak tersedia via API gratis)_\n\n"

    # ── VALAS ─────────────────────────────────────────────────────────────────
    valas_items = [i for i in inv if i["jenis"] == "valas"]
    if valas_items:
        teks += "💱 *VALAS*\n"
        per_cur = defaultdict(lambda: {"beli":0,"jual":0,"unit_beli":0,"unit_jual":0})
        for i in valas_items:
            per_cur[i["mata_uang"]][i["tipe"]] += i["jumlah"]
            per_cur[i["mata_uang"]][f"unit_{i['tipe']}"] += i.get("unit", 0)
        for cur, d in per_cur.items():
            modal_valas = d["beli"]
            total_modal += modal_valas
            unit_aktif  = d["unit_beli"] - d["unit_jual"]
            teks += f"  🏳 *{cur}*\n"
            teks += f"    Modal: {rp_full(modal_valas)} | Aktif: {unit_aktif:.4f} {cur}\n"
            if valas_rates and cur in valas_rates and unit_aktif > 0:
                nilai_kini = unit_aktif * valas_rates[cur]
                total_nilai_kini += nilai_kini
                untung = nilai_kini - (modal_valas - d["jual"])
                teks += f"    Kurs kini: 1 {cur} = {rp_full(valas_rates[cur])}\n"
                teks += f"    Nilai kini: *{rp_full(nilai_kini)}*\n"
                teks += f"    {'🟢' if untung >= 0 else '🔴'} {rp_full(abs(untung))}\n"
        teks += "\n"

    # ── TOTAL ─────────────────────────────────────────────────────────────────
    teks += f"━━━━━━━━━━━━━━\n"
    teks += f"💼 Total Modal: *{rp_full(total_modal)}*\n"
    if total_nilai_kini > 0:
        pl = total_nilai_kini - total_modal
        teks += f"📊 Nilai Kini: *{rp_full(total_nilai_kini)}*\n"
        teks += f"{'🟢 Untung' if pl >= 0 else '🔴 Rugi'} Total: *{rp_full(abs(pl))}*"

    await msg.edit_text(teks, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# KEUANGAN BIASA
# ══════════════════════════════════════════════════════════════════════════════

async def keluar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/keluar 25000 makan siang`", parse_mode="Markdown")
        return
    try:
        jumlah = float(args[0].replace(".","").replace(",",""))
    except:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return
    kategori = args[1].lower()
    catatan  = " ".join(args[2:]) if len(args) > 2 else "-"
    data     = load_data()
    ud       = get_ud(data, update.effective_user.id)
    ud["transaksi"].append({"tipe":"keluar","jumlah":jumlah,"kategori":kategori,"catatan":catatan,"tanggal":datetime.now().isoformat()})
    save_data(data)
    peringatan = ""
    if kategori in ud.get("budget",{}):
        bln = date.today().strftime("%Y-%m")
        total_k = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"]=="keluar" and t["kategori"]==kategori and t["tanggal"][:7]==bln)
        batas = ud["budget"][kategori]; persen = (total_k/batas)*100
        if persen >= 100: peringatan = f"\n\n⚠️ *Budget {kategori} HABIS!*"
        elif persen >= 80: peringatan = f"\n\n⚠️ Sisa budget {kategori}: {rp_full(batas-total_k)}"
    await update.message.reply_text(f"✅ Pengeluaran dicatat!\n💸 *{rp_full(jumlah)}*\n📂 {kategori} | 📝 {catatan}{peringatan}", parse_mode="Markdown")

async def masuk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/masuk 5000000 gaji`", parse_mode="Markdown")
        return
    try:
        jumlah = float(args[0].replace(".","").replace(",",""))
    except:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return
    sumber  = args[1].lower()
    catatan = " ".join(args[2:]) if len(args) > 2 else "-"
    data    = load_data()
    ud      = get_ud(data, update.effective_user.id)
    ud["transaksi"].append({"tipe":"masuk","jumlah":jumlah,"kategori":sumber,"catatan":catatan,"tanggal":datetime.now().isoformat()})
    save_data(data)
    await update.message.reply_text(f"✅ Pemasukan dicatat!\n💰 *{rp_full(jumlah)}*\n📂 {sumber} | 📝 {catatan}", parse_mode="Markdown")

async def ringkasan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data(); ud = get_ud(data, update.effective_user.id); trx = ud["transaksi"]
    hi = date.today().isoformat(); bln = date.today().strftime("%Y-%m")
    kh = sum(t["jumlah"] for t in trx if t["tipe"]=="keluar" and t["tanggal"][:10]==hi)
    mh = sum(t["jumlah"] for t in trx if t["tipe"]=="masuk"  and t["tanggal"][:10]==hi)
    kb = sum(t["jumlah"] for t in trx if t["tipe"]=="keluar" and t["tanggal"][:7]==bln)
    mb = sum(t["jumlah"] for t in trx if t["tipe"]=="masuk"  and t["tanggal"][:7]==bln)
    saldo = mb - kb
    ti  = sum(i["jumlah"] for i in ud["investasi"] if i["tipe"]=="beli")
    th  = sum(h["jumlah"] for h in ud["hutang"]    if not h.get("lunas"))
    tp  = sum(p["jumlah"] for p in ud["piutang"]   if not p.get("lunas"))
    await update.message.reply_text(
        f"📊 *Ringkasan — {date.today().strftime('%d %B %Y')}*\n\n"
        f"*Hari Ini:*\n💰 Masuk: {rp_full(mh)}\n💸 Keluar: {rp_full(kh)}\n\n"
        f"*Bulan Ini:*\n💰 Masuk: {rp_full(mb)}\n💸 Keluar: {rp_full(kb)}\n"
        f"{'🟢' if saldo>=0 else '🔴'} Saldo: *{rp_full(saldo)}*\n\n"
        f"*Overview:*\n📈 Investasi: {rp_full(ti)}\n🤝 Hutang: {rp_full(th)}\n💵 Piutang: {rp_full(tp)}",
        parse_mode="Markdown"
    )

async def laporan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data(); ud = get_ud(data, update.effective_user.id); bln = date.today().strftime("%Y-%m")
    kk = defaultdict(float); mk = defaultdict(float)
    for t in ud["transaksi"]:
        if t["tanggal"][:7] != bln: continue
        (kk if t["tipe"]=="keluar" else mk)[t["kategori"]] += t["jumlah"]
    teks = f"📋 *Laporan {date.today().strftime('%B %Y')}*\n\n"
    if mk:
        teks += "💰 *PEMASUKAN:*\n"
        for k,v in sorted(mk.items(),key=lambda x:-x[1]): teks += f"  • {k}: {rp_full(v)}\n"
        teks += f"  *Total: {rp_full(sum(mk.values()))}*\n\n"
    if kk:
        teks += "💸 *PENGELUARAN:*\n"
        for k,v in sorted(kk.items(),key=lambda x:-x[1]):
            bi = ""
            if k in ud.get("budget",{}):
                bts = ud["budget"][k]; pct = min((v/bts)*100,100)
                bar = "█"*int(pct//10)+"░"*(10-int(pct//10)); bi = f" [{bar}] {pct:.0f}%"
            teks += f"  • {k}: {rp_full(v)}{bi}\n"
        teks += f"  *Total: {rp_full(sum(kk.values()))}*"
    if not mk and not kk: teks += "_Belum ada transaksi bulan ini._"
    await update.message.reply_text(teks, parse_mode="Markdown")

async def riwayat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data(); ud = get_ud(data, update.effective_user.id)
    trx = ud["transaksi"][-10:][::-1]
    if not trx:
        await update.message.reply_text("_Belum ada transaksi._", parse_mode="Markdown"); return
    teks = "🕐 *10 Transaksi Terakhir:*\n\n"
    for t in trx:
        e = "💸" if t["tipe"]=="keluar" else "💰"
        tgl = datetime.fromisoformat(t["tanggal"]).strftime("%d/%m %H:%M")
        teks += f"{e} `{tgl}` | {t['kategori']} | *{rp_full(t['jumlah'])}*\n"
        if t["catatan"] != "-": teks += f"   _{t['catatan']}_\n"
    await update.message.reply_text(teks, parse_mode="Markdown")

async def budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/budget makan 1500000`", parse_mode="Markdown"); return
    kat = args[0].lower()
    try: jml = float(args[1].replace(".","").replace(",",""))
    except: await update.message.reply_text("❌ Jumlah tidak valid."); return
    data = load_data(); ud = get_ud(data, update.effective_user.id)
    ud["budget"][kat] = jml; save_data(data)
    await update.message.reply_text(f"✅ Budget *{kat}* = *{rp_full(jml)}*/bulan", parse_mode="Markdown")

async def cek_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data(); ud = get_ud(data, update.effective_user.id); budgets = ud.get("budget",{})
    if not budgets:
        await update.message.reply_text("_Belum ada budget._", parse_mode="Markdown"); return
    bln = date.today().strftime("%Y-%m"); teks = f"🎯 *Budget {date.today().strftime('%B %Y')}:*\n\n"
    for kat, bts in budgets.items():
        trp = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"]=="keluar" and t["kategori"]==kat and t["tanggal"][:7]==bln)
        sisa = bts - trp; pct = min((trp/bts)*100,100)
        bar  = "█"*int(pct//10)+"░"*(10-int(pct//10))
        e    = "🔴" if pct>=100 else "🟡" if pct>=80 else "🟢"
        teks += f"{e} *{kat}*\n  [{bar}] {pct:.0f}%\n  {rp_full(trp)} / {rp_full(bts)} | sisa {rp_full(max(sisa,0))}\n\n"
    await update.message.reply_text(teks, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# HUTANG & PIUTANG
# ══════════════════════════════════════════════════════════════════════════════

async def hutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/hutang 200000 Budi beli makan`", parse_mode="Markdown"); return
    try: jml = float(args[0].replace(".","").replace(",",""))
    except: await update.message.reply_text("❌ Jumlah tidak valid."); return
    nama = args[1]; cat = " ".join(args[2:]) if len(args)>2 else "-"
    data = load_data(); ud = get_ud(data, update.effective_user.id)
    ud["hutang"].append({"jumlah":jml,"nama":nama,"catatan":cat,"tanggal":datetime.now().isoformat(),"lunas":False})
    save_data(data)
    await update.message.reply_text(f"✅ Hutang dicatat!\n🤝 Kamu hutang ke *{nama}*\n💸 *{rp_full(jml)}*\n📝 {cat}", parse_mode="Markdown")

async def piutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/piutang 150000 Ani pinjam`", parse_mode="Markdown"); return
    try: jml = float(args[0].replace(".","").replace(",",""))
    except: await update.message.reply_text("❌ Jumlah tidak valid."); return
    nama = args[1]; cat = " ".join(args[2:]) if len(args)>2 else "-"
    data = load_data(); ud = get_ud(data, update.effective_user.id)
    ud["piutang"].append({"jumlah":jml,"nama":nama,"catatan":cat,"tanggal":datetime.now().isoformat(),"lunas":False})
    save_data(data)
    await update.message.reply_text(f"✅ Piutang dicatat!\n💵 *{nama}* hutang ke kamu\n💰 *{rp_full(jml)}*\n📝 {cat}", parse_mode="Markdown")

async def hutang_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data(); ud = get_ud(data, update.effective_user.id); items = ud["hutang"]
    if not items:
        await update.message.reply_text("_Belum ada catatan hutang._", parse_mode="Markdown"); return
    belum = [h for h in items if not h["lunas"]]; sudah = [h for h in items if h["lunas"]]
    teks  = "🤝 *Daftar Hutang Kamu:*\n\n"
    if belum:
        teks += "❌ *Belum Lunas:*\n"
        for h in belum:
            idx = items.index(h)+1; tgl = datetime.fromisoformat(h["tanggal"]).strftime("%d/%m/%Y")
            teks += f"  #{idx} *{h['nama']}* — {rp_full(h['jumlah'])}\n       📝 {h['catatan']} | 🗓 {tgl}\n       → `/bayar_hutang {idx}`\n"
    if sudah:
        teks += "\n✅ *Sudah Lunas:*\n"
        for h in sudah: teks += f"  ~~{h['nama']} — {rp_full(h['jumlah'])}~~\n"
    teks += f"\n💸 *Total belum lunas: {rp_full(sum(h['jumlah'] for h in belum))}*"
    await update.message.reply_text(teks, parse_mode="Markdown")

async def piutang_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data(); ud = get_ud(data, update.effective_user.id); items = ud["piutang"]
    if not items:
        await update.message.reply_text("_Belum ada catatan piutang._", parse_mode="Markdown"); return
    belum = [p for p in items if not p["lunas"]]; sudah = [p for p in items if p["lunas"]]
    teks  = "💵 *Daftar Piutang:*\n\n"
    if belum:
        teks += "❌ *Belum Dibayar:*\n"
        for p in belum:
            idx = items.index(p)+1; tgl = datetime.fromisoformat(p["tanggal"]).strftime("%d/%m/%Y")
            teks += f"  #{idx} *{p['nama']}* — {rp_full(p['jumlah'])}\n       📝 {p['catatan']} | 🗓 {tgl}\n       → `/terima_piutang {idx}`\n"
    if sudah:
        teks += "\n✅ *Sudah Diterima:*\n"
        for p in sudah: teks += f"  ~~{p['nama']} — {rp_full(p['jumlah'])}~~\n"
    teks += f"\n💰 *Total belum diterima: {rp_full(sum(p['jumlah'] for p in belum))}*"
    await update.message.reply_text(teks, parse_mode="Markdown")

async def bayar_hutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Format: `/bayar_hutang [nomor]`", parse_mode="Markdown"); return
    try: idx = int(args[0])-1
    except: await update.message.reply_text("❌ Nomor tidak valid."); return
    data = load_data(); ud = get_ud(data, update.effective_user.id)
    if idx < 0 or idx >= len(ud["hutang"]):
        await update.message.reply_text("❌ Nomor tidak ditemukan."); return
    if ud["hutang"][idx]["lunas"]:
        await update.message.reply_text("ℹ️ Hutang ini sudah lunas."); return
    ud["hutang"][idx]["lunas"] = True; ud["hutang"][idx]["tanggal_lunas"] = datetime.now().isoformat()
    save_data(data); h = ud["hutang"][idx]
    await update.message.reply_text(f"✅ Hutang ke *{h['nama']}* sebesar *{rp_full(h['jumlah'])}* lunas! 🎉", parse_mode="Markdown")

async def terima_piutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Format: `/terima_piutang [nomor]`", parse_mode="Markdown"); return
    try: idx = int(args[0])-1
    except: await update.message.reply_text("❌ Nomor tidak valid."); return
    data = load_data(); ud = get_ud(data, update.effective_user.id)
    if idx < 0 or idx >= len(ud["piutang"]):
        await update.message.reply_text("❌ Nomor tidak ditemukan."); return
    if ud["piutang"][idx]["lunas"]:
        await update.message.reply_text("ℹ️ Piutang ini sudah diterima."); return
    ud["piutang"][idx]["lunas"] = True; ud["piutang"][idx]["tanggal_lunas"] = datetime.now().isoformat()
    save_data(data); p = ud["piutang"][idx]
    await update.message.reply_text(f"✅ Piutang dari *{p['nama']}* sebesar *{rp_full(p['jumlah'])}* diterima! 💰", parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# GRAFIK
# ══════════════════════════════════════════════════════════════════════════════

BG = "#0f0f1a"; PANEL = "#1a1a2e"
WK = ["#FF6B6B","#FF8E8E","#FF5252","#E53935","#FF7043","#EF9A9A","#FFCDD2","#D32F2F","#FF8A65","#FFAB91"]
WM = ["#4ECDC4","#26C6DA","#00BCD4","#26A69A","#4DB6AC","#80DEEA","#B2DFDB","#00897B","#00ACC1","#80CBC4"]

async def grafik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data(); ud = get_ud(data, update.effective_user.id)
    bln = date.today().strftime("%Y-%m"); nb = date.today().strftime("%B %Y")
    kk = defaultdict(float); mk = defaultdict(float)
    for t in ud["transaksi"]:
        if t["tanggal"][:7] != bln: continue
        (kk if t["tipe"]=="keluar" else mk)[t["kategori"]] += t["jumlah"]
    tk = sum(kk.values()); tm = sum(mk.values()); saldo = tm - tk
    ti = sum(i["jumlah"] for i in ud["investasi"] if i["tipe"]=="beli")
    th = sum(h["jumlah"] for h in ud["hutang"]    if not h.get("lunas"))
    tp = sum(p["jumlah"] for p in ud["piutang"]   if not p.get("lunas"))
    hl = [(date.today()-timedelta(days=i)) for i in range(13,-1,-1)]
    tr_k = [sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"]=="keluar" and t["tanggal"][:10]==h.isoformat()) for h in hl]
    tr_m = [sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"]=="masuk"  and t["tanggal"][:10]==h.isoformat()) for h in hl]
    lb_h = [h.strftime("%d/%m") for h in hl]

    if not kk and not mk and ti==0 and th==0:
        await update.message.reply_text("_Belum ada data._", parse_mode="Markdown"); return

    fig = plt.figure(figsize=(14,11), facecolor=BG)
    gs  = gridspec.GridSpec(3,3,figure=fig,hspace=0.55,wspace=0.35,left=0.05,right=0.97,top=0.91,bottom=0.07)
    ax_pk = fig.add_subplot(gs[0,0]); ax_pm = fig.add_subplot(gs[0,1])
    ax_info = fig.add_subplot(gs[0,2]); ax_bar = fig.add_subplot(gs[1,:])
    ax_tr  = fig.add_subplot(gs[2,:])
    for ax in [ax_pk,ax_pm,ax_info,ax_bar,ax_tr]: ax.set_facecolor(PANEL)
    fig.text(0.5,0.95,f"📊 Laporan Keuangan — {nb}",ha="center",color="white",fontsize=15,fontweight="bold")

    def draw_pie(ax, vals_dict, colors, title, title_color, total):
        if vals_dict:
            ks = list(vals_dict.keys()); vs = list(vals_dict.values()); cs = colors[:len(ks)]
            _,_,ats = ax.pie(vs,colors=cs,autopct="%1.0f%%",startangle=90,pctdistance=0.72,
                             wedgeprops=dict(width=0.55,edgecolor=PANEL,linewidth=1.5))
            for at in ats: at.set(color="white",fontsize=7,fontweight="bold")
            ax.text(0,0,rp(total),ha="center",va="center",color="white",fontsize=8,fontweight="bold")
            leg = [mpatches.Patch(color=cs[i],label=f"{ks[i]} ({rp(vs[i])})") for i in range(len(ks))]
            ax.legend(handles=leg,loc="lower center",bbox_to_anchor=(0.5,-0.3),ncol=1,frameon=False,labelcolor="white",fontsize=7)
        else:
            ax.text(0.5,0.5,"Tidak ada data",ha="center",va="center",color="#888",transform=ax.transAxes); ax.axis("off")
        ax.set_title(title,color=title_color,fontsize=10,fontweight="bold",pad=8)

    draw_pie(ax_pk, kk, WK, "💸 Pengeluaran", "#FF6B6B", tk)
    draw_pie(ax_pm, mk, WM, "💰 Pemasukan",   "#4ECDC4", tm)

    ax_info.axis("off"); ax_info.set_title("📋 Ringkasan",color="white",fontsize=10,fontweight="bold",pad=8)
    for i,(lbl,val,clr) in enumerate([("Total Masuk",rp_full(tm),"#4ECDC4"),("Total Keluar",rp_full(tk),"#FF6B6B"),("Saldo",rp_full(saldo),"#FFD700" if saldo>=0 else "#FF4444")]):
        y = 0.78 - i*0.26
        ax_info.add_patch(plt.Rectangle((0.05,y-0.1),0.9,0.2,transform=ax_info.transAxes,color="#0f0f1a",clip_on=False,zorder=0))
        ax_info.text(0.5,y+0.04,lbl,ha="center",va="center",transform=ax_info.transAxes,color="#aaa",fontsize=8)
        ax_info.text(0.5,y-0.06,val,ha="center",va="center",transform=ax_info.transAxes,color=clr,fontsize=9,fontweight="bold")
    ax_info.text(0.5,0.04,"🟢 Surplus" if saldo>=0 else "🔴 Defisit",ha="center",va="center",transform=ax_info.transAxes,color="#FFD700" if saldo>=0 else "#FF4444",fontsize=9,fontweight="bold")

    ax_bar.set_title("💼 Investasi & Hutang Piutang",color="white",fontsize=10,fontweight="bold",pad=8)
    cats = ["Investasi\nTotal","Hutang\nBelum Lunas","Piutang\nBelum Diterima"]
    vals = [ti, th, tp]; warna = ["#FFD700","#FF6B6B","#4ECDC4"]
    bars = ax_bar.bar(cats,vals,color=warna,alpha=0.85,edgecolor=PANEL,linewidth=1.5,width=0.4)
    ax_bar.yaxis.set_visible(False); ax_bar.spines[:].set_visible(False)
    ax_bar.tick_params(colors="white"); ax_bar.set_xticklabels(cats,color="white",fontsize=9)
    mx = max(vals) if max(vals)>0 else 1
    for bar,val in zip(bars,vals):
        ax_bar.text(bar.get_x()+bar.get_width()/2,bar.get_height()+mx*0.03,rp_full(val),ha="center",color="white",fontsize=8,fontweight="bold")

    x = range(len(hl))
    ax_tr.fill_between(x,tr_m,alpha=0.15,color="#4ECDC4"); ax_tr.fill_between(x,tr_k,alpha=0.15,color="#FF6B6B")
    ax_tr.plot(x,tr_m,color="#4ECDC4",linewidth=2,marker="o",markersize=4,label="Masuk")
    ax_tr.plot(x,tr_k,color="#FF6B6B",linewidth=2,marker="o",markersize=4,label="Keluar")
    ax_tr.set_xticks(list(x)); ax_tr.set_xticklabels(lb_h,color="white",fontsize=7.5)
    ax_tr.yaxis.set_visible(False); ax_tr.spines[:].set_visible(False)
    ax_tr.set_title("📈 Tren 14 Hari Terakhir",color="white",fontsize=10,fontweight="bold",pad=8)
    ax_tr.legend(frameon=False,labelcolor="white",fontsize=8,loc="upper left")
    mv = max(max(tr_m,default=0),max(tr_k,default=0))
    for i,(m,k) in enumerate(zip(tr_m,tr_k)):
        if m>0: ax_tr.text(i,m+max(mv*0.04,1),rp(m),ha="center",color="#4ECDC4",fontsize=6)
        if k>0: ax_tr.text(i,k+max(mv*0.04,1),rp(k),ha="center",color="#FF6B6B",fontsize=6)

    buf = io.BytesIO()
    plt.savefig(buf,format="png",dpi=150,facecolor=BG,bbox_inches="tight"); buf.seek(0); plt.close()
    caption = (f"📊 *Grafik Keuangan — {nb}*\n💰 Masuk: {rp_full(tm)}\n💸 Keluar: {rp_full(tk)}\n"
               f"{'🟢 Surplus' if saldo>=0 else '🔴 Defisit'}: {rp_full(abs(saldo))}")
    await update.message.reply_photo(photo=buf,caption=caption,parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# PENGINGAT & RESET
# ══════════════════════════════════════════════════════════════════════════════

async def kirim_reminder(context: ContextTypes.DEFAULT_TYPE):
    uid = context.job.data["user_id"]; data = load_data(); ud = get_ud(data, uid)
    hi  = date.today().isoformat(); bln = date.today().strftime("%Y-%m")
    kh  = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"]=="keluar" and t["tanggal"][:10]==hi)
    mh  = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"]=="masuk"  and t["tanggal"][:10]==hi)
    kb  = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"]=="keluar" and t["tanggal"][:7]==bln)
    mb  = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"]=="masuk"  and t["tanggal"][:7]==bln)
    th  = sum(h["jumlah"] for h in ud["hutang"]    if not h.get("lunas"))
    tp  = sum(p["jumlah"] for p in ud["piutang"]   if not p.get("lunas"))
    teks = (f"⏰ *Pengingat Keuangan Harian*\n_{date.today().strftime('%A, %d %B %Y')}_\n\n"
            f"*Hari Ini:*\n💰 Masuk: {rp_full(mh)}\n💸 Keluar: {rp_full(kh)}\n\n"
            f"*Bulan Ini:*\n💰 Masuk: {rp_full(mb)}\n💸 Keluar: {rp_full(kb)}\n"
            f"{'🟢' if mb>=kb else '🔴'} Saldo: *{rp_full(mb-kb)}*\n\n")
    if th>0: teks += f"⚠️ Hutang belum lunas: *{rp_full(th)}*\n"
    if tp>0: teks += f"💵 Piutang belum diterima: *{rp_full(tp)}*\n"
    teks += "\n_Jangan lupa catat transaksi hari ini ya!_ 📝"
    await context.bot.send_message(chat_id=uid,text=teks,parse_mode="Markdown")

async def reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args; uid = update.effective_user.id
    if not args:
        await update.message.reply_text("❌ Format: `/reminder 20:00` atau `/reminder off`", parse_mode="Markdown"); return
    if args[0].lower() == "off":
        for job in context.job_queue.get_jobs_by_name(f"reminder_{uid}"): job.schedule_removal()
        data = load_data(); ud = get_ud(data, uid); ud["reminder"] = None; save_data(data)
        await update.message.reply_text("✅ Pengingat dimatikan."); return
    try: jam, mnt = map(int, args[0].split(":")); waktu = time(jam, mnt)
    except: await update.message.reply_text("❌ Format salah. Contoh: `/reminder 20:00`", parse_mode="Markdown"); return
    for job in context.job_queue.get_jobs_by_name(f"reminder_{uid}"): job.schedule_removal()
    context.job_queue.run_daily(kirim_reminder,time=waktu,data={"user_id":uid},name=f"reminder_{uid}")
    data = load_data(); ud = get_ud(data, uid); ud["reminder"] = args[0]; save_data(data)
    await update.message.reply_text(f"⏰ Pengingat diset jam *{args[0]}* setiap hari! 😊", parse_mode="Markdown")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("✅ Ya, hapus semua",callback_data="reset_ya"),
           InlineKeyboardButton("❌ Batal",callback_data="reset_tidak")]]
    await update.message.reply_text("⚠️ *Yakin mau hapus SEMUA data?*",parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(kb))

async def reset_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "reset_ya":
        data = load_data(); data[str(q.from_user.id)] = {"transaksi":[],"budget":{},"reminder":None,"investasi":[],"hutang":[],"piutang":[]}
        save_data(data); await q.edit_message_text("🗑 Semua data dihapus.")
    else: await q.edit_message_text("✅ Reset dibatalkan.")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(TOKEN).build()
    cmds = [
        ("start",start),("help",start),
        ("keluar",keluar),("masuk",masuk),
        ("ringkasan",ringkasan),("laporan",laporan),("riwayat",riwayat),
        ("budget",budget),("cek_budget",cek_budget),
        ("inv_emas",inv_emas),("inv_crypto",inv_crypto),
        ("inv_saham",inv_saham),("inv_valas",inv_valas),("inv_list",inv_list),
        ("harga_crypto",harga_crypto),("harga_emas",harga_emas),("harga_valas",harga_valas),
        ("hutang",hutang),("piutang",piutang),
        ("hutang_list",hutang_list),("piutang_list",piutang_list),
        ("bayar_hutang",bayar_hutang),("terima_piutang",terima_piutang),
        ("grafik",grafik),("reminder",reminder),("reset",reset),
    ]
    for name, fn in cmds:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(reset_cb, pattern="^reset_"))
    print("🤖 Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
