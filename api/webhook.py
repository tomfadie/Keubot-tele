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

def debug_check_ids(context):
    """Mencetak ID pesan yang seharusnya dihapus untuk debugging."""
    chat_id = context._chat_id 
    nominal_id = context.user_data.get('nominal_request_message_id')
    
    if nominal_id:
        logging.info(f"DEBUG: nominal_request_message_id = {nominal_id} (Chat: {chat_id}). ID siap dihapus.")
    else:
        logging.warning(f"DEBUG: nominal_request_message_id TIDAK DITEMUKAN atau None.")
    return nominal_id
# END FUNGSI DEBUGGING

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

async def handle_unmatched_text(update: Update, context):
    """
    Handler untuk teks yang tidak cocok. Dipicu ketika ConversationHandler 
    berada di END (misalnya, setelah idle terlalu lama).
    """
    await update.message.reply_text(
        "Maaf, sesi pencatatan Anda telah berakhir (mungkin karena idle terlalu lama). "
        "Silakan mulai ulang dengan perintah /start."
    )
    return ConversationHandler.END


async def start(update: Update, context):
    
    chat_id = update.effective_chat.id
    
    # --- PEMBERSIHAN PESAN LAMA DARI SESI SEBELUMNYA ---
    ids_to_delete_keys = [
        'menu_message_id', # ID Menu Utama atau Preview
        'nominal_request_message_id',  # ID Permintaan Nominal
        'description_request_message_id', # ID Permintaan Keterangan
        'fallback_message_id', 
        'error_message_id'
    ]
    
    ids_to_delete = []
    for key in ids_to_delete_keys:
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            ids_to_delete.append(msg_id)

    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logging.info(f"Berhasil menghapus pesan bot/error lama ID: {msg_id}")
        except Exception:
            pass
            
    # Hapus pesan yang Memicu /start (jika update berasal dari callback/tombol)
    if update.callback_query:
        try:
            await update.callback_query.message.delete() 
            logging.info(f"Berhasil menghapus pesan Callback Query yang memicu /start.")
        except Exception:
            pass
    # --------------------------------------------------------------------
    
    user = update.effective_user 
    logging.info(f"Handler 'start' Dipanggil oleh User: {user.id}")

    # Membersihkan semua data transaksi lama
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
            
            # SIMPAN ID PESAN MENU UTAMA YANG BARU
            context.user_data['menu_message_id'] = menu_message.message_id 
            
            # 2. Penanganan Query Lama
            if update.callback_query:
                 try:
                     await update.callback_query.answer() 
                 except Exception:
                     pass

        except Exception as e:
            # 3. KETIKA GAGAL (Gagal mengirim menu utama) - Fallback
            logging.error(f"Gagal mengirim pesan 'start' ke chat {chat_id}: {e}")
            
            try:
                sent_fallback = await context.bot.send_message(
                    chat_id=chat_id, 
                    text="⚠️ Gagal menampilkan menu. Silakan coba /start lagi.",
                    parse_mode='Markdown'
                )
                # Simpan ID pesan fallback baru
                context.user_data['fallback_message_id'] = sent_fallback.message_id
                
                logging.warning("Pesan fallback instruksi start berhasil dikirim.")
            except Exception as fe:
                logging.error(f"Pesan fallback juga gagal terkirim: {fe}")

    # 4. Hapus pesan /start user
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
    
    data = query.data
    chat_id = query.message.chat_id
    text = ""
    
    # --- Defensive Coding: Menjawab Query ---
    try:
        await query.answer()
    except Exception as e:
        logging.warning(f"Gagal menjawab query di choose_route: {e}")
    # ---------------------------------------
    
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
        # Jika data tidak dikenal, kirim pesan error dan akhiri
        await context.bot.send_message(chat_id, "Terjadi kesalahan. Silakan mulai ulang dengan /start.")
        return ConversationHandler.END

    try:
        # Edit Message Text akan mempertahankan ID pesan lama (menu_message_id)
        await query.edit_message_text(
            text, 
            reply_markup=get_menu_kategori(context.user_data['kategori_dict'], data),
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Gagal edit pesan di choose_route: {e}. Mengirim pesan baru.")
        
        # Blok ini sekarang memiliki akses ke variabel 'text' dan 'chat_id'
        sent_message = await context.bot.send_message( 
            chat_id,
            text, # Variabel 'text' sudah didefinisikan
            reply_markup=get_menu_kategori(context.user_data['kategori_dict'], data),
            parse_mode='Markdown'
        )
        # JIKA PESAN BARU DIKIRIM, KITA SIMPAN ID-NYA
        context.user_data['menu_message_id'] = sent_message.message_id
        
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
        # Bersihkan pesan menu kategori yang saat ini ada
        try:
            await query.message.delete()
        except Exception:
            pass
        return await start(update, context) 
    
    kategori_dict = context.user_data.get('kategori_dict', {})
    kategori_nama = next((nama for nama, data_cb in kategori_dict.items() if data_cb == data), 'N/A')
    
    context.user_data['kategori_nama'] = kategori_nama
    
    text = f"Anda memilih *Transaksi {context.user_data['transaksi']}* dengan *Kategori {kategori_nama}*.\n\n"
    text += "Sekarang, *tuliskan jumlah nominal transaksi* (hanya angka, tanpa titik/koma/Rp):"
    
    try:
        # 1. Kirim pesan permintaan nominal baru
        sent_message = await update.callback_query.message.reply_text(
            text, 
            reply_markup=get_menu_kembali('kembali_kategori'), 
            parse_mode='Markdown'
        )
        # 2. Hapus pesan menu kategori lama
        await update.callback_query.message.delete()
        # 3. Simpan ID pesan permintaan nominal yang baru
        context.user_data['nominal_request_message_id'] = sent_message.message_id
    except Exception as e:
        logging.error(f"Gagal mengirim/menghapus pesan di choose_category: {e}")
        # Jika gagal, pastikan tetap mencatat state baru (fallback)
        context.user_data['nominal_request_message_id'] = None

    return GET_DESCRIPTION 

async def get_nominal(update: Update, context):
    chat_id = update.message.chat_id
