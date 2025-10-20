import pandas as pd
import os
import streamlit as st
import matplotlib.pyplot as plt
from io import BytesIO
import datetime 
import base64 # Diperlukan untuk background image

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
# Nama file Excel & Sheet Catatan
# ===========================
data_file = "metering_mux.xlsx"
notes_sheet = "CATATAN_HARIAN" 

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
# Fungsi untuk Load Data 
# ===========================
@st.cache_data(ttl=600) # FIX 1: Tambahkan caching untuk konsistensi di deployment
def load_data(sheet_name):
    """Memuat data dari file Excel, sheet tertentu. Membuat DataFrame kosong jika error."""
    if os.path.exists(data_file):
        try:
            # Menggunakan pd.ExcelFile untuk mengecek ketersediaan sheet
            xls = pd.ExcelFile(data_file)
            if sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                # Pastikan kolom tanggal berupa datetime
                if 'TANGGAL_CATATAN' in df.columns: # Menggunakan nama kolom yang spesifik untuk sheet catatan
                    df['TANGGAL_CATATAN'] = pd.to_datetime(df['TANGGAL_CATATAN'], errors='coerce')
                elif 'TANGGAL' in df.columns: # Untuk sheet data metering
                    df['TANGGAL'] = pd.to_datetime(df['TANGGAL'], errors='coerce')
                elif 'TANGGAL_CEKLIST' in df.columns: # Untuk sheet ceklist harian
                    df['TANGGAL_CEKLIST'] = pd.to_datetime(df['TANGGAL_CEKLIST'], errors='coerce')
                    
                return df.dropna(how='all') # Hapus baris kosong
            else:
                return pd.DataFrame() # Jika sheet belum ada
        except Exception as e:
            # st.error(f"Error saat memuat data dari sheet {sheet_name}: {e}")
            return pd.DataFrame() # Kembalikan DataFrame kosong jika ada error
    return pd.DataFrame()

# ===========================
# Fungsi untuk Save Data 
# ===========================
def save_data(df, sheet_name):
    """Menyimpan DataFrame ke sheet tertentu dalam file Excel."""
    
    # Hapus cache lama agar data yang baru tersimpan langsung terlihat setelah save
    if 'load_data' in globals():
        load_data.clear()
        
    try:
        # Muat semua sheet yang ada, kecuali sheet yang akan diupdate
        sheets_data = {}
        if os.path.exists(data_file):
            xls = pd.ExcelFile(data_file)
            for name in xls.sheet_names:
                if name != sheet_name:
                    sheets_data[name] = pd.read_excel(xls, sheet_name=name)

        # Gunakan ExcelWriter untuk menyimpan/memperbarui
        with pd.ExcelWriter(data_file, engine='openpyxl') as writer:
            # Simpan data yang sedang diupdate
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Simpan kembali data sheet lain yang tidak diupdate
            for name, existing_df in sheets_data.items():
                existing_df.to_excel(writer, sheet_name=name, index=False)
                
    except Exception as e:
        st.error(f"Error saat menyimpan data ke Excel: {e}")

# ===========================
# Mapping Ceklist Harian Digital (Deskripsi + Rekomendasi)
# ===========================
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
            "deskripsi": "Input tidak terbaca sama sekali",
            "rekom": "Servis MUX, cek perangkat keras & software"
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
        
        # Opacity lebih tinggi (lebih buram) saat belum login, lebih rendah saat sudah masuk.
        overlay_opacity = '0.15' if not st.session_state['logged_in'] else '0.25'

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
        # Jika gambar tidak ditemukan, biarkan background default
        st.error(f"Gambar latar 'TVRI JAMBI.jpg' tidak ditemukan. Pastikan file berada di folder yang sama.")

