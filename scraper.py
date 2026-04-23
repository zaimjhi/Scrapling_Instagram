from patchright.async_api import async_playwright
import asyncio
import random
import os
import re
import pandas as pd
import base64
import sys
import json

# Import library Groq
from groq import Groq

STATE_FILE = "ig_state.json"

# ==========================================
# KONFIGURASI GROQ AI & SESI
# ==========================================
API_KEY_GROQ = "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" 

try:
    client_ai = Groq(api_key=API_KEY_GROQ)
except Exception as e:
    client_ai = None
    print(f"\n[!] PERINGATAN: Konfigurasi Groq gagal. Error: {e}")

# ==========================================
# FUNGSI 1: MANAJEMEN SESI & LOGIN
# ==========================================
async def siapkan_sesi(browser):
    if not os.path.exists(STATE_FILE):
        print("\n[-] Kartu akses (Sesi) belum ada.")
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.instagram.com/accounts/login/")
        
        try:
            await page.wait_for_selector('svg[aria-label="Home"], svg[aria-label="Beranda"], svg[aria-label="Search"]', timeout=120000)
            print("[+] Login terdeteksi berhasil!")
        except Exception:
            print("[-] Waktu tunggu habis. Tetap mencoba menyimpan sesi...")
        
        await asyncio.sleep(5.0) 
        await context.storage_state(path=STATE_FILE)
        print(f"[+] Sesi disimpan ke: {STATE_FILE}")
        await page.close()
        return context
    else:
        print(f"\n[+] Sesi ditemukan ({STATE_FILE}). Menginjeksi cookies...")
        context = await browser.new_context(storage_state=STATE_FILE)
        return context

# ==========================================
# ==========================================
# FUNGSI 2: PENGUMPUL LINK DARI PROFIL
# ==========================================
async def ambil_link_profil(context, target_username, jumlah_maksimal=5):
    print(f"\n>>> [CRAWLER] Mengunjungi profil: @{target_username}")
    page = await context.new_page()
    url_profil = f"https://www.instagram.com/{target_username}/"
    
    try:
        await page.goto(url_profil)
        await page.wait_for_selector('main', timeout=15000)
        await asyncio.sleep(4.0) 

        # [PERBAIKAN] Gunakan List agar urutan postingan dari terbaru tetap terjaga!
        kumpulan_link = []
        percobaan_scroll = 0

        print(f"Mencari {jumlah_maksimal} link postingan (Termasuk toleransi PIN)...")
        while len(kumpulan_link) < jumlah_maksimal and percobaan_scroll < 10:
            elemen_link = await page.locator('a[href*="/p/"], a[href*="/reel/"]').all()
            for el in elemen_link:
                href = await el.get_attribute('href')
                if href:
                    url_lengkap = f"https://www.instagram.com{href}"
                    # Cek duplikat manual, agar urutan tidak teracak
                    if url_lengkap not in kumpulan_link:
                        kumpulan_link.append(url_lengkap)
                    
                    if len(kumpulan_link) >= jumlah_maksimal:
                        break
            
            if len(kumpulan_link) < jumlah_maksimal:
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(3.0)
                percobaan_scroll += 1

        print(f"[+] Berhasil mengumpulkan {len(kumpulan_link)} link postingan dari @{target_username}.")
        return kumpulan_link[:jumlah_maksimal]

    except Exception as e:
        print(f"[X] Gagal memuat profil @{target_username}. Error: {e}")
        return []
    finally:
        await page.close()

