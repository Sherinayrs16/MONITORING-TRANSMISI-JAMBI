import pandas as pd
import datetime
import requests
import os

# ===========================
# KONFIGURASI FILE & TELEGRAM (WAJIB DIGANTI!)
# ===========================
# Ganti dengan token bot Anda.
TELEGRAM_BOT_TOKEN = "8023062114:AAGIbQlDnc61cKRUezILa5fH3CHJxblGt8w" 
# Ganti dengan ID Grup/Channel Anda (harus diawali dengan tanda minus '-').
TELEGRAM_CHAT_ID = "-4881806303" 
data_file = "metering_mux.xlsx"
data_sheet = "Sheet1" 

# ===========================
# FUNGSI TELEGRAM
# ===========================
def send_telegram_notification(message):
    """Fungsi untuk mengirim pesan ke Telegram."""
    if TELEGRAM_BOT_TOKEN == "GANTI_DENGAN_TOKEN_BOT_ANDA":
        print("Error: Harap ganti BOT_TOKEN dan CHAT_ID.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status() 
        return True
    except requests.exceptions.RequestException as e:
        # Menghindari kegagalan fatal, hanya tampilkan di log
        print(f"Gagal mengirim notifikasi Telegram: {e}") 
        return False
        
# ===========================
# FUNGSI LOAD DATA
# ===========================
def load_data(sheet_name):
    """Memuat data dari file Excel tanpa menggunakan Streamlit."""
    if os.path.exists(data_file):
        try:
            df = pd.read_excel(data_file, sheet_name=sheet_name, engine='openpyxl')
            
            if 'TANGGAL' in df.columns:
                 # Mengkonversi ke objek date agar konsisten dengan pengecekan
                 df['TANGGAL'] = pd.to_datetime(df['TANGGAL']).dt.date
                 
            return df.dropna(how='all')
        except Exception as e:
            print(f"Error saat memuat data: {e}")
            return pd.DataFrame() 
    return pd.DataFrame()

# ===========================
# LOGIKA UTAMA REMINDER (Dua Mode: ALARM & CHECK DATA HILANG)
# ===========================
def check_and_remind():
    current_time = datetime.datetime.now()
    WAKTU_METERING_OPTIONS = ["02:00", "06:00", "10:00", "14:00", "18:00", "22:00"]
    
    target_dt_to_check = None
    action_type = None 

    for t_str in WAKTU_METERING_OPTIONS:
        jam, menit = map(int, t_str.split(':'))
        
        # Objek datetime untuk waktu metering ideal hari ini
        target_dt = current_time.replace(hour=jam, minute=menit, second=0, microsecond=0)
        
        # Penanganan 22:00 hari sebelumnya: Jika sekarang < 02:00
        if jam == 22 and current_time.hour < 2:
            target_dt -= datetime.timedelta(days=1)
            
        # Jika target_dt sudah lewat hari ini, dan ini bukan penanganan 22:00, 
        # maka cek target untuk besok (kecuali jika kita mencari yang sudah terlewat)
        # Kita hanya fokus pada pengecekan sekitar waktu ALARM dan CHECK.
        
        # --- DEFINISI WAKTU PENTING UNTUK JADWAL INI ---
        alarm_time = target_dt - datetime.timedelta(minutes=20) # Alarm 20 menit sebelum (misal 01:40)
        check_time = target_dt + datetime.timedelta(hours=1)    # Cek 1 jam setelah (misal 03:00)
        
        # --- MODE 1: ALARM PRA-JADWAL ---
        # Cek apakah sekarang berada di sekitar waktu alarm (dalam rentang 5 menit)
        if current_time >= alarm_time - datetime.timedelta(minutes=5) and current_time <= alarm_time + datetime.timedelta(minutes=5):
             target_dt_to_check = target_dt
             action_type = 'ALARM'
             break 

        # --- MODE 2: CHECK PASCA-JADWAL (DATA HILANG) ---
        # Cek apakah sekarang berada di sekitar waktu pengecekan (dalam rentang 5 menit)
        if current_time >= check_time - datetime.timedelta(minutes=5) and current_time <= check_time + datetime.timedelta(minutes=5):
             target_dt_to_check = target_dt
             action_type = 'CHECK'
             break 
    
    # --- PROSES AKSI ---
    if target_dt_to_check and action_type:
        target_date = target_dt_to_check.date()
        target_time_str = target_dt_to_check.strftime('%H:%M')
        
        if action_type == 'ALARM':
            alarm_message = f"""
🔔 *ALARM INPUT DATA METERING!*
*PERSIAPKAN DIRI!* Waktu input sebentar lagi tiba.

*JADWAL WAJIB INPUT:* Jam *{target_time_str}*
*TANGGAL:* {target_date.strftime('%d-%m-%Y')}

Mohon segera buka aplikasi Streamlit dan lakukan input **TEPAT PUKUL {target_time_str}**.
"""
            send_telegram_notification(alarm_message)

        elif action_type == 'CHECK':
            df = load_data(data_sheet)
            is_data_available = False
            
            if not df.empty and 'TANGGAL' in df.columns and 'WAKTU' in df.columns:
                # Cek apakah data untuk tanggal dan waktu target sudah ada
                is_data_available = ((df['TANGGAL'] == target_date) & 
                                     (df['WAKTU'] == target_time_str)).any()
            
            if not is_data_available:
                # KIRIM PESAN DATA HILANG (Pukul 03:00)
                missing_data_message = f"""
❌ *PERINGATAN KERAS! DATA HILANG!*
Data Metering untuk jadwal *{target_time_str}* belum diinput.

*JADWAL HILANG:* Jam *{target_time_str}*
*TANGGAL:* {target_date.strftime('%d-%m-%Y')}

OPERATOR WAJIB LAPOR DAN SEGERA INPUT DATA KETERLAMBATAN.
"""
                send_telegram_notification(missing_data_message)
            else:
                # Data sudah ada, tidak perlu kirim pesan
                pass 
    
    # Ini penting untuk melihat log jika terjadi error
    print(f"Skrip Reminder Selesai. Aksi: {action_type} untuk waktu: {target_dt_to_check}")

if __name__ == "__main__":
    check_and_remind()