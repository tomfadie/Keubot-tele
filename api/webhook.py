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
    preview_text += f"`{transaksi} Rp {nominal_formatted} {kategori_nama} {keterangan}`"
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
            # Mengirim pesan utama
            await context.bot.send_message(
                chat_id=chat_id, 
                text=text, 
                reply_markup=get_menu_transaksi()
            )
            logging.info(f"Pesan 'start' berhasil dikirim ke chat {chat_id}")
            
            if update.callback_query:
                 try:
                     await update.callback_query.answer() 
                     await update.callback_query.message.delete()
                 except Exception:
                     # Menangkap error saat menjawab query atau menghapus pesan lama
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
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Pencatatan dibatalkan. Gunakan /start untuk memulai lagi.")
        except Exception:
             await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="Pencatatan dibatalkan. Gunakan /start untuk memulai lagi."
            )
    
    context.user_data.clear()
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
        await context.bot.send_message(chat_id, "Terjadi kesalahan. Silakan mulai ulang dengan /start.")
        return ConversationHandler.END

    try:
        await query.edit_message_text(
            text, 
            reply_markup=get_menu_kategori(context.user_data['kategori_dict'], data),
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Gagal edit pesan di choose_route: {e}. Mengirim pesan baru.")
        await context.bot.send_message(
            chat_id,
            text, 
            reply_markup=get_menu_kategori(context.user_data['kategori_dict'], data),
            parse_mode='Markdown'
        )
        
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
        await update.callback_query.message.delete()
        context.user_data['nominal_request_message_id'] = sent_message.message_id
    except Exception as e:
        logging.error(f"Gagal mengirim/menghapus pesan di choose_category: {e}")
        # Jika gagal, pastikan tetap mencatat state baru (fallback)
        context.user_data['nominal_request_message_id'] = None

    return GET_DESCRIPTION 

async def get_nominal(update: Update, context):
    chat_id = update.message.chat_id
    user_message_id = update.message.message_id
    
    error_message_id = context.user_data.pop('error_message_id', None)
    if error_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=error_message_id)
        except Exception:
            pass
            
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

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id) 
        if bot_message_to_delete_id:
            await context.bot.delete_message(chat_id=chat_id, message_id=bot_message_to_delete_id)
            context.user_data.pop('nominal_request_message_id', None)
    except Exception:
        pass
    
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
    
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        if bot_message_to_delete_id:
            await context.bot.delete_message(chat_id=chat_id, message_id=bot_message_to_delete_id)
    except Exception:
        pass
            
    preview_text = generate_preview(context.user_data)
    
    await update.message.reply_text(
        preview_text,
        reply_markup=get_menu_preview(),
        parse_mode='Markdown'
    )
    return PREVIEW 

async def handle_kembali_actions(update: Update, context):
    query = update.callback_query
    try:
        await query.answer()
        await query.message.delete()
    except Exception:
        pass
        
    action = query.data
    chat_id = query.message.chat_id
    
    if action == 'kembali_kategori':
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
    
    try:
        await query.answer()
        await query.message.delete()
    except Exception:
        pass
        
    action = query.data
    chat_id = query.message.chat_id
    
    if action == 'aksi_kirim':
        
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
        
        success = send_to_make(payload) # Fungsi sinkron
        
        transaksi_type = payload.get('transaksi', 'N/A')
        nominal_formatted = format_nominal(payload.get('nominal', 0))
        kategori_nama = payload.get('kategori_nama', 'N/A')
        keterangan = payload.get('keterangan', 'N/A')

        ringkasan_data = f"*Ringkasan:* {transaksi_type} Rp {nominal_formatted} - {kategori_nama} ({keterangan})"

        if success:
            response_text = "✅ *Transaksi Berhasil Dicatat!*\nData Anda telah dikirim ke Spreadsheet.\n\n"
            response_text += ringkasan_data
            
            response_text += "\n\nCek Laporan Keuangan Anda pada: [Laporan Keuangan](https://docs.google.com/spreadsheets/d/1A2ephAX4I1zwxmvFlkSAeHRc7OjcN2peQqZgPsGZ8X8/edit?gid=550879818#gid=550879818)"
            response_text += "\n\nJika ingin melakukan pencatatan baru silahkan tekan /start"
        else:
            response_text = "❌ *Pencatatan Gagal!*\nTerjadi kesalahan saat mengirim data ke server. Silakan coba lagi /start"

        await context.bot.send_message(chat_id, response_text, parse_mode='Markdown')
        
        context.user_data.clear()
        
        return ConversationHandler.END
        
    elif action == 'ubah_transaksi':
        return await start(update, context)
        
    elif action == 'ubah_kategori':
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
        context.user_data.pop('nominal', None) 
        
        text = f"Anda memilih *Transaksi {context.user_data['transaksi']}* dengan *Kategori {context.user_data['kategori_nama']}*.\n\n"
        text += "Sekarang, *tuliskan jumlah nominal transaksi* (hanya angka, tanpa titik/koma/Rp):"
        
        await context.bot.send_message(
             chat_id,
             text,
             reply_markup=get_menu_kembali('kembali_kategori'), 
             parse_mode='Markdown'
         )
        return GET_DESCRIPTION 

    elif action == 'ubah_keterangan':
        context.user_data.pop('keterangan', None)
        await context.bot.send_message(
             chat_id,
             "Sekarang, tambahkan *Keterangan* dari transaksi tersebut (misalnya, 'Bubur Ayam', 'Bayar Listrik'):",
             reply_markup=get_menu_kembali('kembali_nominal'), 
             parse_mode='Markdown'
         )
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
    """Menginisialisasi Application dan Conversation Handler tanpa memanggil initialize()."""
    global application_instance
    
    if not TOKEN:
        return None

    try:
        # Application.builder() harus dipanggil sebelum loop dibuat/diset.
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
        
        # 3. Inisialisasi Kondisional (Mengatasi "Application was not initialized")
        if not hasattr(application_instance, '_initialized') or not application_instance._initialized:
            
            # Panggil initialize di loop baru pada request pertama
            new_loop.run_until_complete(application_instance.initialize())
            
            # Set flag agar tidak dipanggil lagi
            application_instance._initialized = True 
            logging.info("Application instance berhasil diinisialisasi (Initialization Complete).")
            
        # 4. Jalankan pemrosesan update di loop baru
        new_loop.run_until_complete(application_instance.process_update(update)) 
        
        # 5. Tutup loop setelah selesai
        new_loop.close()
        # ------------------------------------------------------

        logging.info("Update Telegram berhasil diproses oleh Application (Async complete).")
        return 'OK', 200 
        
    except Exception as e:
        # Set loop kembali ke None saat error untuk menghindari konflik pada request berikutnya
        asyncio.set_event_loop(None) 
        
        logging.error(f"Error saat memproses Update: {e}")
        return 'Internal Server Error', 500
