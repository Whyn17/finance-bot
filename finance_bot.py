"""
Bot Telegram: Personal Finance Tracker
Fitur: Catat keuangan, grafik, pengingat harian
"""

import json
import os
import io
from datetime import datetime, date, time
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
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
        data[uid] = {"transaksi": [], "budget": {}, "reminder": None}
    if "reminder" not in data[uid]:
        data[uid]["reminder"] = None
    return data[uid]

def format_rupiah(amount):
    return f"Rp {amount:,.0f}".replace(",", ".")

# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nama = update.effective_user.first_name
    teks = (
        f"👋 Halo, *{nama}*! Selamat datang di *Finance Tracker Bot* 💰\n\n"
        "📌 *Perintah Lengkap:*\n\n"
        "💸 `/keluar 50000 makan siang`\n"
        "💰 `/masuk 3000000 gaji`\n"
        "📊 `/ringkasan` – saldo hari ini\n"
        "📋 `/laporan` – rincian bulan ini\n"
        "🕐 `/riwayat` – 10 transaksi terakhir\n"
        "🎯 `/budget makan 1500000`\n"
        "✅ `/cek_budget` – sisa budget\n\n"
        "📈 *Grafik:*\n"
        "🥧 `/grafik_kategori` – pie chart pengeluaran\n"
        "📊 `/grafik_mingguan` – bar chart 7 hari\n"
        "📉 `/grafik_tren` – tren 30 hari\n\n"
        "⏰ *Pengingat:*\n"
        "`/reminder 20:00` – set jam pengingat harian\n"
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
            peringatan = f"\n\n⚠️ Budget {kategori} tersisa {format_rupiah(batas - total_kat)}"

    await update.message.reply_text(
        f"✅ Pengeluaran dicatat!\n💸 *{format_rupiah(jumlah)}*\n"
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
        f"✅ Pemasukan dicatat!\n💰 *{format_rupiah(jumlah)}*\n📂 {sumber} | 📝 {catatan}",
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
    masuk_hari = sum(t["jumlah"] for t in transaksi if t["tipe"] == "masuk" and t["tanggal"][:10] == hari_ini)
    keluar_bln = sum(t["jumlah"] for t in transaksi if t["tipe"] == "keluar" and t["tanggal"][:7] == bulan_ini)
    masuk_bln = sum(t["jumlah"] for t in transaksi if t["tipe"] == "masuk" and t["tanggal"][:7] == bulan_ini)
    saldo = masuk_bln - keluar_bln

    await update.message.reply_text(
        f"📊 *Ringkasan — {date.today().strftime('%d %B %Y')}*\n\n"
        f"*Hari Ini:*\n💰 Masuk: {format_rupiah(masuk_hari)}\n💸 Keluar: {format_rupiah(keluar_hari)}\n\n"
        f"*Bulan Ini:*\n💰 Masuk: {format_rupiah(masuk_bln)}\n💸 Keluar: {format_rupiah(keluar_bln)}\n"
        f"{'🟢' if saldo >= 0 else '🔴'} Saldo: *{format_rupiah(saldo)}*",
        parse_mode="Markdown"
    )

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
                budget_info = f" [{bar}] {persen:.0f}%"
            teks += f"  • {kat}: {format_rupiah(jml)}{budget_info}\n"
        teks += f"  *Total: {format_rupiah(sum(keluar_kat.values()))}*"

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
    await update.message.reply_text(f"✅ Budget *{kategori}* = *{format_rupiah(jumlah)}*/bulan", parse_mode="Markdown")

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
        teks += f"{emoji} *{kat}*\n  [{bar}] {persen:.0f}%\n  {format_rupiah(terpakai)} / {format_rupiah(batas)} | sisa {format_rupiah(max(sisa,0))}\n\n"
    await update.message.reply_text(teks, parse_mode="Markdown")

# ─── GRAFIK ───────────────────────────────────────────────────────────────────

WARNA = ["#FF6B6B","#4ECDC4","#45B7D1","#96CEB4","#FFEAA7","#DDA0DD","#98D8C8","#F7DC6F","#BB8FCE","#85C1E9"]

async def grafik_kategori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    bulan_ini = date.today().strftime("%Y-%m")

    keluar_kat = defaultdict(float)
    for t in ud["transaksi"]:
        if t["tipe"] == "keluar" and t["tanggal"][:7] == bulan_ini:
            keluar_kat[t["kategori"]] += t["jumlah"]

    if not keluar_kat:
        await update.message.reply_text("_Belum ada pengeluaran bulan ini._", parse_mode="Markdown")
        return

    labels = list(keluar_kat.keys())
    values = list(keluar_kat.values())
    colors = WARNA[:len(labels)]

    fig, ax = plt.subplots(figsize=(8, 6), facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    wedges, texts, autotexts = ax.pie(
        values, labels=None, colors=colors,
        autopct="%1.1f%%", startangle=90,
        pctdistance=0.75,
        wedgeprops=dict(width=0.6, edgecolor="#1a1a2e", linewidth=2)
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(9)
        at.set_fontweight("bold")

    legend_labels = [f"{l}  {format_rupiah(v)}" for l, v in zip(labels, values)]
    patches = [mpatches.Patch(color=colors[i], label=legend_labels[i]) for i in range(len(labels))]
    ax.legend(handles=patches, loc="lower center", bbox_to_anchor=(0.5, -0.15),
              ncol=2, frameon=False, labelcolor="white", fontsize=9)

    total = sum(values)
    ax.text(0, 0, f"Total\n{format_rupiah(total)}", ha="center", va="center",
            color="white", fontsize=10, fontweight="bold")
    ax.set_title(f"Pengeluaran {date.today().strftime('%B %Y')}",
                 color="white", fontsize=13, fontweight="bold", pad=20)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="#1a1a2e")
    buf.seek(0)
    plt.close()

    await update.message.reply_photo(photo=buf, caption=f"🥧 *Pengeluaran per Kategori — {date.today().strftime('%B %Y')}*", parse_mode="Markdown")

async def grafik_mingguan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import timedelta
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)

    hari_list = [(date.today() - timedelta(days=i)) for i in range(6, -1, -1)]
    label_hari = [h.strftime("%a\n%d/%m") for h in hari_list]

    keluar_list = []
    masuk_list = []
    for h in hari_list:
        tgl = h.isoformat()
        keluar_list.append(sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "keluar" and t["tanggal"][:10] == tgl))
        masuk_list.append(sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "masuk" and t["tanggal"][:10] == tgl))

    x = range(len(hari_list))
    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#1a1a2e")
    ax.set_facecolor("#16213e")

    bar_width = 0.35
    bars1 = ax.bar([i - bar_width/2 for i in x], masuk_list, bar_width, color="#4ECDC4", label="Pemasukan", alpha=0.9)
    bars2 = ax.bar([i + bar_width/2 for i in x], keluar_list, bar_width, color="#FF6B6B", label="Pengeluaran", alpha=0.9)

    ax.set_xticks(list(x))
    ax.set_xticklabels(label_hari, color="white", fontsize=8)
    ax.yaxis.set_visible(False)
    ax.spines[:].set_visible(False)
    ax.set_title("Pemasukan vs Pengeluaran 7 Hari Terakhir", color="white", fontsize=12, fontweight="bold", pad=15)
    ax.legend(frameon=False, labelcolor="white")

    max_val = max(keluar_list + masuk_list) if max(keluar_list + masuk_list) > 0 else 1
    for bar in bars1:
        h = bar.get_height()
        if h > 0:
            ax.text(bar.get_x() + bar.get_width()/2, h + max_val*0.01,
                    f"{h/1000:.0f}k", ha="center", color="#4ECDC4", fontsize=7)
    for bar in bars2:
        h = bar.get_height()
        if h > 0:
            ax.text(bar.get_x() + bar.get_width()/2, h + max_val*0.01,
                    f"{h/1000:.0f}k", ha="center", color="#FF6B6B", fontsize=7)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="#1a1a2e")
    buf.seek(0)
    plt.close()

    await update.message.reply_photo(photo=buf, caption="📊 *Grafik 7 Hari Terakhir*", parse_mode="Markdown")

