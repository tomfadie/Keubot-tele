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

# Mengambil Token dari Environment Variable Vercel
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
    chat_id =
