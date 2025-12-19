import requests
import logging
import os
import re
import json
import asyncio
import nest_asyncio

from flask import Flask, request as flask_request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)

# --- KONFIGURASI DAN STATES ---

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logging.error("BOT_TOKEN Environment Variable tidak ditemukan. Aplikasi tidak akan berfungsi.")

MAKE_WEBHOOK_URL = "https://hook.eu2.make.com/b80ogwk3q1wuydgfgwjgq0nsvcwhot96"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

START_ROUTE, CHOOSE_CATEGORY, GET_NOMINAL, GET_DESCRIPTION, PREVIEW = range(5)

KATEGORI_MASUK = {
    'Gaji': 'masuk_gaji', 'Bonus': 'masuk_bonus', 'Hadiah': 'masuk_hadiah',
    'Lainnya': 'masuk_lainnya'
}
KATEGORI_KELUAR = {
    'Angsuran': 'keluar_angsuran', 'Asuransi': 'keluar_asuransi', 'Belanja': 'keluar_belanja',
    'Hewan': 'keluar_hewan', 'Hiburan': 'keluar_hiburan', 'Investasi': 'keluar_investasi',
    'Kendaraan': 'keluar_kendaraan', 'Kesehatan': 'keluar_kesehatan', 'Langganan': 'keluar_langganan',
    'Makan': 'keluar_makan', 'Pajak': 'keluar_pajak', 'Pakaian': 'keluar_pakaian',
    'Pendidikan': 'keluar_pendidikan', 'Perawatan': 'keluar_perawatan',
    'Rumah Tangga': 'keluar_rumahtangga', 'Tabungan': 'keluar_tabungan', 'Lainnya': 'keluar_lainnya'
}

# --- FUNGSI UTILITY KRITIS (Workaround Event Loop) ---

async def delete_message_safe(context, chat_id, message_id, log_prefix="Pesan"):
    """Menghapus pesan menggunakan pemanggilan async standar, rentan pada Vercel."""
    
    if not message_id:
        return

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logging.info(f"Berhasil menghapus {log_prefix} ID: {message_id} (Safe Delete).")
    except Exception as e:
        logging.warning(f"Gagal menghapus {log_prefix} ID: {message_id}. Error: {e}")
        pass

def send_to_make(data):
    """Mengirim payload data ke webhook Make."""
    try:
        response = requests.post(MAKE_WEBHOOK_URL, json=data)
        response.raise_for_status()
        logging.info(f"Data terkirim ke Make. Status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Gagal mengirim data ke Make: {e}")
        return False

def format_nominal(nominal):
    return "{:,.0f}".format(nominal).replace(",", ".")

def generate_preview(user_data):
    transaksi = user_data.get('transaksi', 'N/A')
    kategori_nama = user_data.get('kategori_nama', 'N/A')
    nominal = user_data.get('nominal', 0)
    keterangan = user_data.get('keterangan', 'N/A')
    nominal_formatted = format_nominal(nominal)
    
    preview_text = f"*Ringkasan Pencatatan:*\n\n"
    preview_text += f"*Transaksi:* {transaksi}\n"
    preview_text += f"*Kategori:* {kategori_nama}\n"
    preview_text += f"*Nominal:* Rp {nominal_formatted}\n"
    preview_text += f"*Keterangan:* {keterangan}\n\n"
    preview_text += f"*{transaksi} Rp {nominal_formatted} {kategori_nama} {keterangan}*"
    return preview_text

def debug_check_ids(context):
    """Mencetak ID pesan yang seharusnya dihapus untuk debugging."""
    chat_id = context._chat_id
    nominal_id = context.user_data.get('nominal_request_message_id')
    
    if nominal_id:
        logging.info(f"DEBUG: nominal_request_message_id = {nominal_id} (Chat: {chat_id}). ID siap dihapus.")
    else:
        logging.warning(f"DEBUG: nominal_request_message_id TIDAK DITEMUKAN atau None.")
    return nominal_id

