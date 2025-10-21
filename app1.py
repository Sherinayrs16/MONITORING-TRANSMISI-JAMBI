import pandas as pd
import os
import streamlit as st
import matplotlib.pyplot as plt
from io import BytesIO
import datetime 
import base64 # Diperlukan untuk background image

# TIDAK PERLU IMPORT 'GSheetsConnection' lagi

# ===========================
# Konfigurasi Halaman (Landscape)
# ===========================
st.set_page_config(
    page_title="📡 Monitoring Metering MUX TVRI Jambi",
    page_icon="📡",
    layout="wide"
)

# Inisialisasi session state untuk status login
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# ===========================
# Nama Sheet di Google Sheets
# ===========================
data_sheet = "Sheet1" 
notes_sheet = "CATATAN_HARIAN" 

# ===========================
# Inisialisasi Koneksi Google Sheets (Cara Resmi)
# ===========================
# Ini akan otomatis membaca [connections.gsheets] dari Secrets Anda
try:
    conn = st.connection("gsheets")
except Exception as e:
    st.error(f"Gagal terhubung ke Google Sheets. Pastikan 'Secrets' sudah benar: {e}")
    st.stop() # Hentikan aplikasi jika koneksi gagal

# ===========================
# Fungsi menghitung VSWR
# ===========================
def hitung_vswr(power_output, reflected):
    # Pastikan input adalah float untuk perhitungan
    power_output = float(power_output)
    reflected = float(reflected)
    if reflected == 0:
        return 1.0
    if reflected >= power_output:
        return float("inf") # Tak terhingga jika reflected >= power
    gamma = (reflected / power_output) ** 0.5
    return round((1 + gamma) / (1 - gamma), 2)

# ===========================
# Fungsi untuk Load Data dari Google Sheets
# ===========================
# @st.cache_data(ttl=60) # Cache data selama 60 detik
def load_data(sheet_name):
    """Memuat data dari Google Sheet, sheet tertentu. Membuat DataFrame kosong jika error."""
    try:
        df = conn.read(sheet=sheet_name, ttl=60) # Gunakan cache internal conn.read
        df = df.dropna(how='all') 
        
        # Konversi kolom tanggal jika ada (penting setelah baca dari GSheet)
        date_cols = ['TANGGAL', 'TANGGAL_CATATAN', 'TANGGAL_CEKLIST']
        for col in date_cols:
            if col in df.columns:
                # Coba konversi, biarkan NaT jika format salah
                df[col] = pd.to_datetime(df[col], errors='coerce') 
                # Jika semua NaT, mungkin kolomnya bukan tanggal, biarkan saja
                if df[col].isnull().all():
                     df[col] = df[col].astype(str) # Atau kembalikan ke string jika perlu

        # Pastikan tipe data kolom numerik benar (GSheet bisa membacanya sebagai object/string)
        numeric_cols = [
            "POWER OUTPUT (WATT)", "VSWR", "C/N (dB)", "MARGIN (dB)",
            "TEGANGAN LISTRIK R (Volt)", "TEGANGAN LISTRIK S (Volt)", 
            "TEGANGAN LISTRIK T (Volt)", "SUHU TX",
            "Bitrate NET TV", "Bitrate RTV", "Bitrate JAMBI TV", "Bitrate JEK TV", 
            "Bitrate SINPO TV", "Bitrate TVRI NASIONAL", "Bitrate TVRI WORLD", 
            "Bitrate TVRI SPORT", "Bitrate TVRI JAMBI" 
        ]
        for col in numeric_cols:
             if col in df.columns:
                 df[col] = pd.to_numeric(df[col], errors='coerce') # Jadi NaN jika tidak bisa konversi

        return df
    except Exception as e:
        # Jika sheet belum ada atau error lain, kembalikan DataFrame kosong
        # st.warning(f"Tidak dapat memuat data dari sheet '{sheet_name}': {e}") 
        return pd.DataFrame()

# ===========================
# Fungsi untuk Save Data ke Google Sheets
# ===========================
def save_data(df, sheet_name):
    """Menyimpan (mengganti) DataFrame ke sheet tertentu dalam Google Sheet."""
    try:
        # PENTING: Ubah semua tipe data ke string sebelum menyimpan ke GSheet
        # Ini menghindari masalah format angka, tanggal, dll.
        df_string = df.astype(str) 
        conn.update(sheet=sheet_name, data=df_string)
        st.cache_data.clear() # Hapus cache setelah menyimpan data baru
        st.success(f"✅ Data berhasil disimpan ke Google Sheet **{sheet_name}**!")
    except Exception as e:
        st.error(f"Error saat menyimpan data ke Google Sheets: {e}")