# ==========================================
# ==========================================
# FUNGSI AI: ANALISIS GAMBAR (DIOPTIMASI)
# ==========================================
async def analisis_gambar_carousel(context, page):
    urls_gambar = set()
    print("  📸 Mendeteksi gambar untuk dikirim ke AI...")
    await page.wait_for_timeout(2000) 
    
    for _ in range(10):
        imgs = await page.locator('img').all()
        for img in imgs:
            try:
                src = await img.get_attribute('src')
                if src and ("http" in src) and ("150x150" not in src) and ("profile" not in src.lower()) and ("logo" not in src.lower()):
                    urls_gambar.add(src)
            except: pass
                
        tombol_next = page.locator('button[aria-label="Next"], button[aria-label="Selanjutnya"], div._aaqg button').first
        if await tombol_next.is_visible():
            await tombol_next.click()
            await asyncio.sleep(2.0)
        else: break 
            
    if not urls_gambar: return "Gagal: Gambar tidak ditemukan di layar"
    if not client_ai: return "Gagal: API Key Groq belum terbaca"

    # [PERBAIKAN] Kembalikan ke format asli Anda: Ambil 5 gambar, jangan cuma 1!
    gambar_diproses = list(urls_gambar)[:5]
    print(f"  🧠 Mengirim {len(gambar_diproses)} gambar ke Groq API...")
    
    try:
        gambar_bytes = []
        for url in gambar_diproses:
            response = await context.request.get(url)
            if response.ok:
                gambar_bytes.append(await response.body())
                
        content_array = [{"type": "text", "text": "Ekstrak informasi teks penting dari gambar ini (Judul, Tanggal, Waktu, Lokasi, Syarat). Jawab singkat dan rapi."}]
        
        for byte_data in gambar_bytes:
            base64_image = base64.b64encode(byte_data).decode('utf-8')
            content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}})
            
        def panggil_ai():
            return client_ai.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct", # Pastikan model Llama 4 Scout Anda aman
                messages=[{"role": "user", "content": content_array}],
                temperature=0.3,
                max_tokens=1024
            )
        respon_ai = await asyncio.to_thread(panggil_ai)
        return respon_ai.choices[0].message.content.strip()
        
    except Exception as e:
        return f"Gagal diekstrak oleh AI (Error: {e})"

## FUNGSI BARU: OCR KOMENTAR DARI FILE UPLOAD (SOLUSI HYBRID)
# ==========================================
# ==========================================
# FUNGSI BARU: OCR KOMENTAR DARI FILE UPLOAD (MENDUKUNG BANYAK GAMBAR)
# ==========================================
async def ocr_komentar_manual(list_gambar_bytes):
    print(f"  📸 [OCR HYBRID] Membaca {len(list_gambar_bytes)} screenshot komentar dari user...")
    try:
        if not client_ai:
            return "Gagal: API Key Groq belum terbaca"
            
        prompt_ocr = """
        Ini adalah beberapa screenshot kolom komentar Instagram yang bersambung. Tolong ekstrak teks komentar yang ditulis oleh netizen di semua gambar ini. 
        Syarat:
        1. Format jawaban wajib: [nama_akun]: isi komentar | [nama_akun_lain]: isi komentar lain
        2. Abaikan teks UI (Reply, Balas, Likes, Log in, dll).
        3. Gabungkan semua komentar dari semua gambar, dan tolong jangan tulis komentar yang sama dua kali.
        4. Jika tidak ada komentar, balas dengan tanda: -
        """
        
        content_array = [{"type": "text", "text": prompt_ocr}]
        
        for gambar_bytes in list_gambar_bytes:
            base64_image = base64.b64encode(gambar_bytes).decode('utf-8')
            content_array.append({
                "type": "image_url", 
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
            })
        
        def panggil_ocr():
            return client_ai.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": content_array}],
                temperature=0.1,
                max_tokens=2048
            )
        
        respon = await asyncio.to_thread(panggil_ocr)
        hasil_ocr = respon.choices[0].message.content.strip()
        print(f"  [+] OCR Manual ({len(list_gambar_bytes)} gambar) Selesai!")
        return hasil_ocr
        
    except Exception as e:
        print(f"  [-] Gagal melakukan OCR Komentar: {e}")
        # PERBAIKAN: Jika error (seperti Limit 429), tulis langsung ke Excel biar ketahuan!
        return f"[GAGAL OCR - BACA ERROR INI]: {e}"
