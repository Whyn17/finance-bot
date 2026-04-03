"""
Bot Telegram: Personal Finance Tracker
Fitur: Keuangan, Investasi, Hutang & Piutang, Grafik, Pengingat
"""

import json
import os
import io
from datetime import datetime, date, time, timedelta
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

TOKEN = os.environ.get("BOT_TOKEN")
DATA_FILE = "keuangan.json"

# ─── Simpan & Load Data ───────────────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user_data(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "transaksi": [], "budget": {}, "reminder": None,
            "investasi": [], "hutang": [], "piutang": []
        }
    for key in ["investasi", "hutang", "piutang"]:
        if key not in data[uid]:
            data[uid][key] = []
    if "reminder" not in data[uid]:
        data[uid]["reminder"] = None
    return data[uid]

def format_rupiah(amount):
    if amount >= 1_000_000:
        return f"Rp {amount/1_000_000:.1f}jt"
    elif amount >= 1_000:
        return f"Rp {amount/1_000:.0f}rb"
    return f"Rp {amount:.0f}"

def format_rupiah_full(amount):
    return f"Rp {amount:,.0f}".replace(",", ".")

# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nama = update.effective_user.first_name
    teks = (
        f"👋 Halo, *{nama}*! Selamat datang di *Finance Tracker Bot* 💰\n\n"

        "💸 *Pengeluaran & Pemasukan:*\n"
        "`/keluar 50000 makan siang`\n"
        "`/masuk 3000000 gaji`\n"
        "`/ringkasan` – saldo hari ini\n"
        "`/laporan` – rincian bulan ini\n"
        "`/riwayat` – 10 transaksi terakhir\n"
        "`/budget makan 1500000`\n"
        "`/cek_budget` – sisa budget\n\n"

        "📈 *Investasi:*\n"
        "`/investasi beli saham 1000000 BBCA` – catat beli\n"
        "`/investasi jual saham 1200000 BBCA` – catat jual\n"
        "`/inv_list` – lihat portofolio\n\n"

        "🤝 *Hutang & Piutang:*\n"
        "`/hutang 200000 Budi beli makan` – kamu hutang ke Budi\n"
        "`/piutang 150000 Ani pinjam` – Ani hutang ke kamu\n"
        "`/bayar_hutang 1` – tandai hutang #1 lunas\n"
        "`/terima_piutang 1` – tandai piutang #1 diterima\n"
        "`/hutang_list` – daftar hutang\n"
        "`/piutang_list` – daftar piutang\n\n"

        "📊 *Grafik & Pengingat:*\n"
        "`/grafik` – grafik keuangan bulan ini\n"
        "`/reminder 20:00` – pengingat harian\n"
        "`/reminder off` – matikan pengingat\n\n"

        "🗑 `/reset` – hapus semua data"
    )
    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── /keluar ──────────────────────────────────────────────────────────────────

