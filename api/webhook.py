import requests
import logging
import os
import re
import json
import asyncio
import nest_asyncio # Kritis: Untuk menjalankan async code (PTB) di Flask/Vercel

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

# Mengambil Token dari Environment Variable Vercel menggunakan os.getenv (Lebih Robust)
TOKEN = os.getenv("BOT_TOKEN") 
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

# Definisi Menu Kategori
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

# --- FUNGSI UTILITY ---

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
    # Tombol ini dikirim di state GET_NOMINAL, dan callback-nya harus di-handle di sana
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
    logging.info(f"Handler 'start' Dipanggil oleh User: {user.id}")

    user_data_identity = {
        'user_id': user.id,
        'first_name': user.first_name,
        'username': user.username if user.username else 'NoUsername'
    }

    context.user_data.clear() 
    context.user_data.update(user_data_identity)
    
    text = "Halo! Silakan pilih transaksi yang ingin Anda catat:"
    chat_id = update.effective_chat.id
    
    if update.message or update.callback_query:
        try:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=text, 
                reply_markup=get_menu_transaksi()
            )
            logging.info(f"Pesan 'start' berhasil dikirim ke chat {chat_id}")
            
            if update.callback_query:
                 await update.callback_query.answer()
                 try:
                     await update.callback_query.message.delete()
                 except Exception:
                     pass

        except Exception as e:
            logging.error(f"Gagal mengirim pesan 'start' ke chat {chat_id}: {e}")
            
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
            
    return CHOOSE_CATEGORY 

async def cancel(update: Update, context):
    if update.message:
        await update.message.reply_text("Pencatatan dibatalkan. Gunakan /start untuk memulai lagi.")
    elif update.callback_query:
        await update.callback_query.edit_message_text("Pencatatan dibatalkan. Gunakan /start untuk memulai lagi.")
    
    context.user_data.clear()
    return ConversationHandler.END

async def choose_route(update: Update, context):
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
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Handle tombol "Kembali ke Menu Transaksi" dari state GET_NOMINAL
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
            # Karena kembali_kategori datang dari state GET_DESCRIPTION, 
            # kita pindah ke state GET_NOMINAL (memilih kategori)
            reply_markup=get_menu_kategori(kategori_dict, transaksi), 
            parse_mode='Markdown'
        )
        return GET_NOMINAL 

    elif action == 'kembali_nominal':
        # kembali_nominal datang dari state PREVIEW
        # kita pindah ke state PREVIEW (meminta deskripsi)
        text = f"Nominal: *Rp {format_nominal(context.user_data.get('nominal', 0))}* sudah dicatat.\n\n"
        text += "Sekarang, tambahkan *Keterangan* dari transaksi tersebut (misalnya, 'Bubur Ayam', 'Bayar Listrik'):"
        
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_menu_kembali('kembali_nominal'),
            parse_mode='Markdown'
        )
        context.user_data['description_request_message_id'] = sent_message.message_id
        return PREVIEW 

async def handle_preview_actions(update: Update, context):
    query = update.callback_query
    await query.answer()
    action = query.data
    
    await query.message.delete()
    
    chat_id = query.message.chat_id
    
    if action == 'aksi_kirim':
        
        # 1. Persiapan Payload (Tetap Sama)
        payload = {
            'user_id': context.user_data.get('user_id'),
            'first_name': context.user_data.get('first_name'),
            'username': context.user_data.get('username'),
            'transaksi': context.user_data.get('transaksi'),
            'kategori_nama': context.user_data.get('kategori_nama'),
            'nominal': context.user_data.get('nominal'),
            'keterangan': context.user_data.get('keterangan'),
        }
        
        success = send_to_make(payload)
        
        # 2. Membuat Teks Konfirmasi yang Lebih Detail
        transaksi_type = payload['transaksi']
        nominal_formatted = format_nominal(payload['nominal'])
        kategori_nama = payload['kategori_nama']
        keterangan = payload['keterangan']

        ringkasan_data = f"*Ringkasan:* {transaksi_type} Rp {nominal_formatted} - {kategori_nama} ({keterangan})"

        if success:
            response_text = "✅ *Transaksi Berhasil Dicatat!*\nData Anda telah dikirim ke Spreadsheet.\n\n"
            response_text += ringkasan_data
        else:
            response_text = "❌ *Pencatatan Gagal!*\nTerjadi kesalahan saat mengirim data ke sistem Make. Silakan coba lagi nanti atau hubungi Admin."

        # 3. Kirim Pesan Konfirmasi
        await context.bot.send_message(chat_id, response_text, parse_mode='Markdown')
        
        # 4. Clear data sementara (penting)
        context.user_data.clear()
        
        # 5. Panggil kembali handler 'start' untuk menampilkan menu awal
        # Kita menggunakan call langsung ke start dan return state yang dihasilkan
        # Perlu membuat objek Update dan Context sementara yang diperlukan start
        
        # Agar bot kembali ke menu, kita panggil start handler dan return state-nya
        # Kita perlu membuat Update object yang benar-benar baru untuk state start
        
        # NOTE: Karena start handler sudah didesain untuk merespons dengan menu dan pindah ke CHOOSE_CATEGORY,
        # kita hanya perlu memanggilnya ulang.
        
        # Kita akan memodifikasi start handler agar bisa dipanggil langsung tanpa Update/Message
        # untuk meminimalkan error, namun cara paling bersih adalah mengarahkan kembali ke state awal
        
        # Kita akan menggunakan cara yang lebih sederhana: 
        # Cukup kirim ulang menu dan kembalikan state ke CHOOSE_CATEGORY
        
        text_menu = "Pencatatan selesai. Silakan pilih transaksi selanjutnya:"
        await context.bot.send_message(
            chat_id=chat_id, 
            text=text_menu, 
            reply_markup=get_menu_transaksi()
        )
        
        # Kembalikan state ke CHOOSE_CATEGORY
        return CHOOSE_CATEGORY # Mengarahkan ke state awal
        
    # ... (lanjutkan blok elif untuk ubah_transaksi, ubah_kategori, dsb. yang tetap sama) ...


# --- FUNGSI ENTRY POINT UTAMA UNTUK SERVERLESS (KRITIS) ---

# Terapkan patch nest_asyncio
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
        
        # KRITIS: Panggil initialize menggunakan asyncio.run() karena ia adalah coroutine.
        asyncio.run(application.initialize())

        # --- PERBAIKAN ROUTING KRITIS ---
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                CHOOSE_CATEGORY: [CallbackQueryHandler(choose_route, pattern=r'^transaksi_(masuk|keluar|tabungan)$')],
                
                # PERBAIKAN: Tombol 'kembali_transaksi' (dari menu kategori) harus di-handle di sini
                GET_NOMINAL: [
                    CallbackQueryHandler(choose_category, pattern=r'^(masuk|keluar|tabungan)_.*$|^kembali_transaksi$')
                ],
                
                GET_DESCRIPTION: [
                    CallbackQueryHandler(handle_kembali_actions, pattern=r'^kembali_kategori$'),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_nominal)
                ],
                PREVIEW: [
                    # Tombol kembali_nominal dari PREVIEW pindah ke handle_kembali_actions
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


@app.route('/webhook', methods=['POST'])
def flask_webhook_handler():
    """Fungsi handler Vercel/Flask."""
    global application_instance
    
    # 1. Lazy Loading/Re-initialization
    if application_instance is None:
        application_instance = init_application()
    
    if application_instance is None:
        logging.error("Application instance tidak ditemukan. (Token Hilang saat runtime/inisialisasi gagal).")
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

