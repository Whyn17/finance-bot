"""
Bot Telegram: Personal Finance Tracker
Cara pakai:
1. Install library: pip install python-telegram-bot
2. Buat bot baru via @BotFather di Telegram, dapatkan TOKEN
3. Ganti YOUR_BOT_TOKEN dengan token kamu
4. Jalankan: python finance_bot.py
"""

import json
import os
from datetime import datetime, date
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

import os
TOKEN = os.environ.get(8600828372:AAFvyDGXlUfnSWCgJs5kTXqxV9bjcWlVY7g)  # Ganti dengan token dari @BotFather
DATA_FILE = "keuangan.json"

# ─── Simpan & Load Data ────────────────────────────────────────────────────────

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
        data[uid] = {"transaksi": [], "budget": {}}
    return data[uid]

# ─── Format Uang ──────────────────────────────────────────────────────────────

def format_rupiah(amount):
    return f"Rp {amount:,.0f}".replace(",", ".")

# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nama = update.effective_user.first_name
    teks = (
        f"👋 Halo, *{nama}*! Selamat datang di *Finance Tracker Bot* 💰\n\n"
        "Aku bisa bantu kamu catat pemasukan & pengeluaran harian.\n\n"
        "📌 *Cara Pakai:*\n"
        "• Catat pengeluaran: `/keluar 50000 makan siang`\n"
        "• Catat pemasukan: `/masuk 3000000 gaji`\n"
        "• Lihat ringkasan: `/ringkasan`\n"
        "• Laporan bulan ini: `/laporan`\n"
        "• Set budget: `/budget makan 1500000`\n"
        "• Hapus data: `/reset`\n"
        "• Bantuan: `/help`"
    )
    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── /help ────────────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teks = (
        "📖 *Daftar Perintah:*\n\n"
        "💸 *Pengeluaran:*\n"
        "`/keluar [jumlah] [kategori] [catatan]`\n"
        "Contoh: `/keluar 25000 transport ojek`\n\n"
        "💰 *Pemasukan:*\n"
        "`/masuk [jumlah] [sumber] [catatan]`\n"
        "Contoh: `/masuk 5000000 gaji bulanan`\n\n"
        "📊 *Laporan:*\n"
        "`/ringkasan` – saldo & total hari ini\n"
        "`/laporan` – rincian bulan ini per kategori\n"
        "`/riwayat` – 10 transaksi terakhir\n\n"
        "🎯 *Budget:*\n"
        "`/budget [kategori] [jumlah]` – set batas pengeluaran\n"
        "`/cek_budget` – lihat sisa budget\n\n"
        "🗑 *Hapus:*\n"
        "`/reset` – hapus semua data (hati-hati!)"
    )
    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── /keluar ──────────────────────────────────────────────────────────────────

async def keluar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Format salah.\nContoh: `/keluar 25000 makan siang`",
            parse_mode="Markdown"
        )
        return

    try:
        jumlah = float(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Jumlah tidak valid. Masukkan angka.")
        return

    kategori = args[1].lower()
    catatan = " ".join(args[2:]) if len(args) > 2 else "-"
    tanggal = datetime.now().isoformat()

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    ud["transaksi"].append({
        "tipe": "keluar",
        "jumlah": jumlah,
        "kategori": kategori,
        "catatan": catatan,
        "tanggal": tanggal
    })
    save_data(data)

    # Cek budget
    peringatan = ""
    if kategori in ud.get("budget", {}):
        bulan_ini = date.today().strftime("%Y-%m")
        total_kat = sum(
            t["jumlah"] for t in ud["transaksi"]
            if t["tipe"] == "keluar"
            and t["kategori"] == kategori
            and t["tanggal"][:7] == bulan_ini
        )
        batas = ud["budget"][kategori]
        persen = (total_kat / batas) * 100
        if persen >= 100:
            peringatan = f"\n\n⚠️ *Budget {kategori} HABIS!* ({format_rupiah(total_kat)} / {format_rupiah(batas)})"
        elif persen >= 80:
            peringatan = f"\n\n⚠️ Budget {kategori} tersisa {format_rupiah(batas - total_kat)} ({100-persen:.0f}%)"

    await update.message.reply_text(
        f"✅ Pengeluaran dicatat!\n\n"
        f"💸 *{format_rupiah(jumlah)}*\n"
        f"📂 Kategori: `{kategori}`\n"
        f"📝 Catatan: {catatan}\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        f"{peringatan}",
        parse_mode="Markdown"
    )

# ─── /masuk ───────────────────────────────────────────────────────────────────

async def masuk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Format salah.\nContoh: `/masuk 5000000 gaji`",
            parse_mode="Markdown"
        )
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
        "tipe": "masuk",
        "jumlah": jumlah,
        "kategori": sumber,
        "catatan": catatan,
        "tanggal": datetime.now().isoformat()
    })
    save_data(data)

    await update.message.reply_text(
        f"✅ Pemasukan dicatat!\n\n"
        f"💰 *{format_rupiah(jumlah)}*\n"
        f"📂 Sumber: `{sumber}`\n"
        f"📝 Catatan: {catatan}\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        parse_mode="Markdown"
    )

# ─── /ringkasan ───────────────────────────────────────────────────────────────