async def keluar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/keluar 25000 makan siang`", parse_mode="Markdown")
        return
    try:
        jumlah = float(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return

    kategori = args[1].lower()
    catatan = " ".join(args[2:]) if len(args) > 2 else "-"

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    ud["transaksi"].append({
        "tipe": "keluar", "jumlah": jumlah,
        "kategori": kategori, "catatan": catatan,
        "tanggal": datetime.now().isoformat()
    })
    save_data(data)

    peringatan = ""
    if kategori in ud.get("budget", {}):
        bulan_ini = date.today().strftime("%Y-%m")
        total_kat = sum(t["jumlah"] for t in ud["transaksi"]
            if t["tipe"] == "keluar" and t["kategori"] == kategori and t["tanggal"][:7] == bulan_ini)
        batas = ud["budget"][kategori]
        persen = (total_kat / batas) * 100
        if persen >= 100:
            peringatan = f"\n\n⚠️ *Budget {kategori} HABIS!*"
        elif persen >= 80:
            peringatan = f"\n\n⚠️ Budget {kategori} tersisa {format_rupiah_full(batas - total_kat)}"

    await update.message.reply_text(
        f"✅ Pengeluaran dicatat!\n💸 *{format_rupiah_full(jumlah)}*\n"
        f"📂 {kategori} | 📝 {catatan}{peringatan}",
        parse_mode="Markdown"
    )

# ─── /masuk ───────────────────────────────────────────────────────────────────

async def masuk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/masuk 5000000 gaji`", parse_mode="Markdown")
        return
    try:
        jumlah = float(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return

    sumber = args[1].lower()
    catatan = " ".join(args[2:]) if len(args) > 2 else "-"

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    ud["transaksi"].append({
        "tipe": "masuk", "jumlah": jumlah,
        "kategori": sumber, "catatan": catatan,
        "tanggal": datetime.now().isoformat()
    })
    save_data(data)

    await update.message.reply_text(
        f"✅ Pemasukan dicatat!\n💰 *{format_rupiah_full(jumlah)}*\n📂 {sumber} | 📝 {catatan}",
        parse_mode="Markdown"
    )

# ─── /ringkasan ───────────────────────────────────────────────────────────────

async def ringkasan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    transaksi = ud["transaksi"]
    hari_ini = date.today().isoformat()
    bulan_ini = date.today().strftime("%Y-%m")

    keluar_hari = sum(t["jumlah"] for t in transaksi if t["tipe"] == "keluar" and t["tanggal"][:10] == hari_ini)
    masuk_hari  = sum(t["jumlah"] for t in transaksi if t["tipe"] == "masuk"  and t["tanggal"][:10] == hari_ini)
    keluar_bln  = sum(t["jumlah"] for t in transaksi if t["tipe"] == "keluar" and t["tanggal"][:7] == bulan_ini)
    masuk_bln   = sum(t["jumlah"] for t in transaksi if t["tipe"] == "masuk"  and t["tanggal"][:7] == bulan_ini)
    saldo = masuk_bln - keluar_bln

    total_inv     = sum(i["jumlah"] for i in ud["investasi"] if i["tipe"] == "beli" and not i.get("terjual"))
    total_hutang  = sum(h["jumlah"] for h in ud["hutang"]   if not h.get("lunas"))
    total_piutang = sum(p["jumlah"] for p in ud["piutang"]  if not p.get("lunas"))

    await update.message.reply_text(
        f"📊 *Ringkasan — {date.today().strftime('%d %B %Y')}*\n\n"
        f"*Hari Ini:*\n💰 Masuk: {format_rupiah_full(masuk_hari)}\n💸 Keluar: {format_rupiah_full(keluar_hari)}\n\n"
        f"*Bulan Ini:*\n💰 Masuk: {format_rupiah_full(masuk_bln)}\n💸 Keluar: {format_rupiah_full(keluar_bln)}\n"
        f"{'🟢' if saldo >= 0 else '🔴'} Saldo: *{format_rupiah_full(saldo)}*\n\n"
        f"*Overview:*\n"
        f"📈 Investasi aktif: {format_rupiah_full(total_inv)}\n"
        f"🤝 Hutang belum lunas: {format_rupiah_full(total_hutang)}\n"
        f"💵 Piutang belum diterima: {format_rupiah_full(total_piutang)}",
        parse_mode="Markdown"
    )

# ─── /laporan ─────────────────────────────────────────────────────────────────

async def laporan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    bulan_ini = date.today().strftime("%Y-%m")

    keluar_kat = defaultdict(float)
    masuk_kat  = defaultdict(float)
    for t in ud["transaksi"]:
        if t["tanggal"][:7] != bulan_ini:
            continue
        if t["tipe"] == "keluar":
            keluar_kat[t["kategori"]] += t["jumlah"]
        else:
            masuk_kat[t["kategori"]] += t["jumlah"]

    teks = f"📋 *Laporan {date.today().strftime('%B %Y')}*\n\n"
    if masuk_kat:
        teks += "💰 *PEMASUKAN:*\n"
        for kat, jml in sorted(masuk_kat.items(), key=lambda x: -x[1]):
            teks += f"  • {kat}: {format_rupiah_full(jml)}\n"
        teks += f"  *Total: {format_rupiah_full(sum(masuk_kat.values()))}*\n\n"

    if keluar_kat:
        teks += "💸 *PENGELUARAN:*\n"
        for kat, jml in sorted(keluar_kat.items(), key=lambda x: -x[1]):
            budget_info = ""
            if kat in ud.get("budget", {}):
                batas = ud["budget"][kat]
                persen = min((jml / batas) * 100, 100)
                bar = "█" * int(persen // 10) + "░" * (10 - int(persen // 10))
                budget_info = f" [{bar}] {persen:.0f}%"
            teks += f"  • {kat}: {format_rupiah_full(jml)}{budget_info}\n"
        teks += f"  *Total: {format_rupiah_full(sum(keluar_kat.values()))}*"

    if not masuk_kat and not keluar_kat:
        teks += "_Belum ada transaksi bulan ini._"

    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── /riwayat ─────────────────────────────────────────────────────────────────

async def riwayat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    transaksi = ud["transaksi"][-10:][::-1]
    if not transaksi:
        await update.message.reply_text("_Belum ada transaksi._", parse_mode="Markdown")
        return
    teks = "🕐 *10 Transaksi Terakhir:*\n\n"
    for t in transaksi:
        emoji = "💸" if t["tipe"] == "keluar" else "💰"
        tgl = datetime.fromisoformat(t["tanggal"]).strftime("%d/%m %H:%M")
        teks += f"{emoji} `{tgl}` | {t['kategori']} | *{format_rupiah_full(t['jumlah'])}*\n"
        if t["catatan"] != "-":
            teks += f"   _{t['catatan']}_\n"
    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── /budget & /cek_budget ────────────────────────────────────────────────────

async def budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/budget makan 1500000`", parse_mode="Markdown")
        return
    kategori = args[0].lower()
    try:
        jumlah = float(args[1].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    ud["budget"][kategori] = jumlah
    save_data(data)
    await update.message.reply_text(f"✅ Budget *{kategori}* = *{format_rupiah_full(jumlah)}*/bulan", parse_mode="Markdown")

async def cek_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    budgets = ud.get("budget", {})
    if not budgets:
        await update.message.reply_text("_Belum ada budget._\nGunakan `/budget [kategori] [jumlah]`", parse_mode="Markdown")
        return
    bulan_ini = date.today().strftime("%Y-%m")
    teks = f"🎯 *Budget {date.today().strftime('%B %Y')}:*\n\n"
    for kat, batas in budgets.items():
        terpakai = sum(t["jumlah"] for t in ud["transaksi"]
            if t["tipe"] == "keluar" and t["kategori"] == kat and t["tanggal"][:7] == bulan_ini)
        sisa = batas - terpakai
        persen = min((terpakai / batas) * 100, 100)
        bar = "█" * int(persen // 10) + "░" * (10 - int(persen // 10))
        emoji = "🔴" if persen >= 100 else "🟡" if persen >= 80 else "🟢"
        teks += f"{emoji} *{kat}*\n  [{bar}] {persen:.0f}%\n  {format_rupiah_full(terpakai)} / {format_rupiah_full(batas)} | sisa {format_rupiah_full(max(sisa,0))}\n\n"
    await update.message.reply_text(teks, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# INVESTASI
# ══════════════════════════════════════════════════════════════════════════════

async def investasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /investasi beli saham 1000000 BBCA
    /investasi jual saham 1200000 BBCA
    Tipe investasi: saham, reksa_dana, crypto, emas, deposito, dll
    """
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "❌ Format:\n"
            "`/investasi beli [jenis] [jumlah] [nama]`\n"
            "`/investasi jual [jenis] [jumlah] [nama]`\n\n"
            "Contoh:\n"
            "`/investasi beli saham 1000000 BBCA`\n"
            "`/investasi beli reksa_dana 500000 Bibit`\n"
            "`/investasi jual crypto 800000 BTC`",
            parse_mode="Markdown"
        )
        return

    aksi  = args[0].lower()
    jenis = args[1].lower()
    try:
        jumlah = float(args[2].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return
    nama = " ".join(args[3:]) if len(args) > 3 else jenis

    if aksi not in ["beli", "jual"]:
        await update.message.reply_text("❌ Aksi harus `beli` atau `jual`.", parse_mode="Markdown")
        return

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    ud["investasi"].append({
        "tipe": aksi, "jenis": jenis, "nama": nama,
        "jumlah": jumlah, "tanggal": datetime.now().isoformat(),
        "terjual": aksi == "jual"
    })
    save_data(data)

    emoji = "📈" if aksi == "beli" else "📉"
    await update.message.reply_text(
        f"{emoji} Investasi dicatat!\n\n"
        f"Aksi: *{aksi.upper()}*\n"
        f"Jenis: {jenis} | Nama: {nama}\n"
        f"Jumlah: *{format_rupiah_full(jumlah)}*\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        parse_mode="Markdown"
    )

async def inv_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    inv = ud["investasi"]

    if not inv:
        await update.message.reply_text("_Belum ada catatan investasi._\nGunakan `/investasi beli [jenis] [jumlah] [nama]`", parse_mode="Markdown")
        return

    # Kelompokkan per jenis
    per_jenis = defaultdict(lambda: {"beli": 0, "jual": 0, "items": []})
    for i in inv:
        per_jenis[i["jenis"]]["items"].append(i)
        per_jenis[i["jenis"]][i["tipe"]] += i["jumlah"]

    total_modal = 0
    total_hasil = 0
    teks = "📈 *Portofolio Investasi:*\n\n"

    for jenis, d in per_jenis.items():
        modal  = d["beli"]
        hasil  = d["jual"]
        aktif  = modal - hasil
        untung = hasil - modal if hasil > 0 else 0
        total_modal += modal
        total_hasil += hasil

        emoji_jenis = {
            "saham": "📊", "reksa_dana": "🏦", "crypto": "🪙",
            "emas": "🥇", "deposito": "🏛", "obligasi": "📜"
        }.get(jenis, "💼")

        teks += f"{emoji_jenis} *{jenis.upper()}*\n"
        teks += f"  Modal: {format_rupiah_full(modal)}\n"
        if hasil > 0:
            teks += f"  Hasil jual: {format_rupiah_full(hasil)}\n"
            teks += f"  {'🟢 Untung' if untung >= 0 else '🔴 Rugi'}: {format_rupiah_full(abs(untung))}\n"
        teks += f"  Aktif: *{format_rupiah_full(aktif)}*\n\n"

    teks += f"━━━━━━━━━━━━━━\n"
    teks += f"💼 Total Modal: *{format_rupiah_full(total_modal)}*\n"
    teks += f"💵 Total Hasil: *{format_rupiah_full(total_hasil)}*"

    await update.message.reply_text(teks, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# HUTANG & PIUTANG
# ══════════════════════════════════════════════════════════════════════════════

async def hutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hutang 200000 Budi beli makan"""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Format: `/hutang [jumlah] [nama] [catatan]`\n"
            "Contoh: `/hutang 200000 Budi beli makan`",
            parse_mode="Markdown"
        )
        return
    try:
        jumlah = float(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return

    nama    = args[1]
    catatan = " ".join(args[2:]) if len(args) > 2 else "-"

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    ud["hutang"].append({
        "jumlah": jumlah, "nama": nama, "catatan": catatan,
        "tanggal": datetime.now().isoformat(), "lunas": False
    })
    save_data(data)

    await update.message.reply_text(
        f"✅ Hutang dicatat!\n\n"
        f"🤝 Kamu hutang ke *{nama}*\n"
        f"💸 *{format_rupiah_full(jumlah)}*\n"
        f"📝 {catatan}",
        parse_mode="Markdown"
    )

async def piutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/piutang 150000 Ani pinjam bensin"""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Format: `/piutang [jumlah] [nama] [catatan]`\n"
            "Contoh: `/piutang 150000 Ani pinjam`",
            parse_mode="Markdown"
        )
        return
    try:
        jumlah = float(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return

    nama    = args[1]
    catatan = " ".join(args[2:]) if len(args) > 2 else "-"

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    ud["piutang"].append({
        "jumlah": jumlah, "nama": nama, "catatan": catatan,
        "tanggal": datetime.now().isoformat(), "lunas": False
    })
    save_data(data)

    await update.message.reply_text(
        f"✅ Piutang dicatat!\n\n"
        f"💵 *{nama}* hutang ke kamu\n"
        f"💰 *{format_rupiah_full(jumlah)}*\n"
        f"📝 {catatan}",
        parse_mode="Markdown"
    )

async def hutang_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    items = ud["hutang"]

    if not items:
        await update.message.reply_text("_Belum ada catatan hutang._", parse_mode="Markdown")
        return

    belum = [h for h in items if not h["lunas"]]
    sudah = [h for h in items if h["lunas"]]
    total_belum = sum(h["jumlah"] for h in belum)

    teks = "🤝 *Daftar Hutang Kamu:*\n\n"
    if belum:
        teks += "❌ *Belum Lunas:*\n"
        for i, h in enumerate(belum):
            tgl = datetime.fromisoformat(h["tanggal"]).strftime("%d/%m/%Y")
            idx = items.index(h) + 1
            teks += f"  #{idx} *{h['nama']}* — {format_rupiah_full(h['jumlah'])}\n"
            teks += f"       📝 {h['catatan']} | 🗓 {tgl}\n"
            teks += f"       → `/bayar_hutang {idx}`\n"
    if sudah:
        teks += "\n✅ *Sudah Lunas:*\n"
        for h in sudah:
            teks += f"  ~~{h['nama']} — {format_rupiah_full(h['jumlah'])}~~\n"

    teks += f"\n💸 *Total belum lunas: {format_rupiah_full(total_belum)}*"
    await update.message.reply_text(teks, parse_mode="Markdown")

async def piutang_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    items = ud["piutang"]

    if not items:
        await update.message.reply_text("_Belum ada catatan piutang._", parse_mode="Markdown")
        return

    belum = [p for p in items if not p["lunas"]]
    sudah = [p for p in items if p["lunas"]]
    total_belum = sum(p["jumlah"] for p in belum)

    teks = "💵 *Daftar Piutang (Orang yang Hutang ke Kamu):*\n\n"
    if belum:
        teks += "❌ *Belum Dibayar:*\n"
        for p in belum:
            tgl = datetime.fromisoformat(p["tanggal"]).strftime("%d/%m/%Y")
            idx = items.index(p) + 1
            teks += f"  #{idx} *{p['nama']}* — {format_rupiah_full(p['jumlah'])}\n"
            teks += f"       📝 {p['catatan']} | 🗓 {tgl}\n"
            teks += f"       → `/terima_piutang {idx}`\n"
    if sudah:
        teks += "\n✅ *Sudah Diterima:*\n"
        for p in sudah:
            teks += f"  ~~{p['nama']} — {format_rupiah_full(p['jumlah'])}~~\n"

    teks += f"\n💰 *Total belum diterima: {format_rupiah_full(total_belum)}*"
    await update.message.reply_text(teks, parse_mode="Markdown")

async def bayar_hutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Format: `/bayar_hutang [nomor]`\nLihat nomor di `/hutang_list`", parse_mode="Markdown")
        return
    try:
        idx = int(args[0]) - 1
    except ValueError:
        await update.message.reply_text("❌ Nomor tidak valid.")
        return

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    if idx < 0 or idx >= len(ud["hutang"]):
        await update.message.reply_text("❌ Nomor hutang tidak ditemukan.")
        return
    if ud["hutang"][idx]["lunas"]:
        await update.message.reply_text("ℹ️ Hutang ini sudah lunas sebelumnya.")
        return

    ud["hutang"][idx]["lunas"] = True
    ud["hutang"][idx]["tanggal_lunas"] = datetime.now().isoformat()
    save_data(data)

    h = ud["hutang"][idx]
    await update.message.reply_text(
        f"✅ Hutang ke *{h['nama']}* sebesar *{format_rupiah_full(h['jumlah'])}* sudah lunas! 🎉",
        parse_mode="Markdown"
    )

async def terima_piutang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Format: `/terima_piutang [nomor]`\nLihat nomor di `/piutang_list`", parse_mode="Markdown")
        return
    try:
        idx = int(args[0]) - 1
    except ValueError:
        await update.message.reply_text("❌ Nomor tidak valid.")
        return

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    if idx < 0 or idx >= len(ud["piutang"]):
        await update.message.reply_text("❌ Nomor piutang tidak ditemukan.")
        return
    if ud["piutang"][idx]["lunas"]:
        await update.message.reply_text("ℹ️ Piutang ini sudah diterima sebelumnya.")
        return

    ud["piutang"][idx]["lunas"] = True
    ud["piutang"][idx]["tanggal_lunas"] = datetime.now().isoformat()
    save_data(data)

    p = ud["piutang"][idx]
    await update.message.reply_text(
        f"✅ Piutang dari *{p['nama']}* sebesar *{format_rupiah_full(p['jumlah'])}* sudah diterima! 💰",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════════════════════════════
# GRAFIK
# ══════════════════════════════════════════════════════════════════════════════

WARNA_KELUAR = ["#FF6B6B","#FF8E8E","#FF5252","#E53935","#FF7043","#EF9A9A","#FFCDD2","#D32F2F","#FF8A65","#FFAB91"]
WARNA_MASUK  = ["#4ECDC4","#26C6DA","#00BCD4","#26A69A","#4DB6AC","#80DEEA","#B2DFDB","#00897B","#00ACC1","#80CBC4"]
BG    = "#0f0f1a"
PANEL = "#1a1a2e"

async def grafik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    bulan_ini  = date.today().strftime("%Y-%m")
    nama_bulan = date.today().strftime("%B %Y")

    keluar_kat = defaultdict(float)
    masuk_kat  = defaultdict(float)
    for t in ud["transaksi"]:
        if t["tanggal"][:7] != bulan_ini:
            continue
        if t["tipe"] == "keluar":
            keluar_kat[t["kategori"]] += t["jumlah"]
        else:
            masuk_kat[t["kategori"]] += t["jumlah"]

    total_masuk  = sum(masuk_kat.values())
    total_keluar = sum(keluar_kat.values())
    saldo        = total_masuk - total_keluar
    total_inv    = sum(i["jumlah"] for i in ud["investasi"] if i["tipe"] == "beli")
    total_hutang = sum(h["jumlah"] for h in ud["hutang"]   if not h["lunas"])
    total_piutang= sum(p["jumlah"] for p in ud["piutang"]  if not p["lunas"])

    # Tren 14 hari
    hari_list   = [(date.today() - timedelta(days=i)) for i in range(13, -1, -1)]
    tren_keluar = [sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "keluar" and t["tanggal"][:10] == h.isoformat()) for h in hari_list]
    tren_masuk  = [sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "masuk"  and t["tanggal"][:10] == h.isoformat()) for h in hari_list]
    label_hari  = [h.strftime("%d/%m") for h in hari_list]

    if not keluar_kat and not masuk_kat and total_inv == 0 and total_hutang == 0:
        await update.message.reply_text("_Belum ada data untuk ditampilkan._", parse_mode="Markdown")
        return

    # ── Layout: 3 baris ──────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 11), facecolor=BG)
    gs  = gridspec.GridSpec(3, 3, figure=fig,
                            hspace=0.55, wspace=0.35,
                            left=0.05, right=0.97, top=0.91, bottom=0.07)

    ax_pie_k = fig.add_subplot(gs[0, 0])
    ax_pie_m = fig.add_subplot(gs[0, 1])
    ax_info  = fig.add_subplot(gs[0, 2])
    ax_extra = fig.add_subplot(gs[1, :])   # investasi + hutang/piutang bar
    ax_tren  = fig.add_subplot(gs[2, :])   # tren 14 hari

    for ax in [ax_pie_k, ax_pie_m, ax_info, ax_extra, ax_tren]:
        ax.set_facecolor(PANEL)

    fig.text(0.5, 0.95, f"📊 Laporan Keuangan — {nama_bulan}",
             ha="center", va="center", color="white", fontsize=15, fontweight="bold")

    # ── PIE pengeluaran ───────────────────────────────────────────────────────
    if keluar_kat:
        kat_k = list(keluar_kat.keys())
        val_k = list(keluar_kat.values())
        clr_k = WARNA_KELUAR[:len(kat_k)]
        _, _, autotexts = ax_pie_k.pie(val_k, colors=clr_k, autopct="%1.0f%%",
            startangle=90, pctdistance=0.72,
            wedgeprops=dict(width=0.55, edgecolor=PANEL, linewidth=1.5))
        for at in autotexts:
            at.set(color="white", fontsize=7, fontweight="bold")
        ax_pie_k.text(0, 0, format_rupiah(total_keluar), ha="center", va="center",
                      color="white", fontsize=8, fontweight="bold")
        leg = [mpatches.Patch(color=clr_k[i], label=f"{kat_k[i]} ({format_rupiah(val_k[i])})") for i in range(len(kat_k))]
        ax_pie_k.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5, -0.3),
                        ncol=1, frameon=False, labelcolor="white", fontsize=7)
    else:
        ax_pie_k.text(0.5, 0.5, "Tidak ada\npengeluaran", ha="center", va="center", color="#888", transform=ax_pie_k.transAxes)
        ax_pie_k.axis("off")
    ax_pie_k.set_title("💸 Pengeluaran", color="#FF6B6B", fontsize=10, fontweight="bold", pad=8)

    # ── PIE pemasukan ─────────────────────────────────────────────────────────
    if masuk_kat:
        kat_m = list(masuk_kat.keys())
        val_m = list(masuk_kat.values())
        clr_m = WARNA_MASUK[:len(kat_m)]
        _, _, autotexts2 = ax_pie_m.pie(val_m, colors=clr_m, autopct="%1.0f%%",
            startangle=90, pctdistance=0.72,
            wedgeprops=dict(width=0.55, edgecolor=PANEL, linewidth=1.5))
        for at in autotexts2:
            at.set(color="white", fontsize=7, fontweight="bold")
        ax_pie_m.text(0, 0, format_rupiah(total_masuk), ha="center", va="center",
                      color="white", fontsize=8, fontweight="bold")
        leg2 = [mpatches.Patch(color=clr_m[i], label=f"{kat_m[i]} ({format_rupiah(val_m[i])})") for i in range(len(kat_m))]
        ax_pie_m.legend(handles=leg2, loc="lower center", bbox_to_anchor=(0.5, -0.3),
                        ncol=1, frameon=False, labelcolor="white", fontsize=7)
    else:
        ax_pie_m.text(0.5, 0.5, "Tidak ada\npemasukan", ha="center", va="center", color="#888", transform=ax_pie_m.transAxes)
        ax_pie_m.axis("off")
    ax_pie_m.set_title("💰 Pemasukan", color="#4ECDC4", fontsize=10, fontweight="bold", pad=8)

    # ── INFO RINGKASAN ────────────────────────────────────────────────────────
    ax_info.axis("off")
    ax_info.set_title("📋 Ringkasan", color="white", fontsize=10, fontweight="bold", pad=8)
    items_info = [
        ("Total Masuk",    format_rupiah_full(total_masuk),   "#4ECDC4"),
        ("Total Keluar",   format_rupiah_full(total_keluar),  "#FF6B6B"),
        ("Saldo",          format_rupiah_full(saldo),         "#FFD700" if saldo >= 0 else "#FF4444"),
    ]
    for i, (label, val, clr) in enumerate(items_info):
        y = 0.78 - i * 0.26
        ax_info.add_patch(plt.Rectangle((0.05, y - 0.1), 0.9, 0.2,
            transform=ax_info.transAxes, color="#0f0f1a", clip_on=False, zorder=0))
        ax_info.text(0.5, y + 0.04, label, ha="center", va="center",
            transform=ax_info.transAxes, color="#aaa", fontsize=8)
        ax_info.text(0.5, y - 0.06, val, ha="center", va="center",
            transform=ax_info.transAxes, color=clr, fontsize=9, fontweight="bold")
    ax_info.text(0.5, 0.04, "🟢 Surplus" if saldo >= 0 else "🔴 Defisit",
        ha="center", va="center", transform=ax_info.transAxes,
        color="#FFD700" if saldo >= 0 else "#FF4444", fontsize=9, fontweight="bold")

    # ── BAR: Investasi, Hutang, Piutang ──────────────────────────────────────
    ax_extra.set_title("💼 Investasi & Hutang Piutang", color="white", fontsize=10, fontweight="bold", pad=8)
    kategori_extra = ["Investasi\nAktif", "Hutang\nBelum Lunas", "Piutang\nBelum Diterima"]
    nilai_extra    = [total_inv, total_hutang, total_piutang]
    warna_extra    = ["#FFD700", "#FF6B6B", "#4ECDC4"]

    bars = ax_extra.bar(kategori_extra, nilai_extra, color=warna_extra, alpha=0.85,
                        edgecolor=PANEL, linewidth=1.5, width=0.4)
    ax_extra.yaxis.set_visible(False)
    ax_extra.spines[:].set_visible(False)
    ax_extra.tick_params(colors="white")
    ax_extra.set_xticklabels(kategori_extra, color="white", fontsize=9)

    max_extra = max(nilai_extra) if max(nilai_extra) > 0 else 1
    for bar, val in zip(bars, nilai_extra):
        ax_extra.text(bar.get_x() + bar.get_width()/2,
                      bar.get_height() + max_extra * 0.03,
                      format_rupiah_full(val),
                      ha="center", color="white", fontsize=8, fontweight="bold")

    # ── TREN 14 HARI ─────────────────────────────────────────────────────────
    x = range(len(hari_list))
    ax_tren.fill_between(x, tren_masuk,  alpha=0.15, color="#4ECDC4")
    ax_tren.fill_between(x, tren_keluar, alpha=0.15, color="#FF6B6B")
    ax_tren.plot(x, tren_masuk,  color="#4ECDC4", linewidth=2, marker="o", markersize=4, label="Masuk")
    ax_tren.plot(x, tren_keluar, color="#FF6B6B", linewidth=2, marker="o", markersize=4, label="Keluar")
    ax_tren.set_xticks(list(x))
    ax_tren.set_xticklabels(label_hari, color="white", fontsize=7.5)
    ax_tren.yaxis.set_visible(False)
    ax_tren.spines[:].set_visible(False)
    ax_tren.set_title("📈 Tren 14 Hari Terakhir", color="white", fontsize=10, fontweight="bold", pad=8)
    ax_tren.legend(frameon=False, labelcolor="white", fontsize=8, loc="upper left")
    max_val = max(max(tren_masuk, default=0), max(tren_keluar, default=0))
    for i, (m, k) in enumerate(zip(tren_masuk, tren_keluar)):
        if m > 0:
            ax_tren.text(i, m + max(max_val * 0.04, 1), format_rupiah(m), ha="center", color="#4ECDC4", fontsize=6)
        if k > 0:
            ax_tren.text(i, k + max(max_val * 0.04, 1), format_rupiah(k), ha="center", color="#FF6B6B", fontsize=6)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=BG, bbox_inches="tight")
    buf.seek(0)
    plt.close()

    caption = (
        f"📊 *Grafik Keuangan — {nama_bulan}*\n"
        f"💰 Masuk: {format_rupiah_full(total_masuk)}\n"
        f"💸 Keluar: {format_rupiah_full(total_keluar)}\n"
        f"{'🟢 Surplus' if saldo >= 0 else '🔴 Defisit'}: {format_rupiah_full(abs(saldo))}\n"
        f"📈 Investasi: {format_rupiah_full(total_inv)} | "
        f"🤝 Hutang: {format_rupiah_full(total_hutang)} | "
        f"💵 Piutang: {format_rupiah_full(total_piutang)}"
    )
    await update.message.reply_photo(photo=buf, caption=caption, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
# PENGINGAT HARIAN
# ══════════════════════════════════════════════════════════════════════════════

async def kirim_reminder(context: ContextTypes.DEFAULT_TYPE):
    job     = context.job
    user_id = job.data["user_id"]
    data    = load_data()
    ud      = get_user_data(data, user_id)

    hari_ini  = date.today().isoformat()
    bulan_ini = date.today().strftime("%Y-%m")
    keluar_hari  = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "keluar" and t["tanggal"][:10] == hari_ini)
    masuk_hari   = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "masuk"  and t["tanggal"][:10] == hari_ini)
    keluar_bln   = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "keluar" and t["tanggal"][:7] == bulan_ini)
    masuk_bln    = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "masuk"  and t["tanggal"][:7] == bulan_ini)
    total_hutang = sum(h["jumlah"] for h in ud["hutang"]   if not h["lunas"])
    total_piutang= sum(p["jumlah"] for p in ud["piutang"]  if not p["lunas"])

    teks = (
        f"⏰ *Pengingat Keuangan Harian*\n"
        f"_{date.today().strftime('%A, %d %B %Y')}_\n\n"
        f"*Hari Ini:*\n💰 Masuk: {format_rupiah_full(masuk_hari)}\n💸 Keluar: {format_rupiah_full(keluar_hari)}\n\n"
        f"*Bulan Ini:*\n💰 Masuk: {format_rupiah_full(masuk_bln)}\n💸 Keluar: {format_rupiah_full(keluar_bln)}\n"
        f"{'🟢' if masuk_bln >= keluar_bln else '🔴'} Saldo: *{format_rupiah_full(masuk_bln - keluar_bln)}*\n\n"
    )
    if total_hutang > 0:
        teks += f"⚠️ Hutang belum lunas: *{format_rupiah_full(total_hutang)}*\n"
    if total_piutang > 0:
        teks += f"💵 Piutang belum diterima: *{format_rupiah_full(total_piutang)}*\n"
    teks += f"\n_Jangan lupa catat transaksi hari ini ya!_ 📝"

    await context.bot.send_message(chat_id=user_id, text=teks, parse_mode="Markdown")

async def reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args    = context.args
    user_id = update.effective_user.id

    if not args:
        await update.message.reply_text("❌ Format: `/reminder 20:00` atau `/reminder off`", parse_mode="Markdown")
        return

    if args[0].lower() == "off":
        for job in context.job_queue.get_jobs_by_name(f"reminder_{user_id}"):
            job.schedule_removal()
        data = load_data()
        ud = get_user_data(data, user_id)
        ud["reminder"] = None
        save_data(data)
        await update.message.reply_text("✅ Pengingat harian dimatikan.")
        return

    try:
        jam, menit = map(int, args[0].split(":"))
        waktu = time(jam, menit)
    except Exception:
        await update.message.reply_text("❌ Format jam salah. Contoh: `/reminder 20:00`", parse_mode="Markdown")
        return

    for job in context.job_queue.get_jobs_by_name(f"reminder_{user_id}"):
        job.schedule_removal()

    context.job_queue.run_daily(kirim_reminder, time=waktu,
                                data={"user_id": user_id}, name=f"reminder_{user_id}")

    data = load_data()
    ud = get_user_data(data, user_id)
    ud["reminder"] = args[0]
    save_data(data)

    await update.message.reply_text(
        f"⏰ Pengingat harian diset jam *{args[0]}*!\nKamu akan dapat ringkasan otomatis setiap hari. 😊",
        parse_mode="Markdown"
    )

# ── /reset ────────────────────────────────────────────────────────────────────

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("✅ Ya, hapus semua", callback_data="reset_ya"),
        InlineKeyboardButton("❌ Batal", callback_data="reset_tidak"),
    ]]
    await update.message.reply_text("⚠️ *Yakin mau hapus SEMUA data?*",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "reset_ya":
        data = load_data()
        uid = str(query.from_user.id)
        data[uid] = {"transaksi": [], "budget": {}, "reminder": None, "investasi": [], "hutang": [], "piutang": []}
        save_data(data)
        await query.edit_message_text("🗑 Semua data telah dihapus.")
    else:
        await query.edit_message_text("✅ Reset dibatalkan.")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",          start))
    app.add_handler(CommandHandler("help",           start))
    app.add_handler(CommandHandler("keluar",         keluar))
    app.add_handler(CommandHandler("masuk",          masuk))
    app.add_handler(CommandHandler("ringkasan",      ringkasan))
    app.add_handler(CommandHandler("laporan",        laporan))
    app.add_handler(CommandHandler("riwayat",        riwayat))
    app.add_handler(CommandHandler("budget",         budget))
    app.add_handler(CommandHandler("cek_budget",     cek_budget))
    app.add_handler(CommandHandler("investasi",      investasi))
    app.add_handler(CommandHandler("inv_list",       inv_list))
    app.add_handler(CommandHandler("hutang",         hutang))
    app.add_handler(CommandHandler("piutang",        piutang))
    app.add_handler(CommandHandler("hutang_list",    hutang_list))
    app.add_handler(CommandHandler("piutang_list",   piutang_list))
    app.add_handler(CommandHandler("bayar_hutang",   bayar_hutang))
    app.add_handler(CommandHandler("terima_piutang", terima_piutang))
    app.add_handler(CommandHandler("grafik",         grafik))
    app.add_handler(CommandHandler("reminder",       reminder))
    app.add_handler(CommandHandler("reset",          reset))
    app.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))

    print("🤖 Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
