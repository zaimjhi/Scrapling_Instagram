import streamlit as st
import pandas as pd
import os
import subprocess
import time
import json
from datetime import datetime
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import plotly.express as px
from fpdf import FPDF
import asyncio

# Konfigurasi halaman web
st.set_page_config(page_title="Dashboard Scraping IG", page_icon="📊", layout="wide")

# ==========================================
# 0. SISTEM AUTENTIKASI & DATABASE AKUN
# ==========================================
FILE_DATABASE_USER = "users.json"

def muat_data_user():
    if os.path.exists(FILE_DATABASE_USER):
        with open(FILE_DATABASE_USER, "r") as file:
            return json.load(file)
    else:
        akun_awal = {"admin": "admin123", "zaim": "zaim2026"}
        with open(FILE_DATABASE_USER, "w") as file:
            json.dump(akun_awal, file)
        return akun_awal

def simpan_data_user(data):
    with open(FILE_DATABASE_USER, "w") as file:
        json.dump(data, file)

db_user = muat_data_user()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# --- LAYAR LOGIN & DAFTAR ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>🔐 Sistem Scraping Instagram</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Silakan login atau buat akun baru untuk mengakses ruang kerja.</p>", unsafe_allow_html=True)
    
    col_kiri, col_tengah, col_kanan = st.columns([1, 1.5, 1])
    with col_tengah:
        tab_login, tab_daftar = st.tabs(["🔑 Masuk (Login)", "📝 Buat Akun Baru"])
        
        with tab_login:
            with st.form("login_form"):
                user_input = st.text_input("Username")
                pass_input = st.text_input("Password", type="password")
                btn_login = st.form_submit_button("Masuk", use_container_width=True)
                
                if btn_login:
                    if user_input in db_user and db_user[user_input] == pass_input:
                        st.session_state.logged_in = True
                        st.session_state.username = user_input
                        st.success("✅ Login berhasil! Memuat ruang kerja...")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Username tidak ditemukan atau Password salah!")
                        
        with tab_daftar:
            with st.form("register_form"):
                new_user = st.text_input("Buat Username Baru (Tanpa Spasi)")
                new_pass = st.text_input("Buat Password", type="password")
                konfirmasi_pass = st.text_input("Ulangi Password", type="password")
                btn_daftar = st.form_submit_button("Daftar Sekarang", use_container_width=True)
                
                if btn_daftar:
                    if new_user.strip() == "" or new_pass == "":
                        st.error("⚠️ Username dan Password tidak boleh kosong!")
                    elif " " in new_user:
                        st.error("⚠️ Username tidak boleh menggunakan spasi!")
                    elif new_user in db_user:
                        st.error("⚠️ Username ini sudah dipakai orang lain! Pilih yang lain.")
                    elif new_pass != konfirmasi_pass:
                        st.error("⚠️ Password tidak cocok!")
                    else:
                        db_user[new_user] = new_pass
                        simpan_data_user(db_user)
                        os.makedirs(f"data/{new_user}", exist_ok=True)
                        st.success(f"🎉 Akun '{new_user}' berhasil dibuat! Silakan pindah ke tab Login untuk masuk.")

    st.stop()

# ==========================================
# PERSIAPAN RUANG KERJA (WORKSPACE)
# ==========================================
username = st.session_state.username
user_dir = f"data/{username}"
os.makedirs(user_dir, exist_ok=True) 

target_file = f"{user_dir}/Target_Scraping.xlsx"
file_path = f"{user_dir}/Dataset_Scraping_Master.xlsx"
config_file = f"{user_dir}/config.json"