async def ringkasan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    transaksi = ud["transaksi"]

    hari_ini = date.today().isoformat()
    bulan_ini = date.today().strftime("%Y-%m")

    # Harian
    keluar_hari = sum(t["jumlah"] for t in transaksi if t["tipe"] == "keluar" and t["tanggal"][:10] == hari_ini)
    masuk_hari = sum(t["jumlah"] for t in transaksi if t["tipe"] == "masuk" and t["tanggal"][:10] == hari_ini)

    # Bulanan
    keluar_bln = sum(t["jumlah"] for t in transaksi if t["tipe"] == "keluar" and t["tanggal"][:7] == bulan_ini)
    masuk_bln = sum(t["jumlah"] for t in transaksi if t["tipe"] == "masuk" and t["tanggal"][:7] == bulan_ini)

    saldo = masuk_bln - keluar_bln
    emoji_saldo = "🟢" if saldo >= 0 else "🔴"

    teks = (
        f"📊 *Ringkasan Keuangan*\n"
        f"_{date.today().strftime('%d %B %Y')}_\n\n"
        f"*— Hari Ini —*\n"
        f"💰 Pemasukan: {format_rupiah(masuk_hari)}\n"
        f"💸 Pengeluaran: {format_rupiah(keluar_hari)}\n\n"
        f"*— Bulan Ini —*\n"
        f"💰 Pemasukan: {format_rupiah(masuk_bln)}\n"
        f"💸 Pengeluaran: {format_rupiah(keluar_bln)}\n"
        f"{emoji_saldo} Saldo: *{format_rupiah(saldo)}*"
    )
    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── /laporan ─────────────────────────────────────────────────────────────────

async def laporan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    bulan_ini = date.today().strftime("%Y-%m")

    keluar_kat = defaultdict(float)
    masuk_kat = defaultdict(float)

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
            teks += f"  • {kat}: {format_rupiah(jml)}\n"
        teks += f"  *Total: {format_rupiah(sum(masuk_kat.values()))}*\n\n"

    if keluar_kat:
        teks += "💸 *PENGELUARAN:*\n"
        for kat, jml in sorted(keluar_kat.items(), key=lambda x: -x[1]):
            budget_info = ""
            if kat in ud.get("budget", {}):
                batas = ud["budget"][kat]
                persen = min((jml / batas) * 100, 100)
                bar = "█" * int(persen // 10) + "░" * (10 - int(persen // 10))
                budget_info = f"\n    [{bar}] {persen:.0f}%"
            teks += f"  • {kat}: {format_rupiah(jml)}{budget_info}\n"
        teks += f"  *Total: {format_rupiah(sum(keluar_kat.values()))}*\n\n"

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
        teks += f"{emoji} `{tgl}` | {t['kategori']} | *{format_rupiah(t['jumlah'])}*\n"
        if t["catatan"] != "-":
            teks += f"   _{t['catatan']}_\n"

    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── /budget ──────────────────────────────────────────────────────────────────

async def budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Format: `/budget [kategori] [jumlah]`\nContoh: `/budget makan 1500000`",
            parse_mode="Markdown"
        )
        return

    kategori = args[0].lower()
    try:
        jumlah = float(args[1].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ Jumlah tidak valid.")
        return

    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    if "budget" not in ud:
        ud["budget"] = {}
    ud["budget"][kategori] = jumlah
    save_data(data)

    await update.message.reply_text(
        f"✅ Budget *{kategori}* diset ke *{format_rupiah(jumlah)}* per bulan.",
        parse_mode="Markdown"
    )

# ─── /cek_budget ──────────────────────────────────────────────────────────────

async def cek_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    budgets = ud.get("budget", {})

    if not budgets:
        await update.message.reply_text("_Belum ada budget yang diset._\nGunakan `/budget [kategori] [jumlah]`", parse_mode="Markdown")
        return

    bulan_ini = date.today().strftime("%Y-%m")
    teks = f"🎯 *Budget {date.today().strftime('%B %Y')}:*\n\n"

    for kat, batas in budgets.items():
        terpakai = sum(
            t["jumlah"] for t in ud["transaksi"]
            if t["tipe"] == "keluar"
            and t["kategori"] == kat
            and t["tanggal"][:7] == bulan_ini
        )
        sisa = batas - terpakai
        persen = min((terpakai / batas) * 100, 100)
        bar = "█" * int(persen // 10) + "░" * (10 - int(persen // 10))
        emoji = "🔴" if persen >= 100 else "🟡" if persen >= 80 else "🟢"

        teks += (
            f"{emoji} *{kat}*\n"
            f"  [{bar}] {persen:.0f}%\n"
            f"  Terpakai: {format_rupiah(terpakai)} / {format_rupiah(batas)}\n"
            f"  Sisa: {format_rupiah(max(sisa, 0))}\n\n"
        )

    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── /reset ───────────────────────────────────────────────────────────────────

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("✅ Ya, hapus semua", callback_data="reset_ya"),
            InlineKeyboardButton("❌ Batal", callback_data="reset_tidak"),
        ]
    ]
    await update.message.reply_text(
        "⚠️ *Yakin mau hapus SEMUA data?* Tindakan ini tidak bisa dibatalkan!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "reset_ya":
        data = load_data()
        uid = str(query.from_user.id)
        data[uid] = {"transaksi": [], "budget": {}}
        save_data(data)
        await query.edit_message_text("🗑 Semua data telah dihapus.")
    else:
        await query.edit_message_text("✅ Reset dibatalkan.")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("keluar", keluar))
    app.add_handler(CommandHandler("masuk", masuk))
    app.add_handler(CommandHandler("ringkasan", ringkasan))
    app.add_handler(CommandHandler("laporan", laporan))
    app.add_handler(CommandHandler("riwayat", riwayat))
    app.add_handler(CommandHandler("budget", budget))
    app.add_handler(CommandHandler("cek_budget", cek_budget))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))

    print("🤖 Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