def get_menu_transaksi():
    keyboard = [
        [InlineKeyboardButton("✅ Masuk", callback_data='transaksi_masuk')],
        [InlineKeyboardButton("❌ Keluar", callback_data='transaksi_keluar')],
        [InlineKeyboardButton("💳 Tabungan", callback_data='transaksi_tabungan')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_menu_kategori(kategori_dict, route_name):
    keyboard = []
    row = []
    for nama, data in kategori_dict.items():
        row.append(InlineKeyboardButton(nama, callback_data=data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Menu Transaksi", callback_data='kembali_transaksi')])
    return InlineKeyboardMarkup(keyboard)

def get_menu_preview():
    keyboard = [
        [InlineKeyboardButton("✅ Kirim", callback_data='aksi_kirim')],
        [InlineKeyboardButton("Ubah Transaksi", callback_data='ubah_transaksi'),
         InlineKeyboardButton("Ubah Kategori", callback_data='ubah_kategori')],
        [InlineKeyboardButton("Ubah Nominal", callback_data='ubah_nominal'),
         InlineKeyboardButton("Ubah Keterangan", callback_data='ubah_keterangan')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_menu_kembali(callback_data):
    keyboard = [
        [InlineKeyboardButton("⬅️ Kembali ke Menu Sebelumnya", callback_data=callback_data)],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- HANDLERS UTAMA (Semua fungsi async) ---

async def start(update: Update, context):
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # --- 1. HAPUS FALLBACK MESSAGE LAMA DARI SESI SEBELUMNYA ---
    # Ini memastikan pesan "Gagal menampilkan menu interaktif..." dari sesi Cold Start yang gagal dihapus.
    fallback_id_to_delete = context.user_data.pop('fallback_message_id', None)
    await delete_message_safe(context, chat_id, fallback_id_to_delete, "pesan fallback")

    # KRITIS: Hapus pesan konfirmasi cancel
    cancel_conf_id_to_delete = context.user_data.pop('cancel_confirmation_id', None)
    await delete_message_safe(context, chat_id, cancel_conf_id_to_delete, "pesan konfirmasi cancel")
    # -----------------------------------------------------------

    # 2. Siapkan dan Bersihkan Data
    user_data_identity = {
        'user_id': user.id,
        'first_name': user.first_name,
        'username': user.username if user.username else 'NoUsername'
    }

    context.user_data.clear() # Membersihkan semua data transaksi lama
    context.user_data.update(user_data_identity) # Memasukkan kembali identitas pengguna
    
    text = "Halo! Silakan pilih transaksi yang ingin Anda catat:"
    
    if update.message or update.callback_query:
        try:
            # 3. COBA KIRIM MENU UTAMA (SUCCESS CASE)
            menu_message = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=get_menu_transaksi()
            )
            logging.info(f"Pesan 'start' berhasil dikirim ke chat {chat_id}")
            
            # KRITIS: Simpan ID menu awal agar bisa dihapus oleh /cancel
            context.user_data['start_menu_id'] = menu_message.message_id
            
            # 4. Penanganan Query Lama (jika start dipanggil dari callback query)
            if update.callback_query:
                try:
                    await update.callback_query.answer()
                    await delete_message_safe(context, chat_id, update.callback_query.message.message_id, "pesan tombol lama")
                except Exception:
                    pass

        except Exception as e:
            # 5. KETIKA GAGAL KARENA RuntimeError (COLD START ERROR CASE)
            logging.error(f"Gagal mengirim pesan 'start' ke chat {chat_id} (Kemungkinan Cold Start): {e}")
            
            # --- FALLBACK: Mengirim Pesan Sederhana & Menyimpan ID ---
            try:
                fallback_message = await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Gagal menampilkan menu interaktif. Silakan coba /start lagi.",
                    parse_mode='Markdown'
                )
                context.user_data['fallback_message_id'] = fallback_message.message_id
                logging.warning("Pesan fallback instruksi start berhasil dikirim.")
            except Exception as fe:
                logging.error(f"Pesan fallback juga gagal terkirim: {fe}")
            # --------------------------------------------------------

    # 6. Hapus pesan /start user
    if update.message:
        await delete_message_safe(context, chat_id, update.message.message_id, "pesan /start user")
            
    return CHOOSE_CATEGORY

async def cancel(update: Update, context):
    chat_id = update.effective_chat.id
    
    # List semua ID yang mungkin perlu dihapus saat pembatalan
    ids_to_check = [
        'nominal_request_message_id', 
        'description_request_message_id',
        'fallback_message_id', 
        'category_menu_id',       
        'preview_message_id',     
        'start_menu_id',
        'cancel_confirmation_id' # Masih perlu dibersihkan jika ada sisa dari sesi sebelumnya
    ]
    
    # 1. Hapus semua ID pesan interaktif lama
    for key in ids_to_check:
        message_id = context.user_data.pop(key, None)
        if message_id:
            await delete_message_safe(context, chat_id, message_id, f"Pesan {key}")
            
    # --- VARIABEL SEMENTARA UNTUK MENYIMPAN ID KONFIRMASI BARU ---
    conf_id = None 
    # -----------------------------------------------------------

    if update.message:
        # Hapus pesan /cancel dari pengguna
        await delete_message_safe(context, chat_id, update.message.message_id, "Pesan user /cancel")
        
        # Kirim pesan konfirmasi
        confirmation_message = await context.bot.send_message(
            chat_id=chat_id,
            text="✅ *Pencatatan dibatalkan.* Silakan gunakan /start untuk memulai lagi.",
            parse_mode='Markdown'
        )
        # Ambil ID untuk disimpan secara temporer
        conf_id = confirmation_message.message_id
        
    elif update.callback_query:
        query = update.callback_query
        try:
            await query.answer()
            
            # Edit pesan tombol
            await query.edit_message_text(
                "✅ *Pencatatan dibatalkan.* Silakan gunakan /start untuk memulai lagi.",
                parse_mode='Markdown'
            )
            # Ambil ID untuk disimpan secara temporer (ID pesan yang di-edit)
            conf_id = query.message.message_id
            
        except Exception as e:
            logging.warning(f"Gagal edit pesan saat cancel: {e}. Mengirim pesan baru.")
            
            # Jika gagal edit, kirim pesan baru
            confirmation_message = await context.bot.send_message(
                chat_id=chat_id,
                text="✅ *Pencatatan dibatalkan.* Data lama telah dibersihkan. Silakan gunakan /start untuk memulai lagi.",
                parse_mode='Markdown'
            )
            conf_id = confirmation_message.message_id
    
    # --- FIX KRITIS: BERSIHKAN DATA SESI LALU SISAKAN ID KONFIRMASI ---
    context.user_data.clear()
    
    # Pasang kembali ID konfirmasi yang baru saja didapat (HANYA INI YANG DISIMPAN)
    if conf_id:
        context.user_data['cancel_confirmation_id'] = conf_id
        
    return ConversationHandler.END

async def choose_route(update: Update, context):
    query = update.callback_query
    
    # --- Defensive Coding: Menjawab Query ---
    try:
        await query.answer()
    except Exception as e:
        logging.warning(f"Gagal menjawab query di choose_route: {e}")
    # ---------------------------------------
    
    data = query.data
    chat_id = query.message.chat_id
    text = ""
    
    if data == 'transaksi_masuk':
        context.user_data['transaksi'] = 'Masuk'
        context.user_data['kategori_dict'] = KATEGORI_MASUK
        text = "Silahkan pilih *Kategori* dari Pemasukan:"
    elif data == 'transaksi_keluar':
        context.user_data['transaksi'] = 'Keluar'
        context.user_data['kategori_dict'] = KATEGORI_KELUAR
        text = "Silahkan pilih *Kategori* dari Pengeluaran:"
    elif data == 'transaksi_tabungan':
        context.user_data['transaksi'] = 'Tabungan'
        context.user_data['kategori_dict'] = KATEGORI_KELUAR
        text = "Anda memilih *Tabungan*. Pengeluaran akan dilakukan dari Tabungan. Silahkan Pilih *Kategori*:"
    else:
        await context.bot.send_message(chat_id, "Terjadi kesalahan. Silakan mulai ulang dengan /start.")
        return ConversationHandler.END

    try:
        # Coba edit pesan yang membawa tombol transaksi (menu awal)
        await query.edit_message_text(
            text,
            reply_markup=get_menu_kategori(context.user_data['kategori_dict'], data),
            parse_mode='Markdown'
        )
        
        # --- PERBAIKAN A: Simpan ID pesan menu kategori yang sekarang (setelah di edit) ---
        context.user_data['category_menu_id'] = query.message.message_id
        # ---------------------------------------------------------------------------------

    except Exception as e:
        logging.error(f"Gagal edit pesan di choose_route: {e}. Mengirim pesan baru.")
        new_message = await context.bot.send_message(
            chat_id,
            text,
            reply_markup=get_menu_kategori(context.user_data['kategori_dict'], data),
            parse_mode='Markdown'
        )
        # --- PERBAIKAN A: Simpan ID pesan menu kategori yang baru ---
        context.user_data['category_menu_id'] = new_message.message_id
        # -----------------------------------------------------------
        
    return GET_NOMINAL

async def choose_category(update: Update, context):
    query = update.callback_query
    
    try:
        await query.answer()
    except Exception:
        pass
        
    data = query.data
    chat_id = query.message.chat_id
    
    if data == 'kembali_transaksi':
        return await start(update, context)
    
    kategori_dict = context.user_data.get('kategori_dict', {})
    kategori_nama = next((nama for nama, data_cb in kategori_dict.items() if data_cb == data), 'N/A')
    
    context.user_data['kategori_nama'] = kategori_nama
    
    text = f"Anda memilih *Transaksi {context.user_data['transaksi']}* dengan *Kategori {kategori_nama}*.\n\n"
    text += "Sekarang, *tuliskan jumlah nominal transaksi* (hanya angka, tanpa titik/koma/Rp):"
    
    try:
        sent_message = await update.callback_query.message.reply_text(
            text,
            reply_markup=get_menu_kembali('kembali_kategori'),
            parse_mode='Markdown'
        )
        await delete_message_safe(context, chat_id, update.callback_query.message.message_id, "pesan kategori lama")
        context.user_data['nominal_request_message_id'] = sent_message.message_id
    except Exception as e:
        logging.error(f"Gagal mengirim/menghapus pesan di choose_category: {e}")
        context.user_data['nominal_request_message_id'] = None

    return GET_DESCRIPTION

async def get_nominal(update: Update, context):
    chat_id = update.message.chat_id
    user_message_id = update.message.message_id
    
    # --- PANGGILAN FUNGSI DEBUG UNTUK VERIFIKASI ID ---
    debug_check_ids(context) 
    # --------------------------------------------------

    # Hapus pesan error lama (jika ada)
    error_message_id = context.user_data.pop('error_message_id', None)
    await delete_message_safe(context, chat_id, error_message_id, "pesan error lama")
            
    nominal = None

    # 1. VALIDASI INPUT
    try:
        nominal_str = re.sub(r'\D', '', update.message.text)
        nominal = int(nominal_str)
        if nominal <= 0:
            raise ValueError
        
    except (ValueError, TypeError):
        # --- ERROR HANDLING: INPUT TIDAK VALID ---
        
        # Hapus pesan user yang salah
        await delete_message_safe(context, chat_id, user_message_id, "pesan user salah")
        
        # Kirim pesan error baru
        error_msg = await update.message.reply_text(
            "Nominal tidak valid. Harap masukkan *Hanya Angka Positif* (tanpa titik/koma/Rp).",
            parse_mode='Markdown'
        )
        context.user_data['error_message_id'] = error_msg.message_id
        
        return GET_DESCRIPTION

    # --- INPUT VALID: Penghapusan Pesan dan Lanjut State ---

    # 2. Hapus pesan User (Input Nominal yang Valid)
    await delete_message_safe(context, chat_id, user_message_id, "pesan user valid")

    # 3. Hapus pesan Bot Lama (Permintaan Nominal)
    bot_message_to_delete_id = context.user_data.pop('nominal_request_message_id', None)
    await delete_message_safe(context, chat_id, bot_message_to_delete_id, "pesan bot lama")
            
    # 4. Simpan Nominal dan Kirim Permintaan Keterangan
    context.user_data['nominal'] = nominal
    
    kategori_nama = context.user_data.get('kategori_nama', 'Kategori Tidak Ditemukan')
    
    text = f"Nominal: *Rp {format_nominal(nominal)}* berhasil dicatat sebagai *{kategori_nama}*.\n\n"
    text += "Sekarang, tambahkan *Keterangan* dari transaksi tersebut (misalnya, 'Bubur Ayam', 'Bayar Listrik'):"
    
    sent_message = await update.message.reply_text(
        text, 
        reply_markup=get_menu_kembali('kembali_nominal'), 
        parse_mode='Markdown'
    )
    context.user_data['description_request_message_id'] = sent_message.message_id
    
    return PREVIEW

async def get_description(update: Update, context):
    chat_id = update.message.chat_id
    user_message_id = update.message.message_id
    bot_message_to_delete_id = context.user_data.pop('description_request_message_id', None)
    
    keterangan = update.message.text
    context.user_data['keterangan'] = keterangan
    
    # --- Penghapusan Pesan ---

    # 1. Hapus pesan Bot Request Lama (Permintaan Keterangan)
    await delete_message_safe(context, chat_id, bot_message_to_delete_id, "Deskripsi Request")

    # 2. Hapus pesan User Input (Keterangan)
    await delete_message_safe(context, chat_id, user_message_id, "Deskripsi User Input")
        
    # --- Lanjut ke Preview ---
            
    preview_text = generate_preview(context.user_data)
    
    preview_message = await update.message.reply_text(
        preview_text,
        reply_markup=get_menu_preview(),
        parse_mode='Markdown'
    )
    context.user_data['preview_message_id'] = preview_message.message_id
    # ---------------------------------------------------------
    
    return PREVIEW
    
async def handle_kembali_actions(update: Update, context):
    query = update.callback_query
    
    # 1. Menjawab Query dan Mencoba Hapus Pesan Bot (Pesan Nominal/Keterangan)
    try:
        await query.answer()
    except Exception:
        pass
        
    # Hapus pesan yang memiliki tombol ini
    await delete_message_safe(context, query.message.chat_id, query.message.message_id, f"pesan kembali: {query.data}")
            
    action = query.data
    chat_id = query.message.chat_id
    
    if action == 'kembali_kategori':
        # Hapus sisa ID pesan nominal_request_message_id jika ada
        context.user_data.pop('nominal_request_message_id', None)
        
        kategori_dict = context.user_data.get('kategori_dict', {})
        transaksi = context.user_data.get('transaksi', 'N/A').lower()
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Silakan pilih Kategori baru untuk {context.user_data['transaksi']}:",
            reply_markup=get_menu_kategori(kategori_dict, transaksi),
            parse_mode='Markdown'
        )
        return GET_NOMINAL

    elif action == 'kembali_nominal':
        # --- LOGIKA PERBAIKAN BUG UBBAH NOMINAL ---
        
        # 1. Hapus ID pesan deskripsi/nominal lama (sudah dilakukan di awal fungsi ini)
        context.user_data.pop('description_request_message_id', None)
        
        # 2. Hapus nilai nominal dan keterangan yang tersimpan
        context.user_data.pop('nominal', None)
        context.user_data.pop('keterangan', None)
        
        # 3. Siapkan pesan untuk meminta nominal baru
        kategori_nama = context.user_data.get('kategori_nama', 'N/A')
        text = f"Anda memilih *Transaksi {context.user_data['transaksi']}* dengan *Kategori {kategori_nama}*.\n\n"
        text += "Sekarang, *tuliskan jumlah nominal transaksi* (hanya angka, tanpa titik/koma/Rp):"
        
        # 4. Kirim pesan permintaan nominal baru
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_menu_kembali('kembali_kategori'), 
            parse_mode='Markdown'
        )
        
        # Simpan ID pesan permintaan nominal yang baru
        context.user_data['nominal_request_message_id'] = sent_message.message_id
        
        # 5. Pindah state ke GET_DESCRIPTION (state yang menerima input nominal)
        return GET_DESCRIPTION

async def handle_preview_actions(update: Update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    
    # 1. Menjawab Query
    try:
        await query.answer()
    except Exception:
        pass
        
    # 2. Mencoba Menghapus Pesan Preview
    await delete_message_safe(context, chat_id, query.message.message_id, "pesan Preview")
            
    action = query.data
    
    if action == 'aksi_kirim':
        # ... Logic Kirim Data ...
        payload = {
            'user_id': context.user_data.get('user_id'),
            'first_name': context.user_data.get('first_name'),
            'username': context.user_data.get('username'),
            'transaksi': context.user_data.get('transaksi'),
            'kategori_nama': context.user_data.get('kategori_nama'),
            'nominal': context.user_data.get('nominal'),
            'keterangan': context.user_data.get('keterangan'),
        }
        
        current_username = payload.get('username')
        if not current_username or current_username.lower() == 'nousername':
            payload['username'] = 'NoUsernameSet'
        
        success = send_to_make(payload)
        
        transaksi_type = payload.get('transaksi', 'N/A')
        nominal_formatted = format_nominal(payload.get('nominal', 0))
        kategori_nama = payload.get('kategori_nama', 'N/A')
        keterangan = payload.get('keterangan', 'N/A')

        ringkasan_data = f"*Transaksi:* {transaksi_type} Rp {nominal_formatted} - {kategori_nama} ({keterangan})"

        if success:
            response_text = "✅ *Transaksi Berhasil Dicatat!*\nData Anda telah dikirim ke Spreadsheet.\n\n"
            response_text += ringkasan_data
            
            response_text += "\n\nCek Laporan Keuangan Anda pada: [Laporan Keuangan](https://docs.google.com/spreadsheets/d/1A2ephAX4I1zwxmvFlkSAeHRc7OjcN2peQqZgPsGZ8X8/edit?gid=550879818#gid=550879818)"
            response_text += "\n\nJika ingin melakukan pencatatan baru silahkan tekan /start"
        else:
            response_text = "❌ *Pencatatan Gagal!*\nTerjadi kesalahan saat mengirim data ke server. Silakan coba lagi /start"

        await context.bot.send_message(
            chat_id,
            response_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        context.user_data.clear()
        
        return ConversationHandler.END
        
    elif action == 'ubah_transaksi':
        return await start(update, context)
        
    elif action == 'ubah_kategori':
        # ... Logic Ubah Kategori ...
        kategori_dict = context.user_data.get('kategori_dict', {})
        transaksi = context.user_data.get('transaksi', 'N/A').lower()
        
        await context.bot.send_message(
            chat_id,
            f"Silakan pilih Kategori baru untuk {context.user_data['transaksi']}:",
            reply_markup=get_menu_kategori(kategori_dict, transaksi),
            parse_mode='Markdown'
        )
        return GET_NOMINAL
        
    elif action == 'ubah_nominal':
        # --- LOGIKA PERBAIKAN UBBAH NOMINAL ---
        context.user_data.pop('nominal', None)
        context.user_data.pop('keterangan', None) # Hapus keterangan agar alur kembali bersih
        
        text = f"Anda memilih *Transaksi {context.user_data['transaksi']}* dengan *Kategori {context.user_data['kategori_nama']}*.\n\n"
        text += "Sekarang, *tuliskan jumlah nominal transaksi* (hanya angka, tanpa titik/koma/Rp):"
        
        # Kirim pesan permintaan nominal baru dan simpan ID-nya
        sent_message = await context.bot.send_message(
             chat_id,
             text,
             reply_markup=get_menu_kembali('kembali_kategori'),
             parse_mode='Markdown'
           )
        context.user_data['nominal_request_message_id'] = sent_message.message_id # Simpan ID
        return GET_DESCRIPTION

    elif action == 'ubah_keterangan':
        # 1. Hapus nilai keterangan lama
        context.user_data.pop('keterangan', None)
        
        # 2. Ambil data yang akan ditampilkan
        nominal = context.user_data.get('nominal', 0)
        kategori_nama = context.user_data.get('kategori_nama', 'N/A')
        
        # 3. Bentuk pesan baru dengan informasi nominal
        text = f"Nominal: *Rp {format_nominal(nominal)}* berhasil dicatat sebagai *{kategori_nama}*.\n\n"
        text += "Sekarang, tambahkan *Keterangan* dari transaksi tersebut (misalnya, 'Bubur Ayam', 'Bayar Listrik'):"
        
        # 4. Kirim pesan dan simpan ID-nya
        sent_message = await context.bot.send_message(
             chat_id,
             text,
             reply_markup=get_menu_kembali('kembali_nominal'),
             parse_mode='Markdown'
           )
        
        # KRITIS: Simpan ID pesan ini agar bisa dihapus oleh get_description
        context.user_data['description_request_message_id'] = sent_message.message_id 
        
        return PREVIEW

    return PREVIEW


# --- FUNGSI ENTRY POINT UTAMA UNTUK SERVERLESS (KRITIS) ---

# Terapkan patch nest_asyncio di scope global
try:
    nest_asyncio.apply()
except RuntimeError:
    pass

# Inisialisasi Flask App (Vercel akan mencari instance 'app')
app = Flask(__name__)

# Deklarasi global untuk Application instance
application_instance = None

def init_application():
    """Menginisialisasi Application dan Conversation Handler."""
    global application_instance
    
    if not TOKEN:
        return None

    try:
        application = Application.builder().token(TOKEN).build()
        
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", start),
            ],
            states={
                CHOOSE_CATEGORY: [
                    CallbackQueryHandler(choose_route, pattern=r'^transaksi_(masuk|keluar|tabungan)$')
                ],
                
                GET_NOMINAL: [
                    CallbackQueryHandler(choose_category, pattern=r'^(masuk|keluar)_.*$|^kembali_transaksi$')
                ],
                
                GET_DESCRIPTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_nominal),
                    CallbackQueryHandler(handle_kembali_actions, pattern=r'^kembali_kategori$'),
                ],
                
                PREVIEW: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_description),
                    CallbackQueryHandler(handle_kembali_actions, pattern=r'^kembali_nominal$'),
                    CallbackQueryHandler(handle_preview_actions, pattern=r'^aksi_.*|ubah_.*$'),
                ]
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
            ],
            per_user=True,
            per_chat=True,
            allow_reentry=True
        )

        application.add_handler(conv_handler)
        logging.info("Aplikasi Telegram berhasil diinisialisasi.")
        return application
        
    except Exception as e:
        logging.error(f"Error saat inisialisasi Application: {e}")
        return None