# ==========================================
# FUNGSI EXPORT PDF
# ==========================================
def generate_pdf(dataframe, user_name):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    pdf.set_font("helvetica", style="B", size=16)
    pdf.cell(0, 10, "Laporan Scraping Instagram", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("helvetica", size=11)
    pdf.cell(0, 10, f"Diekstrak oleh: {user_name} | Total Data: {len(dataframe)}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    for idx, row in dataframe.iterrows():
        tanggal = str(row['Tanggal']).split(' ')[0]
        akun = str(row['Username']).encode('latin-1', 'ignore').decode('latin-1')
        url = str(row['URL Postingan']).encode('latin-1', 'ignore').decode('latin-1')
        teks_ai = str(row['Teks Gambar (AI)'])[:150].encode('latin-1', 'ignore').decode('latin-1') + "..."
        
        pdf.set_font("helvetica", style="B", size=11)
        pdf.cell(0, 6, f"[{tanggal}] - @{akun}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", size=10)
        pdf.set_text_color(0, 0, 255)
        pdf.cell(0, 6, f"Link: {url}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, f"Hasil Ekstrak AI: {teks_ai}")
        pdf.ln(4)
        
    return bytes(pdf.output())

# ==========================================
# HEADER & TOMBOL LOGOUT
# ==========================================
col_title, col_logout = st.columns([4, 1])
with col_title:
    st.title(f"📊 Dashboard: {username.capitalize()}")
with col_logout:
    st.write("") 
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

st.markdown("Dashboard ini menampilkan data hasil ekstraksi Anda sendiri. Terapkan filter di samping untuk menyesuaikan tabel, laporan unduhan, dan visualisasi.")

# ==========================================
# 1. SIDEBAR: KONTROL TARGET SCRAPING BARU
# ==========================================
st.sidebar.header("🎯 Target Scraping")

if os.path.exists(target_file):
    target_df = pd.read_excel(target_file, engine='openpyxl')
else:
    target_df = pd.DataFrame([{"Username": "", "Jumlah Post": 5}])

edited_target_df = st.sidebar.data_editor(
    target_df,
    num_rows="dynamic",
    hide_index=True,
    use_container_width=True,
    column_config={
        "Username": st.column_config.TextColumn("Username IG"),
        "Jumlah Post": st.column_config.NumberColumn("Jumlah", min_value=1, max_value=100, step=1)
    }
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Opsi Pengambilan Data")
st.sidebar.caption("Matikan 'Teks Gambar (AI)' jika tidak perlu agar tidak memakan kuota API.")

opsi_semua = ["Tanggal", "Username", "Jumlah Like", "Jumlah Komentar", "Caption", "Top Komentar", "Teks Gambar (AI)"]

if os.path.exists(config_file):
    with open(config_file, "r") as f:
        opsi_default = json.load(f).get("opsi_dipilih", opsi_semua)
else:
    opsi_default = opsi_semua

opsi_dipilih = st.sidebar.multiselect(
    "Pilih data yang ingin diekstrak:",
    options=opsi_semua,
    default=opsi_default
)

# --- [INJEKSI BARU] WIDGET UPLOAD FOTO MANUAL (MULTI-GAMBAR) ---
st.sidebar.markdown("---")
st.sidebar.header("💡 Solusi Bypass Komentar")
st.sidebar.info("Upload screenshot komentar di sini jika bot gagal mengekstrak otomatis. Bisa pilih lebih dari 1 gambar!")
files_komentar_manual = st.sidebar.file_uploader("Upload Foto Komentar", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

# --- [INJEKSI BARU] TOGGLE MODE DEBUG ---
st.sidebar.markdown("---")
mode_debug = st.sidebar.checkbox("🐞 Aktifkan Mode Debug (Tahan Layar untuk cari Bug)")
# ------------------------------------------------

if st.sidebar.button("▶️ Mulai Scraping", type="primary"):
    df_bersih = edited_target_df[edited_target_df['Username'].astype(str).str.strip() != ""]
    df_bersih = df_bersih.dropna(subset=['Username'])

    if df_bersih.empty:
        st.sidebar.warning("⚠️ Tolong isi minimal 1 username di tabel sebelum memulai!")
    elif len(opsi_dipilih) == 0:
         st.sidebar.warning("⚠️ Pilih minimal 1 jenis data yang ingin diekstrak di bagian Opsi!")
    else:
        try:
            df_bersih['Username'] = df_bersih['Username'].astype(str).str.strip()
            df_bersih.to_excel(target_file, index=False, engine='openpyxl')
            
            with open(config_file, "w") as f:
                json.dump({"opsi_dipilih": opsi_dipilih}, f)
            
            total_akun = len(df_bersih)
            total_post = df_bersih['Jumlah Post'].sum()
            
            with st.spinner(f"⏳ Mengeksekusi {total_akun} akun untuk {username}... Mohon tunggu."):
                proses = subprocess.run(["python", "scraper.py", username], capture_output=True, text=True)
                
                # ==========================================
                # 🐞 PERANGKAP BUG: TAMPILKAN LOG TERMINAL
                # ==========================================
                if mode_debug:
                    st.sidebar.markdown("### 🐞 LOG CRAWLER (TAMPILAN BUG):")
                    st.sidebar.text_area("Detail Proses & Error:", value=f"--- OUTPUT ---\n{proses.stdout}\n\n--- ERROR ---\n{proses.stderr}", height=300)
                    st.sidebar.warning("☝️ Copy teks di atas jika terjadi masalah, dan kirim ke AI! (Hapus centang Mode Debug untuk kembali normal)")
                    st.stop() # Menghentikan paksa aplikasi di sini agar tidak me-refresh!
                # ==========================================

                if proses.returncode == 0:
                    st.sidebar.success(f"✅ Scraping {total_akun} akun selesai!")
                    
                    # --- [INJEKSI BARU] EKSEKUSI OCR MANUAL SETELAH SCRAPING ---
                    if files_komentar_manual and len(files_komentar_manual) > 0 and "Top Komentar" in opsi_dipilih:
                        with st.spinner(f"📸 Membaca teks dari {len(files_komentar_manual)} screenshot komentar..."):
                            try:
                                import scraper 
                                
                                # Ambil bytes dari semua gambar
                                list_gambar_bytes = [file.getvalue() for file in files_komentar_manual]
                                
                                # Jalankan OCR dengan List Gambar
                                hasil_komentar_ai = asyncio.run(scraper.ocr_komentar_manual(list_gambar_bytes))
                                
                                # Sisipkan hasilnya ke baris PALING BAWAH
                                if os.path.exists(file_path):
                                    df_update = pd.read_excel(file_path, engine='openpyxl')
                                    if not df_update.empty:
                                        baris_terakhir = df_update.index[-1]
                                        df_update.at[baris_terakhir, 'Top Komentar'] = hasil_komentar_ai
                                        df_update.to_excel(file_path, index=False, engine='openpyxl')
                                        st.sidebar.success(f"✅ {len(files_komentar_manual)} gambar komentar ditambahkan ke baris bawah!")
                            except Exception as e:
                                st.sidebar.error(f"Gagal memproses gambar manual: {e}")
                    # -------------------------------------------------------------

                    time.sleep(2)
                    st.rerun()
                else:
                    st.sidebar.error("❌ Terjadi kesalahan saat scraping!")
                    with st.sidebar.expander("Lihat Detail Error"):
                        st.code(proses.stderr)
                        
        except Exception as e:
            st.sidebar.error(f"❌ Gagal memicu scraper: {e}")

st.sidebar.markdown("---")

# ==========================================
# 2. MAIN PAGE: LOGIKA FILTER & TAB TAMPILAN
# ==========================================
if os.path.exists(file_path):
    try:
        df_master = pd.read_excel(file_path, engine='openpyxl')
        
        df_master['Tanggal'] = pd.to_datetime(df_master['Tanggal'], errors='coerce')
        min_date = df_master['Tanggal'].min().date() if not pd.isna(df_master['Tanggal'].min()) else datetime.today().date()
        max_date = df_master['Tanggal'].max().date() if not pd.isna(df_master['Tanggal'].max()) else datetime.today().date()
        
        st.sidebar.header("🔍 Filter Data & Laporan")
        
        if 'Username' in df_master.columns:
            usernames = sorted(df_master['Username'].dropna().unique().tolist())
            selected_user = st.sidebar.selectbox("Pilih Akun (Username):", ["Semua Akun"] + usernames)
            
        rentang_tanggal = st.sidebar.date_input("Pilih Rentang Tanggal:", value=[min_date, max_date], min_value=min_date, max_value=max_date)
            
        df_tampil = df_master.copy()
        
        if selected_user != "Semua Akun":
            df_tampil = df_tampil[df_tampil['Username'] == selected_user]
            
        if len(rentang_tanggal) == 2:
            start_date, end_date = rentang_tanggal
            mask = (df_tampil['Tanggal'].dt.date >= start_date) & (df_tampil['Tanggal'].dt.date <= end_date)
            df_tampil = df_tampil.loc[mask]

        df_tampil['Tanggal'] = df_tampil['Tanggal'].dt.strftime('%Y-%m-%d')
        
        tab_tabel, tab_visual = st.tabs(["📋 Data & Laporan", "📈 Visualisasi Grafis"])
        
        with tab_tabel:
            col1, col2 = st.columns(2)
            col1.metric("Total Postingan Tampil", len(df_tampil))
            if 'Username' in df_tampil.columns:
                col2.metric("Total Akun Tampil", df_tampil['Username'].nunique())
            
            st.info("💡 **Mode Edit:** Anda bisa merevisi teks AI atau menghapus baris. Perubahan pada tabel difilter akan memperbarui file Master.")
            
            edited_master_df = st.data_editor(df_tampil, use_container_width=True, height=450, num_rows="dynamic")
            
            col_btn1, col_btn2, col_btn3 = st.columns([1.5, 1, 1])
            
            with col_btn1:
                if st.button("💾 Simpan Perubahan (Permanen)", type="primary"):
                    if selected_user != "Semua Akun" or len(rentang_tanggal) == 2:
                        kondisi_hapus = pd.Series(True, index=df_master.index)
                        if selected_user != "Semua Akun":
                            kondisi_hapus = kondisi_hapus & (df_master['Username'] == selected_user)
                        if len(rentang_tanggal) == 2:
                            kondisi_hapus = kondisi_hapus & (df_master['Tanggal'].dt.date >= start_date) & (df_master['Tanggal'].dt.date <= end_date)
                            
                        df_master_sisa = df_master[~kondisi_hapus]
                        df_final = pd.concat([df_master_sisa, edited_master_df], ignore_index=True)
                    else:
                        df_final = edited_master_df.copy()
                    
                    df_final.to_excel(file_path, index=False, engine='openpyxl')
                    st.success("✅ Tersimpan!")
                    time.sleep(1)
                    st.rerun()
                    
            with col_btn2:
                import io
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_tampil.to_excel(writer, index=False)
                st.download_button(
                    label="⬇️ Download Excel (Filter)",
                    data=buffer.getvalue(),
                    file_name=f"Laporan_{username}_Filtered.xlsx",
                    mime="application/vnd.ms-excel"
                )
                
            with col_btn3:
                pdf_bytes = generate_pdf(df_tampil, username)
                st.download_button(
                    label="⬇️ Download PDF Laporan",
                    data=pdf_bytes,
                    file_name=f"Laporan_Ringkas_{username}.pdf",
                    mime="application/pdf"
                )

        with tab_visual:
            if df_tampil.empty:
                st.warning("Data kosong pada rentang waktu/akun yang dipilih. Tidak ada yang bisa divisualisasikan.")
            else:
                st.markdown("### ☁️ Kata Paling Sering Muncul (Wordcloud)")
                st.caption("Dianalisis berdasarkan Caption Instagram dari data yang difilter.")
                
                teks_kumpulan = " ".join(df_tampil['Caption'].dropna().astype(str))
                teks_kumpulan = teks_kumpulan.replace("-", "") 
                
                if teks_kumpulan.strip() != "":
                    wordcloud = WordCloud(width=800, height=350, background_color='white', colormap='viridis').generate(teks_kumpulan)
                    fig_wc, ax_wc = plt.subplots(figsize=(10, 5))
                    ax_wc.imshow(wordcloud, interpolation='bilinear')
                    ax_wc.axis("off")
                    st.pyplot(fig_wc)
                else:
                    st.info("Tidak ada teks caption yang cukup untuk membuat Wordcloud.")

                st.markdown("---")
                col_chart1, col_chart2 = st.columns(2)
                
                df_counts = df_tampil['Username'].value_counts().reset_index()
                df_counts.columns = ['Username', 'Jumlah Postingan']
                
                with col_chart1:
                    st.markdown("### 🥧 Proporsi Postingan per Akun")
                    fig_pie = px.pie(df_counts, names='Username', values='Jumlah Postingan', hole=0.4, 
                                     color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                with col_chart2:
                    st.markdown("### 📊 Perbandingan Volume Postingan")
                    fig_bar = px.bar(df_counts, x='Username', y='Jumlah Postingan', text='Jumlah Postingan',
                                     color='Username', color_discrete_sequence=px.colors.qualitative.Set2)
                    fig_bar.update_traces(textposition='outside')
                    fig_bar.update_layout(showlegend=False)
                    st.plotly_chart(fig_bar, use_container_width=True)
                    
    except Exception as e:
        st.error(f"Terjadi kesalahan saat memproses data/visualisasi: {e}")
else:
    st.info("👋 Ruang kerja ini masih kosong. Silakan masukkan target di tabel samping dan klik 'Mulai Scraping'!")