# ===========================
# Fungsi Halaman Login
# ===========================
def login_form():
    """Menampilkan form login sederhana."""
    # Panggil style di sini agar CSS login aktif
    apply_background_and_style() 

    # Layout di tengah
    st.markdown("<div style='text-align: center;'><h1>📡 Login Monitoring MUX TVRI Jambi</h1></div>", unsafe_allow_html=True)
    
    # Form login. Pastikan ID form ini sesuai dengan selector CSS: "Login-target"
    with st.form("Login"):
        st.subheader("Masukkan Username dan Password")
        # Masukkan div agar input form login tetap terlihat di atas background (jika ada)
        st.markdown("<div id='login-container'>", unsafe_allow_html=True) 
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_button = st.form_submit_button("Masuk")
        st.markdown("</div>", unsafe_allow_html=True) 

        if login_button:
            # Autentikasi: Username dan Password "admin"
            if username == "admin" and password == "admin":
                st.session_state['logged_in'] = True
                st.rerun() # Refresh untuk menampilkan aplikasi utama
            else:
                st.error("❌ Username atau Password salah!")
                
    st.stop() # Hentikan eksekusi di sini jika belum login

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
        vswr_calc = hitung_vswr(calc_power, calc_reflected)
        if vswr_calc == float("inf"):
            st.error("⚠️ Reflected ≥ Power Output → VSWR tak terhingga!")
        else:
            st.info(f"Hasil perhitungan VSWR: **{vswr_calc}**")

    # ======================
    # RULES PARAMETER
    # ======================
    rules_param = {
        "Power Output (Watt)": [
            {"min": 10000, "max": 11900, "status": "Normal", "rekom": "Output sesuai standar"},
            {"min": 8000, "max": 9999, "status": "Warning", "rekom": "Catat penurunan, cek beban pemancar"},
            {"min": 0, "max": 7999, "status": "Trouble", "rekom": "Jika drop: periksa exciter, amplifier, kabel RF"},
            {"min": 11901, "max": 20000, "status": "Trouble", "rekom": "Jika over: periksa setting & kalibrasi daya output"}
        ],
        "VSWR": [
            {"min": 0, "max": 1.24, "status": "Normal", "rekom": "VSWR aman"},
            {"min": 1.25, "max": 1.30, "status": "Warning", "rekom": "Kencangkan konektor, cek feeder dan kondisi fisik antena"},
            {"min": 1.31, "max": 10.0, "status": "Trouble", "rekom": "Segera turunkan daya, periksa antena & feeder"}
        ],
        "C/N (dB)": [
            {"min": 40, "max": 50, "status": "Normal", "rekom": "Sinyal satelit sangat stabil, tidak perlu tindakan"},
            {"min": 30, "max": 39.9, "status": "Warning", "rekom": "Pantau sinyal, cek kabel/konektor"},
            {"min": 0,  "max": 29.9, "status": "Trouble", "rekom": "Atur ulang parabola, cek LNB/dish, lakukan perbaikan segera, ganti kalau perlu"}
        ],
        "Margin (dB)": [
            {"min": 20, "max": 30, "status": "Normal", "rekom": "Link sangat aman, tidak perlu tindakan"},
            {"min": 10, "max": 19.9, "status": "Warning", "rekom": "periksa konektor RF dan pastikan tidak ada halangan di jalur dish"},
            {"min": 0,  "max": 9.9, "status": "Trouble", "rekom": "atur ulang dish, periksa LNB, dan cek kabel coaxial"}
        ],
        "Tegangan Listrik (Volt)": [
            {"min": 215, "max": 225, "status": "Normal", "rekom": "Tegangan stabil"},
            {"min": 210, "max": 214, "status": "Warning", "rekom": "Pantau voltase, hidupkan stabilizer bila perlu"},
            {"min": 226, "max": 230, "status": "Warning", "rekom": "Pantau voltase, hidupkan stabilizer bila perlu"},
            {"min": 0, "max": 209, "status": "Trouble", "rekom": "Periksa suplai PLN/UPS, cek kabel distribusi, pakai genset jika darurat"},
            {"min": 231, "max": 300, "status": "Trouble", "rekom": "Periksa suplai PLN/UPS, cek kabel distribusi, pakai genset jika darurat"}
        ],
        "Suhu TX (°C)": [
            {"min": 17, "max": 20.9, "status": "Normal", "rekom": "Suhu normal"},
            {"min": 21, "max": 25.9, "status": "Warning", "rekom": "Cek pendingin, bersihkan filter AC"},
            {"min": 26, "max": 100, "status": "Trouble", "rekom": "Segera servis AC / tambah pendingin"}
        ]
    }

    # Fungsi cek status
    def cek_param(nama, nilai):
        for rule in rules_param[nama]:
            if rule["min"] <= nilai <= rule["max"]:
                return rule["status"], rule["rekom"]
        return "N/A", "Tidak ada rekomendasi"

    # ======================
    # FORM INPUT DATA
    # ======================
    with st.form("form_metering"):
        st.subheader("📝 Input Data Harian")
        
        # --- Input Tanggal dan Waktu (Lebar Penuh) ---
        col1_form, col2_form = st.columns(2)
        tanggal = col1_form.date_input("Tanggal")
        waktu_options = ["02:00", "06:00", "10:00", "14:00", "18:00", "22:00"]
        waktu = col2_form.selectbox("Waktu", waktu_options)

        # --- Input Parameter Utama (Lebar penuh) ---
        power_output = st.number_input("Power Output (Watt)", min_value=0, step=1)
        vswr_input = st.number_input("VSWR", min_value=1.0, step=0.01, format="%.2f")
        cn = st.number_input("C/N (dB)", min_value=1.0, step=0.01, format="%.2f")
        margin = st.number_input("Margin (dB)", min_value=1.0, step=0.01, format="%.2f")

        # --- Input Tegangan Listrik (3 kolom) ---
        col3, col4, col5 = st.columns(3)
        teg_r = col3.number_input("Phase R", step=1, key="teg_r")
        teg_s = col4.number_input("Phase S", step=1, key="teg_s")
        teg_t = col5.number_input("Phase T", step=1, key="teg_t")

        suhu_tx = st.number_input("Suhu TX (°C)", min_value=1.0, step=0.01, format="%.2f")

        # --- Input TV & Bitrate (Menggunakan 2 kolom Sama Rata) ---
        st.subheader("Status Channel TV & Bitrate")
        
        # Group 1: NET TV
        st.markdown("#### NET TV")
        col_net_ok, col_net_bitrate = st.columns(2)
        net_tv = col_net_ok.selectbox("Status NET TV", ["OK", "NO"], key="net_tv_ok")
        bitrate_net = col_net_bitrate.number_input("Bitrate NET TV (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="net_tv_bitrate")
        
        # Group 2: RTV
        st.markdown("#### RTV")
        col_rtv_ok, col_rtv_bitrate = st.columns(2)
        rtv = col_rtv_ok.selectbox("Status RTV", ["OK", "NO"], key="rtv_ok")
        bitrate_rtv = col_rtv_bitrate.number_input("Bitrate RTV (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="rtv_bitrate")
        
        
        # Group 3: JAMBI TV
        st.markdown("#### JAMBI TV")
        col_jambi_ok, col_jambi_bitrate = st.columns(2)
        jambi_tv = col_jambi_ok.selectbox("Status JAMBI TV", ["OK", "NO"], key="jambi_tv_ok")
        bitrate_jambi = col_jambi_bitrate.number_input("Bitrate JAMBI TV (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="jambi_tv_bitrate")
        
        
        # Group 4: JEK TV
        st.markdown("#### JEK TV")
        col_jek_ok, col_jek_bitrate = st.columns(2)
        jek_tv = col_jek_ok.selectbox("Status JEK TV", ["OK", "NO"], key="jek_tv_ok")
        bitrate_jek = col_jek_bitrate.number_input("Bitrate JEK TV (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="jek_tv_bitrate")
        
        
        # Group 5: SINPO TV
        st.markdown("#### SINPO TV")
        col_sinpo_ok, col_sinpo_bitrate = st.columns(2)
        sinpo_tv = col_sinpo_ok.selectbox("Status SINPO TV", ["OK", "NO"], key="sinpo_tv_ok")
        bitrate_sinpo = col_sinpo_bitrate.number_input("Bitrate SINPO TV (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="sinpo_tv_bitrate")
        
        
        # Group 6: TVRI NASIONAL
        st.markdown("#### TVRI NASIONAL")
        col_tvri_nasional_ok, col_tvri_nasional_bitrate = st.columns(2)
        tvri_nasional = col_tvri_nasional_ok.selectbox("Status TVRI NASIONAL", ["OK", "NO"], key="tvri_nasional_ok")
        bitrate_tvri_nasional = col_tvri_nasional_bitrate.number_input("Bitrate TVRI NASIONAL (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="tvri_nasional_bitrate")
        
        
        # Group 7: TVRI WORLD
        st.markdown("#### TVRI WORLD")
        col_tvri_world_ok, col_tvri_world_bitrate = st.columns(2)
        tvri_world = col_tvri_world_ok.selectbox("Status TVRI WORLD", ["OK", "NO"], key="tvri_world_ok")
        bitrate_tvri_world = col_tvri_world_bitrate.number_input("Bitrate TVRI WORLD (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="tvri_world_bitrate")
        
        
        # Group 8: TVRI SPORT
        st.markdown("#### TVRI SPORT")
        col_tvri_sport_ok, col_tvri_sport_bitrate = st.columns(2)
        tvri_sport = col_tvri_sport_ok.selectbox("Status TVRI SPORT", ["OK", "NO"], key="tvri_sport_ok")
        bitrate_tvri_sport = col_tvri_sport_bitrate.number_input("Bitrate TVRI SPORT (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="tvri_sport_bitrate")
        
        
        # Group 9: TVRI JAMBI
        st.markdown("#### TVRI JAMBI")
        col_tvri_jambi_ok, col_tvri_jambi_bitrate = st.columns(2)
        tvri_jambi = col_tvri_jambi_ok.selectbox("Status TVRI JAMBI", ["OK", "NO"], key="tvri_jambi_ok")
        bitrate_tvri_jambi = col_tvri_jambi_bitrate.number_input("Bitrate TVRI JAMBI (Mbps)", min_value=1.0, step=0.01, format="%.2f", key="tvri_jambi_bitrate")
        

        # --- Kualitas A/V, Operator, Catatan (Lebar Penuh) ---
        kualitas_av = st.selectbox("Kualitas Audio / Video", ["A/V OK", "A/V NO"])
        operator = st.text_input("Operator")
        
        # 📝 CATATAN
        catatan = st.text_area(
            "Catatan/Keterangan",  # Label
            placeholder="Isi catatan seperti 'Perbaiki ini', 'Semua normal', dll.", 
            height=100
        )
        # -----------------------

        # 🔘 Tombol aksi
        lihat_rekom = st.form_submit_button("🔍 Lihat Rekomendasi")
        simpan_data = st.form_submit_button("✅ Simpan Data") 

    # ======================
    # ANALISIS OTOMATIS
    # ======================
    if lihat_rekom or simpan_data:
        # 🔹 Analisa otomatis parameter
        data_analisis = []
        data_analisis.append(["Power Output (Watt)", power_output, *cek_param("Power Output (Watt)", power_output)])
        data_analisis.append(["VSWR", vswr_input, *cek_param("VSWR", vswr_input)])
        data_analisis.append(["C/N (dB)", cn, *cek_param("C/N (dB)", cn)])
        data_analisis.append(["Margin (dB)", margin, *cek_param("Margin (dB)", margin)])
        data_analisis.append(["Tegangan R (Volt)", teg_r, *cek_param("Tegangan Listrik (Volt)", teg_r)])
        data_analisis.append(["Tegangan S (Volt)", teg_s, *cek_param("Tegangan Listrik (Volt)", teg_s)])
        data_analisis.append(["Tegangan T (Volt)", teg_t, *cek_param("Tegangan Listrik (Volt)", teg_t)])
        data_analisis.append(["Suhu TX (°C)", suhu_tx, *cek_param("Suhu TX (°C)", suhu_tx)])

        df_rekom = pd.DataFrame(data_analisis, columns=["Parameter", "Nilai Input", "Status", "Rekomendasi"])

        st.subheader("📊 Analisa & Rekomendasi Maintenance")
        st.dataframe(df_rekom, use_container_width=True)

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

            # Menggunakan load_data untuk data metering (sheet default)
            df_existing = load_data('Sheet1') 
            if df_existing.empty:
                df_all = pd.DataFrame([data_input])
            else:
                # Cek apakah ada baris duplikat (tanggal + waktu) sebelum concat
                df_new = pd.DataFrame([data_input])
                df_existing['DUP_CHECK'] = df_existing['TANGGAL'].astype(str) + '_' + df_existing['WAKTU'].astype(str)
                df_new['DUP_CHECK'] = df_new['TANGGAL'].astype(str) + '_' + df_new['WAKTU'].astype(str)
                
                # Filter data yang sudah ada yang tidak sama dengan data baru
                df_existing_filtered = df_existing[~df_existing['DUP_CHECK'].isin(df_new['DUP_CHECK'])]
                df_all = pd.concat([df_existing_filtered.drop(columns=['DUP_CHECK'], errors='ignore'), df_new.drop(columns=['DUP_CHECK'], errors='ignore')], ignore_index=True)

            # Menyimpan data metering ke sheet pertama (default: Sheet1)
            try:
                save_data(df_all, 'Sheet1')
                st.success("✅ Data berhasil ditambahkan ke Metering!")
            except Exception as e:
                st.error(f"Gagal menyimpan data ke Excel: {e}")

# ===========================
# Fungsi Halaman Visualisasi (Pengganti Tab 2)
# ===========================
def show_visualisasi_data():
    st.title("📊 Visualisasi Data")
    
    # FIX 2: Ganti pembacaan file langsung dengan fungsi load_data yang sudah di-cache
    df = load_data('Sheet1') 
    
    # Jika DataFrame kosong, berikan info dan hentikan eksekusi
    if df.empty:
        st.info("⚠️ Belum ada data. Silakan input dulu di menu Input Data & Kalkulator.")
        return # Tambahkan return agar kode visualisasi di bawah tidak dieksekusi

    # Lanjutkan ke pemrosesan data dan visualisasi
    
    # Format datetime
    df["TANGGAL"] = pd.to_datetime(df["TANGGAL"])
    df["DATETIME"] = pd.to_datetime(df["TANGGAL"].astype(str) + " " + df["WAKTU"].astype(str), errors="coerce")
    df = df.dropna(subset=["DATETIME"]).sort_values("DATETIME")
    
    # Inisialisasi df_group sebagai DataFrame kosong
    df_group = pd.DataFrame()

    st.subheader("Grafik Tren Parameter")
    opsi_agregasi = st.radio("Pilih Periode Visualisasi:", ["Harian", "Bulan"], horizontal=True) 

    # Filter sesuai opsi
    if opsi_agregasi == "Harian":
        if not df.empty:
            default_date = df["TANGGAL"].max().date() if not df.empty else datetime.date.today()
            pilih_tanggal = st.date_input("Pilih Tanggal", value=default_date, max_value=df["TANGGAL"].max().date())
            df_group = df[df["TANGGAL"].dt.date == pilih_tanggal]
        else:
            st.info("Tidak ada data untuk ditampilkan.")

    else:  # Rentang Tanggal
        st.write("Pilih rentang tanggal untuk visualisasi.")
        
        if not df.empty:
            min_date = df["TANGGAL"].min().date()
            max_date = df["TANGGAL"].max().date()

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

            # Logika filter rentang tanggal
            if start_date > end_date:
                st.error("Tanggal Awal tidak boleh setelah Tanggal Akhir.")
                df_group = pd.DataFrame() 
            else:
                start_datetime = pd.to_datetime(start_date)
                end_datetime_exclusive = pd.to_datetime(end_date) + pd.Timedelta(days=1)
                
                df_group = df[(df["DATETIME"] >= start_datetime) & (df["DATETIME"] < end_datetime_exclusive)].copy()
        else:
            st.info("Tidak ada data untuk ditampilkan.")

    # 🔹 Parameter
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
            for col in parameter:
                ax.scatter(df_group["DATETIME"], df_group[col], label=col)
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
    
    # ===========================
    # Data Tersimpan + Pilihan Tampilan
    # ===========================
    st.subheader("📑 Data Tersimpan (Metering)")

    opsi_tampilan = st.selectbox("Tampilkan berapa baris terakhir?", ["5", "10", "100", "Semua"], index=0)

    if opsi_tampilan == "5":
        st.dataframe(df.tail(5), use_container_width=True)
    elif opsi_tampilan == "10":
        st.dataframe(df.tail(10), use_container_width=True)
    elif opsi_tampilan == "100":
        st.dataframe(df.tail(100), use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)

    # ===========================
    # Download Data (Filter per Rentang Tanggal)
    # ===========================
    st.subheader("📥 Download Data (Metering)")
    st.write("Pilih rentang tanggal untuk data yang ingin diunduh.")

    min_date_dl = df["TANGGAL"].min().date()
    max_date_dl = df["TANGGAL"].max().date()

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
    
    df_download = df.copy()

    if start_date_dl > end_date_dl:
        st.error("Tanggal Awal tidak boleh setelah Tanggal Akhir untuk proses download.")
        df_download = pd.DataFrame() 
    else:
        start_datetime_dl = pd.to_datetime(start_date_dl)
        end_datetime_exclusive_dl = pd.to_datetime(end_date_dl) + pd.Timedelta(days=1)
        
        df_download = df[(df["DATETIME"] >= start_datetime_dl) & (df["DATETIME"] < end_datetime_exclusive_dl)].copy()

    # Drop kolom DATETIME sebelum download
    df_download = df_download.drop(columns=['DATETIME'], errors='ignore')

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


# ===========================
# Fungsi Halaman Ceklist (Pengganti Tab 3)
# *PERUBAHAN: MENGHAPUS FUNGSI PEWARNAAN STATUS DAN MERAPATKAN JARAK*
# ===========================

def show_ceklist_harian():
    st.title("✅ Ceklist Harian Digital")
    st.write("Pilih kondisi tiap parameter.")
    
    HOUR_OPTIONS = ['Shift 1: 00.00 - 08.00', 'Shift 2: 08:00 - 16.00', 'Shift 3: 16:00-00.00']

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
        # Teks parameter dibuat menonjol
        st.markdown(f"**{param}**")
        
        # Inisialisasi default state (penting untuk st.radio di luar form)
        if f"ceklist_{param}" not in st.session_state:
            st.session_state[f"ceklist_{param}"] = "Normal"
            
        # Widget st.radio akan me-rerun script saat diubah
        pilihan = st.radio(
            f"Kondisi {param}", 
            ["Normal", "Warning", "Trouble"], 
            horizontal=True, 
            key=f"ceklist_{param}", # Key menyimpan state di session_state
            label_visibility="collapsed"
        )
        
        # Tampilkan deskripsi kondisi langsung tanpa warna
        deskripsi = kondisi[pilihan]['deskripsi']
        rekomendasi = kondisi[pilihan]['rekom']
        
        # Menggunakan st.markdown dengan teks tebal (hitam)
        st.markdown(f"**📌 {deskripsi}**")
        
        # simpan hasil lengkap ke hasil_ceklist (menggunakan nilai yang baru dari widget)
        hasil_ceklist[param] = {
            "Kondisi": pilihan,
            "Deskripsi": deskripsi,
            "Rekomendasi": rekomendasi
        }
        # st.markdown("---") # Garis pemisah dihapus untuk merapatkan jarak

    # --- ACTION BUTTONS (Standard Buttons for Logic) ---
    col_rekom, col_simpan = st.columns(2)
    
    # Tombol Aksi - Tidak menggunakan st.form_submit_button lagi
    lihat_rekom = col_rekom.button("📋 Tampilkan Rekomendasi")
    simpan_catatan = col_simpan.button("💾 Simpan Catatan Harian")

    # --- Tampilkan Rekomendasi (Opsional) ---
    if lihat_rekom:
        st.subheader("🛠️ Rekomendasi Maintenance")
        for p, data in hasil_ceklist.items():
            # Tampilkan rekomendasi tanpa warna
            st.markdown(f"**{p} ({data['Kondisi']}):** {data['Rekomendasi']}")

    # --- Simpan Data ke Excel Sheet Catatan ---
    if simpan_catatan:
        # Data dasar untuk 1 baris (Horizontal)
        data_simpan_horizontal = {
            "TANGGAL_CEKLIST": [pd.to_datetime(tanggal_catatan).strftime("%Y-%m-%d")],
            "JAM_CEKLIST": [jam_catatan],
            "OPERATOR_CEKLIST": [operator_catatan],
        }
        
        # 1. PIVOT DATA: Konversi hasil ceklist menjadi kolom horizontal
        for param, data in hasil_ceklist.items():
            kondisi_key = f"{param}_KONDISI"
            rekom_key = f"{param}_REKOMENDASI"
            
            data_simpan_horizontal[kondisi_key] = [data["Kondisi"]]
            data_simpan_horizontal[rekom_key] = [data["Rekomendasi"]] 

        df_new_notes = pd.DataFrame(data_simpan_horizontal)
        
        # 2. Re-index kolom DataFrame baru agar sesuai dengan FINAL_COLUMNS
        df_new_notes = df_new_notes.reindex(columns=FINAL_COLUMNS, fill_value=None)
        
        # Load data catatan yang sudah ada
        df_existing_notes = load_data(notes_sheet)
        
        # 3. GABUNGKAN
        if not df_existing_notes.empty:
             df_existing_notes = df_existing_notes.reindex(columns=FINAL_COLUMNS, fill_value=None)
             df_all_notes = pd.concat([df_existing_notes, df_new_notes], ignore_index=True)
        else:
             df_all_notes = df_new_notes

        # Simpan DataFrame gabungan ke sheet CATATAN_HARIAN
        try:
            save_data(df_all_notes, notes_sheet)
            st.success(f"✅ Catatan harian berhasil disimpan ke sheet **{notes_sheet}**!")
        except Exception as e:
            st.error(f"Gagal menyimpan catatan ke Excel: {e}")

    # ----------------------------------------------------
    # --- Tampilkan Data Catatan Harian ---
    # ----------------------------------------------------
    st.subheader("📑 Data Tersimpan (Catatan Harian)")
    df_notes_display = load_data(notes_sheet)

    if df_notes_display.empty:
        st.info("Belum ada catatan harian yang tersimpan.")
    else:
        # Konversi TANGGAL_CEKLIST ke tipe datetime
        if 'TANGGAL_CEKLIST' in df_notes_display.columns:
            df_notes_display['TANGGAL_CEKLIST'] = pd.to_datetime(df_notes_display['TANGGAL_CEKLIST'], errors='coerce')
        
        # Buat kolom gabungan TANGGAL_WAKTU untuk pengurutan
        if 'TANGGAL_CEKLIST' in df_notes_display.columns and 'JAM_CEKLIST' in df_notes_display.columns:
            
            df_notes_display['TANGGAL_WAKTU'] = df_notes_display['TANGGAL_CEKLIST'].dt.strftime('%Y-%m-%d') + ' ' + df_notes_display['JAM_CEKLIST'].astype(str)
            df_notes_display['TANGGAL_WAKTU'] = pd.to_datetime(df_notes_display['TANGGAL_WAKTU'], errors='coerce')
            
            # Urutkan berdasarkan TANGGAL_WAKTU terbaru
            df_notes_display = df_notes_display.sort_values(by='TANGGAL_WAKTU', ascending=False)
        
        # Format ulang TANGGAL_CEKLIST 
        if 'TANGGAL_CEKLIST' in df_notes_display.columns:
            df_notes_display['TANGGAL_CEKLIST'] = df_notes_display['TANGGAL_CEKLIST'].dt.strftime('%Y-%m-%d')
        
        # Drop kolom bantu (TANGGAL_WAKTU)
        cols_to_drop = ['TANGGAL_WAKTU'] 
        df_notes_display = df_notes_display.drop(columns=cols_to_drop, errors='ignore')
        
        # Tampilkan DataFrame
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
    
    # PERBAIKAN: Panggil style di sini agar background selalu ada di halaman utama
    apply_background_and_style() 

    # Judul utama di konten aplikasi
    st.markdown("<h1 style='text-align: center;'>📡 Monitoring Metering MUX Transmisi Telanaipura TVRI Stasiun Jambi</h1>", unsafe_allow_html=True)
    
    # === SIDEBAR UNTUK NAVIGASI ===
    st.sidebar.title("Menu Utama")
    
    # Default page selection
    if 'current_page' not in st.session_state:
        st.session_state['current_page'] = "📝 Input Data & Kalkulator"
        
    page_options = ["📝 Input Data & Kalkulator", "📊 Visualisasi Data", "✅ Ceklist Harian Digital"]
    
    # Gunakan session state untuk mempertahankan pilihan
    page = st.sidebar.selectbox(
        "Pilih Halaman:",
        page_options,
        index=page_options.index(st.session_state['current_page']),
        key='sidebar_page_select'
    )
    
    st.session_state['current_page'] = page # Update session state

    # === LOGOUT BUTTON ===
    if st.sidebar.button("🚪 Logout"):
        st.session_state['logged_in'] = False
        st.rerun()

    # === KONTEN UTAMA ===
    if page == "📝 Input Data & Kalkulator":
        show_input_kalkulator()
    elif page == "📊 Visualisasi Data":
        show_visualisasi_data()
    elif page == "✅ Ceklist Harian Digital":
        show_ceklist_harian()