@app.route('/webhook', methods=['POST'])
def flask_webhook_handler():
    """Fungsi handler Vercel/Flask. Pola Loop Baru per Request + Policy."""
    
    global application_instance
    
    # 1. Lazy Loading/Re-initialization
    if application_instance is None:
        application_instance = init_application()
    
    if application_instance is None:
        logging.error("Application instance tidak ditemukan.")
        return 'Internal Server Error', 500
        
    try:
        data = flask_request.get_json(force=True)
    except Exception as e:
        logging.error(f"Gagal parsing JSON request dari Telegram (Flask): {e}")
        return 'Bad Request', 400

    try:
        update = Update.de_json(data, application_instance.bot)
        
        # --- PERBAIKAN KRITIS UNTUK FINAL EVENT LOOP ---
        
        # 1. Tentukan Event Loop Policy (Penting untuk thread-safety di serverless)
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        
        # 2. Buat loop baru
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        
        # 3. PANGGIL INITIALIZE PADA SETIAP REQUEST
        new_loop.run_until_complete(application_instance.initialize())
        logging.info("Application instance berhasil di-reset koneksi HTTP-nya.")
            
        # 4. Jalankan pemrosesan update di loop baru
        new_loop.run_until_complete(application_instance.process_update(update))
        
        # ------------------------------------------------------

        logging.info("Update Telegram berhasil diproses oleh Application (Async complete).")
        return 'OK', 200
        
    except Exception as e:
        # PENTING: Set loop kembali ke None saat error untuk menghindari konflik pada request berikutnya
        asyncio.set_event_loop(None)
        
        logging.error(f"Error saat memproses Update: {e}")
        return 'Internal Server Error', 500









