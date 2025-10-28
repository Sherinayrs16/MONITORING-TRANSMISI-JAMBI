import pandas as pd
import os
import streamlit as st
import matplotlib.pyplot as plt
from io import BytesIO
import datetime 
import base64
import json
import gspread
from gspread_dataframe import set_with_dataframe # <--- DIPERLUKAN UNTUK save_data

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
# Nama Sheet
# ===========================
data_sheet = "Sheet1"
notes_sheet = "CATATAN_HARIAN" 

# ===========================
# INISIALISASI GSPREAD CLIENT (Menggunakan @st.cache_resource)
# ===========================
@st.cache_resource(ttl=None) # <-- PENTING: Cache koneksi (objek non-hashable)
def get_gspread_client():
    secrets = st.secrets["connections"]["gsheets"]
    
    # Kumpulkan semua data JSON dari secrets
    gcp_credentials = {
        "type": "service_account",
        "project_id": secrets["project_id"],
        "private_key_id": secrets["private_key_id"],
        # KUNCI UTAMA: Mengganti '\n' dari string secrets ke karakter newline (\n) sebenarnya
        "private_key": secrets["private_key"].replace("\\n", "\n").strip(), 
        "client_email": secrets["client_email"],
        "client_id": secrets["client_id"],
        "auth_uri": secrets["auth_uri"],
        "token_uri": secrets["token_uri"],
        "auth_provider_x509_cert_url": secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": secrets["client_x509_cert_url"],
        "universe_domain": secrets["universe_domain"],
    }
    
    # Otorisasi gspread client
    client = gspread.service_account_from_dict(gcp_credentials)
    return client
    
# Inisialisasi client dan ambil ID sheet sekali
gs_client = get_gspread_client()
spreadsheet_id = st.secrets["connections"]["gsheets"]["spreadsheet_id"]


# ===========================
# Fungsi untuk Load Data (MODIFIKASI FINAL)
# ===========================
@st.cache_data(ttl=600)
def get_data(sheet_id, worksheet_name): # <-- HANYA MENGGUNAKAN ARGUMEN HASHABLE
    """Memuat data dari Google Sheet. Membuat DataFrame kosong jika error."""
    try:
        # Panggil client yang sudah di-cache
        client = get_gspread_client() 
        ss = client.open_by_key(sheet_id)
        ws = ss.worksheet(worksheet_name)
        
        df = pd.DataFrame(ws.get_all_records())
        df = df.dropna(how='all') 
        
        # Logika memastikan kolom tanggal berupa datetime
        if 'TANGGAL_CATATAN' in df.columns: 
            df['TANGGAL_CATATAN'] = pd.to_datetime(df['TANGGAL_CATATAN'], errors='coerce')
        elif 'TANGGAL' in df.columns: 
            df['TANGGAL'] = pd.to_datetime(df['TANGGAL'], errors='coerce')
        elif 'TANGGAL_CEKLIST' in df.columns: 
            df['TANGGAL_CEKLIST'] = pd.to_datetime(df['TANGGAL_CEKLIST'], errors='coerce')
            
        return df
    except Exception as e:
        st.error(f"Gagal mengambil data dari Google Sheets. Pastikan 'spreadsheet_id' dan nama sheet benar. Error: {e}")
        return pd.DataFrame()

# ===========================
# Fungsi untuk Save Data (MODIFIKASI FINAL DENGAN GSPREAD)
# ===========================
def save_data(df_to_save, sheet_name):
    """Menyimpan (mengganti) DataFrame ke sheet tertentu dalam Google Sheet menggunakan gspread."""
    try:
        client = get_gspread_client()
        ss = client.open_by_key(spreadsheet_id)
        ws = ss.worksheet(sheet_name)

        # Hapus data yang ada (termasuk header)
        ws.clear()
        
        # Tulis DataFrame ke worksheet (membutuhkan library gspread-dataframe)
        set_with_dataframe(ws, df_to_save, include_index=False)
        return True
    except Exception as e:
        st.error(f"Error saat menyimpan data ke Google Sheets: {e}")
        return False

# Panggilan data utama (untuk digunakan di seluruh aplikasi)
df = get_data(spreadsheet_id, data_sheet)

# ===========================
# Fungsi menghitung VSWR
# ===========================
def hitung_vswr(power_output, reflected):
    if reflected == 0:
        return 1.0
    if reflected >= power_output:
        return float("inf")
    gamma = (reflected / power_output) ** 0.5
    return round((1 + gamma) / (1 - gamma), 2)

# ===========================
# Mapping Ceklist Harian Digital (Deskripsi + Rekomendasi)
# ===========================
# ... (ceklist_rules Anda di sini - terlalu panjang untuk disalin, tetapi asumsikan ada di kode Anda)

