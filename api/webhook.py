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
    logging.info(f"Handler 'start' Dipanggil oleh User: {user.id}")

    # --- PERBAIKAN: Hapus Pesan Fallback Lama jika ada ---
    chat_id = update.effective_chat.id
    # Mengambil dan menghapus ID pesan fallback dari user_data
    fallback_id_to_delete = context.user_data.pop('fallback_message_id', None) 
    
    if fallback_id_to_delete:
        try:
            # Mencoba menghapus pesan fallback yang dikirim di sesi gagal sebelumnya
            await context.bot.delete_message(chat_id=chat_id, message_id=fallback_id_to_delete)
            logging.info(f"Berhasil menghapus pesan fallback lama ID: {fallback_id_to_delete}")
        except Exception as e:
            # PENTING: Menangkap dan mencatat error spesifik (misalnya Event loop is closed)
            logging.warning(f"Gagal menghapus pesan fallback lama ID: {fallback_id_to_delete}. Error: {e}")
            pass
            
    # --- PERBAIKAN BARU: Hapus Pesan CANCEL Lama ---
    cancel_id_to_delete = context.user_data.pop('cancel_message_id', None) 
    if cancel_id_to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=cancel_id_to_delete)
            logging.info(f"Berhasil menghapus pesan cancel lama ID: {cancel_id_to_delete}")
        except Exception as e:
            logging.warning(f"Gagal menghapus pesan cancel lama ID: {cancel_id_to_delete}. Error: {e}")
            pass
    # ----------------------------------------------------

    user_data_identity = {
        'user_id': user.id,
        'first_name': user.first_name,
        'username': user.username if user.username else 'NoUsername'
    }

    context.user_data.clear()
    context.user_data.update(user_data_identity)
    
    text = "Halo! Silakan pilih transaksi yang ingin Anda catat:"
    
    if update.message or update.callback_query:
        try:
            # 1. Coba Kirim Menu Utama
            menu_message = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=get_menu_transaksi()
            )
            logging.info(f"Pesan 'start' berhasil dikirim ke chat {chat_id}")
            
            # 2. Penanganan Query Lama
            if update.callback_query:
                try:
                    await update.callback_query.answer()
                    await update.callback_query.message.delete()
                except Exception:
                    pass

        except Exception as e:
            # 3. KETIKA GAGAL KARENA RuntimeError (Cold Start)
            logging.error(f"Gagal mengirim pesan 'start' ke chat {chat_id}: {e}")
            
            # --- FALLBACK: Mengirim Pesan Sederhana & Menyimpan ID ---
            try:
                fallback_message = await context.bot.send_message( # <--- Menyimpan objek pesan
                    chat_id=chat_id,
                    text="⚠️ Gagal menampilkan menu interaktif. Silakan coba /start lagi.",
                    parse_mode='Markdown'
                )
                # Menyimpan ID pesan fallback agar bisa dihapus di /start berikutnya
                context.user_data['fallback_message_id'] = fallback_message.message_id 
                logging.warning("Pesan fallback instruksi start berhasil dikirim.")
            except Exception as fe:
                logging.error(f"Pesan fallback juga gagal terkirim: {fe}")
            # --------------------------------------------------------

    # 4. Hapus pesan /start user
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
            
    return CHOOSE_CATEGORY

async def cancel(update: Update, context):
    chat_id = update.effective_chat.id
    
    # --- 1. Hapus Pesan Bot dari State Terakhir ---
    message_ids_to_delete = []
    # Kumpulkan semua ID pesan yang harus dihapus
    for key in ['nominal_request_message_id', 'description_request_message_id', 'error_message_id']:
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            message_ids_to_delete.append(msg_id)
            
    for msg_id in message_ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logging.info(f"Berhasil menghapus pesan bot lama ID: {msg_id} (Cancel)")
        except Exception as e:
            logging.warning(f"Gagal menghapus pesan bot lama ID: {msg_id} (Cancel). Error: {e}")
            pass
            
    # --- 2. Kirim Pesan Konfirmasi Pembatalan & Tangkap ID-nya ---
    response_text = "Pencatatan dibatalkan. Gunakan /start untuk memulai lagi."
    sent_message = None # Inisialisasi variabel pesan yang terkirim

    if update.message:
        try:
            sent_message = await update.message.reply_text(response_text)
            # Hapus pesan user /cancel
            try:
                await update.message.delete()
            except Exception:
                pass
        except Exception as e:
             logging.error(f"Gagal mengirim/menghapus pesan konfirmasi cancel: {e}")
             
    elif update.callback_query:
        query = update.callback_query
        try:
            await query.answer()
            # Mencoba edit pesan callback terakhir
            sent_message = await query.message.edit_text(response_text)
        except Exception:
            # Fallback jika gagal edit (pesan sudah dihapus)
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text=response_text
            )
            
    # --- 3. Bersihkan Data Konversasi dan Simpan ID Cancel ---
    # Simpan ID pesan konfirmasi agar tidak ikut terhapus oleh .clear() sementara
    cancel_id_to_save = sent_message.message_id if sent_message else None
    
    # Hapus semua data transaksi lama (nominal, keterangan, kategori, dll.)
    context.user_data.clear()
    
    # Kembalikan ID pesan konfirmasi agar bisa dihapus oleh /start berikutnya
    if cancel_id_to_save:
        context.user_data['cancel_message_id'] = cancel_id_to_save
    
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
        context.user_data['nominal_request_message_id'] = None

    return GET_DESCRIPTION

