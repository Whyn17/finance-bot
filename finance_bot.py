"""
Bot Telegram: Personal Finance Tracker
Fitur: Catat keuangan, 1 grafik ringkasan, pengingat harian
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
        data[uid] = {"transaksi": [], "budget": {}, "reminder": None}
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
        "📌 *Perintah:*\n\n"
        "💸 `/keluar 50000 makan siang`\n"
        "💰 `/masuk 3000000 gaji`\n"
        "📊 `/ringkasan` – saldo hari ini\n"
        "📋 `/laporan` – rincian bulan ini\n"
        "🕐 `/riwayat` – 10 transaksi terakhir\n"
        "🎯 `/budget makan 1500000`\n"
        "✅ `/cek_budget` – sisa budget\n"
        "📈 `/grafik` – grafik keuangan bulan ini\n\n"
        "⏰ *Pengingat:*\n"
        "`/reminder 20:00` – set pengingat harian\n"
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
    masuk_hari = sum(t["jumlah"] for t in transaksi if t["tipe"] == "masuk" and t["tanggal"][:10] == hari_ini)
    keluar_bln = sum(t["jumlah"] for t in transaksi if t["tipe"] == "keluar" and t["tanggal"][:7] == bulan_ini)
    masuk_bln = sum(t["jumlah"] for t in transaksi if t["tipe"] == "masuk" and t["tanggal"][:7] == bulan_ini)
    saldo = masuk_bln - keluar_bln

    await update.message.reply_text(
        f"📊 *Ringkasan — {date.today().strftime('%d %B %Y')}*\n\n"
        f"*Hari Ini:*\n💰 Masuk: {format_rupiah_full(masuk_hari)}\n💸 Keluar: {format_rupiah_full(keluar_hari)}\n\n"
        f"*Bulan Ini:*\n💰 Masuk: {format_rupiah_full(masuk_bln)}\n💸 Keluar: {format_rupiah_full(keluar_bln)}\n"
        f"{'🟢' if saldo >= 0 else '🔴'} Saldo: *{format_rupiah_full(saldo)}*",
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

# ─── /grafik ──────────────────────────────────────────────────────────────────

WARNA_KELUAR = ["#FF6B6B","#FF8E8E","#FFB3B3","#FF5252","#E53935","#EF9A9A","#FFCDD2","#D32F2F","#FF7043","#FF8A65"]
WARNA_MASUK  = ["#4ECDC4","#26C6DA","#80DEEA","#00BCD4","#26A69A","#80CBC4","#B2DFDB","#00897B","#4DB6AC","#00ACC1"]
BG = "#0f0f1a"
PANEL = "#1a1a2e"

async def grafik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    ud = get_user_data(data, update.effective_user.id)
    bulan_ini = date.today().strftime("%Y-%m")
    nama_bulan = date.today().strftime("%B %Y")

    # Kumpulkan data
    keluar_kat = defaultdict(float)
    masuk_kat = defaultdict(float)
    for t in ud["transaksi"]:
        if t["tanggal"][:7] != bulan_ini:
            continue
        if t["tipe"] == "keluar":
            keluar_kat[t["kategori"]] += t["jumlah"]
        else:
            masuk_kat[t["kategori"]] += t["jumlah"]

    if not keluar_kat and not masuk_kat:
        await update.message.reply_text("_Belum ada transaksi bulan ini._", parse_mode="Markdown")
        return

    total_masuk = sum(masuk_kat.values())
    total_keluar = sum(keluar_kat.values())
    saldo = total_masuk - total_keluar

    # Tren 14 hari
    hari_list = [(date.today() - timedelta(days=i)) for i in range(13, -1, -1)]
    tren_keluar = [sum(t["jumlah"] for t in ud["transaksi"]
        if t["tipe"] == "keluar" and t["tanggal"][:10] == h.isoformat()) for h in hari_list]
    tren_masuk = [sum(t["jumlah"] for t in ud["transaksi"]
        if t["tipe"] == "masuk" and t["tanggal"][:10] == h.isoformat()) for h in hari_list]
    label_hari = [h.strftime("%d/%m") for h in hari_list]

    # ── Layout: 2 baris, 3 kolom ──────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 9), facecolor=BG)
    gs = gridspec.GridSpec(2, 3, figure=fig,
                           hspace=0.45, wspace=0.35,
                           left=0.06, right=0.97, top=0.88, bottom=0.1)

    ax_pie_k  = fig.add_subplot(gs[0, 0])   # pie pengeluaran
    ax_pie_m  = fig.add_subplot(gs[0, 1])   # pie pemasukan
    ax_info   = fig.add_subplot(gs[0, 2])   # kotak info ringkasan
    ax_tren   = fig.add_subplot(gs[1, :])   # tren 14 hari full width

    for ax in [ax_pie_k, ax_pie_m, ax_info, ax_tren]:
        ax.set_facecolor(PANEL)

    # ── Judul utama ───────────────────────────────────────────────────────────
    fig.text(0.5, 0.94, f"📊 Laporan Keuangan — {nama_bulan}",
             ha="center", va="center", color="white",
             fontsize=15, fontweight="bold")

    # ── PIE 1: Pengeluaran per kategori ──────────────────────────────────────
    if keluar_kat:
        kat_k = list(keluar_kat.keys())
        val_k = list(keluar_kat.values())
        clr_k = WARNA_KELUAR[:len(kat_k)]
        wedges, _, autotexts = ax_pie_k.pie(
            val_k, colors=clr_k, autopct="%1.0f%%",
            startangle=90, pctdistance=0.72,
            wedgeprops=dict(width=0.55, edgecolor=PANEL, linewidth=1.5)
        )
        for at in autotexts:
            at.set(color="white", fontsize=7, fontweight="bold")
        ax_pie_k.set_title("💸 Pengeluaran", color="#FF6B6B", fontsize=10, fontweight="bold", pad=8)
        ax_pie_k.text(0, 0, format_rupiah(total_keluar),
                      ha="center", va="center", color="white", fontsize=8, fontweight="bold")
        legend_k = [mpatches.Patch(color=clr_k[i], label=f"{kat_k[i]} ({format_rupiah(val_k[i])})")
                    for i in range(len(kat_k))]
        ax_pie_k.legend(handles=legend_k, loc="lower center",
                        bbox_to_anchor=(0.5, -0.28), ncol=1,
                        frameon=False, labelcolor="white", fontsize=7)
    else:
        ax_pie_k.text(0.5, 0.5, "Tidak ada\npengeluaran",
                      ha="center", va="center", color="#888", transform=ax_pie_k.transAxes)
        ax_pie_k.set_title("💸 Pengeluaran", color="#FF6B6B", fontsize=10, fontweight="bold", pad=8)
        ax_pie_k.axis("off")

    # ── PIE 2: Pemasukan per sumber ───────────────────────────────────────────
    if masuk_kat:
        kat_m = list(masuk_kat.keys())
        val_m = list(masuk_kat.values())
        clr_m = WARNA_MASUK[:len(kat_m)]
        wedges2, _, autotexts2 = ax_pie_m.pie(
            val_m, colors=clr_m, autopct="%1.0f%%",
            startangle=90, pctdistance=0.72,
            wedgeprops=dict(width=0.55, edgecolor=PANEL, linewidth=1.5)
        )
        for at in autotexts2:
            at.set(color="white", fontsize=7, fontweight="bold")
        ax_pie_m.set_title("💰 Pemasukan", color="#4ECDC4", fontsize=10, fontweight="bold", pad=8)
        ax_pie_m.text(0, 0, format_rupiah(total_masuk),
                      ha="center", va="center", color="white", fontsize=8, fontweight="bold")
        legend_m = [mpatches.Patch(color=clr_m[i], label=f"{kat_m[i]} ({format_rupiah(val_m[i])})")
                    for i in range(len(kat_m))]
        ax_pie_m.legend(handles=legend_m, loc="lower center",
                        bbox_to_anchor=(0.5, -0.28), ncol=1,
                        frameon=False, labelcolor="white", fontsize=7)
    else:
        ax_pie_m.text(0.5, 0.5, "Tidak ada\npemasukan",
                      ha="center", va="center", color="#888", transform=ax_pie_m.transAxes)
        ax_pie_m.set_title("💰 Pemasukan", color="#4ECDC4", fontsize=10, fontweight="bold", pad=8)
        ax_pie_m.axis("off")

    # ── KOTAK INFO RINGKASAN ──────────────────────────────────────────────────
    ax_info.axis("off")
    ax_info.set_title("📋 Ringkasan", color="white", fontsize=10, fontweight="bold", pad=8)

    items = [
        ("Total Masuk",   format_rupiah_full(total_masuk),  "#4ECDC4"),
        ("Total Keluar",  format_rupiah_full(total_keluar), "#FF6B6B"),
        ("Saldo",         format_rupiah_full(saldo),        "#FFD700" if saldo >= 0 else "#FF4444"),
    ]
    for i, (label, val, clr) in enumerate(items):
        y = 0.78 - i * 0.28
        ax_info.add_patch(plt.Rectangle((0.05, y - 0.12), 0.9, 0.22,
                          transform=ax_info.transAxes, color="#0f0f1a",
                          clip_on=False, zorder=0, linewidth=0))
        ax_info.text(0.5, y + 0.04, label, ha="center", va="center",
                     transform=ax_info.transAxes, color="#aaa", fontsize=8)
        ax_info.text(0.5, y - 0.07, val, ha="center", va="center",
                     transform=ax_info.transAxes, color=clr, fontsize=10, fontweight="bold")

    emoji_saldo = "🟢 Surplus" if saldo >= 0 else "🔴 Defisit"
    ax_info.text(0.5, 0.04, emoji_saldo, ha="center", va="center",
                 transform=ax_info.transAxes, color="#FFD700" if saldo >= 0 else "#FF4444",
                 fontsize=9, fontweight="bold")

    # ── TREN 14 HARI ─────────────────────────────────────────────────────────
    x = range(len(hari_list))
    ax_tren.fill_between(x, tren_masuk, alpha=0.15, color="#4ECDC4")
    ax_tren.fill_between(x, tren_keluar, alpha=0.15, color="#FF6B6B")
    ax_tren.plot(x, tren_masuk, color="#4ECDC4", linewidth=2, marker="o", markersize=4, label="Masuk")
    ax_tren.plot(x, tren_keluar, color="#FF6B6B", linewidth=2, marker="o", markersize=4, label="Keluar")

    ax_tren.set_xticks(list(x))
    ax_tren.set_xticklabels(label_hari, color="white", fontsize=7.5)
    ax_tren.yaxis.set_visible(False)
    ax_tren.spines[:].set_visible(False)
    ax_tren.tick_params(colors="white")
    ax_tren.set_title("📈 Tren 14 Hari Terakhir", color="white", fontsize=10, fontweight="bold", pad=8)
    ax_tren.legend(frameon=False, labelcolor="white", fontsize=8, loc="upper left")

    # label nilai di titik
    max_val = max(max(tren_masuk, default=0), max(tren_keluar, default=0))
    for i, (m, k) in enumerate(zip(tren_masuk, tren_keluar)):
        if m > 0:
            ax_tren.text(i, m + max_val * 0.04, format_rupiah(m),
                         ha="center", color="#4ECDC4", fontsize=6.5)
        if k > 0:
            ax_tren.text(i, k + max_val * 0.04, format_rupiah(k),
                         ha="center", color="#FF6B6B", fontsize=6.5)

    # ── Render & kirim ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=BG, bbox_inches="tight")
    buf.seek(0)
    plt.close()

    saldo_teks = f"{'🟢 Surplus' if saldo >= 0 else '🔴 Defisit'} {format_rupiah_full(abs(saldo))}"
    caption = (
        f"📊 *Grafik Keuangan — {nama_bulan}*\n"
        f"💰 Masuk: {format_rupiah_full(total_masuk)}\n"
        f"💸 Keluar: {format_rupiah_full(total_keluar)}\n"
        f"{saldo_teks}"
    )
    await update.message.reply_photo(photo=buf, caption=caption, parse_mode="Markdown")

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
        f"💰 Masuk: {format_rupiah_full(masuk_hari)}\n"
        f"💸 Keluar: {format_rupiah_full(keluar_hari)}\n\n"
        f"*Bulan Ini:*\n"
        f"💰 Masuk: {format_rupiah_full(masuk_bln)}\n"
        f"💸 Keluar: {format_rupiah_full(keluar_bln)}\n"
        f"{'🟢' if masuk_bln >= keluar_bln else '🔴'} Saldo: *{format_rupiah_full(masuk_bln - keluar_bln)}*\n\n"
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
    app.add_handler(CommandHandler("grafik", grafik))
    app.add_handler(CommandHandler("reminder", reminder))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))

    print("🤖 Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
