import requests
import logging
import os
import re
import json # Diperlukan untuk parsing JSON request dari GCP
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes # Dipertahankan untuk kompatibilitas type hinting
)

# --- KONFIGURASI DAN STATES ---

# KRITIS UNTUK KEAMANAN: Mengambil Token dari Environment Variable GCP
TOKEN = os.environ.get("BOT_TOKEN") 
if not TOKEN:
    # Di GCP, ini akan tercatat sebagai error di Cloud Logging
    logging.error("BOT_TOKEN Environment Variable tidak ditemukan di GCP.")

# URL Webhook Make Anda (Ganti dengan URL Asli Anda)
MAKE_WEBHOOK_URL = "https://hook.eu2.make.com/b80ogwk3q1wuydgfgwjgq0nsvcwhot96"

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Definisi States (TETAP SAMA)
START_ROUTE, CHOOSE_CATEGORY, GET_NOMINAL, GET_DESCRIPTION, PREVIEW = range(5)

# Definisi Menu Kategori (TETAP SAMA)
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
    'RumahTangga': 'keluar_rumahtangga', 'Tabungan': 'keluar_tabungan', 'Lainnya': 'keluar_lainnya'
}

# --- FUNGSI UTILITY (TETAP SAMA) ---

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

# ... [Semua Utility Functions (format_nominal, generate_preview, get_menu_transaksi, dll) DITEMPATKAN DI SINI] ...

# Salin semua utility functions dari kode Anda sebelumnya di sini (tidak ditampilkan untuk menghemat ruang).
# Pastikan semua fungsi ini ada sebelum digunakan oleh handler di bawah.

def format_nominal(nominal):
    return "{:,.0f}".format(nominal).replace(",", ".")

def generate_preview(user_data):
    transaksi = user_data.get('transaksi', 'N/A')
    kategori_nama = user_data.get('kategori_nama', 'N/A')
    nominal = user_data.get('nominal', 0)
    keterangan = user_data.get('keterangan', 'N/A')
    nominal_formatted = format_nominal(nominal)
    
    preview_text = f"*Inputan Anda:*\n\n"
    preview_text += f"*Transaksi:* {transaksi}\n"
    preview_text += f"*Kategori:* {kategori_nama}\n"
    preview_text += f"*Nominal:* Rp {nominal_formatted}\n"
    preview_text += f"*Keterangan:* {keterangan}\n\n"
    preview_text += f"`{transaksi} {nominal} {kategori_nama} {keterangan}`"
    return preview_text

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


# --- HANDLERS UTAMA (Semua handler dipertahankan) ---

# Ganti ContextTypes.DEFAULT_TYPE dengan context (sesuai kode asli Anda)

async def start(update: Update, context):
    # ... (fungsi ini tetap sama) ...
    if update.message:
        user = update.message.from_user
    elif update.callback_query:
        query = update.callback_query
        user = query.from_user
        await query.answer()

    user_data_identity = {
        'user_id': user.id,
        'first_name': user.first_name,
        'username': user.username if user.username else 'NoUsername'
    }

    context.user_data.clear() 
    context.user_data.update(user_data_identity)
    
    text = "Halo! Silakan pilih transaksi yang ingin Anda catat:"
    
    if update.message:
        await update.message.reply_text(text, reply_markup=get_menu_transaksi())
    elif update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=get_menu_transaksi())
        except Exception:
            await context.bot.send_message(user.id, text, reply_markup=get_menu_transaksi())
        
    return CHOOSE_CATEGORY 

async def cancel(update: Update, context):
    # ... (fungsi ini tetap sama) ...
    await update.message.reply_text("Pencatatan dibatalkan. Gunakan /start untuk memulai lagi.")
    context.user_data.clear()
    return ConversationHandler.END

async def choose_route(update: Update, context):
    # ... (fungsi ini tetap sama) ...
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'transaksi_masuk':
        context.user_data['transaksi'] = 'Masuk' 
        context.user_data['kategori_dict'] = KATEGORI_MASUK
        text = "Silahkan Pilih Kategori dari Pemasukan"
    elif data == 'transaksi_keluar':
        context.user_data['transaksi'] = 'Keluar'
        context.user_data['kategori_dict'] = KATEGORI_KELUAR
        text = "Silahkan Pilih Kategori dari Pengeluaran"
    elif data == 'transaksi_tabungan':
        context.user_data['transaksi'] = 'Tabungan'
        context.user_data['kategori_dict'] = KATEGORI_KELUAR 
        text = "Anda memilih *Tabungan*. Pengeluaran akan dilakukan dari Tabungan. Silahkan Pilih Kategori:"
    else:
        await query.edit_message_text("Terjadi kesalahan. Silakan mulai ulang dengan /start.")
        return ConversationHandler.END

    await query.edit_message_text(
        text, 
        reply_markup=get_menu_kategori(context.user_data['kategori_dict'], data),
        parse_mode='Markdown'
    )
    return GET_NOMINAL 