async def grafik_tren(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import timedelta
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)

    hari_list = [(date.today() - timedelta(days=i)) for i in range(29, -1, -1)]
    label_hari = [h.strftime("%d/%m") for h in hari_list]

    keluar_list = []
    for h in hari_list:
        tgl = h.isoformat()
        keluar_list.append(sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "keluar" and t["tanggal"][:10] == tgl))

    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#1a1a2e")
    ax.set_facecolor("#16213e")

    ax.fill_between(range(len(hari_list)), keluar_list, alpha=0.3, color="#FF6B6B")
    ax.plot(range(len(hari_list)), keluar_list, color="#FF6B6B", linewidth=2, marker="o", markersize=3)

    ax.set_xticks(range(0, len(hari_list), 5))
    ax.set_xticklabels([label_hari[i] for i in range(0, len(hari_list), 5)], color="white", fontsize=8)
    ax.yaxis.set_visible(False)
    ax.spines[:].set_visible(False)
    ax.set_title("Tren Pengeluaran 30 Hari Terakhir", color="white", fontsize=12, fontweight="bold", pad=15)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="#1a1a2e")
    buf.seek(0)
    plt.close()

    await update.message.reply_photo(photo=buf, caption="📉 *Tren Pengeluaran 30 Hari*", parse_mode="Markdown")

