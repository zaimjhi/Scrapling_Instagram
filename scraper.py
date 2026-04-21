from patchright.async_api import async_playwright
import asyncio
import random
import os
import re
import pandas as pd
import base64

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
        print(">>> Mengarahkan ke halaman Login Instagram...")
        
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.instagram.com/accounts/login/")
        
        print("\n" + "="*50)
        print("⏳ TINDAKAN DIBUTUHKAN: JENDELA BROWSER TERBUKA!")
        print("Silakan login manual di browser. Script menunggu...")
        print("="*50 + "\n")
        
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

        kumpulan_link = set()
        percobaan_scroll = 0

        print(f"Mencari {jumlah_maksimal} link postingan (Termasuk toleransi PIN)...")
        while len(kumpulan_link) < jumlah_maksimal and percobaan_scroll < 10:
            elemen_link = await page.locator('a[href*="/p/"], a[href*="/reel/"]').all()
            
            for el in elemen_link:
                href = await el.get_attribute('href')
                if href:
                    url_lengkap = f"https://www.instagram.com{href}"
                    kumpulan_link.add(url_lengkap)
                    if len(kumpulan_link) >= jumlah_maksimal:
                        break
            
            if len(kumpulan_link) < jumlah_maksimal:
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(3.0)
                percobaan_scroll += 1

        print(f"[+] Berhasil mengumpulkan {len(kumpulan_link)} link postingan dari @{target_username}.")
        return list(kumpulan_link)[:jumlah_maksimal]

    except Exception as e:
        print(f"[X] Gagal memuat profil @{target_username}. Error: {e}")
        return []
    finally:
        await page.close()

# ==========================================
# FUNGSI BARU: ANALISIS GAMBAR DENGAN GROQ VISION
# ==========================================
# ==========================================
# FUNGSI BARU: ANALISIS GAMBAR DENGAN GROQ VISION (DIPERBARUI)
# ==========================================
async def analisis_gambar_carousel(context, page):
    urls_gambar = set()
    print("  📸 Mendeteksi gambar di postingan...")
    
    # Tunggu sebentar ekstra untuk memastikan gambar benar-benar termuat
    await page.wait_for_timeout(2000) 
    
    for _ in range(10):
        # Ubah pencariannya menjadi lebih luas (semua img di halaman)
        imgs = await page.locator('img').all()
        for img in imgs:
            try:
                src = await img.get_attribute('src')
                # Filter ketat: Harus ada src, format gambar, bukan icon profile, bukan logo kecil
                if src and ("http" in src) and ("150x150" not in src) and ("profile" not in src.lower()) and ("logo" not in src.lower()):
                    urls_gambar.add(src)
            except:
                pass
                
        # Cari tombol panah kanan (Next) - antisipasi bahasa Inggris/Indonesia/Icon
        tombol_next = page.locator('button[aria-label="Next"], button[aria-label="Selanjutnya"], div._aaqg button').first
        
        if await tombol_next.is_visible():
            await tombol_next.click()
            await asyncio.sleep(2.0) # Jeda lebih lama agar gambar slide berikutnya sempat loading
        else:
            break 
            
    if not urls_gambar:
        print("  [!] Peringatan: Script tidak menemukan gambar apapun di halaman ini.")
        return "Gagal: Gambar tidak ditemukan di layar"
        
    if not client_ai:
        return "Gagal: API Key Groq belum terbaca"

    # Batasi maksimal 5 gambar sesuai aturan Groq
    gambar_diproses = list(urls_gambar)[:5]
    print(f"  🧠 Mengirim {len(gambar_diproses)} gambar ke Groq API...")
    
    try:
        gambar_bytes = []
        for url in gambar_diproses:
            response = await context.request.get(url)
            if response.ok:
                gambar_bytes.append(await response.body())
                
        # Format prompt dasar
        content_array = [
            {
                "type": "text", 
                "text": "Ini adalah beberapa gambar dari satu postingan Instagram. Tolong ekstrak semua informasi teks penting dari gambar-gambar ini. Jika ini adalah pamflet acara/loker, rangkum Judul, Tanggal, Waktu, Lokasi, dan Syaratnya. Jawab dengan singkat, padat, dan format yang rapi."
            }
        ]
        
        for byte_data in gambar_bytes:
            base64_image = base64.b64encode(byte_data).decode('utf-8')
            content_array.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })
            
        def panggil_ai():
            return client_ai.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct", # Model Vision TERBARU di Groq
                messages=[{"role": "user", "content": content_array}],
                temperature=0.3,
                max_tokens=1024
            )
        respon_ai = await asyncio.to_thread(panggil_ai)
        return respon_ai.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"  [X] Gagal memproses gambar dengan AI: {e}")
        return f"Gagal diekstrak oleh AI (Error: {e})"
