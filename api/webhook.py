import requests
import logging
import os
import re
import json
from flask import Flask, request as flask_request  # Diperlukan untuk Vercel entry point
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

# Mengambil Token dari Environment Variable Vercel
TOKEN = os.environ.get("BOT_TOKEN") 
if not TOKEN:
    logging.error("BOT_TOKEN Environment Variable tidak ditemukan.")

# URL Webhook Make Anda (Pastikan ini benar)
MAKE_WEBHOOK_URL = "https://hook.eu2.make.com/b80ogwk3q1wuydgfgwjgq0nsvcwhot96"

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Definisi States
START_ROUTE, CHOOSE_CATEGORY, GET_NOMINAL, GET_DESCRIPTION, PREVIEW = range(5)

# Definisi Menu Kategori (Disederhanakan)
KATEGORI_MASUK = {
    'Gaji': 'masuk_gaji', 'Bonus': 'masuk_bonus', 'Hadiah': 'masuk_hadiah', 
    'Lainnya': 'masuk_lainnya'
}
KATEGORI_KELUAR = {
    'Angsuran': 'keluar_angsuran', 'Asuransi': 'keluar_asuransi', 'Belanja': 'keluar_belanja', 
    # ... Tambahkan kategori keluar lainnya di sini ...
    'RumahTangga': 'keluar_rumahtangga', 'Tabungan': 'keluar_tabungan', 'Lainnya': 'keluar_lainnya'
}

# --- FUNGSI UTILITY (Tidak Berubah) ---

def send_to_make(data):
    # ... (Fungsi send_to_make Anda di sini) ...
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
    
    preview_text = f"*Inputan Anda:*\n\n"
    preview_text += f"*Transaksi:* {transaksi}\n"
    preview_text += f"*Kategori:* {kategori_nama}\n"
    preview_text += f"*Nominal:* Rp {nominal_formatted}\n"
    preview_text += f"*Keterangan:* {keterangan}\n\n"
    preview_text += f"`{transaksi} {nominal} {kategori_nama} {keterangan}`"
    return preview_text