import asyncio
# ... (import lainnya) ...

# FUNGSI HELPER UNTUK MENGATASI RUNTIME ERROR DI VERCEL
async def delete_message_with_workaround(context, chat_id, message_id, log_prefix):
    """Menghapus pesan menggunakan asyncio.wrap_future untuk mengatasi RuntimeError di serverless."""
    
    if not message_id:
        return

    try:
        # Dapatkan instance bot dari application
        bot_instance = context.application.bot
        
        # Buat Future untuk operasi delete_message
        future = bot_instance.delete_message(chat_id=chat_id, message_id=message_id)
        
        # Jalankan Future ini secara aman dalam loop yang sama (Workaround)
        await asyncio.wrap_future(future)
        logging.info(f"Berhasil menghapus {log_prefix} ID: {message_id} menggunakan Workaround.")
    except Exception as e:
        logging.warning(f"Gagal menghapus {log_prefix} ID: {message_id}. Error: {e}")
        # Jangan raise exception, biarkan alur berjalan
        pass
        

async def get_nominal(update: Update, context):
    chat_id = update.message.chat_id
    user_message_id = update.message.message_id
    
    # --- PANGGILAN FUNGSI DEBUG UNTUK VERIFIKASI ID ---
    # Pastikan debug_check_ids() tidak memanggil delete_message secara internal
    # debug_check_ids(context) 
    # --------------------------------------------------

    # Hapus pesan error lama (jika ada) menggunakan Workaround
    error_message_id = context.user_data.pop('error_message_id', None)
    await delete_message_with_workaround(context, chat_id, error_message_id, "pesan error")
        
    # Variabel nominal diinisialisasi None
    nominal = None
    
    # --- 1. VALIDASI & PENENTUAN NOMINAL ---
    try:
        nominal_str = re.sub(r'\D', '', update.message.text)
        nominal = int(nominal_str)
        if nominal <= 0:
            raise ValueError
        
        # Simpan nominal segera setelah sukses divalidasi
        context.user_data['nominal'] = nominal
        
    except (ValueError, TypeError):
        # --- ERROR HANDLING: INPUT TIDAK VALID ---
        
        # Hapus pesan user yang salah menggunakan Workaround
        await delete_message_with_workaround(context, chat_id, user_message_id, "pesan user salah")
        
        # Kirim pesan error baru
        error_msg = await update.message.reply_text(
            "Nominal tidak valid. Harap masukkan *Hanya Angka Positif* (tanpa titik/koma/Rp).",
            parse_mode='Markdown'
        )
        context.user_data['error_message_id'] = error_msg.message_id
        
        return GET_DESCRIPTION

    # --- Penghapusan (Hanya dijalankan jika validasi sukses) ---

    # 2. Hapus pesan User (Input Nominal yang Valid) menggunakan Workaround
    await delete_message_with_workaround(context, chat_id, user_message_id, "pesan user valid")

    # 3. Hapus pesan Bot Lama (Permintaan Nominal) menggunakan Workaround
    bot_message_to_delete_id = context.user_data.pop('nominal_request_message_id', None)
    await delete_message_with_workaround(context, chat_id, bot_message_to_delete_id, "pesan bot lama")
            
    # --- Lanjutkan ke alur bot berikutnya (Validasi Sukses) ---
    
    # 4. AMBIL VARIABEL & KIRIM PERMINTAAN KETERANGAN
    kategori_nama = context.user_data.get('kategori_nama', 'Kategori Tidak Ditemukan')
    
    # Memastikan format_nominal telah didefinisikan di tempat lain
    text = f"Nominal: *Rp {format_nominal(nominal)}* berhasil dicatat sebagai *{kategori_nama}*.\n\n"
    text += "Sekarang, tambahkan *Keterangan* dari transaksi tersebut (misalnya, 'Bubur Ayam', 'Bayar Air PDAM'):"
    
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
        
    # --- PERBAIKAN: Membalik Urutan Penghapusan ---

   # 1. Hapus pesan User Input (Keterangan) - PRIORITAS 1 (Pesan yang baru masuk)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        logging.info(f"Berhasil menghapus pesan user ID: {user_message_id} (Deskripsi)")
    except Exception as e:
        logging.warning(f"Gagal menghapus pesan user ID: {user_message_id} (Deskripsi). Error: {e}")
        pass
        
    # 2. Hapus pesan Bot Request Lama (Permintaan Keterangan) - PRIORITAS 2
    if bot_message_to_delete_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=bot_message_to_delete_id)
            logging.info(f"Berhasil menghapus pesan bot lama ID: {bot_message_to_delete_id} (Deskripsi Request)")
        except Exception as e:
            # Karena masalah Event Loop sudah teratasi, logging ini hanya untuk error lain.
            logging.warning(f"Gagal menghapus pesan bot lama ID: {bot_message_to_delete_id} (Deskripsi Request). Error: {e}")
            pass
    
    # ----------------------------------------------------
         
    preview_text = generate_preview(context.user_data)
    
    await update.message.reply_text(
        preview_text,
        reply_markup=get_menu_preview(),
        parse_mode='Markdown'
    )
    return PREVIEW
    