ceklist_rules = {
    "Transmitter (Exciter & PA)": {
        "Normal": {
            "deskripsi": "Daya output stabil, suhu normal, tidak ada alarm",
            "rekom": "Tidak ada tindakan, kondisi transmitter normal"
        },
        "Warning": {
            "deskripsi": "Daya output menurun, suhu meningkat",
            "rekom": "Periksa pendingin udara, bersihkan filter, pantau daya output"
        },
        "Trouble": {
            "deskripsi": "Daya output turun drastis, suhu overheat",
            "rekom": "Periksa exciter/PA, lakukan kalibrasi RF, panggil teknisi servis"
        }
    },
    "Antena": {
        "Normal": {
            "deskripsi": "VSWR normal, sinyal stabil, kondisi fisik antena baik",
            "rekom": "Tidak ada tindakan, kondisi antena baik"
        },
        "Warning": {
            "deskripsi": "VSWR meningkat, mulai terjadi pantulan daya — indikasi konektor longgar atau feeder mulai menurun kualitasnya",
            "rekom": "Periksa dan kencangkan konektor, bersihkan jalur feeder, pastikan tidak ada korosi atau kelembapan pada konektor"
        },
        "Trouble": {
            "deskripsi": "VSWR tinggi, sinyal tidak stabil atau hilang — kemungkinan antena retak, bocor air, atau feeder rusak",
            "rekom": "Ganti feeder/antena, lakukan perbaikan fisik segera"
        }
    },
    "Encoder": {
        "Normal": {
            "deskripsi": "Bitrate stabil, output normal",
            "rekom": "Tidak ada tindakan, encoder berfungsi baik"
        },
        "Warning": {
            "deskripsi": "Bitrate turun 10–20%, terjadi delay atau patah-patah pada video output",
            "rekom": "Restart encoder, cek software dan jaringan"
        },
        "Trouble": {
            "deskripsi": "Output encoder tidak ada (blank)",
            "rekom": "Cek hardware encoder, ganti unit jika rusak"
        }
    },
        "IRD (Integrated Receiver Decoder)": {
        "Normal": {
            "deskripsi": "Sinyal input dan output video/audio normal",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Kualitas sinyal menurun, kadang terjadi glitch pada video/audio",
            "rekom": "Periksa level sinyal input, cek konektor dan kabel, pastikan suhu perangkat stabil atau tidak terlalu panas"
        },
        "Trouble": {
            "deskripsi": "Tidak ada sinyal, video/audio tidak keluar",
            "rekom": "Cek sumber input RF atau IP, reboot IRD, dan pastikan konfigurasi parameter input sesuai"
        }
    },
    "Multiplexer": {
        "Normal": {
            "deskripsi": "Semua input-output terbaca normal dan bitrate stabil",
            "rekom": "Tidak ada tindakan, kondisi MUX baik"
        },
        "Warning": {
            "deskripsi": "Input sesekali hilang atau bitrate turun",
            "rekom": "Restart MUX, cek port input/output"
        },
        "Trouble": {
            "deskripsi": "Input tidak terbaca sama sekali, ada indikator lampu merah menyala",
            "rekom": "Servis MUX, cek perangkat keras & software, cek kabel inputan, IRD dan encoder"
        }
    },
    "Parabola + LNB": {
        "Normal": {
            "deskripsi": "Arah parabola tepat, sinyal kuat, LNB dalam kondisi baik",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Arah parabola bergeser, sinyal melemah",
            "rekom": "Atur ulang arah parabola, cek dan kencangkan konektor LNB"
        },
        "Trouble": {
            "deskripsi": "Tidak ada sinyal sama sekali",
            "rekom": "Ganti LNB, periksa kabel feeder, atur ulang pointing parabola"
        }
    },
    "AVR": {
        "Normal": {
            "deskripsi": "Tegangan output stabil",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Tegangan naik turun ringan",
            "rekom": "Periksa setting AVR, pendinginan, sambungan kabel"
        },
        "Trouble": {
            "deskripsi": "Tegangan fluktuasi besar, tidak stabil",
            "rekom": "Servis AVR, ganti komponen internal jika perlu"
        }
    },
    "Grounding": {
        "Normal": {
            "deskripsi": "Resistansi < 5 Ohm, kabel & rod rapi, sistem grounding baik, mampu mengalirkan arus petir dan gangguan listrik dengan aman",
            "rekom": "Tidak ada tindakan, ukur resistensi berkala terutama saat musim hujan"
        },
        "Warning": {
            "deskripsi": "Resistansi 5–7 Ohm, efektifitas penyaluran arus petir mulai menurun — potensi sambaran petir tidak sepenuhnya tersalur ke tanah, ada korosi di sambungan",
            "rekom": "Tambah atau perbaiki rod grounding, periksa sambungan kabel ground dan pastikan tidak berkarat"
        },
        "Trouble": {
            "deskripsi": "Resistansi > 7 Ohm,  proteksi petir tidak berfungsi — arus petir berpotensi merusak peralatan transmisi",
            "rekom": "Perbaiki jalur ground, pasang rod tambahan, ganti kabel/rod rusak, dan lakukan pengujian resistansi tanah setelah perbaikan"
        }
    },
    "Cooling System": {
        "Normal": {
            "deskripsi": "Semua kipas normal, hembusan angin kuat",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Putaran kipas melemah atau bising",
            "rekom": "Bersihkan kipas, cek bearing, cek kabel listrik"
        },
        "Trouble": {
            "deskripsi": "Kipas mati total",
            "rekom": "Ganti kipas baru, cek suplai listrik"
        }
    },
    "AC Ruangan Transmisi": {
        "Normal": {
            "deskripsi": "Suhu ruangan 18–24°C stabil",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Suhu 25–26°C",
            "rekom": "Bersihkan filter AC, periksa freon"
        },
        "Trouble": {
            "deskripsi": "AC mati/tidak dingin, suhu >27°C ",
            "rekom": "Isi freon, servis AC, periksa kompresor dan kapasitor, ganti unit"
        }
    },
    "UPS": {
        "Normal": {
            "deskripsi": "Backup normal, baterai bagus, tidak ada alarm",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Backup singkat, alarm indikator berbunyi",
            "rekom": "Periksa aki, bersihkan ventilasi UPS, pastikan suhu ruangan tidak panas"
        },
        "Trouble": {
            "deskripsi": "Tidak ada backup sama sekali saat listrik padam",
            "rekom": "Ganti aki, servis UPS"
        }
    },
    "Genset": {
        "Normal": {
            "deskripsi": "Mesin hidup normal, beban stabil, bahan bakar cukup",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Mesin sulit dinyalakan, bahan bakar hampir habis",
            "rekom": "Cek aki starter, isi bahan bakar, bersihkah / ganti filter"
        },
        "Trouble": {
            "deskripsi": "Mesin tidak hidup/drop",
            "rekom": "Servis genset, ganti oli, filter, atau aki"
        }
    },
    "Router": {
        "Normal": {
            "deskripsi": "Koneksi internet lancar dan stabil",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Koneksi internet melambat",
            "rekom": "Restart router, cek kabel LAN/fiber"
        },
        "Trouble": {
            "deskripsi": "Tidak ada koneksi internet",
            "rekom": "Ganti router atau hubungi ISP"
        }
    },
    "Switch Hub": {
        "Normal": {
            "deskripsi": "Semua port aktif, koneksi lancar",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Satu atau beberapa port mati/tidak berfungsi",
            "rekom": "Gunakan port cadangan atau ganti port rusak"
        },
        "Trouble": {
            "deskripsi": "Semua port mati, perangkat tidak menyala",
            "rekom": "Ganti switch hub, cek power supply"
        }
    },
    "Multiviewer": {
        "Normal": {
            "deskripsi": "Semua channel tampil normal di monitor",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Beberapa channel hilang atau delay",
            "rekom": "Restart sistem, cek input/output matrix"
        },
        "Trouble": {
            "deskripsi": "Semua channel blank",
            "rekom": "Servis atau ganti multiviewer"
        }
    },
    "Set Top Box": {
        "Normal": {
            "deskripsi": "Channel terkunci normal, gambar dan suara lancar",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Channel sulit terkunci, sinyal melemah",
            "rekom": "Scan ulang channel, reset STB"
        },
        "Trouble": {
            "deskripsi": "Tidak bisa lock channel sama sekali",
            "rekom": "Ganti STB atau periksa antena"
        }
    },
    "RCS (Remote Control System)": {
        "Normal": {
            "deskripsi": "Sistem remote berjalan normal, semua perangkat terpantau",
            "rekom": "Tidak ada tindakan"
        },
        "Warning": {
            "deskripsi": "Respon lambat, data kadang delay",
            "rekom": "Cek jaringan dan software RCS"
        },
        "Trouble": {
            "deskripsi": "Tidak bisa remote/monitoring mati total",
            "rekom": "Cek hardware/software RCS, restart server"
        }
    }
}
# ... (Akhir ceklist_rules)