# ===========================
# Mapping Ceklist Harian Digital 
# (Kode ini sama seperti sebelumnya, tidak perlu diubah)
# ===========================
ceklist_rules = {
    "Transmitter (Exciter & PA)": {
        "Normal": {"deskripsi": "Daya output stabil, suhu normal, tidak ada alarm", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Daya output menurun, suhu meningkat", "rekom": "Periksa pendingin, bersihkan filter"},
        "Trouble": {"deskripsi": "Daya output turun drastis, suhu overheat", "rekom": "Periksa exciter/PA, kalibrasi RF"}
    },
    "Antena": {
        "Normal": {"deskripsi": "VSWR normal, sinyal stabil", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "VSWR meningkat, konektor longgar/feeder menurun", "rekom": "Kencangkan konektor, bersihkan feeder"},
        "Trouble": {"deskripsi": "VSWR tinggi, sinyal hilang", "rekom": "Ganti feeder/antena"}
    },
     "Encoder": {
        "Normal": {"deskripsi": "Bitrate stabil, output normal", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Bitrate turun 10–20%, delay/patah-patah", "rekom": "Restart encoder, cek software/jaringan"},
        "Trouble": {"deskripsi": "Output encoder tidak ada (blank)", "rekom": "Cek hardware encoder, ganti unit"}
    },
    "IRD (Integrated Receiver Decoder)": {
        "Normal": {"deskripsi": "Sinyal input & output normal", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Kualitas sinyal menurun, glitch", "rekom": "Periksa level sinyal, cek konektor/kabel"},
        "Trouble": {"deskripsi": "Tidak ada sinyal, video/audio tidak keluar", "rekom": "Cek sumber input, reboot IRD"}
    },
    "Multiplexer": {
        "Normal": {"deskripsi": "Semua input-output normal, bitrate stabil", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Input hilang sesekali/bitrate turun", "rekom": "Restart MUX, cek port input/output"},
        "Trouble": {"deskripsi": "Input tidak terbaca", "rekom": "Servis MUX, cek hardware/software"}
    },
    "Parabola + LNB": {
        "Normal": {"deskripsi": "Arah tepat, sinyal kuat, LNB baik", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Arah bergeser, sinyal melemah", "rekom": "Atur ulang arah, kencangkan konektor LNB"},
        "Trouble": {"deskripsi": "Tidak ada sinyal", "rekom": "Ganti LNB, periksa kabel, atur ulang pointing"}
    },
     "AVR": {
        "Normal": {"deskripsi": "Tegangan output stabil", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Tegangan naik turun ringan", "rekom": "Periksa setting AVR, pendinginan, kabel"},
        "Trouble": {"deskripsi": "Tegangan fluktuasi besar", "rekom": "Servis AVR, ganti komponen"}
    },
    "Grounding": {
        "Normal": {"deskripsi": "Resistansi < 5 Ohm, kabel rapi", "rekom": "Tidak ada tindakan, ukur berkala"},
        "Warning": {"deskripsi": "Resistansi 5–7 Ohm, korosi sambungan", "rekom": "Tambah/perbaiki rod, periksa sambungan"},
        "Trouble": {"deskripsi": "Resistansi > 7 Ohm, proteksi tidak fungsi", "rekom": "Perbaiki jalur ground, tambah rod"}
    },
    "Cooling System": {
        "Normal": {"deskripsi": "Semua kipas normal, angin kuat", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Putaran kipas melemah/bising", "rekom": "Bersihkan kipas, cek bearing/kabel"},
        "Trouble": {"deskripsi": "Kipas mati total", "rekom": "Ganti kipas, cek suplai listrik"}
    },
     "AC Ruangan Transmisi": {
        "Normal": {"deskripsi": "Suhu ruangan 18–24°C stabil", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Suhu 25–26°C", "rekom": "Bersihkan filter AC, periksa freon"},
        "Trouble": {"deskripsi": "AC mati/tidak dingin, suhu >27°C", "rekom": "Isi freon, servis AC, ganti unit"}
    },
    "UPS": {
        "Normal": {"deskripsi": "Backup normal, baterai bagus", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Backup singkat, alarm berbunyi", "rekom": "Periksa aki, bersihkan ventilasi"},
        "Trouble": {"deskripsi": "Tidak ada backup saat listrik padam", "rekom": "Ganti aki, servis UPS"}
    },
    "Genset": {
        "Normal": {"deskripsi": "Mesin hidup normal, beban stabil", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Mesin sulit dinyalakan, bahan bakar habis", "rekom": "Cek aki starter, isi bahan bakar, ganti filter"},
        "Trouble": {"deskripsi": "Mesin tidak hidup/drop", "rekom": "Servis genset, ganti oli/filter/aki"}
    },
    "Router": {
        "Normal": {"deskripsi": "Koneksi internet lancar & stabil", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Koneksi internet melambat", "rekom": "Restart router, cek kabel LAN/fiber"},
        "Trouble": {"deskripsi": "Tidak ada koneksi internet", "rekom": "Ganti router atau hubungi ISP"}
    },
    "Switch Hub": {
        "Normal": {"deskripsi": "Semua port aktif, koneksi lancar", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Satu/beberapa port mati", "rekom": "Gunakan port cadangan, ganti port"},
        "Trouble": {"deskripsi": "Semua port mati, perangkat tidak nyala", "rekom": "Ganti switch hub, cek power supply"}
    },
     "Multiviewer": {
        "Normal": {"deskripsi": "Semua channel tampil normal", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Beberapa channel hilang/delay", "rekom": "Restart sistem, cek input/output matrix"},
        "Trouble": {"deskripsi": "Semua channel blank", "rekom": "Servis atau ganti multiviewer"}
    },
    "Set Top Box": {
        "Normal": {"deskripsi": "Channel terkunci, gambar/suara lancar", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Channel sulit terkunci, sinyal melemah", "rekom": "Scan ulang channel, reset STB"},
        "Trouble": {"deskripsi": "Tidak bisa lock channel", "rekom": "Ganti STB atau periksa antena"}
    },
     "RCS (Remote Control System)": {
        "Normal": {"deskripsi": "Sistem remote normal, perangkat terpantau", "rekom": "Tidak ada tindakan"},
        "Warning": {"deskripsi": "Respon lambat, data delay", "rekom": "Cek jaringan dan software RCS"},
        "Trouble": {"deskripsi": "Tidak bisa remote/monitoring mati total", "rekom": "Cek hardware/software RCS, restart server"}
    }
}

# ===========================
# Background Image Function & Styling
# (Kode ini sama seperti sebelumnya, tidak perlu diubah)
# ===========================
def apply_background_and_style():
    """Mengaplikasikan background image dan styling ke seluruh aplikasi."""
    background_image = "TVRI JAMBI.jpg"
    if os.path.exists(background_image):
        try: # Tambahkan try-except untuk penanganan error file
            with open(background_image, "rb") as f:
                bg_b64 = base64.b64encode(f.read()).decode()
            
            overlay_opacity = '0.15' if not st.session_state['logged_in'] else '0.25'
            css = f"""
            <style>
            .stApp {{ background-image: url("data:image/jpg;base64,{bg_b64}"); background-size: cover; background-position: center; background-attachment: fixed; }}
            .stApp::before {{ content: ""; position: absolute; inset: 0; background: rgba(255,255,255,{overlay_opacity}); z-index: 0; pointer-events: none; }}
            [data-testid="stAppViewContainer"] > .main {{ position: relative; z-index: 1; color: #000 !important; }}
            h1, h2, h3, h4, h5, h6, p, span, label, div, a, strong, em, .stMarkdown, .stExpander, .stButton, .stMetric {{ color: #000 !important; font-weight: 700 !important; text-shadow: none !important; }}
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div, .stDateInput input, .stTextArea textarea {{ color: #000 !important; font-weight: 700 !important; background-color: rgba(255, 255, 255, 0.5) !important; }} /* Background input sedikit transparan */
            .stApp form[data-testid="stForm"]#Login-target {{ padding: 2rem; border: 2px solid #ccc; border-radius: 10px; background-color: rgba(255, 255, 255, 0.95); max-width: 400px; margin: 100px auto; }}
            .stButton > button {{ background-color: #0057B8 !important; color: white !important; font-weight: 700 !important; border-radius: 8px !important; width: 100%; }}
            .stApp [data-testid="stForm"] .stButton > button, .stApp [data-testid="stSidebar"] .stButton > button, .stApp .stButton > button {{ width: auto !important; min-width: 100px; }}
            [data-testid="stSidebar"] > div:first-child {{ background: rgba(255,255,255,0.95) !important; color: #000 !important; position: relative; z-index: 2; }}
            .stDataFrame div {{ color: #000 !important; font-weight: 700 !important; }}
            [data-testid="stRadio"] label div {{ color: #000 !important; font-weight: 700 !important; }}
            [data-testid="stRadio"] input:checked + div {{ background-color: rgba(0, 87, 184, 0.2) !important; color: #000 !important; }}
            </style>
            """
            st.markdown(css, unsafe_allow_html=True)
        except FileNotFoundError:
             st.error(f"Gambar latar '{background_image}' tidak ditemukan.")
        except Exception as e:
             st.error(f"Error saat memuat gambar latar: {e}")
    else:
        st.warning(f"Gambar latar '{background_image}' tidak ditemukan. Background tidak akan tampil.")

# ===========================
# Fungsi Halaman Login
# (Kode ini sama seperti sebelumnya, tidak perlu diubah)
# ===========================
def login_form():
    apply_background_and_style() 
    st.markdown("<div style='text-align: center;'><h1>📡 Login Monitoring MUX TVRI Jambi</h1></div>", unsafe_allow_html=True)
    with st.form("Login"):
        st.subheader("Masukkan Username dan Password")
        st.markdown("<div id='login-container'>", unsafe_allow_html=True) 
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_button = st.form_submit_button("Masuk")
        st.markdown("</div>", unsafe_allow_html=True) 
        if login_button:
            if username == "admin" and password == "admin": # Ganti dengan autentikasi yang lebih aman jika perlu
                st.session_state['logged_in'] = True
                st.rerun() 
            else:
                st.error("❌ Username atau Password salah!")
    st.stop()

# ===========================
# Fungsi Halaman Input Data & Kalkulator
# (Sedikit penyesuaian tipe data input)
# ===========================
def show_input_kalkulator():
    st.title("📝 Input Data & Kalkulator")
    
    st.subheader("🧮 Kalkulator VSWR")
    colk1, colk2 = st.columns(2)
    # Gunakan step=None untuk input float yang lebih fleksibel
    calc_power = colk1.number_input("Power Output (Watt)", min_value=0.0, step=None, format="%.2f", key="calc_power") 
    calc_reflected = colk2.number_input("Reflected (Watt)", min_value=0.0, step=None, format="%.2f", key="calc_reflected")

    if st.button("🔢 Hitung VSWR"):
        if calc_power is not None and calc_reflected is not None: # Pastikan input tidak kosong
            vswr_calc = hitung_vswr(calc_power, calc_reflected)
            if vswr_calc == float("inf"):
                st.error("⚠️ Reflected ≥ Power Output → VSWR tak terhingga!")
            else:
                st.info(f"Hasil perhitungan VSWR: **{vswr_calc}**")
        else:
             st.warning("Masukkan nilai Power Output dan Reflected.")


    rules_param = {
        "Power Output (Watt)": [{"min": 10000, "max": 11900, "status": "Normal", "rekom": "Output sesuai standar"}, {"min": 8000, "max": 9999, "status": "Warning", "rekom": "Catat penurunan"}, {"min": 0, "max": 7999, "status": "Trouble", "rekom": "Periksa exciter/amp"}, {"min": 11901, "max": 20000, "status": "Trouble", "rekom": "Periksa setting daya"}],
        "VSWR": [{"min": 0, "max": 1.24, "status": "Normal", "rekom": "VSWR aman"}, {"min": 1.25, "max": 1.30, "status": "Warning", "rekom": "Kencangkan konektor"}, {"min": 1.31, "max": 10.0, "status": "Trouble", "rekom": "Turunkan daya, periksa antena"}],
        "C/N (dB)": [{"min": 40, "max": 50, "status": "Normal", "rekom": "Sinyal stabil"}, {"min": 30, "max": 39.9, "status": "Warning", "rekom": "Pantau sinyal"}, {"min": 0,  "max": 29.9, "status": "Trouble", "rekom": "Atur ulang parabola"}],
        "Margin (dB)": [{"min": 20, "max": 30, "status": "Normal", "rekom": "Link aman"}, {"min": 10, "max": 19.9, "status": "Warning", "rekom": "Periksa konektor RF"}, {"min": 0,  "max": 9.9, "status": "Trouble", "rekom": "Atur ulang dish"}],
        "Tegangan Listrik (Volt)": [{"min": 215, "max": 225, "status": "Normal", "rekom": "Tegangan stabil"}, {"min": 210, "max": 214, "status": "Warning", "rekom": "Pantau voltase"}, {"min": 226, "max": 230, "status": "Warning", "rekom": "Pantau voltase"}, {"min": 0, "max": 209, "status": "Trouble", "rekom": "Periksa suplai/UPS"}, {"min": 231, "max": 300, "status": "Trouble", "rekom": "Periksa suplai/UPS"}],
        "Suhu TX (°C)": [{"min": 17, "max": 20.9, "status": "Normal", "rekom": "Suhu normal"}, {"min": 21, "max": 25.9, "status": "Warning", "rekom": "Cek pendingin"}, {"min": 26, "max": 100, "status": "Trouble", "rekom": "Servis AC"}]
    }

    def cek_param(nama, nilai):
        if nilai is None: return "N/A", "Nilai belum diinput"
        nilai = float(nilai) # Pastikan float untuk perbandingan
        for rule in rules_param[nama]:
            if rule["min"] <= nilai <= rule["max"]:
                return rule["status"], rule["rekom"]
        # Jika nilai di luar semua rentang (misal VSWR > 10)
        if nilai > rules_param[nama][-1]["max"]: 
             return rules_param[nama][-1]["status"], rules_param[nama][-1]["rekom"]
        if nilai < rules_param[nama][0]["min"]:
             return rules_param[nama][0]["status"], rules_param[nama][0]["rekom"]
        return "N/A", "Tidak ada rekomendasi"

    with st.form("form_metering"):
        st.subheader("📝 Input Data Harian")
        
        col1_form, col2_form = st.columns(2)
        tanggal = col1_form.date_input("Tanggal", value=datetime.date.today()) # Default hari ini
        waktu_options = ["02:00", "06:00", "10:00", "14:00", "18:00", "22:00"]
        waktu = col2_form.selectbox("Waktu", waktu_options)

        # Gunakan step=None untuk input float yang lebih fleksibel
        power_output = st.number_input("Power Output (Watt)", min_value=0.0, step=None, format="%.2f") 
        vswr_input = st.number_input("VSWR", min_value=1.0, step=None, format="%.2f")
        cn = st.number_input("C/N (dB)", min_value=0.0, step=None, format="%.2f")
        margin = st.number_input("Margin (dB)", min_value=0.0, step=None, format="%.2f")

        col3, col4, col5 = st.columns(3)
        teg_r = col3.number_input("Phase R (Volt)", min_value=0.0, step=None, format="%.1f", key="teg_r")
        teg_s = col4.number_input("Phase S (Volt)", min_value=0.0, step=None, format="%.1f", key="teg_s")
        teg_t = col5.number_input("Phase T (Volt)", min_value=0.0, step=None, format="%.1f", key="teg_t")

        suhu_tx = st.number_input("Suhu TX (°C)", min_value=0.0, step=None, format="%.1f")

        st.subheader("Status Channel TV & Bitrate")
        tv_channels = ["NET TV", "RTV", "JAMBI TV", "JEK TV", "SINPO TV", 
                       "TVRI NASIONAL", "TVRI WORLD", "TVRI SPORT", "TVRI JAMBI"]
        bitrate_inputs = {}
        status_inputs = {}

        for tv in tv_channels:
             st.markdown(f"#### {tv}")
             col_ok, col_bitrate = st.columns(2)
             status_inputs[tv] = col_ok.selectbox(f"Status {tv}", ["OK", "NO"], key=f"{tv}_ok")
             bitrate_inputs[tv] = col_bitrate.number_input(f"Bitrate {tv} (Mbps)", min_value=0.0, step=None, format="%.2f", key=f"{tv}_bitrate")

        kualitas_av = st.selectbox("Kualitas Audio / Video", ["A/V OK", "A/V NO"])
        operator = st.text_input("Operator")
        catatan = st.text_area("Catatan/Keterangan", placeholder="Isi catatan...", height=100)

        lihat_rekom = st.form_submit_button("🔍 Lihat Rekomendasi")
        simpan_data = st.form_submit_button("✅ Simpan Data") 

    if lihat_rekom or simpan_data:
        # Validasi bahwa input numerik tidak None sebelum cek_param
        params_to_check = {
            "Power Output (Watt)": power_output, "VSWR": vswr_input, "C/N (dB)": cn,
            "Margin (dB)": margin, "Tegangan Listrik (Volt)": teg_r, # Cek R, S, T dengan rule yg sama
             "Suhu TX (°C)": suhu_tx 
        }
        data_analisis = []
        for name, value in params_to_check.items():
            status, rekom = cek_param(name, value)
            display_value = value if value is not None else "N/A"
            data_analisis.append([name, display_value, status, rekom])
        
        # Cek S dan T secara terpisah tapi gunakan rule yang sama
        status_s, rekom_s = cek_param("Tegangan Listrik (Volt)", teg_s)
        data_analisis.append(["Tegangan S (Volt)", teg_s if teg_s is not None else "N/A", status_s, rekom_s])
        status_t, rekom_t = cek_param("Tegangan Listrik (Volt)", teg_t)
        data_analisis.append(["Tegangan T (Volt)", teg_t if teg_t is not None else "N/A", status_t, rekom_t])

        df_rekom = pd.DataFrame(data_analisis, columns=["Parameter", "Nilai Input", "Status", "Rekomendasi"])
        st.subheader("📊 Analisa & Rekomendasi Maintenance")
        st.dataframe(df_rekom, use_container_width=True)

        if simpan_data:
            # Pastikan semua input ada sebelum menyimpan
            required_numeric_inputs = [power_output, vswr_input, cn, margin, teg_r, teg_s, teg_t, suhu_tx] + list(bitrate_inputs.values())
            if None in required_numeric_inputs or not operator:
                 st.error("❌ Gagal menyimpan! Pastikan semua input angka dan nama operator terisi.")
            else:
                data_input = {
                    "TANGGAL": pd.to_datetime(tanggal).strftime("%Y-%m-%d"), "WAKTU": waktu,
                    "POWER OUTPUT (WATT)": power_output, "VSWR": vswr_input, "C/N (dB)": cn, "MARGIN (dB)": margin,
                    "TEGANGAN LISTRIK R (Volt)": teg_r, "TEGANGAN LISTRIK S (Volt)": teg_s, "TEGANGAN LISTRIK T (Volt)": teg_t,
                    "SUHU TX": suhu_tx,
                    "KUALITAS AUDIO / VIDEO": kualitas_av, "OPERATOR": operator, "CATATAN/KETERANGAN": catatan, 
                }
                # Tambahkan status dan bitrate channel
                for tv in tv_channels:
                    data_input[tv] = status_inputs[tv]
                    data_input[f"Bitrate {tv}"] = bitrate_inputs[tv]

                df_existing = load_data(data_sheet) 
                
                # --- Penanganan Tanggal & Duplikat ---
                df_new = pd.DataFrame([data_input])
                # Konversi TANGGAL di data baru ke datetime untuk pengecekan
                df_new['TANGGAL'] = pd.to_datetime(df_new['TANGGAL']) 
                
                if df_existing.empty:
                    df_all = df_new
                else:
                    # Pastikan TANGGAL di data lama juga datetime
                    if 'TANGGAL' in df_existing.columns:
                        df_existing['TANGGAL'] = pd.to_datetime(df_existing['TANGGAL'], errors='coerce')
                    
                    # Cek duplikat (tanggal + waktu sama)
                    df_existing['DUP_CHECK'] = df_existing['TANGGAL'].dt.strftime('%Y-%m-%d') + '_' + df_existing['WAKTU'].astype(str)
                    df_new['DUP_CHECK'] = df_new['TANGGAL'].dt.strftime('%Y-%m-%d') + '_' + df_new['WAKTU'].astype(str)
                    
                    df_existing_filtered = df_existing[~df_existing['DUP_CHECK'].isin(df_new['DUP_CHECK'])]
                    df_all = pd.concat([df_existing_filtered.drop(columns=['DUP_CHECK'], errors='ignore'), 
                                        df_new.drop(columns=['DUP_CHECK'], errors='ignore')], 
                                       ignore_index=True)

                # --- Format Ulang Sebelum Simpan ---
                # Format TANGGAL jadi string YYYY-MM-DD untuk GSheet
                if 'TANGGAL' in df_all.columns:
                    df_all['TANGGAL'] = pd.to_datetime(df_all['TANGGAL']).dt.strftime('%Y-%m-%d')

                # Pastikan urutan kolom konsisten (opsional tapi bagus)
                # Ambil header dari GSheet jika ada, atau buat dari data baru jika GSheet kosong
                try:
                    header = conn.read(sheet=data_sheet, nrows=1).columns.tolist()
                    # Tambah kolom baru jika ada di df_all tapi belum di header GSheet
                    new_cols = [col for col in df_all.columns if col not in header]
                    final_header = header + new_cols
                    df_all = df_all.reindex(columns=final_header) 
                except Exception: # Jika GSheet kosong atau error baca header
                     pass # Biarkan urutan kolom apa adanya

                # Simpan ke Google Sheet
                save_data(df_all, data_sheet) # Fungsi save_data sudah ada st.success

# ===========================
# Fungsi Halaman Visualisasi Data
# ===========================
def show_visualisasi_data():
    st.title("📊 Visualisasi Data")
    
    df = load_data(data_sheet) 
    
    if df.empty:
        st.info("⚠️ Belum ada data metering tersimpan di Google Sheet.")
        return 
    
    try:
        # Buat kolom DATETIME untuk plotting dan sorting
        if 'TANGGAL' in df.columns and 'WAKTU' in df.columns:
             df['TANGGAL'] = pd.to_datetime(df['TANGGAL'], errors='coerce')
             # Gabungkan tanggal dan waktu, tangani error jika format waktu salah
             df["DATETIME"] = pd.to_datetime(df['TANGGAL'].dt.strftime('%Y-%m-%d') + ' ' + df['WAKTU'].astype(str), errors='coerce') 
             df = df.dropna(subset=["DATETIME"]).sort_values("DATETIME")
        else:
             st.error("Kolom 'TANGGAL' atau 'WAKTU' tidak ditemukan di Google Sheet.")
             return

        df_group = pd.DataFrame() # Inisialisasi

        st.subheader("Grafik Tren Parameter")
        opsi_agregasi = st.radio("Pilih Periode Visualisasi:", ["Harian", "Rentang Tanggal"], horizontal=True, key="vis_radio") 

        if opsi_agregasi == "Harian":
            if not df.empty:
                # Ambil tanggal unik dari data yang valid
                available_dates = sorted(df['TANGGAL'].dt.date.unique(), reverse=True) 
                if not available_dates:
                     st.warning("Tidak ada data tanggal yang valid.")
                     return
                
                # Default ke tanggal terbaru
                default_date = available_dates[0]
                
                pilih_tanggal = st.selectbox(
                    "Pilih Tanggal", 
                    options=available_dates, 
                    index=0, # Default ke index 0 (terbaru)
                    format_func=lambda date: date.strftime('%Y-%m-%d'), # Format tampilan
                    key="vis_date_select"
                )
                
                if pilih_tanggal:
                    df_group = df[df["TANGGAL"].dt.date == pilih_tanggal].copy() 
                else: 
                     df_group = pd.DataFrame() # Kosong jika tidak ada tanggal terpilih

            else: st.info("Tidak ada data.")

        else: # Rentang Tanggal
            st.write("Pilih rentang tanggal untuk visualisasi.")
            if not df.empty:
                min_date = df["TANGGAL"].min().date()
                max_date = df["TANGGAL"].max().date()

                col_start, col_end = st.columns(2)
                start_date = col_start.date_input("Tanggal Awal", value=min_date, min_value=min_date, max_value=max_date, key="viz_start_date")
                end_date = col_end.date_input("Tanggal Akhir", value=max_date, min_value=min_date, max_value=max_date, key="viz_end_date")

                if start_date and end_date and start_date <= end_date:
                    # Filter inklusif start_date sampai akhir end_date
                    mask = (df['TANGGAL'].dt.date >= start_date) & (df['TANGGAL'].dt.date <= end_date)
                    df_group = df.loc[mask].copy()
                elif start_date > end_date:
                    st.error("Tanggal Awal tidak boleh setelah Tanggal Akhir.")
                    df_group = pd.DataFrame()
                else: 
                     df_group = pd.DataFrame()
            else: st.info("Tidak ada data.")

        # Parameter untuk visualisasi (hanya numerik)
        numeric_cols_viz = df.select_dtypes(include=['number']).columns.tolist()
        # Hapus kolom non-fisik jika ada (misal index atau ID)
        params_to_exclude = ['index', 'id'] # Sesuaikan jika ada kolom lain
        available_params = [col for col in numeric_cols_viz if col.lower() not in params_to_exclude]

        if not available_params:
             st.warning("Tidak ada kolom data numerik yang bisa divisualisasikan.")
             return

        default_selection = [p for p in ["POWER OUTPUT (WATT)", "VSWR"] if p in available_params]

        parameter = st.multiselect(
            "Pilih Parameter:",
            available_params,
            default=default_selection,
            key="vis_param_select"
        )

        # Plotting
        if parameter and not df_group.empty:
            fig, ax = plt.subplots(figsize=(12, 6)) # Perbesar sedikit
            for col in parameter:
                if col in df_group.columns:
                     # Pastikan data numerik sebelum plot
                     plot_data = pd.to_numeric(df_group[col], errors='coerce') 
                     if not plot_data.isnull().all(): # Jangan plot jika semua NaN
                        ax.plot(df_group["DATETIME"], plot_data, marker="o", linestyle='-', label=col)
            
            # Format Sumbu X
            if opsi_agregasi == "Harian":
                 ax.set_xlabel("Jam")
                 ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%H:%M'))
            else:
                 ax.set_xlabel("Tanggal dan Waktu")
                 fig.autofmt_xdate() # Rotasi otomatis jika label tumpang tindih

            ax.set_ylabel("Nilai")
            ax.set_title(f"Grafik Parameter Transmisi")
            ax.legend()
            ax.grid(True, linestyle='--', alpha=0.6)
            plt.tight_layout()
            st.pyplot(fig)
        elif parameter and df_group.empty:
            st.warning("⚠️ Tidak ada data untuk tanggal/rentang yang dipilih.")
        
        # Tampilkan Data Tabel
        st.subheader("📑 Data Tersimpan (Metering)")
        df_display = df.sort_values(by="DATETIME", ascending=False).drop(columns=['DATETIME'], errors='ignore').copy()
        if 'TANGGAL' in df_display.columns:
            df_display['TANGGAL'] = df_display['TANGGAL'].dt.strftime('%Y-%m-%d') # Format tanggal jadi string lagi

        # Hapus kolom index default dari GSheet jika terbaca
        if 'Unnamed: 0' in df_display.columns: 
             df_display = df_display.drop(columns=['Unnamed: 0'])

        opsi_tampilan = st.selectbox("Tampilkan baris terakhir:", ["5", "10", "100", "Semua"], index=0, key="vis_table_rows")
        rows_to_show = {"5": 5, "10": 10, "100": 100}.get(opsi_tampilan)
        if rows_to_show:
            st.dataframe(df_display.head(rows_to_show), use_container_width=True)
        else: # Tampilkan semua
            st.dataframe(df_display, use_container_width=True)

        # Download Data
        st.subheader("📥 Download Data (Metering)")
        st.write("Pilih rentang tanggal untuk data yang ingin diunduh.")
        if not df.empty:
            min_date_dl = df["TANGGAL"].min().date()
            max_date_dl = df["TANGGAL"].max().date()
            col_start_dl, col_end_dl = st.columns(2)
            start_date_dl = col_start_dl.date_input("Tanggal Awal Download", value=min_date_dl, min_value=min_date_dl, max_value=max_date_dl, key="dl_start_date")
            end_date_dl = col_end_dl.date_input("Tanggal Akhir Download", value=max_date_dl, min_value=min_date_dl, max_value=max_date_dl, key="dl_end_date")

            if start_date_dl and end_date_dl and start_date_dl <= end_date_dl:
                mask_dl = (df['TANGGAL'].dt.date >= start_date_dl) & (df['TANGGAL'].dt.date <= end_date_dl)
                df_download = df.loc[mask_dl].drop(columns=['DATETIME'], errors='ignore').copy()
                if 'TANGGAL' in df_download.columns:
                     df_download['TANGGAL'] = df_download['TANGGAL'].dt.strftime('%Y-%m-%d')
                
                if not df_download.empty:
                    # Hapus index default dari GSheet sebelum download
                    if 'Unnamed: 0' in df_download.columns: 
                         df_download = df_download.drop(columns=['Unnamed: 0'])
                    
                    buffer = BytesIO()
                    df_download.to_excel(buffer, index=False, engine='openpyxl') 
                    buffer.seek(0)
                    st.download_button(
                        label="⬇️ Download Data (Excel)", data=buffer, 
                        file_name=f"metering_{start_date_dl}_to_{end_date_dl}.xlsx", 
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else: st.warning("Tidak ada data dalam rentang tanggal download yang dipilih.")
            elif start_date_dl > end_date_dl:
                st.error("Tanggal Awal Download tidak boleh setelah Tanggal Akhir.")
        else: st.info("Tidak ada data untuk diunduh.")

    except Exception as e:
        st.error(f"Terjadi error saat visualisasi data: {e}")
        st.warning("Mungkin ada masalah format data di Google Sheet.")

# ===========================
# Fungsi Halaman Ceklist Harian
# ===========================
def show_ceklist_harian():
    st.title("✅ Ceklist Harian Digital")
    st.write("Pilih kondisi tiap parameter.")
    
    HOUR_OPTIONS = ['Shift 1: 00.00 - 08.00', 'Shift 2: 08:00 - 16.00', 'Shift 3: 16:00-00.00']

    # Definisikan kolom final (urutan penting untuk konsistensi)
    FINAL_COLUMNS = ["TANGGAL_CEKLIST", "JAM_CEKLIST", "OPERATOR_CEKLIST"]
    for param in ceklist_rules.keys():
        FINAL_COLUMNS.append(f"{param}_KONDISI")
        FINAL_COLUMNS.append(f"{param}_REKOMENDASI")

    st.subheader("Informasi Catatan")
    col_date, col_hour, col_op = st.columns([1, 1, 1])
    tanggal_catatan = col_date.date_input("Tanggal", value=datetime.date.today(), key="date_note_input")
    jam_catatan = col_hour.selectbox("Jam", HOUR_OPTIONS, key="hour_note_input")
    operator_catatan = col_op.text_input("Operator", key="operator_note_input")
        
    st.markdown("---")
    st.subheader("Pilihan Kondisi Perangkat")
    
    hasil_ceklist = {}
    for param, kondisi in ceklist_rules.items():
        st.markdown(f"**{param}**")
        if f"ceklist_{param}" not in st.session_state:
            st.session_state[f"ceklist_{param}"] = "Normal" # Default
            
        pilihan = st.radio(f"Kondisi {param}", ["Normal", "Warning", "Trouble"], horizontal=True, 
                           key=f"ceklist_{param}", label_visibility="collapsed")
        
        deskripsi = kondisi.get(pilihan, {}).get('deskripsi', 'N/A') # Lebih aman jika ada typo
        rekomendasi = kondisi.get(pilihan, {}).get('rekom', 'N/A')
        
        st.markdown(f"**📌 {deskripsi}**")
        hasil_ceklist[param] = {"Kondisi": pilihan, "Deskripsi": deskripsi, "Rekomendasi": rekomendasi}

    col_rekom, col_simpan = st.columns(2)
    lihat_rekom = col_rekom.button("📋 Tampilkan Rekomendasi")
    simpan_catatan = col_simpan.button("💾 Simpan Catatan Harian")

    if lihat_rekom:
        st.subheader("🛠️ Rekomendasi Maintenance")
        rekom_list = []
        for p, data in hasil_ceklist.items():
             if data['Kondisi'] != 'Normal': # Hanya tampilkan jika bukan Normal
                 rekom_list.append(f"**{p} ({data['Kondisi']}):** {data['Rekomendasi']}")
        if rekom_list:
             st.markdown("\n".join(f"- {item}" for item in rekom_list))
        else:
             st.info("Semua parameter dalam kondisi Normal.")

    if simpan_catatan:
         if not operator_catatan: # Validasi Nama Operator
              st.error("❌ Gagal menyimpan! Nama Operator harus diisi.")
         else:
            data_simpan_horizontal = {
                "TANGGAL_CEKLIST": [pd.to_datetime(tanggal_catatan).strftime("%Y-%m-%d")],
                "JAM_CEKLIST": [jam_catatan], "OPERATOR_CEKLIST": [operator_catatan],
            }
            for param, data in hasil_ceklist.items():
                data_simpan_horizontal[f"{param}_KONDISI"] = [data["Kondisi"]]
                data_simpan_horizontal[f"{param}_REKOMENDASI"] = [data["Rekomendasi"]] 

            df_new_notes = pd.DataFrame(data_simpan_horizontal)
            df_new_notes = df_new_notes.reindex(columns=FINAL_COLUMNS, fill_value='') # Isi NaN dgn string kosong
            
            df_existing_notes = load_data(notes_sheet)
            
            # Gabungkan dengan data lama
            if not df_existing_notes.empty:
                 # Pastikan TANGGAL di data lama jadi string
                 if 'TANGGAL_CEKLIST' in df_existing_notes.columns:
                      df_existing_notes['TANGGAL_CEKLIST'] = pd.to_datetime(df_existing_notes['TANGGAL_CEKLIST'], errors='coerce').dt.strftime('%Y-%m-%d')
                 # Samakan urutan kolom & isi NaN dgn string kosong
                 df_existing_notes = df_existing_notes.reindex(columns=FINAL_COLUMNS, fill_value='') 
                 df_all_notes = pd.concat([df_existing_notes, df_new_notes], ignore_index=True)
            else:
                 df_all_notes = df_new_notes

            # Hapus baris duplikat berdasarkan tanggal, jam, dan operator
            df_all_notes = df_all_notes.drop_duplicates(subset=["TANGGAL_CEKLIST", "JAM_CEKLIST", "OPERATOR_CEKLIST"], keep='last')

            save_data(df_all_notes, notes_sheet) # Fungsi save_data sudah ada st.success

    # Tampilkan Data Catatan Harian
    st.subheader("📑 Data Tersimpan (Catatan Harian)")
    df_notes_display = load_data(notes_sheet)

    if df_notes_display.empty:
        st.info("Belum ada catatan harian tersimpan di Google Sheet.")
    else:
        # Urutkan berdasarkan tanggal dan jam (jika ada)
        if 'TANGGAL_CEKLIST' in df_notes_display.columns and 'JAM_CEKLIST' in df_notes_display.columns:
            try: # Coba buat kolom datetime untuk sorting
                 df_notes_display['TANGGAL_CEKLIST_DT'] = pd.to_datetime(df_notes_display['TANGGAL_CEKLIST'], errors='coerce')
                 # Ekstrak jam dari string 'Shift X: HH.MM - HH.MM'
                 df_notes_display['JAM_SORT'] = df_notes_display['JAM_CEKLIST'].astype(str).str.extract(r'(\d{2}\.\d{2})').fillna('00.00').str.replace('.', ':', regex=False)
                 df_notes_display['DATETIME_SORT'] = pd.to_datetime(df_notes_display['TANGGAL_CEKLIST_DT'].dt.strftime('%Y-%m-%d') + ' ' + df_notes_display['JAM_SORT'], errors='coerce')
                 df_notes_display = df_notes_display.sort_values(by='DATETIME_SORT', ascending=False).drop(columns=['TANGGAL_CEKLIST_DT', 'JAM_SORT', 'DATETIME_SORT'], errors='ignore')
            except Exception: # Jika error parsing, tampilkan tanpa sorting waktu
                 df_notes_display = df_notes_display.sort_values(by='TANGGAL_CEKLIST', ascending=False)
        elif 'TANGGAL_CEKLIST' in df_notes_display.columns: # Sort by date only if time fails or not present
             df_notes_display['TANGGAL_CEKLIST'] = pd.to_datetime(df_notes_display['TANGGAL_CEKLIST'], errors='coerce')
             df_notes_display = df_notes_display.sort_values(by='TANGGAL_CEKLIST', ascending=False)
             df_notes_display['TANGGAL_CEKLIST'] = df_notes_display['TANGGAL_CEKLIST'].dt.strftime('%Y-%m-%d') # Format kembali ke string
        
        # Hapus index default dari GSheet jika terbaca
        if 'Unnamed: 0' in df_notes_display.columns: 
             df_notes_display = df_notes_display.drop(columns=['Unnamed: 0'])

        st.dataframe(df_notes_display, use_container_width=True)

        # Download Catatan Harian
        st.subheader("📥 Download Data (Catatan Harian)")
        buffer_notes = BytesIO()
        df_notes_download = df_notes_display.copy() # Gunakan data yang sudah di-sort
        # Hapus index default GSheet sebelum download
        if 'Unnamed: 0' in df_notes_download.columns: 
             df_notes_download = df_notes_download.drop(columns=['Unnamed: 0'])
             
        df_notes_download.to_excel(buffer_notes, index=False, engine='openpyxl')
        buffer_notes.seek(0)
        st.download_button(label="⬇️ Download Catatan Harian (Excel)", data=buffer_notes,
                           file_name="catatan_harian_mux_tvri.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ===========================
# Routing Aplikasi Utama
# ===========================
if not st.session_state.get('logged_in', False): # Lebih aman pakai .get()
    login_form()
else:
    apply_background_and_style() 
    st.markdown("<h1 style='text-align: center;'>📡 Monitoring Metering MUX Transmisi TVRI Jambi</h1>", unsafe_allow_html=True)
    
    st.sidebar.title("Menu Utama")
    if 'current_page' not in st.session_state:
        st.session_state['current_page'] = "📝 Input Data & Kalkulator" # Default
        
    page_options = ["📝 Input Data & Kalkulator", "📊 Visualisasi Data", "✅ Ceklist Harian Digital"]
    page = st.sidebar.selectbox("Pilih Halaman:", page_options, 
                                index=page_options.index(st.session_state['current_page']), 
                                key='sidebar_page_select')
    st.session_state['current_page'] = page 

    if st.sidebar.button("🚪 Logout"):
        st.session_state['logged_in'] = False
        st.cache_data.clear() # Hapus cache saat logout
        st.rerun()

    # Tampilkan halaman sesuai pilihan
    if page == "📝 Input Data & Kalkulator":
        show_input_kalkulator()
    elif page == "📊 Visualisasi Data":
        show_visualisasi_data()
    elif page == "✅ Ceklist Harian Digital":
        show_ceklist_harian()