def get_menu_transaksi():
    # ... (Fungsi get_menu_transaksi Anda di sini) ...
    keyboard = [
        [InlineKeyboardButton("✅ Masuk", callback_data='transaksi_masuk')],
        [InlineKeyboardButton("❌ Keluar", callback_data='transaksi_keluar')],
        [InlineKeyboardButton("💳 Tabungan", callback_data='transaksi_tabungan')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_menu_kategori(kategori_dict, route_name):
    # ... (Fungsi get_menu_kategori Anda di sini) ...
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
    # ... (Fungsi get_menu_preview Anda di sini) ...
    keyboard = [
        [InlineKeyboardButton("✅ Kirim", callback_data='aksi_kirim')],
        [InlineKeyboardButton("Ubah Transaksi", callback_data='ubah_transaksi'), 
         InlineKeyboardButton("Ubah Kategori", callback_data='ubah_kategori')],
        [InlineKeyboardButton("Ubah Nominal", callback_data='ubah_nominal'), 
         InlineKeyboardButton("Ubah Keterangan", callback_data='ubah_keterangan')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_menu_kembali(callback_data):
    # ... (Fungsi get_menu_kembali Anda di sini) ...
    keyboard = [
        [InlineKeyboardButton("⬅️ Kembali ke Menu Sebelumnya", callback_data=callback_data)],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- HANDLERS UTAMA ---

async def start(update: Update, context):
    """Memulai Conversation Handler dan menampilkan menu utama.
       Koreksi: Menggunakan update.effective_chat untuk menjamin pengiriman pesan."""
    
    # --- LOGGING KRITIS ---
    logging.info(f"Handler 'start' Dipanggil oleh User: {update.effective_user.id}")
    # -----------------------
    
    user = update.effective_user
    chat_id = update.effective_chat.id

    user_data_identity = {
        'user_id': user.id,
        'first_name': user.first_name,
        'username': user.username if user.username else 'NoUsername'
    }

    context.user_data.clear() 
    context.user_data.update(user_data_identity)
    
    text = "Halo! Silakan pilih transaksi yang ingin Anda catat:"
    
    # KOREKSI PENTING: Pengiriman Pesan yang Stabil
    try:
        # Selalu gunakan send_message ke chat ID untuk pesan awal /start
        await context.bot.send_message(
            chat_id=chat_id, 
            text=text, 
            reply_markup=get_menu_transaksi()
        )
        logging.info(f"Pesan 'start' berhasil dikirim ke chat {chat_id}")
        
        # Jawab callback query jika dipanggil oleh tombol (seperti "Ubah Transaksi")
        if update.callback_query:
             await update.callback_query.answer()
             # Hapus pesan tombol yang lama
             try:
                 await update.callback_query.message.delete()
             except Exception:
                 pass

    except Exception as e:
        logging.error(f"Gagal mengirim pesan 'start' ke chat {chat_id}: {e}")
        
    # Hapus pesan /start user (opsional, untuk kerapihan)
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
            
    return CHOOSE_CATEGORY 

async def cancel(update: Update, context):
    # ... (Fungsi cancel Anda di sini) ...
    if update.message:
        await update.message.reply_text("Pencatatan dibatalkan. Gunakan /start untuk memulai lagi.")
    elif update.callback_query:
        await update.callback_query.edit_message_text("Pencatatan dibatalkan. Gunakan /start untuk memulai lagi.")
    
    context.user_data.clear()
    return ConversationHandler.END

# ... (Handler-Handler Lain: choose_route, choose_category, get_nominal, get_description, 
#      handle_kembali_actions, handle_preview_actions) 
# ... (Semua handler ini harus tetap sama seperti sebelumnya)

async def choose_route(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    # ... (Implementasi choose_route) ...
    # ...

async def choose_category(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    # ... (Implementasi choose_category) ...
    # ...

async def get_nominal(update: Update, context):
    # ... (Implementasi get_nominal) ...
    # ...

async def get_description(update: Update, context):
    # ... (Implementasi get_description) ...
    # ...

async def handle_kembali_actions(update: Update, context):
    # ... (Implementasi handle_kembali_actions) ...
    # ...

async def handle_preview_actions(update: Update, context):
    # ... (Implementasi handle_preview_actions) ...
    # ...


# --- FUNGSI ENTRY POINT UTAMA UNTUK VERCEL (KRITIS) ---

def init_application():
    """Menginisialisasi Application dan Conversation Handler."""
    
    if not TOKEN:
        return None

    try:
        application = Application.builder().token(TOKEN).build()

        # Definisikan Conversation Handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                CHOOSE_CATEGORY: [CallbackQueryHandler(choose_route, pattern=r'^transaksi_(masuk|keluar|tabungan)$')],
                GET_NOMINAL: [CallbackQueryHandler(choose_category, pattern=r'^(masuk|keluar|tabungan)_.*$')],
                GET_DESCRIPTION: [
                    CallbackQueryHandler(handle_kembali_actions, pattern=r'^kembali_kategori$'),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_nominal)
                ],
                PREVIEW: [
                    CallbackQueryHandler(handle_kembali_actions, pattern=r'^kembali_nominal$'),
                    CallbackQueryHandler(handle_preview_actions, pattern=r'^aksi_.*|ubah_.*$'),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
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

# PENTING: Inisialisasi Application secara global (jika menggunakan Flask)
application_instance = init_application()

# Inisialisasi Flask App
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """
    Fungsi handler yang diakses oleh Flask/Vercel pada jalur /webhook.
    """
    global application_instance
    
    if application_instance is None:
        logging.error("Application instance tidak ditemukan. (Token Hilang).")
        return 'Internal Server Error', 500
        
    try:
        # Flask request data
        data = flask_request.get_json(force=True)
        
    except Exception as e:
        logging.error(f"Gagal parsing JSON request dari Telegram (Flask): {e}")
        return 'Bad Request', 400

    try:
        # Buat objek Update dan proses menggunakan Application instance
        update = Update.de_json(data, application_instance.bot)
        application_instance.process_update(update)
        
        logging.info("Update Telegram berhasil diproses oleh Application.")
        return 'OK', 200 # HARUS merespons 200 OK ke Telegram
        
    except Exception as e:
        logging.error(f"Error saat memproses Update: {e}")
        return 'Internal Server Error', 500