# ==========================================
# FUNGSI 3: EKSTRAKTOR DATA LENGKAP
# ==========================================
async def ekstrak_data_postingan(context, url):
    print(f"\nMengurai data: {url}")
    page = await context.new_page()
    
    try:
        await page.goto(url)
        await asyncio.sleep(random.uniform(4.0, 6.0))
        await page.wait_for_selector('main', timeout=15000)
        await asyncio.sleep(3.0)
        
        # --- EKSTRAK TEKS DARI GAMBAR ---
        teks_dari_gambar = await analisis_gambar_carousel(context, page)
        
        # 1. Ekstrak Tanggal Postingan
        tanggal_loc = page.locator('time').first
        tanggal_post = await tanggal_loc.get_attribute('datetime') if await tanggal_loc.count() > 0 else "1970-01-01"
        if "T" in tanggal_post:
            tanggal_post = tanggal_post.split("T")[0]

        # 2. Ekstrak Username
        username_loc = page.locator('header h2 a, h2[dir="auto"] a').first
        username = await username_loc.inner_text() if await username_loc.count() > 0 else "Username gagal dilacak"
        
        # 3. Ekstrak Caption Utama
        caption_loc = page.locator('h1[dir="auto"]').first
        caption = await caption_loc.inner_text() if await caption_loc.count() > 0 else ""

        # 4. Ambil Meta SEO
        meta_description = await page.evaluate('''() => {
            let meta = document.querySelector('meta[property="og:title"]') || document.querySelector('meta[name="description"]');
            return meta ? meta.content : "";
        }''')

        jumlah_like = "0"
        jumlah_komen = "0"
        
        if meta_description:
            like_match = re.search(r'([\d,\.]+)\s*(likes?|suka)', meta_description, re.IGNORECASE)
            if like_match: jumlah_like = like_match.group(1)
            
            komen_match = re.search(r'([\d,\.]+)\s*(comments?|komentar)', meta_description, re.IGNORECASE)
            if komen_match: jumlah_komen = komen_match.group(1)

            if not caption or len(caption) < 5:
                caption = meta_description

        # Data Cleaning Caption
        if " on Instagram:" in caption:
            if not username or username == "Username gagal dilacak":
                username = caption.split(" on Instagram:")[0]
            parts = caption.split(' on Instagram: "')
            if len(parts) > 1:
                caption = parts[1]
                if caption.endswith('"'): caption = caption[:-1]
        
        if not username or username == "Username gagal dilacak":
            username = "Username tidak ditemukan"

        # 5. Ekstrak Teks Komentar
        teks_komentar = []
        try:
            semua_span = await page.locator('ul span[dir="auto"]').all_inner_texts()
            for teks in semua_span:
                teks_bersih = teks.strip()
                if teks_bersih and len(teks_bersih) > 3 and teks_bersih not in caption:
                    teks_komentar.append(teks_bersih)
        except Exception:
            pass
        
        kumpulan_komentar = " | ".join(teks_komentar[:3]) if teks_komentar else "-"

        return {
            "Tanggal": tanggal_post,
            "URL Postingan": url,
            "Username": username.strip(),
            "Jumlah Like": jumlah_like,
            "Jumlah Komentar": jumlah_komen,
            "Caption": caption.strip(),
            "Teks Gambar (AI)": teks_dari_gambar,
            "Top Komentar": kumpulan_komentar
        }
        
    except Exception as e:
        print(f"  [X] Gagal mengekstrak {url}. Error: {e}")
        return None
    finally:
        await page.close()