# ==========================================
# FUNGSI 3: EKSTRAKTOR DATA LENGKAP (MODE IPHONE + PEMBASMI POP-UP + OCR)
# ==========================================
# FUNGSI 3: EKSTRAKTOR DATA LENGKAP (MODE IPHONE + KLIK KOMENTAR + OCR)
# ==========================================
# ==========================================
# FUNGSI 3: EKSTRAKTOR DATA LENGKAP (MODE IPHONE + SCROLL CAPTION)
# ==========================================
# ==========================================
# FUNGSI 3: EKSTRAKTOR DATA LENGKAP (MODE IPHONE + SAPU JAGAT CAPTION)
# ==========================================
async def ekstrak_data_postingan(context, url, opsi_pilihan):
    print(f"\nMengurai data: {url}")
    
    page = await context.new_page()
    
    await page.set_extra_http_headers({
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
    })
    
    await page.set_viewport_size({"width": 390, "height": 844})
    
    tanggal_post = "-"
    username = "-"
    jumlah_like = "-"
    jumlah_komen = "-"
    caption = "-"
    teks_dari_gambar = "-"
    kumpulan_komentar = "-"
    
    try:
        await page.goto(url)
        print("  📱 Membuka halaman dengan KTP iPhone...")
        await asyncio.sleep(4.0)

        try:
            await page.keyboard.press('Escape')
            await asyncio.sleep(0.5)
            tombol_x = page.locator('svg[aria-label="Close"], svg[aria-label="Tutup"]').first
            if await tombol_x.is_visible(timeout=2000):
                await tombol_x.locator("..").click()
                await asyncio.sleep(1.0)
            await page.mouse.click(350, 60)
            await asyncio.sleep(1.0)
        except: pass

        print("  🖱️ Melakukan scroll pemanasan untuk memancing elemen...")
        for _ in range(3):
            await page.mouse.wheel(0, 400)
            await asyncio.sleep(1.0)

        if "Teks Gambar (AI)" in opsi_pilihan:
            teks_dari_gambar = await analisis_gambar_carousel(context, page)
            
        if "Tanggal" in opsi_pilihan:
            try:
                tanggal_raw = await page.locator('time').first.get_attribute('datetime', timeout=3000)
                if tanggal_raw and "T" in tanggal_raw:
                    dt_utc = pd.to_datetime(tanggal_raw)
                    dt_wita = dt_utc + pd.Timedelta(hours=8)
                    tanggal_post = dt_wita.strftime('%Y-%m-%d')
            except: pass

        if "Username" in opsi_pilihan or "Caption" in opsi_pilihan:
            match_url = re.search(r'instagram\.com/([^/]+)/', url)
            username = match_url.group(1) if match_url else "-"
            if username in ['p', 'reel', 'tv']: username = "-"

        # ==========================================
        # JURUS SAPU JAGAT: EKSTRAK CAPTION & META (KHUSUS REELS & POST)
        # ==========================================
        meta_desc = ""
        meta_og_desc = ""
        try:
            # Ambil jaring seluas mungkin dari Meta Data
            meta_desc = await page.locator('meta[name="description"]').get_attribute('content', timeout=2000)
            meta_og_desc = await page.locator('meta[property="og:description"]').get_attribute('content', timeout=2000)
        except: pass

        if meta_desc:
            if "Jumlah Like" in opsi_pilihan:
                l_match = re.search(r'([\d,\.]+)\s*(?:likes?|suka)', meta_desc, re.IGNORECASE)
                if l_match: jumlah_like = l_match.group(1)
            if "Jumlah Komentar" in opsi_pilihan:
                c_match = re.search(r'([\d,\.]+)\s*(?:comments?|komentar)', meta_desc, re.IGNORECASE)
                if c_match: jumlah_komen = c_match.group(1)

        if "Caption" in opsi_pilihan:
            # Prioritas 1: og:description (Paling sering memuat caption utuh tanpa embel-embel Like)
            if meta_og_desc and meta_og_desc.strip():
                caption = meta_og_desc
            # Prioritas 2: description biasa
            elif meta_desc and " on Instagram:" in meta_desc:
                caption = meta_desc
            # Prioritas 3: Cari langsung dari layar kalau meta datanya gaib
            else:
                try:
                    caption = await page.locator('h1[dir="auto"], span[dir="auto"], div[dir="auto"]').first.inner_text(timeout=2000)
                except:
                    caption = "-"

            # Membersihkan sisa teks bawaan Meta ("100 Likes, 2 Comments - Username on Instagram: ...")
            if caption and caption != "-":
                if " on Instagram:" in caption:
                    parts = caption.split(' on Instagram: "')
                    caption = parts[1].rstrip('"') if len(parts) > 1 else caption
                elif " - " in caption and ("Likes" in caption or "Comments" in caption):
                    try: caption = caption.split(" - ", 1)[1]
                    except: pass

        if "Top Komentar" in opsi_pilihan:
            kumpulan_komentar = "-" # Tetap - agar diisi oleh foto manual Anda

        return {
            "Tanggal": tanggal_post,
            "URL Postingan": url, 
            "Username": username.strip() if username else "-",
            "Jumlah Like": jumlah_like,
            "Jumlah Komentar": jumlah_komen,
            "Caption": caption.strip() if caption else "-",
            "Top Komentar": kumpulan_komentar,
            "Teks Gambar (AI)": teks_dari_gambar
        }
        
    except Exception as e:
        print(f"  [X] Gagal mengekstrak {url}. Error: {e}")
        return None
    finally:
        await page.close()