async def go_back_to_category(update: Update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_to_delete_id = query.message.message_id # ID pesan nominal yang ingin dihapus
    
    # 1. Menjawab Query
    try:
        await query.answer()
    except Exception:
        pass
        
    # 2. Blok KHUSUS untuk mengatasi RuntimeError pada delete_message
    try:
        # Panggil bot.delete_message secara eksplisit.
        # Jika error persisten, ini adalah solusi paling bersih untuk PTB di serverless
        await context.bot.delete_message(chat_id=chat_id, message_id=message_to_delete_id)
        logging.info(f"Berhasil menghapus pesan bot nominal ID: {message_to_delete_id} saat 'kembali_kategori'.")
    except Exception as e:
        # Jika gagal delete, coba lagi dengan cara lain (hanya sebagai debugging/fallback)
        logging.warning(f"Gagal menghapus pesan bot nominal saat 'kembali_kategori'. Error: {e}")
        pass

    # Hapus ID pesan nominal_request_message_id dari user_data
    context.user_data.pop('nominal_request_message_id', None)
    
    kategori_dict = context.user_data.get('kategori_dict', {})
    transaksi = context.user_data.get('transaksi', 'N/A')

    # 2. Memunculkan kembali menu kategori
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Silakan pilih *Kategori* untuk transaksi *{transaksi}*:",
        reply_markup=get_menu_kategori(kategori_dict, transaksi.lower()),
        parse_mode='Markdown'
    )

    return GET_NOMINAL # <--- State yang benar untuk memilih kategori

async def go_back_to_nominal(update: Update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    message_to_delete_id = query.message.message_id # ID pesan Keterangan yang ingin dihapus
    
    # 1. Menjawab Query
    try:
        await query.answer()
    except Exception:
        pass
        
    # 2. Hapus Pesan Bot (MENGGUNAKAN WORKAROUND THREADSAFE)
    try:
        # Dapatkan event loop yang sedang aktif
        current_loop = asyncio.get_event_loop()
        
        # Eksekusi delete_message dalam loop secara sinkron (Workaround Vercel)
        # Gunakan bot dari context.application (lebih aman dari context.bot)
        # Catatan: context.bot adalah instance ExtBot
        bot_instance = context.application.bot
        
        # Buat Future untuk operasi delete_message
        future = bot_instance.delete_message(chat_id=chat_id, message_id=message_to_delete_id)
        
        # Jalankan Future ini secara sinkron dalam loop yang sama.
        # Ini mengatasi masalah "bound to a different event loop"
        await asyncio.wrap_future(future)
        
        logging.info(f"Berhasil menghapus pesan bot keterangan ID: {message_to_delete_id} menggunakan Threadsafe Workaround.")
    except Exception as e:
        # Jika gagal delete, log error
        logging.warning(f"Gagal menghapus pesan bot keterangan saat 'kembali_nominal'. Error: {e}")
        pass
        
    # --- LANJUTKAN ALUR STANDAR ---
        
    # Hapus ID pesan permintaan keterangan dari user_data
    context.user_data.pop('description_request_message_id', None)
    
    # 3. Hapus Nominal Lama (untuk input ulang Nominal)
    context.user_data.pop('nominal', None)
    context.user_data.pop('keterangan', None)

    # 4. KIRIM ULANG PESAN PERMINTAAN NOMINAL BARU
    
    transaksi = context.user_data.get('transaksi', 'N/A')
    kategori_nama = context.user_data.get('kategori_nama', 'N/A')
    
    text = f"Anda memilih *Transaksi {transaksi}* dengan *Kategori {kategori_nama}*.\n\n"
    text += "Silakan masukkan *Nominal baru* (hanya angka, tanpa titik/koma/Rp):"
    
    sent_message = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=get_menu_kembali('kembali_kategori'),
        parse_mode='Markdown'
    )
    
    context.user_data['nominal_request_message_id'] = sent_message.message_id
    
    # 5. PINDAH STATE
    return GET_DESCRIPTION

