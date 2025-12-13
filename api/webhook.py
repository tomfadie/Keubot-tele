# FUNGSI ENTRY POINT UTAMA UNTUK VERCEL/GCP
# Nama fungsi ini adalah 'handler' dan dipanggil oleh Vercel saat menerima request HTTP
def handler(request):
    """
    Fungsi utama yang menerima request dari Webhook Telegram.
    """
    
    # Kritis: Pindah inisialisasi Application ke sini!
    application_instance = init_application()
    
    if application_instance is None:
        logging.error("Application instance tidak ditemukan. (Pastikan BOT_TOKEN benar).")
        return 'Internal Server Error', 500
        
    try:
        # 1. Ambil data JSON dari request.
        request_body = request.get_data()
        data = json.loads(request_body)
        
    except Exception as e:
        logging.error(f"Gagal parsing JSON request dari Telegram: {e}")
        return 'Bad Request', 400

    try:
        # 2. Buat objek Update dan proses menggunakan Application instance
        update = Update.de_json(data, application_instance.bot)
        application_instance.process_update(update)
        
        logging.info("Update Telegram berhasil diproses oleh Application.")
        return 'OK', 200 # HARUS merespons 200 OK ke Telegram
        
    except Exception as e:
        logging.error(f"Error saat memproses Update: {e}")
        return 'Internal Server Error', 500