# PROGRAM UTAMA (MAIN)
# ==========================================
async def main():
    username_aktif = sys.argv[1] if len(sys.argv) > 1 else "umum"
    folder_user = f"data/{username_aktif}"
    os.makedirs(folder_user, exist_ok=True)
    
    nama_file_input = f"{folder_user}/Target_Scraping.xlsx"
    nama_file_excel = f"{folder_user}/Dataset_Scraping_Master.xlsx"
    file_config = f"{folder_user}/config.json"
    
    # 1. Membaca Opsi Pengaturan Filter yang dicentang user di Web
    opsi_pilihan = ["Tanggal", "Username", "Jumlah Like", "Jumlah Komentar", "Caption", "Top Komentar", "Teks Gambar (AI)"]
    if os.path.exists(file_config):
        with open(file_config, "r") as f:
            opsi_pilihan = json.load(f).get("opsi_dipilih", opsi_pilihan)
            
    print(f"\n⚙️ Mode Ekstraksi Aktif: {', '.join(opsi_pilihan)}")
    
    if not os.path.exists(nama_file_input):
        print(f"\n[X] File {nama_file_input} tidak ditemukan!")
        return
        
    try:
        print(f"\n📊 Membaca target dari '{nama_file_input}'...")
        df_target = pd.read_excel(nama_file_input, engine='openpyxl')
        df_target = df_target.dropna(subset=['Username'])
    except Exception as e:
        print(f"[X] Gagal membaca Excel: {e}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await siapkan_sesi(browser)

        for index, row in df_target.iterrows():
            akun = str(row['Username']).strip()
            try: jumlah_post_asli = int(row['Jumlah Post'])
            except: jumlah_post_asli = 5

            target_link_diambil = jumlah_post_asli + 3

            print("\n" + "="*50)
            print(f"🔄 MEMPROSES: @{akun} | MENGAMBIL {target_link_diambil} LINK (Mencegah Pinned Post)")
            print("="*50)

            hasil_sementara = []
            daftar_link = await ambil_link_profil(context, akun, target_link_diambil)

            if not daftar_link: continue

            print("\n>>> [EKSTRAKSI] Mulai menyedot data...")
            
            for i, url in enumerate(daftar_link):
                # Ekstrak data sesuai filter yang dilempar
                data = await ekstrak_data_postingan(context, url, opsi_pilihan)
                if data: hasil_sementara.append(data)
                
                if i < len(daftar_link) - 1:
                    waktu_jeda = random.uniform(8.0, 15.0)
                    print(f"[*] Delay anti-blokir (post): {waktu_jeda:.1f} detik...")
                    await asyncio.sleep(waktu_jeda)

            if hasil_sementara:
                print("\n⚙️ Melakukan filtering Pinned Post... Mengurutkan data berdasarkan Tanggal terbaru.")
                
                if "Tanggal" in opsi_pilihan:
                    hasil_sementara.sort(key=lambda x: x['Tanggal'], reverse=True)
                    
                hasil_akhir_terbaru = hasil_sementara[:jumlah_post_asli]

                print(f"📊 Menyimpan {len(hasil_akhir_terbaru)} postingan untuk @{akun} ke Master Excel...")
                
                df_baru = pd.DataFrame(hasil_akhir_terbaru)
                kolom_urutan = ["Tanggal", "URL Postingan", "Username", "Jumlah Like", "Jumlah Komentar", "Caption", "Top Komentar", "Teks Gambar (AI)"]
                df_baru = df_baru[kolom_urutan]
                
                if os.path.exists(nama_file_excel):
                    df_lama = pd.read_excel(nama_file_excel, engine='openpyxl')
                    df_gabung = pd.concat([df_lama, df_baru], ignore_index=True)
                    df_gabung = df_gabung.drop_duplicates(subset=['URL Postingan'], keep='last')
                else:
                    df_gabung = df_baru

                df_gabung.to_excel(nama_file_excel, index=False, engine='openpyxl')
                print(f"✅ SUKSES! Data @{akun} tersimpan. Total baris Master: {len(df_gabung)}")
            
            if index < len(df_target) - 1:
                jeda_akun = random.uniform(25.0, 45.0)
                await asyncio.sleep(jeda_akun)

        await context.storage_state(path=STATE_FILE)
        await browser.close()
        print("\n" + "="*50)
        print(f"🎉 SEMUA TUGAS SELESAI! Data tersimpan di folder 'data/{username_aktif}'")

if __name__ == "__main__":
    asyncio.run(main())