async def handle_preview_actions(update: Update, context):
    query = update.callback_query
    
    # 1. Menjawab Query
    try:
        await query.answer()
    except Exception:
        pass
        
    # 2. Mencoba Menghapus Pesan Preview 
    chat_id = query.message.chat_id
    
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        logging.info("Berhasil menghapus pesan Preview sebelum mengirim konfirmasi.")
    except Exception as e:
        logging.warning(f"Gagal menghapus pesan Preview ID:{query.message.message_id}. Error: {e}")
        pass
        
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

        ringkasan_data = f"*Ringkasan:* {transaksi_type} Rp {nominal_formatted} - {kategori_nama} ({keterangan})"

        if success:
            response_text = "✅ *Transaksi Berhasil Dicatat!*\nData Anda telah dikirim ke Spreadsheet.\n\n"
            response_text += ringkasan_data
            
            response_text += "\n\nCek Laporan Keuangan Anda pada: [Laporan Keuangan](https://docs.google.com/spreadsheets/d/1A2ephAX4I1zwxmvFlkSAeHRc7OjcN2peQqZgPsGZ8X8/edit?gid=550879818#gid=550879818)"
            response_text += "\nJika ingin melakukan pencatatan baru silahkan tekan /start"
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
            f"Silakan pilih *Kategori baru* untuk transaksi *{context.user_data['transaksi']}*:",
            reply_markup=get_menu_kategori(kategori_dict, transaksi),
            parse_mode='Markdown'
        )
        return GET_NOMINAL
        
    elif action == 'ubah_nominal':
        logging.info("Aksi Ubah Nominal Dijalankan.")
    
        # --- 1. CLEANUP DATA LAMA ---
        # Hapus Nominal lama
        context.user_data.pop('nominal', None) 
        # Hapus Keterangan lama (WAJIB dihapus agar alur meminta input keterangan baru)
        context.user_data.pop('keterangan', None) 
        # Hapus ID pesan permintaan Keterangan lama (Jika ada)
        context.user_data.pop('description_request_message_id', None)
    
        # --- 2. KIRIM PERMINTAAN NOMINAL BARU ---
    
            # Pesan Preview (yang ditekan tombolnya) sudah dihapus di awal handle_preview_actions
    
        text = f"Anda memilih *Transaksi {context.user_data['transaksi']}* dengan *Kategori {context.user_data['kategori_nama']}*.\n\n"
        text += "Sekarang, *tuliskan jumlah nominal transaksi baru* (hanya angka, tanpa titik/koma/Rp):"
    
        sent_message = await context.bot.send_message(
             chat_id,
             text,
             reply_markup=get_menu_kembali('kembali_kategori'),
             parse_mode='Markdown'
           )
           
        # Simpan ID pesan permintaan nominal yang baru, agar bisa dihapus oleh get_nominal
        context.user_data['nominal_request_message_id'] = sent_message.message_id
        
        # 3. PINDAH STATE
        return GET_DESCRIPTION

    elif action == 'ubah_keterangan':
        logging.info("Aksi Ubah Keterangan Dijalankan.")
        
        # --- 1. Hapus Keterangan Lama ---
        context.user_data.pop('keterangan', None) 
        # ID pesan permintaan nominal/kategori/preview lain sudah ditangani di alur sebelumnya
        
        # --- 2. KIRIM PERMINTAAN KETERANGAN BARU ---
        
        sent_message = await context.bot.send_message( # <--- Tangkap objek pesan
             chat_id,
             "Sekarang, tambahkan *Keterangan baru* dari transaksi tersebut (misalnya, 'Bubur Ayam', 'Bayar Listrik'):",
             reply_markup=get_menu_kembali('kembali_nominal'),
             parse_mode='Markdown'
           )
           
        # --- PERBAIKAN KRITIS: SIMPAN ID PESAN BARU ---
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
                    CallbackQueryHandler(go_back_to_category, pattern=r'^kembali_kategori$'),
                ],
                
                PREVIEW: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_description),
                    CallbackQueryHandler(go_back_to_nominal, pattern=r'^kembali_nominal$'),
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
        
        # ------------------------------------------------------

        logging.info("Update Telegram berhasil diproses oleh Application (Async complete).")
        return 'OK', 200
        
    except Exception as e:
        # Set loop kembali ke None saat error untuk menghindari konflik pada request berikutnya
        asyncio.set_event_loop(None)
        
        logging.error(f"Error saat memproses Update: {e}")
        return 'Internal Server Error', 500