# ─── PENGINGAT HARIAN ─────────────────────────────────────────────────────────

async def kirim_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.data["user_id"]
    data = load_data()
    ud = get_user_data(data, user_id)

    hari_ini = date.today().isoformat()
    bulan_ini = date.today().strftime("%Y-%m")
    keluar_hari = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "keluar" and t["tanggal"][:10] == hari_ini)
    masuk_hari = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "masuk" and t["tanggal"][:10] == hari_ini)
    keluar_bln = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "keluar" and t["tanggal"][:7] == bulan_ini)
    masuk_bln = sum(t["jumlah"] for t in ud["transaksi"] if t["tipe"] == "masuk" and t["tanggal"][:7] == bulan_ini)

    teks = (
        f"⏰ *Pengingat Keuangan Harian*\n"
        f"_{date.today().strftime('%A, %d %B %Y')}_\n\n"
        f"*Hari Ini:*\n"
        f"💰 Masuk: {format_rupiah(masuk_hari)}\n"
        f"💸 Keluar: {format_rupiah(keluar_hari)}\n\n"
        f"*Bulan Ini:*\n"
        f"💰 Masuk: {format_rupiah(masuk_bln)}\n"
        f"💸 Keluar: {format_rupiah(keluar_bln)}\n"
        f"{'🟢' if masuk_bln >= keluar_bln else '🔴'} Saldo: *{format_rupiah(masuk_bln - keluar_bln)}*\n\n"
        f"_Jangan lupa catat transaksi hari ini ya!_ 📝"
    )
    await context.bot.send_message(chat_id=user_id, text=teks, parse_mode="Markdown")

async def reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user_id = update.effective_user.id

    if not args:
        await update.message.reply_text("❌ Format: `/reminder 20:00` atau `/reminder off`", parse_mode="Markdown")
        return

    if args[0].lower() == "off":
        current_jobs = context.job_queue.get_jobs_by_name(f"reminder_{user_id}")
        for job in current_jobs:
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

    current_jobs = context.job_queue.get_jobs_by_name(f"reminder_{user_id}")
    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_daily(
        kirim_reminder,
        time=waktu,
        data={"user_id": user_id},
        name=f"reminder_{user_id}"
    )

    data = load_data()
    ud = get_user_data(data, user_id)
    ud["reminder"] = args[0]
    save_data(data)

    await update.message.reply_text(
        f"⏰ Pengingat harian diset jam *{args[0]}*!\n"
        f"Kamu akan dapat ringkasan keuangan setiap hari otomatis. 😊",
        parse_mode="Markdown"
    )

# ─── /reset ───────────────────────────────────────────────────────────────────

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("✅ Ya, hapus semua", callback_data="reset_ya"),
        InlineKeyboardButton("❌ Batal", callback_data="reset_tidak"),
    ]]
    await update.message.reply_text(
        "⚠️ *Yakin mau hapus SEMUA data?*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "reset_ya":
        data = load_data()
        uid = str(query.from_user.id)
        data[uid] = {"transaksi": [], "budget": {}, "reminder": None}
        save_data(data)
        await query.edit_message_text("🗑 Semua data telah dihapus.")
    else:
        await query.edit_message_text("✅ Reset dibatalkan.")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("keluar", keluar))
    app.add_handler(CommandHandler("masuk", masuk))
    app.add_handler(CommandHandler("ringkasan", ringkasan))
    app.add_handler(CommandHandler("laporan", laporan))
    app.add_handler(CommandHandler("riwayat", riwayat))
    app.add_handler(CommandHandler("budget", budget))
    app.add_handler(CommandHandler("cek_budget", cek_budget))
    app.add_handler(CommandHandler("grafik_kategori", grafik_kategori))
    app.add_handler(CommandHandler("grafik_mingguan", grafik_mingguan))
    app.add_handler(CommandHandler("grafik_tren", grafik_tren))
    app.add_handler(CommandHandler("reminder", reminder))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))

    print("🤖 Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
