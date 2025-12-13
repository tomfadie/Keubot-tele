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

# --- KONFIGURASI DAN STATES (TIDAK BERUBAH) ---
# ... (Semua kode di atas init_application tetap sama)

# Mengambil Token dari Environment Variable Vercel
TOKEN = os.environ.get("BOT_TOKEN") 
if not TOKEN:
    logging.error("BOT_TOKEN Environment Variable tidak ditemukan. Aplikasi tidak akan berfungsi.")

# URL Webhook Make Anda (Pastikan ini benar)
MAKE_WEBHOOK_URL = "https://hook.eu2.make.com/b80ogwk3q1wuydgfgwjgq0nsvcwhot96"

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Definisi States
START_ROUTE, CHOOSE_CATEGORY, GET_NOMINAL, GET_DESCRIPTION, PREVIEW = range(5)

# Definisi Menu Kategori (Disederhanakan untuk brevity, asumsikan sama)
KATEGORI_MASUK = {'Gaji': 'masuk_gaji', 'Lainnya': 'masuk_lainnya'}
KATEGORI_KELUAR = {'Belanja': 'keluar_belanja', 'Makan': 'keluar_makan'}

# ... (Semua fungsi utility seperti send_to_make, format_nominal, get_menu_transaksi, etc. TIDAK BERUBAH)

# --- HANDLERS UTAMA (TIDAK BERUBAH, asumsikan sudah async) ---
# ... (Semua fungsi handler start, cancel, choose_route, choose_category, get_nominal, get_description, handle_kembali_actions, handle_preview_actions TIDAK BERUBAH)

# --- FUNGSI ENTRY POINT UTAMA UNTUK SERVERLESS (KRITIS) ---

# Terapkan patch nest_asyncio
try:
    nest_asyncio.apply()
except RuntimeError:
    pass 

app = Flask(__name__)

def init_application():
    """Menginisialisasi Application dan Conversation Handler."""
    
    if not TOKEN:
        return None

    try:
        application = Application.builder().token(TOKEN).build()
        
        # KRITIS: Panggil initialize menggunakan asyncio.run()
        asyncio.run(application.initialize())

        # --- PERBAIKAN KRITIS PADA CONVERSATION HANDLER ---
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                CHOOSE_CATEGORY: [CallbackQueryHandler(choose_route, pattern=r'^transaksi_(masuk|keluar|tabungan)$')],
                
                # PERBAIKAN 1: Tambahkan pattern 'kembali_transaksi' agar tombol kembali merespons di state ini
                GET_NOMINAL: [
                    CallbackQueryHandler(choose_category, pattern=r'^(masuk|keluar|tabungan)_.*$|^kembali_transaksi$')
                ],
                
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

# PENTING: Application instance harus dibuat sebelum digunakan (sekali saja)
application_instance = init_application()


@app.route('/webhook', methods=['POST'])
def flask_webhook_handler():
    """Fungsi handler Vercel/Flask."""
    global application_instance
    
    if application_instance is None:
        logging.error("Application instance tidak ditemukan. (Token Hilang).")
        return 'Internal Server Error', 500
        
    try:
        data = flask_request.get_json(force=True)
    except Exception as e:
        logging.error(f"Gagal parsing JSON request dari Telegram (Flask): {e}")
        return 'Bad Request', 400

    try:
        update = Update.de_json(data, application_instance.bot)
        # KRITIS: Menggunakan asyncio.run untuk menjamin eksekusi async PTB selesai
        asyncio.run(application_instance.process_update(update)) 

        logging.info("Update Telegram berhasil diproses oleh Application (Async complete).")
        return 'OK', 200 
        
    except Exception as e:
        logging.error(f"Error saat memproses Update: {e}")
        return 'Internal Server Error', 500