# ===========================
# Background Image Function & Styling
# ===========================
def apply_background_and_style():
    """Mengaplikasikan background image dan styling ke seluruh aplikasi."""
    background_image = "TVRI JAMBI.jpg"

    if os.path.exists(background_image):
        def get_base64_of_image(image_file):
            with open(image_file, "rb") as f:
                return base64.b64encode(f.read()).decode()

        bg_b64 = get_base64_of_image(background_image)
        
        overlay_opacity = '0.15' if not st.session_state['logged_in'] else '0.4'

        css = f"""
        <style>
        /* background image pada seluruh aplikasi */
        .stApp {{
            position: relative;
            min-height: 100vh;
            background-image: url("data:image/jpg;base64,{bg_b64}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}

        /* overlay putih semi-transparan agar teks hitam kontras */
        .stApp::before {{
            content: "";
            position: absolute;
            inset: 0;
            background: rgba(255,255,255,{overlay_opacity}); 
            z-index: 0;
            pointer-events: none;
        }}

        /* Pastikan konten aplikasi berada di atas overlay */
        [data-testid="stAppViewContainer"] > .main {{
            position: relative;
            z-index: 1;
            color: #000 !important;
        }}

        /* Semua teks dibuat tebal dan berwarna hitam */
        h1, h2, h3, h4, h5, h6,
        p, span, label, div, a, strong, em,
        .stMarkdown, .stExpander, .stButton, .stMetric {{
            color: #000 !important;
            font-weight: 700 !important;
            text-shadow: none !important;
        }}

        /* Pastikan widget input & label terlihat */
        .stTextInput, .stNumberInput, .stSelectbox, .stDateInput, .stTextArea {{
            color: #000 !important;
            font-weight: 700 !important;
        }}
        
        /* 🔑 CSS KHUSUS UNTUK FORM LOGIN (agar di tengah dan kecil) */
        /* Hanya form dengan ID 'Login' yang akan terpengaruh */
        .stApp form[data-testid="stForm"]#Login-target {{
            padding: 2rem;
            border: 2px solid #ccc;
            border-radius: 10px;
            background-color: rgba(255, 255, 255, 0.95); /* Box semi-transparan putih */
            max-width: 400px; /* Batasi lebar hanya untuk form login */
            margin: 100px auto; /* Pusatkan form login */
        }}
        
        /* Tombol utama tetap terlihat (sesuaikan bila perlu) */
        .stButton > button {{
            background-color: #0057B8 !important;
            color: white !important;
            font-weight: 700 !important;
            border-radius: 8px !important;
            width: 100%;
        }}

        /* Tombol di aplikasi utama/sidebar menggunakan lebar default streamlit (tidak full-width) */
        /* Override width: 100% untuk tombol yang bukan di form login */
        .stApp [data-testid="stForm"] .stButton > button,
        .stApp [data-testid="stSidebar"] .stButton > button,
        .stApp .stButton > button {{ /* Perluas scope ke semua st.button */
            width: auto !important;
            min-width: 100px;
        }}
        
        /* Sidebar tetap putih dan diatas overlay */
        [data-testid="stSidebar"] > div:first-child {{
            background: rgba(255,255,255,0.95) !important;
            color: #000 !important;
            position: relative;
            z-index: 2;
        }}

        /* Table / dataframe teks */
        .stDataFrame div {{
            color: #000 !important;
            font-weight: 700 !important;
        }}
        
        /* ======================================= */
        /* CSS KHUSUS UNTUK COLORING CEKLIST HARIAN (Background Selected Pill) */
        /* PEWARNAAN KHUSUS UNTUK NORMAL/WARNING/TROUBLE DIHAPUS SESUAI PERMINTAAN USER */
        /* ======================================= */
        
        /* Teks default (saat tidak dipilih) tetap hitam seperti styling global, 
           dan font tetap tebal */
        [data-testid="stRadio"] label div {{
            color: #000 !important; 
            font-weight: 700 !important; 
        }}
        
        /* Mengatur agar saat dipilih, latar belakangnya menggunakan warna netral Streamlit default, 
           dan teks tetap hitam */
        [data-testid="stRadio"] input:checked + div {{
            background-color: rgba(0, 87, 184, 0.2) !important; /* Default light blue/neutral */
            color: #000 !important; /* Pastikan teks tetap hitam */
        }}
        
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)
    else:
        st.error(f"Gambar latar 'TVRI JAMBI.jpg' tidak ditemukan. Pastikan file berada di folder yang sama.")

# ===========================
# Fungsi Halaman Login
# ===========================
def login_form():
    """Menampilkan form login sederhana."""
    apply_background_and_style() 

    st.markdown("<div style='text-align: center;'><h1>📡 Login Monitoring Metering MUX TVRI Jambi</h1></div>", unsafe_allow_html=True)
    
    with st.form("Login"):
        st.subheader("Masukkan Username dan Password")
        st.markdown("<div id='login-container'>", unsafe_allow_html=True) 
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_button = st.form_submit_button("Masuk")
        st.markdown("</div>", unsafe_allow_html=True) 

        if login_button:
            if username == "admin" and password == "admin123":
                st.session_state['logged_in'] = True
                st.rerun()
            else:
                st.error("❌ Username atau Password salah!")
                
    st.stop()

# ===========================
# Fungsi Halaman Aplikasi (Pengganti Tab 1)
# ===========================
def show_input_kalkulator():
    st.title("📝 Input Data & Kalkulator")
    
    st.subheader("🧮 Kalkulator VSWR")
    colk1, colk2 = st.columns(2)
    calc_power = colk1.number_input("Power Output (Watt)", min_value=0, step=1, key="calc_power")
    calc_reflected = colk2.number_input("Reflected (Watt)", min_value=0, step=1, key="calc_reflected")

    if st.button("🔢 Hitung VSWR"):
        # PASTIKAN FUNGSI hitung_vswr SUDAH ADA DI GLOBAL SCOPE
        vswr_calc = hitung_vswr(calc_power, calc_reflected)
        if vswr_calc == float("inf"):
            st.error("⚠️ Reflected ≥ Power Output → VSWR tak terhingga!")
        else:
            st.info(f"Hasil perhitungan VSWR: **{vswr_calc}**")

    # ======================
    # RULES PARAMETER (LOKAL DI DALAM FUNGSI)
    # ======================
    rules_param = {
        "Power Output (Watt)": [
            {"min": 10000, "max": 11900, "status": "Normal",
             "rekom": "Output sesuai standar, tidak perlu tindakan",
             "keterangan": "Daya pemancar dalam batas aman dan sesuai standar operasional."},
            {"min": 8000, "max": 9999, "status": "Warning",
             "rekom": "Catat penurunan, cek beban pemancar",
             "keterangan": "Terjadi sedikit penurunan daya, namun masih dalam batas toleransi aman."},
            {"min": 0, "max": 7999, "status": "Trouble",
             "rekom": "Jika drop: periksa exciter, amplifier, kabel RF",
             "keterangan": "Daya terlalu rendah, berpotensi menyebabkan gangguan transmisi siaran."},
            {"min": 11901, "max": 20000, "status": "Trouble",
             "rekom": "Jika over: periksa setting & kalibrasi daya output",
             "keterangan": "Daya melebihi batas standar, berisiko merusak perangkat pemancar."}
        ],
        "VSWR": [
            {"min": 0, "max": 1.24, "status": "Normal",
             "rekom": "VSWR aman, tidak perlu tindakan",
             "keterangan": "Nilai VSWR stabil dan menunjukkan efisiensi pancaran optimal."},
            {"min": 1.25, "max": 1.30, "status": "Warning",
             "rekom": "Kencangkan konektor RF, cek feeder dan kondisi fisik antena",
             "keterangan": "Refleksi sinyal mulai meningkat, perlu pengecekan konektor dan antena."},
            {"min": 1.31, "max": 10.0, "status": "Trouble",
             "rekom": "Segera turunkan daya, periksa antena & feeder",
             "keterangan": "VSWR tinggi menandakan ketidaksesuaian impedansi, berpotensi merusak pemancar."}
        ],
        "C/N (dB)": [
            {"min": 40, "max": 50, "status": "Normal",
             "rekom": "Sinyal satelit sangat stabil, tidak perlu tindakan",
             "keterangan": "Kualitas sinyal satelit sangat baik dan stabil."},
            {"min": 30, "max": 39.9, "status": "Warning",
             "rekom": "Pantau sinyal, Pantau kondisi cuaca. Jika hujan, ini normal. Jika cuaca cerah, periksa konektor, kabel, dan arah dish.",
             "keterangan": "Kualitas sinyal menurun, kemungkinan akibat cuaca atau gangguan perangkat antena."},
            {"min": 0,  "max": 29.9, "status": "Trouble",
             "rekom": "Atur ulang parabola, cek LNB/dish, lakukan perbaikan segera, ganti kalau perlu",
             "keterangan": "Kualitas sinyal sangat buruk, berisiko menyebabkan hilangnya siaran."}
        ],
        "Margin (dB)": [
            {"min": 20, "max": 30, "status": "Normal",
             "rekom": "Link sangat aman, tidak perlu tindakan",
             "keterangan": "Koneksi link dalam kondisi optimal dan stabil."},
            {"min": 10, "max": 19.9, "status": "Warning",
             "rekom": "periksa konektor RF dan pastikan tidak ada halangan di jalur dish",
             "keterangan": "Margin mulai menurun, perlu pemeriksaan jalur transmisi."},
            {"min": 0,  "max": 9.9, "status": "Trouble",
             "rekom": "atur ulang dish, periksa LNB, dan cek kabel coaxial, pastikan tidak ada korosi atau konektor longgar.",
             "keterangan": "Margin sangat rendah, transmisi berpotensi tidak stabil."}
        ],
        "Tegangan Listrik (Volt)": [
            {"min": 215, "max": 225, "status": "Normal",
             "rekom": "Tegangan stabil, tidak perlu tindakan",
             "keterangan": "Suplai listrik dalam kondisi stabil dan sesuai standar operasional."},
            {"min": 210, "max": 214, "status": "Warning",
             "rekom": "Pantau voltase, hidupkan stabilizer bila perlu",
             "keterangan": "Tegangan sedikit menurun, masih dalam batas aman namun perlu pemantauan."},
            {"min": 226, "max": 230, "status": "Warning",
             "rekom": "Pantau voltase, hidupkan stabilizer bila perlu",
             "keterangan": "Tegangan sedikit tinggi, perlu pengawasan agar tidak naik berlebih."},
            {"min": 0, "max": 209, "status": "Trouble",
             "rekom": "Periksa suplai PLN/UPS, cek kabel distribusi, pakai genset jika darurat",
             "keterangan": "Tegangan terlalu rendah, dapat mengganggu kinerja peralatan elektronik."},
            {"min": 231, "max": 300, "status": "Trouble",
             "rekom": "Tegangan over. Periksa suplai PLN/UPS, cek kabel distribusi, pakai genset jika darurat",
             "keterangan": "Tegangan berlebih, berpotensi menyebabkan kerusakan pada perangkat."}
        ],
        "Suhu TX (°C)": [
            {"min": 0, "max": 15.9, "status": "Warning",
             "rekom": "Suhu terlalu dingin, pantau risiko embun atau lembap di peralatan, naikkan suhu ac/pendingin ruangan",
             "keterangan": "Suhu di bawah standar operasional, berisiko menyebabkan kondensasi pada komponen."},
            {"min": 16, "max": 20.9, "status": "Normal",
             "rekom": "Suhu normal, tidak perlu tindakan",
             "keterangan": "Suhu stabil dan aman untuk perangkat transmisi."},
            {"min": 21, "max": 25.9, "status": "Warning",
             "rekom": "Cek pendingin ruangan jika ada ac yang mati turunkan suhu, bersihkan filter AC",
             "keterangan": "Suhu sedikit tinggi, perlu pemantauan agar tidak meningkat lebih lanjut."},
            {"min": 26, "max": 100, "status": "Trouble",
             "rekom": "Segera servis AC / tambah pendingin ruangan",
             "keterangan": "Suhu terlalu tinggi, berpotensi menyebabkan overheating pada perangkat pemancar."}
        ]
    }

    # ==================================================
    # RULES BITRATE KANAL TV (LOKAL DI DALAM FUNGSI)
    # ==================================================
    rules_bitrate = {
        "Bitrate NET TV (Mbps)": [
            {"min": 0, "max": 0.99, "status": "Trouble",
             "rekom": "Laporkan ke pihak NET TV pusat untuk konfirmasi. Tidak dilakukan tindakan lokal sebelum instruksi diterima. Catat waktu dan durasi bitrate 0 Mbps.",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 1.0, "max": 1.49, "status": "Warning",
             "rekom": "Pantau kestabilan bitrate pada transcoder NET TV. Jika fluktuasi >10–15 menit, catat waktu kejadian dan laporkan ke pihak NET TV.",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 1.5, "max": 2.0, "status": "Normal",
             "rekom": "Tidak ada tindakan, bitrate stabil sesuai kontrak 2 Mbps. Tetap pantau kestabilan.",
             "keterangan": "Siaran NET TV berjalan normal dengan bitrate sesuai standar kontrak."}
        ],
        "Bitrate RTV (Mbps)": [
            {"min": 0, "max": 1.99, "status": "Trouble",
             "rekom": "Laporkan ke pihak RTV untuk pengecekan siaran. Tunda tindakan lokal sampai ada arahan resmi. Atau pantau jadwal Sun Outage",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 2.0, "max": 3.49, "status": "Warning",
             "rekom": "Pantau bitrate dari encoder RTV. Jika penurunan berulang, catat polanya dan informasikan ke RTV.",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 3.5, "max": 4.0, "status": "Normal",
             "rekom": "Tidak ada tindakan, bitrate stabil sesuai kontrak 4 Mbps. Tetap pantau kestabilan.",
             "keterangan": "Siaran RTV berjalan normal dengan bitrate sesuai standar kontrak."}
        ],
        "Bitrate JAMBI TV (Mbps)": [
            {"min": 0, "max": 0.99, "status": "Trouble",
             "rekom": "Laporkan ke pihak Jambi TV terkait penurunan bitrate. Tunggu konfirmasi sebelum tindakan teknis. Catat waktu & parameter jaringan.",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 1.0, "max": 1.49, "status": "Warning",
             "rekom": "Pantau output encoder Jambi TV dan koneksi IP ke MUX. Jika fluktuatif, laporkan ke pihak Jambi TV.",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 1.5, "max": 2.0, "status": "Normal",
             "rekom": "Tidak ada tindakan, bitrate stabil sesuai kontrak 2 Mbps. Tetap pantau kestabilan",
             "keterangan": "Siaran JAMBI TV berjalan normal dengan bitrate sesuai standar kontrak."}
        ],
        "Bitrate JEK TV (Mbps)": [
            {"min": 0, "max": 0.99, "status": "Trouble",
             "rekom": "Laporkan ke pihak JEK TV untuk pengecekan siaran. Tunda tindakan sampai ada arahan resmi. Atau pantau jadwal Sun Outage",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 1.0, "max": 1.49, "status": "Warning",
             "rekom": "Cek converter JEK TV. Jika hanya kanal ini turun, laporkan ke pihak RTV.",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 1.5, "max": 2.0, "status": "Normal",
             "rekom": "Bitrate stabil, tidak perlu maintenance. Lanjutkan pemantauan harian.",
             "keterangan": "Siaran JEK TV berjalan normal dengan bitrate sesuai standar kontrak."}
        ],
        "Bitrate SINPO TV (Mbps)": [
            {"min": 0, "max": 0.99, "status": "Trouble",
             "rekom": "Laporkan ke pihak SINPO TV . Tunda tindakan sampai ada arahan resmi. Atau pantau jadwal Sun Outage",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 1.0, "max": 1.49, "status": "Warning",
             "rekom": "Pantau fluktuasi bitrate SINPO TV. Jika tidak kembali normal dalam 10–15 menit, hubungi pihak SINPO.",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 1.5, "max": 2.0, "status": "Normal",
             "rekom": "Bitrate stabil, tidak perlu maintenance. Lanjutkan pemantauan harian",
             "keterangan": "Siaran SINPO TV berjalan normal dengan bitrate sesuai standar kontrak."}
        ],
        "Bitrate TVRI NASIONAL (Mbps)": [
            {"min": 0, "max": 1.99, "status": "Trouble",
             "rekom": "Jika bitrate 0 Mbps atau siaran hilang, cek IRD Harmonic dan lakukan Encrypt siaran. Jika tetap hilang, koordinasikan dengan TVRI pusat. Atau pantau jadwal Sun Outage",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 2.0, "max": 3.49, "status": "Warning",
             "rekom": "Pantau perubahan bitrate pada IRD, jika bitrate terus menurun dan tidak sesuai standar SLA maka lakukan pergantian perangkat .",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 3.5, "max": 4.0, "status": "Normal",
             "rekom": "Bitrate stabil, tidak perlu tindakan.",
             "keterangan": "Siaran TVRI NASIONAL berjalan normal dengan bitrate sesuai standar kontrak."}
        ],
        "Bitrate TVRI WORLD (Mbps)": [
            {"min": 0, "max": 1.99, "status": "Trouble",
             "rekom": "Jika bitrate 0 Mbps atau siaran hilang, cek IRD Harmonic dan lakukan Encrypt siaran. Jika tetap hilang, koordinasikan dengan TVRI pusat. Atau pantau jadwal Sun Outage",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 2.0, "max": 3.49, "status": "Warning",
             "rekom": "Pantau perubahan bitrate pada IRD, jika bitrate terus menurun dan tidak sesuai standar SLA maka lakukan pergantian perangkat.",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 3.5, "max": 4.0, "status": "Normal",
             "rekom": "Tidak ada masalah, jalur aman. Pantau jika ada event internasional besar.",
             "keterangan": "Siaran TVRI World berjalan lancar dan bitrate sesuai standar kontrak."}
        ],
        "Bitrate TVRI SPORT (Mbps)": [
            {"min": 0, "max": 1.99, "status": "Trouble",
             "rekom": "Jika bitrate 0 Mbps: (1) Cabut-pasang kartu encrypt IRD Ericsson. (2) Jika belum normal, pasang kabel LAN dari IRD ke pc lalu masuk ke sistem IRD menggunakan IP, lalu centang kolom Decrypt & Decode. Jika tetap gagal, hubungi TVRI pusat. Atau pantau jadwal Sun Outage",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 2.0, "max": 3.49, "status": "Warning",
             "rekom": "Pantau perubahan bitrate pada IRD, jika bitrate terus menurun dan tidak sesuai standar SLA maka lakukan pergantian perangkat",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 3.5, "max": 4.0, "status": "Normal",
             "rekom": "Kondisi baik, stream lancar. Tetap pantau bitrate saat live event.",
             "keterangan": "Siaran TVRI SPORT berjalan normal dengan bitrate sesuai standar kontrak."}
        ],
        "Bitrate TVRI JAMBI (Mbps)": [
            {"min": 0, "max": 1.99, "status": "Trouble",
             "rekom": "Jika bitrate 0 Mbps, cek sistem encoder (lihat status inputan masing-masing port yaitu SDI, HDMI, & CVBS. Kalau status inputan merah berarti tidak ada inputan, selanjutnya ganti ke port yang status nya hijau. Jika menggunakan IRD, restart IRD",
             "keterangan": "Bitrate hilang atau sangat rendah"},
            {"min": 2.0, "max": 3.49, "status": "Warning",
             "rekom": "Pantau perubahan bitrate pada encoder/IRD, jika bitrate terus menurun dan tidak sesuai standar SLA maka lakukan pergantian perangkat.",
             "keterangan": "Bitrate menurun dari standar, kemungkinan terjadi gangguan sementara."},
            {"min": 3.5, "max": 4.0, "status": "Normal",
             "rekom": "Normal, encoder/IRD dan MUX berfungsi baik. Tidak perlu tindakan.",
             "keterangan": "Siaran TVRI JAMBI berjalan normal dengan bitrate sesuai standar kontrak."}
        ],
    }
    
    # ==================================================
    # GABUNGKAN KEDUA DICTIONARY RULES MENJADI SATU
    # ==================================================
    rules_param.update(rules_bitrate)

    # ==================================================
    # FUNGSI PEMERIKSA PARAMETER (VERSI BARU - LOKAL)
    # ==================================================
    def cek_param(nama, nilai):
        """
        Mengecek status, keterangan, dan rekomendasi dari suatu parameter teknis
        berdasarkan nilai aktual dan rentang batas pada rules_param.
        Fungsi ini mengembalikan dictionary, bukan tuple.
        """
        if nama not in rules_param:
            return {
                "Parameter": nama,
                "Nilai": nilai,
                "Status": "N/A",
                "Keterangan": "Parameter tidak terdaftar dalam aturan pengukuran.",
                "Rekomendasi": "Periksa kembali nama parameter atau tambahkan ke rules_param."
            }

        for rule in rules_param[nama]:
            if rule["min"] <= nilai <= rule["max"]:
                hasil = {
                    "Parameter": nama,
                    "Nilai": nilai,
                    "Status": rule["status"],
                    "Keterangan": rule.get("keterangan", "Tidak ada keterangan."), # Pakai .get() agar aman
                    "Rekomendasi": rule.get("rekom", "Tidak ada rekomendasi.")
                }
                return hasil

        # Jika nilai tidak masuk rentang manapun
        return {
            "Parameter": nama,
            "Nilai": nilai,
            "Status": "N/A",
            "Keterangan": "Nilai di luar jangkauan aturan yang ditetapkan.",
            "Rekomendasi": "Periksa ulang input nilai atau tambahkan batas baru pada rules_param."
        }

    # ======================
    # FORM INPUT DATA
    # ======================
    with st.form("form_metering"):
        st.subheader("📝 Input Data Harian")
        
        col1_form, col2_form = st.columns(2)
        tanggal = col1_form.date_input("Tanggal")
        waktu_options = ["02:00", "06:00", "10:00", "14:00", "18:00", "22:00"]
        waktu = col2_form.selectbox("Waktu", waktu_options)

        # Perbaikan: min_value=0.0 untuk parameter yang bisa 0
        power_output = st.number_input("Power Output (Watt)", min_value=0, step=1)
        vswr_input = st.number_input("VSWR", min_value=0.0, step=0.01, format="%.2f", value=1.0)
        cn = st.number_input("C/N (dB)", min_value=0.0, step=0.01, format="%.2f", value=1.0)
        margin = st.number_input("Margin (dB)", min_value=0.0, step=0.01, format="%.2f", value=1.0)

        col3, col4, col5 = st.columns(3)
        teg_r = col3.number_input("Phase R", step=1, key="teg_r")
        teg_s = col4.number_input("Phase S", step=1, key="teg_s")
        teg_t = col5.number_input("Phase T", step=1, key="teg_t")

        suhu_tx = st.number_input("Suhu TX (°C)", min_value=0.0, step=0.01, format="%.2f", value=1.0)

        st.subheader("Status Channel TV & Bitrate")
        
        # Perbaikan: min_value=0.0 untuk semua bitrate
        st.markdown("#### NET TV")
        col_net_ok, col_net_bitrate = st.columns(2)
        net_tv = col_net_ok.selectbox("Status NET TV", ["OK", "NO"], key="net_tv_ok")
        bitrate_net = col_net_bitrate.number_input("Bitrate NET TV (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="net_tv_bitrate", value=1.0)
        
        st.markdown("#### RTV")
        col_rtv_ok, col_rtv_bitrate = st.columns(2)
        rtv = col_rtv_ok.selectbox("Status RTV", ["OK", "NO"], key="rtv_ok")
        bitrate_rtv = col_rtv_bitrate.number_input("Bitrate RTV (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="rtv_bitrate", value=1.0)
        
        st.markdown("#### JAMBI TV")
        col_jambi_ok, col_jambi_bitrate = st.columns(2)
        jambi_tv = col_jambi_ok.selectbox("Status JAMBI TV", ["OK", "NO"], key="jambi_tv_ok")
        bitrate_jambi = col_jambi_bitrate.number_input("Bitrate JAMBI TV (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="jambi_tv_bitrate", value=1.0)
        
        st.markdown("#### JEK TV")
        col_jek_ok, col_jek_bitrate = st.columns(2)
        jek_tv = col_jek_ok.selectbox("Status JEK TV", ["OK", "NO"], key="jek_tv_ok")
        bitrate_jek = col_jek_bitrate.number_input("Bitrate JEK TV (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="jek_tv_bitrate", value=1.0)
        
        st.markdown("#### SINPO TV")
        col_sinpo_ok, col_sinpo_bitrate = st.columns(2)
        sinpo_tv = col_sinpo_ok.selectbox("Status SINPO TV", ["OK", "NO"], key="sinpo_tv_ok")
        bitrate_sinpo = col_sinpo_bitrate.number_input("Bitrate SINPO TV (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="sinpo_tv_bitrate", value=1.0)
        
        st.markdown("#### TVRI NASIONAL")
        col_tvri_nasional_ok, col_tvri_nasional_bitrate = st.columns(2)
        tvri_nasional = col_tvri_nasional_ok.selectbox("Status TVRI NASIONAL", ["OK", "NO"], key="tvri_nasional_ok")
        bitrate_tvri_nasional = col_tvri_nasional_bitrate.number_input("Bitrate TVRI NASIONAL (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="tvri_nasional_bitrate", value=1.0)
        
        st.markdown("#### TVRI WORLD")
        col_tvri_world_ok, col_tvri_world_bitrate = st.columns(2)
        tvri_world = col_tvri_world_ok.selectbox("Status TVRI WORLD", ["OK", "NO"], key="tvri_world_ok")
        bitrate_tvri_world = col_tvri_world_bitrate.number_input("Bitrate TVRI WORLD (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="tvri_world_bitrate", value=1.0)
        
        st.markdown("#### TVRI SPORT")
        col_tvri_sport_ok, col_tvri_sport_bitrate = st.columns(2)
        tvri_sport = col_tvri_sport_ok.selectbox("Status TVRI SPORT", ["OK", "NO"], key="tvri_sport_ok")
        bitrate_tvri_sport = col_tvri_sport_bitrate.number_input("Bitrate TVRI SPORT (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="tvri_sport_bitrate", value=1.0)
        
        st.markdown("#### TVRI JAMBI")
        col_tvri_jambi_ok, col_tvri_jambi_bitrate = st.columns(2)
        tvri_jambi = col_tvri_jambi_ok.selectbox("Status TVRI JAMBI", ["OK", "NO"], key="tvri_jambi_ok")
        bitrate_tvri_jambi = col_tvri_jambi_bitrate.number_input("Bitrate TVRI JAMBI (Mbps)", min_value=0.0, step=0.01, format="%.2f", key="tvri_jambi_bitrate", value=1.0)
        
        kualitas_av = st.selectbox("Kualitas Audio / Video", ["A/V OK", "A/V NO"])
        operator = st.text_input("Operator")
        
        catatan = st.text_area(
            "Catatan/Keterangan",  
            placeholder="Isi catatan seperti 'Perbaiki ini', 'Semua normal', dll.", 
            height=100
        )

        lihat_rekom = st.form_submit_button("🔍 Lihat Rekomendasi")
        simpan_data = st.form_submit_button("✅ Simpan Data") 

    # ======================
    # ANALISIS OTOMATIS (PERBAIKAN ERROR)
    # ======================
    if lihat_rekom or simpan_data:
        data_analisis = [] # Ini akan menjadi list of dictionaries
        
        # --- PERBAIKAN: Panggil cek_param dan langsung append dictionary-nya ---
        data_analisis.append(cek_param("Power Output (Watt)", power_output))
        data_analisis.append(cek_param("VSWR", vswr_input))
        data_analisis.append(cek_param("C/N (dB)", cn))
        data_analisis.append(cek_param("Margin (dB)", margin))

        # --- PERBAIKAN: Penanganan khusus untuk Tegangan R, S, T ---
        hasil_teg_r = cek_param("Tegangan Listrik (Volt)", teg_r)
        hasil_teg_r["Parameter"] = "Tegangan R (Volt)" # Ganti nama parameter
        data_analisis.append(hasil_teg_r)
        
        hasil_teg_s = cek_param("Tegangan Listrik (Volt)", teg_s)
        hasil_teg_s["Parameter"] = "Tegangan S (Volt)" # Ganti nama parameter
        data_analisis.append(hasil_teg_s)
        
        hasil_teg_t = cek_param("Tegangan Listrik (Volt)", teg_t)
        hasil_teg_t["Parameter"] = "Tegangan T (Volt)" # Ganti nama parameter
        data_analisis.append(hasil_teg_t)
        
        data_analisis.append(cek_param("Suhu TX (°C)", suhu_tx))
        
        # --- Memanggil cek_param dengan key spesifik per channel ---
        data_analisis.append(cek_param("Bitrate NET TV (Mbps)", bitrate_net))
        data_analisis.append(cek_param("Bitrate RTV (Mbps)", bitrate_rtv))
        data_analisis.append(cek_param("Bitrate JAMBI TV (Mbps)", bitrate_jambi))
        data_analisis.append(cek_param("Bitrate JEK TV (Mbps)", bitrate_jek))
        data_analisis.append(cek_param("Bitrate SINPO TV (Mbps)", bitrate_sinpo))
        data_analisis.append(cek_param("Bitrate TVRI NASIONAL (Mbps)", bitrate_tvri_nasional))
        data_analisis.append(cek_param("Bitrate TVRI WORLD (Mbps)", bitrate_tvri_world))
        data_analisis.append(cek_param("Bitrate TVRI SPORT (Mbps)", bitrate_tvri_sport))
        data_analisis.append(cek_param("Bitrate TVRI JAMBI (Mbps)", bitrate_tvri_jambi))
        
        # --- PERBAIKAN: Buat DataFrame dari list of dictionaries ---
        df_rekom = pd.DataFrame(data_analisis)
        
        # Ganti nama kolom 'Nilai' (dari cek_param) menjadi 'Nilai Input'
        df_rekom = df_rekom.rename(columns={"Nilai": "Nilai Input"})
        
        # Tentukan urutan kolom yang ingin ditampilkan
        kolom_tampil = ["Parameter", "Nilai Input", "Status", "Keterangan", "Rekomendasi"]
        
        # Filter agar hanya kolom yang ada di df_rekom yang ditampilkan (mencegah error)
        kolom_valid = [kol for kol in kolom_tampil if kol in df_rekom.columns]
        
        st.subheader("📊 Analisa & Rekomendasi Maintenance")
        # Tampilkan dataframe dengan kolom yang sudah diurutkan dan valid
        st.dataframe(df_rekom[kolom_valid], use_container_width=True)

        # ======================
        # SIMPAN DATA JIKA DIPILIH
        # ======================
        if simpan_data:
            data_input = {
                "TANGGAL": pd.to_datetime(tanggal).strftime("%Y-%m-%d"),
                "WAKTU": waktu,
                "POWER OUTPUT (WATT)": power_output,
                "VSWR": vswr_input,
                "C/N (dB)": cn,
                "MARGIN (dB)": margin,
                "TEGANGAN LISTRIK R (Volt)": teg_r,
                "TEGANGAN LISTRIK S (Volt)": teg_s,
                "TEGANGAN LISTRIK T (Volt)": teg_t,
                "SUHU TX": suhu_tx,
                "NET TV": net_tv, "Bitrate NET TV": bitrate_net,
                "RTV": rtv, "Bitrate RTV": bitrate_rtv,
                "JAMBI TV": jambi_tv, "Bitrate JAMBI TV": bitrate_jambi,
                "JEK TV": jek_tv, "Bitrate JEK TV": bitrate_jek,
                "SINPO TV": sinpo_tv, "Bitrate SINPO TV": bitrate_sinpo,
                "TVRI NASIONAL": tvri_nasional, "Bitrate TVRI NASIONAL": bitrate_tvri_nasional,
                "TVRI WORLD": tvri_world, "Bitrate TVRI WORLD": bitrate_tvri_world,
                "TVRI SPORT": tvri_sport, "Bitrate TVRI SPORT": bitrate_tvri_sport,
                "TVRI JAMBI": tvri_jambi, "Bitrate TVRI JAMBI": bitrate_tvri_jambi,
                "KUALITAS AUDIO / VIDEO": kualitas_av,
                "OPERATOR": operator,
                "CATATAN/KETERANGAN": catatan, 
            }

            # Menggunakan fungsi get_data() yang baru
            df_existing = get_data(spreadsheet_id, data_sheet) 
            
            if not df_existing.empty and 'TANGGAL' in df_existing.columns:
                 df_existing['TANGGAL'] = pd.to_datetime(df_existing['TANGGAL'], errors='coerce')

            df_new = pd.DataFrame([data_input])
            df_new['TANGGAL'] = pd.to_datetime(df_new['TANGGAL'])

            if df_existing.empty:
                df_all = df_new
            else:
                # Periksa apakah kolom DUP_CHECK ada sebelum mengaksesnya
                if 'TANGGAL' in df_existing.columns and 'WAKTU' in df_existing.columns:
                    df_existing['DUP_CHECK'] = df_existing['TANGGAL'].dt.strftime('%Y-%m-%d') + '_' + df_existing['WAKTU'].astype(str)
                else:
                    df_existing['DUP_CHECK'] = None # Buat kolom kosong jika TANGGAL/WAKTU tidak ada
                    
                df_new['DUP_CHECK'] = df_new['TANGGAL'].dt.strftime('%Y-%m-%d') + '_' + df_new['WAKTU'].astype(str)
                
                df_existing_filtered = df_existing[~df_existing['DUP_CHECK'].isin(df_new['DUP_CHECK'])]
                df_all = pd.concat([df_existing_filtered.drop(columns=['DUP_CHECK'], errors='ignore'), df_new.drop(columns=['DUP_CHECK'], errors='ignore')], ignore_index=True)

            if 'TANGGAL' in df_all.columns:
                 df_all['TANGGAL'] = pd.to_datetime(df_all['TANGGAL']).dt.strftime('%Y-%m-%d')

            # Menyimpan data metering ke Google Sheet
            if save_data(df_all, data_sheet):
                st.success(f"✅ Data berhasil ditambahkan ke Google Sheet **{data_sheet}**!")
# ===========================
# Fungsi Halaman Visualisasi (Pengganti Tab 2)
# ===========================
def show_visualisasi_data():
    st.title("📊 Visualisasi Data")
    
    # PANGGILAN BARU: Menggunakan get_data() yang sudah di-cache
    df_viz = get_data(spreadsheet_id, data_sheet) 
    
    if df_viz.empty:
        st.info("⚠️ Belum ada data. Silakan input dulu di menu **Input Data & Kalkulator**.")
        return 
    
    try:
        df_viz["TANGGAL"] = pd.to_datetime(df_viz["TANGGAL"])
        df_viz["DATETIME"] = pd.to_datetime(df_viz["TANGGAL"].astype(str) + " " + df_viz["WAKTU"].astype(str), errors="coerce")
        df_viz = df_viz.dropna(subset=["DATETIME"]).sort_values("DATETIME")
        
        # ... (Sisa logika visualisasi menggunakan df_viz)
        
        df_group = pd.DataFrame() # Initialize

        st.subheader("Grafik Tren Parameter")
        opsi_agregasi = st.radio("Pilih Periode Visualisasi:", ["Harian", "Bulan"], horizontal=True) 

        # Filter sesuai opsi
        if opsi_agregasi == "Harian":
            if not df_viz.empty:
                max_date_data = df_viz["TANGGAL"].max().date()
                default_date = max_date_data if not df_viz.empty else datetime.date.today()
                
                pilih_tanggal = st.date_input(
                    "Pilih Tanggal", 
                    value=default_date, 
                    min_value=df_viz["TANGGAL"].min().date(),
                    max_value=max_date_data
                )
                
                df_group = df_viz[df_viz["TANGGAL"].dt.date == pilih_tanggal]
            else:
                st.info("Tidak ada data untuk ditampilkan.")

        else:  # Rentang Tanggal
            st.write("Pilih rentang tanggal untuk visualisasi.")
            
            if not df_viz.empty:
                min_date = df_viz["TANGGAL"].min().date()
                max_date = df_viz["TANGGAL"].max().date()

                col_start, col_end = st.columns(2)
                
                start_date = col_start.date_input(
                    "Tanggal Awal (Start Date)", 
                    value=min_date, 
                    min_value=min_date, 
                    max_value=max_date,
                    key="viz_start_date" 
                )
                
                end_date = col_end.date_input(
                    "Tanggal Akhir (End Date)", 
                    value=max_date,
                    min_value=min_date,
                    max_value=max_date,
                    key="viz_end_date" 
                )

                if start_date > end_date:
                    st.error("Tanggal Awal tidak boleh setelah Tanggal Akhir.")
                    df_group = pd.DataFrame() 
                else:
                    start_datetime = pd.to_datetime(start_date)
                    end_datetime_exclusive = pd.to_datetime(end_date) + pd.Timedelta(days=1)
                    
                    df_group = df_viz[(df_viz["DATETIME"] >= start_datetime) & (df_viz["DATETIME"] < end_datetime_exclusive)].copy()
            else:
                st.info("Tidak ada data untuk ditampilkan.")

        parameter = st.multiselect(
            "Pilih Parameter untuk Ditampilkan:",
            ["POWER OUTPUT (WATT)", "VSWR", "C/N (dB)", "MARGIN (dB)",
                "TEGANGAN LISTRIK R (Volt)", "TEGANGAN LISTRIK S (Volt)",
                "TEGANGAN LISTRIK T (Volt)", "SUHU TX"],
            default=["POWER OUTPUT (WATT)", "VSWR"]
        )

        if parameter and not df_group.empty:
            fig, ax = plt.subplots(figsize=(12, 5))

            if opsi_agregasi == "Harian":
                if len(df_group) <= 1:
                     for col in parameter:
                        ax.plot(df_group["DATETIME"], df_group[col], 'o-', label=col)
                else:
                    for col in parameter:
                        ax.plot(df_group["DATETIME"], df_group[col], 'o-', label=col)
                
                if len(df_group["DATETIME"]) > 0:
                    ax.set_xticks(df_group["DATETIME"])
                    ax.set_xticklabels(df_group["DATETIME"].dt.strftime("%H:%M"), rotation=45)
                ax.set_xlabel("Jam")

            else:  # Rentang Tanggal
                for col in parameter:
                    ax.plot(df_group["DATETIME"], df_group[col], marker="o", label=col)
                ax.set_xlabel("Tanggal dan Waktu")

            ax.set_ylabel("Nilai")
            ax.set_title(f"Grafik Parameter Transmisi ({opsi_agregasi})")
            ax.legend()
            ax.grid(True)
            plt.tight_layout()
            st.pyplot(fig)

        elif parameter and df_group.empty:
            st.warning("⚠️ Tidak ada data untuk rentang yang dipilih.")
        
        # Data Tersimpan + Pilihan Tampilan
        st.subheader("📑 Data Tersimpan (Metering)")

        df_display = df_viz.sort_values(by="DATETIME", ascending=False).drop(columns=['DATETIME'], errors='ignore').copy()

        if 'TANGGAL' in df_display.columns:
            df_display['TANGGAL'] = df_display['TANGGAL'].dt.strftime('%Y-%m-%d')

        opsi_tampilan = st.selectbox("Tampilkan berapa baris terakhir?", ["5", "10", "100", "Semua"], index=0)

        if opsi_tampilan == "5":
            st.dataframe(df_display.head(5), use_container_width=True)
        elif opsi_tampilan == "10":
            st.dataframe(df_display.head(10), use_container_width=True)
        elif opsi_tampilan == "100":
            st.dataframe(df_display.head(100), use_container_width=True)
        else:
            st.dataframe(df_display, use_container_width=True)

        # Download Data (Filter per Rentang Tanggal)
        st.subheader("📥 Download Data (Metering)")
        st.write("Pilih rentang tanggal untuk data yang ingin diunduh.")

        min_date_dl = df_viz["TANGGAL"].min().date()
        max_date_dl = df_viz["TANGGAL"].max().date()

        col_start_dl, col_end_dl = st.columns(2)

        start_date_dl = col_start_dl.date_input(
            "Tanggal Awal Download", 
            value=min_date_dl, 
            min_value=min_date_dl, 
            max_value=max_date_dl,
            key="dl_start_date"
        )

        end_date_dl = col_end_dl.date_input(
            "Tanggal Akhir Download", 
            value=max_date_dl,
            min_value=min_date_dl,
            max_value=max_date_dl,
            key="dl_end_date"
        )
        
        df_download = df_viz.copy()

        if start_date_dl > end_date_dl:
            st.error("Tanggal Awal tidak boleh setelah Tanggal Akhir untuk proses download.")
            df_download = pd.DataFrame() 
        else:
            start_datetime_dl = pd.to_datetime(start_date_dl)
            end_datetime_exclusive_dl = pd.to_datetime(end_date_dl) + pd.Timedelta(days=1)
            
            df_download = df_viz[(df_viz["DATETIME"] >= start_datetime_dl) & (df_viz["DATETIME"] < end_datetime_exclusive_dl)].copy()

        df_download = df_download.drop(columns=['DATETIME'], errors='ignore')
        if 'TANGGAL' in df_download.columns:
            df_download['TANGGAL'] = df_download['TANGGAL'].dt.strftime('%Y-%m-%d')

        if not df_download.empty:
            buffer = BytesIO()
            df_download.to_excel(buffer, index=False) 
            buffer.seek(0)

            st.download_button(
                label="⬇️ Download Data (Excel)",
                data=buffer,
                file_name=f"metering_{start_date_dl}_to_{end_date_dl}.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Pilih rentang tanggal yang valid atau pastikan ada data dalam rentang tersebut untuk mengunduh.")

    except Exception as e:
        st.info("⚠️ Belum ada data. Silakan input dulu di menu **Input Data & Kalkulator**.")


# ===========================
# Fungsi Halaman Ceklist (Pengganti Tab 3)
# *VERSI DENGAN CARD PUTIH UNTUK DESKRIPSI & REKOMENDASI*
# ===========================

def show_ceklist_harian():
    st.title("✅ Ceklist Harian Digital")
    st.write("Pilih kondisi tiap parameter.")
    
    HOUR_OPTIONS = ['Shift 1: 00.00 - 08.00', 'Shift 2: 08:00 - 16.00', 'Shift 3: 16:00 - 00.00']

    # --- Definisikan Kolom Final untuk Konsistensi Data ---
    FINAL_COLUMNS = [
        "TANGGAL_CEKLIST",
        "JAM_CEKLIST",
        "OPERATOR_CEKLIST"
    ]
    for param in ceklist_rules.keys():
        FINAL_COLUMNS.append(f"{param}_KONDISI")
        FINAL_COLUMNS.append(f"{param}_REKOMENDASI")

    # --- INPUT HEADER (Date, Jam, Operator) ---
    st.subheader("Informasi Catatan")
    col_date, col_hour, col_op = st.columns([1, 1, 1])
    
    with col_date:
        tanggal_catatan = st.date_input("Tanggal", key="date_note_input", value=datetime.date.today())
    with col_hour:
        jam_catatan = st.selectbox("Jam", HOUR_OPTIONS, key="hour_note_input")
    with col_op:
        operator_catatan = st.text_input("Operator", key="operator_note_input")
        
    st.markdown("---")
    
    # --- CHECKLIST ITEMS (OUTSIDE FORM FOR INSTANT UPDATE) ---
    st.subheader("Pilihan Kondisi Perangkat")
    hasil_ceklist = {}
    
    for param, kondisi in ceklist_rules.items():
        st.markdown(f"**{param}**")
        
        if f"ceklist_{param}" not in st.session_state:
            st.session_state[f"ceklist_{param}"] = "Normal"
            
        pilihan = st.radio(
            f"Kondisi {param}", 
            ["Normal", "Warning", "Trouble"], 
            horizontal=True, 
            key=f"ceklist_{param}",
            label_visibility="collapsed"
        )
        
        deskripsi = kondisi[pilihan]['deskripsi']
        rekomendasi = kondisi[pilihan]['rekom']

        # === CARD PUTIH UNTUK DESKRIPSI SETIAP PARAMETER ===
        st.markdown(
            f"""
            <div style="
                background-color: rgba(255, 255, 255, 0.85);
                padding: 10px 15px;
                border-radius: 10px;
                margin-top: 5px;
                margin-bottom: 10px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                border: 1px solid rgba(200,200,200,0.4);
            ">
                <b>📌 {deskripsi}</b><br>
                <small><i>{rekomendasi}</i></small>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        hasil_ceklist[param] = {
            "Kondisi": pilihan,
            "Deskripsi": deskripsi,
            "Rekomendasi": rekomendasi
        }

    # --- ACTION BUTTONS ---
    col_rekom, col_simpan = st.columns(2)
    lihat_rekom = col_rekom.button("📋 Tampilkan Rekomendasi")
    simpan_catatan = col_simpan.button("💾 Simpan Catatan Harian")

    if lihat_rekom:
    # Card besar putih solid
        st.markdown(
        """
        <div style="
            background-color: #ffffff;
            padding: 25px 40px;
            border-radius: 16px;
            margin-top: 20px;
            margin-bottom: 25px;
            box-shadow: 0 6px 15px rgba(0,0,0,0.25);
            border: 1px solid rgba(220,220,220,0.8);
        ">
            <h3 style="text-align:center; margin-bottom:25px; color:#222;">
                🛠️ Rekomendasi Maintenance
            </h3>
        """,
        unsafe_allow_html=True
    )

    # tampilkan tiap item
    for p, data in hasil_ceklist.items():
        # warna tulisan sesuai status
        if data["Kondisi"] == "Normal":
            color = "#1b1b1b"
        elif data["Kondisi"] == "Warning":
            color = "#c99500"
        else:
            color = "#c0392b"

        st.markdown(
            f"""
            <div style="
                margin:8px 0;
                padding:6px 10px;
                background-color: rgba(245,245,245,0.9);
                border-radius: 6px;
                border-left: 4px solid {color};
                color:#000;
                line-height:1.5;
            ">
                <b style="color:{color};">{p} ({data['Kondisi']}):</b> {data['Rekomendasi']}
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)

    if simpan_catatan:
        data_simpan_horizontal = {
            "TANGGAL_CEKLIST": [pd.to_datetime(tanggal_catatan).strftime("%Y-%m-%d")],
            "JAM_CEKLIST": [jam_catatan],
            "OPERATOR_CEKLIST": [operator_catatan],
        }
        
        for param, data in hasil_ceklist.items():
            kondisi_key = f"{param}_KONDISI"
            rekom_key = f"{param}_REKOMENDASI"
            
            data_simpan_horizontal[kondisi_key] = [data["Kondisi"]]
            data_simpan_horizontal[rekom_key] = [data["Rekomendasi"]] 

        df_new_notes = pd.DataFrame(data_simpan_horizontal)
        df_new_notes = df_new_notes.reindex(columns=FINAL_COLUMNS, fill_value=None)
        
        # PANGGILAN BARU: Menggunakan get_data() yang sudah di-cache
        df_existing_notes = get_data(spreadsheet_id, notes_sheet)
        
        if not df_existing_notes.empty and 'TANGGAL_CEKLIST' in df_existing_notes.columns:
             df_existing_notes['TANGGAL_CEKLIST'] = pd.to_datetime(df_existing_notes['TANGGAL_CEKLIST'], errors='coerce').dt.strftime('%Y-%m-%d')
        
        if not df_existing_notes.empty:
             df_existing_notes = df_existing_notes.reindex(columns=FINAL_COLUMNS, fill_value=None)
             df_all_notes = pd.concat([df_existing_notes, df_new_notes], ignore_index=True)
        else:
             df_all_notes = df_new_notes

        # Simpan DataFrame gabungan ke Google Sheet 'CATATAN_HARIAN'
        if save_data(df_all_notes, notes_sheet):
            st.success(f"✅ Catatan harian berhasil disimpan ke Google Sheet **{notes_sheet}**!")

    # --- Tampilkan Data Catatan Harian ---
    st.subheader("📑 Data Tersimpan (Catatan Harian)")
    df_notes_display = get_data(spreadsheet_id, notes_sheet) # PANGGILAN BARU

    if df_notes_display.empty:
        st.info("Belum ada catatan harian yang tersimpan.")
    else:
        if 'TANGGAL_CEKLIST' in df_notes_display.columns:
            df_notes_display['TANGGAL_CEKLIST'] = pd.to_datetime(df_notes_display['TANGGAL_CEKLIST'], errors='coerce')
        
        if 'TANGGAL_CEKLIST' in df_notes_display.columns and 'JAM_CEKLIST' in df_notes_display.columns:
            
            df_notes_display['TANGGAL_WAKTU'] = df_notes_display['TANGGAL_CEKLIST'].dt.strftime('%Y-%m-%d') + ' ' + df_notes_display['JAM_CEKLIST'].astype(str).str.split(':').str[0]
            df_notes_display['TANGGAL_WAKTU'] = pd.to_datetime(df_notes_display['TANGGAL_WAKTU'], errors='coerce')
            
            df_notes_display = df_notes_display.sort_values(by='TANGGAL_WAKTU', ascending=False)
        
        if 'TANGGAL_CEKLIST' in df_notes_display.columns:
            df_notes_display['TANGGAL_CEKLIST'] = df_notes_display['TANGGAL_CEKLIST'].dt.strftime('%Y-%m-%d')
        
        cols_to_drop = ['TANGGAL_WAKTU'] 
        df_notes_display = df_notes_display.drop(columns=cols_to_drop, errors='ignore')
        
        st.dataframe(df_notes_display, use_container_width=True)

    # --- Download Data Catatan Harian ---
    if not df_notes_display.empty:
        st.subheader("📥 Download Data (Catatan Harian)")
        buffer_notes = BytesIO()
        
        df_notes_download = df_notes_display.copy()
        
        df_notes_download.to_excel(buffer_notes, index=False)
        buffer_notes.seek(0)

        st.download_button(
            label="⬇️ Download Catatan Harian (Excel)",
            data=buffer_notes,
            file_name="catatan_harian_mux_tvri.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# ===========================
# CEK STATUS LOGIN SEBELUM START APLIKASI
# ===========================
if not st.session_state['logged_in']:
    login_form()

# ===========================
# EKSEKUSI APLIKASI UTAMA (Hanya berjalan setelah Login)
# ===========================
if st.session_state['logged_in']:
    
    apply_background_and_style() 

    st.markdown("<h1 style='text-align: center;'>📡 Monitoring Metering MUX Transmisi Telanaipura TVRI Stasiun Jambi</h1>", unsafe_allow_html=True)
    
    st.sidebar.title("Menu Utama")
    
    if 'current_page' not in st.session_state:
        st.session_state['current_page'] = "📝 Input Data & Kalkulator"
        
    page_options = ["📝 Input Data & Kalkulator", "📊 Visualisasi Data", "✅ Ceklist Harian Digital"]
    
    page = st.sidebar.selectbox(
        "Pilih Halaman:",
        page_options,
        index=page_options.index(st.session_state['current_page']),
        key='sidebar_page_select'
    )
    
    st.session_state['current_page'] = page 

    if st.sidebar.button("🚪 Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    if page == "📝 Input Data & Kalkulator":
        show_input_kalkulator()
    elif page == "📊 Visualisasi Data":
        show_visualisasi_data()
    elif page == "✅ Ceklist Harian Digital":
        show_ceklist_harian()