async def choose_category(update: Update, context):
    # ... (fungsi ini tetap sama) ...
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'kembali_transaksi':
        return await start(update, context) 
    
    kategori_dict = context.user_data.get('kategori_dict', {})
    kategori_nama = next((nama for nama, data_cb in kategori_dict.items() if data_cb == data), 'N/A')
    
    context.user_data['kategori_nama'] = kategori_nama
    
    text = f"Anda memilih *Transaksi {context.user_data['transaksi']}* dengan *Kategori {kategori_nama}*.\n\n"
    text += "Sekarang, *tuliskan jumlah nominal transaksi* (hanya angka, tanpa titik/koma/Rp):"
    
    sent_message = await update.callback_query.message.reply_text(
        text, 
        reply_markup=get_menu_kembali('kembali_kategori'), 
        parse_mode='Markdown'
    )
    
    await update.callback_query.message.delete()

    context.user_data['nominal_request_message_id'] = sent_message.message_id
    
    return GET_DESCRIPTION 

async def get_nominal(update: Update, context):
    # ... (fungsi ini tetap sama) ...
    chat_id = update.message.chat_id
    user_message_id = update.message.message_id
    
    error_message_id = context.user_data.pop('error_message_id', None)
    if error_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=error_message_id)
        except Exception as e:
            logging.warning(f"Gagal menghapus pesan error lama: {e}")
            
    bot_message_to_delete_id = context.user_data.get('nominal_request_message_id')
    
    try:
        nominal_str = re.sub(r'\D', '', update.message.text)
        nominal = int(nominal_str)
        if nominal <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id) 
        
        error_msg = await update.message.reply_text(
            "Nominal tidak valid. Harap masukkan *Hanya Angka Positif* (tanpa titik/koma/Rp).",
            parse_mode='Markdown'
        )
        context.user_data['error_message_id'] = error_msg.message_id
        
        return GET_DESCRIPTION 

    await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id) 
    
    if bot_message_to_delete_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=bot_message_to_delete_id)
            context.user_data.pop('nominal_request_message_id', None)
        except Exception as e:
            logging.warning(f"Gagal menghapus pesan bot: {e}")
    
    context.user_data['nominal'] = nominal
    
    text = f"Nominal: *Rp {format_nominal(nominal)}* berhasil dicatat.\n\n"
    text += "Sekarang, tambahkan *Keterangan* dari transaksi tersebut (misalnya, 'Bubur Ayam', 'Bayar Listrik'):"
    
    sent_message = await update.message.reply_text(
        text, 
        reply_markup=get_menu_kembali('kembali_nominal'), 
        parse_mode='Markdown'
    )
    context.user_data['description_request_message_id'] = sent_message.message_id 
    
    return PREVIEW 

async def get_description(update: Update, context):
    # ... (fungsi ini tetap sama) ...
    chat_id = update.message.chat_id
    user_message_id = update.message.message_id
    bot_message_to_delete_id = context.user_data.pop('description_request_message_id', None)
    
    keterangan = update.message.text
    context.user_data['keterangan'] = keterangan
    
    await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    
    if bot_message_to_delete_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=bot_message_to_delete_id)
        except Exception as e:
            logging.warning(f"Gagal menghapus pesan bot Keterangan: {e}")
            
    preview_text = generate_preview(context.user_data)
    
    await update.message.reply_text(
        preview_text,
        reply_markup=get_menu_preview(),
        parse_mode='Markdown'
    )
    return PREVIEW 

async def handle_kembali_actions(update: Update, context):
    # ... (fungsi ini tetap sama) ...
    query = update.callback_query
    await query.answer()
    action = query.data
    
    chat_id = query.message.chat_id
    await query.message.delete()
    
    if action == 'kembali_kategori':
        kategori_dict = context.user_data.get('kategori_dict', {})
        transaksi = context.user_data.get('transaksi', 'N/A').lower()
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Silakan pilih Kategori baru untuk {context.user_data['transaksi']}:",
            reply_markup=get_menu_kategori(kategori_dict, transaksi),
            parse_mode='Markdown'
        )