# ==========================================
# PROGRAM UTAMA (MAIN)
# ==========================================
async def main():
    nama_file_input = "Target_Scraping.xlsx"
    
    if not os.path.exists(nama_file_input):
        print(f"\n[X] File {nama_file_input} tidak ditemukan!")
        print("Silakan buat file Excel tersebut dengan kolom 'Username' dan 'Jumlah Post'.")
        return
        
    try:
        print(f"\n📊 Membaca target dari '{nama_file_input}'...")
        df_target = pd.read_excel(nama_file_input, engine='openpyxl')
        
        if 'Username' not in df_target.columns or 'Jumlah Post' not in df_target.columns:
            print("[X] Kolom 'Username' atau 'Jumlah Post' tidak ditemukan di file Excel!")
            return
            
        df_target = df_target.dropna(subset=['Username'])
        print(f"[+] Ditemukan {len(df_target)} akun target untuk diproses.")
    except Exception as e:
        print(f"[X] Gagal membaca Excel: {e}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await siapkan_sesi(browser)

        for index, row in df_target.iterrows():
            akun = str(row['Username']).strip()
            
            try:
                jumlah_post_asli = int(row['Jumlah Post'])
            except:
                jumlah_post_asli = 5

            target_link_diambil = jumlah_post_asli + 3

            print("\n" + "="*50)
            print(f"🔄 MEMPROSES: @{akun} | MENGAMBIL {target_link_diambil} LINK (Mencegah Pinned Post)")
            print("="*50)

            hasil_sementara = []
            daftar_link = await ambil_link_profil(context, akun, target_link_diambil)

            if not daftar_link:
                print(f"[-] Tidak ada link yang bisa diekstrak dari @{akun}. Lanjut ke target berikutnya...")
                continue

            print("\n>>> [EKSTRAKSI] Mulai menyedot data...")
            
            for i, url in enumerate(daftar_link):
                data = await ekstrak_data_postingan(context, url)
                if data:
                    hasil_sementara.append(data)
                
                if i < len(daftar_link) - 1:
                    waktu_jeda = random.uniform(8.0, 15.0)
                    print(f"[*] Delay anti-blokir (post): {waktu_jeda:.1f} detik...")
                    await asyncio.sleep(waktu_jeda)

            if hasil_sementara:
                print("\n⚙️ Melakukan filtering Pinned Post... Mengurutkan data berdasarkan Tanggal terbaru.")
                
                hasil_sementara.sort(key=lambda x: x['Tanggal'], reverse=True)
                hasil_akhir_terbaru = hasil_sementara[:jumlah_post_asli]

                print(f"📊 Menyimpan {len(hasil_akhir_terbaru)} postingan TERBARU untuk @{akun} ke Master Excel...")
                
                df_baru = pd.DataFrame(hasil_akhir_terbaru)
                kolom_urutan = ["Tanggal", "URL Postingan", "Username", "Jumlah Like", "Jumlah Komentar", "Caption", "Teks Gambar (AI)", "Top Komentar"]
                df_baru = df_baru[kolom_urutan]
                
                nama_file_excel = "Dataset_Scraping_Master.xlsx"
                
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
                print(f"\n[*] Selesai dengan @{akun}. Jeda {jeda_akun:.1f} detik sebelum akun berikutnya...")
                await asyncio.sleep(jeda_akun)

        await context.storage_state(path=STATE_FILE)
        await browser.close()
        
        print("\n" + "="*50)
        print("🎉 SEMUA TUGAS SELESAI! Data tersimpan di 'Dataset_Scraping_Master.xlsx'")
        print("="*50)

if __name__ == "__main__":
    asyncio.run(main())