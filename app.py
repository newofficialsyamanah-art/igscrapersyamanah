import concurrent.futures
import csv
import io
import json
import os
import random
import re
import threading
import time
from datetime import datetime
import requests
from flask import Flask, jsonify, render_template, request, Response, send_file
from modules import Get_Followers, Get_Following, Sessions_Manager, db_manager, excel_exporter

app = Flask(__name__)

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

# Global state for background scraping worker (use RLock to prevent any re-entrant deadlocks)
state_lock = threading.RLock()
scrape_thread = None
stop_event = threading.Event()

scraping_state = {
    "is_scraping": False,
    "scrape_type": "followers",
    "target": "",
    "current_count": 0,
    "total_target": 0,
    "progress_pct": 0,
    "status_text": "Menunggu instruksi...",
    "logs": ["[System] Web UI siap digunakan."],
    "error": None,
    "results": [],
    "emails_found_count": 0,
    "db_saved_count": 0,
    "db_type": db_manager.DB_TYPE
}

email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    with state_lock:
        scraping_state["logs"].append(formatted)
        if len(scraping_state["logs"]) > 200:
            scraping_state["logs"] = scraping_state["logs"][-200:]

def extract_profile_details(username, http_session=None):
    """
    Mengambil email publik, jumlah followers, following, dan bio
    melalui Googlebot pre-rendered page.
    """
    details = {
        "email": None,
        "follower_count_str": "-",
        "following_count_str": "-",
        "follower_count": 0,
        "following_count": 0,
    }
    if not username:
        return details
    try:
        url = f"https://www.instagram.com/{username}/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        client = http_session if http_session is not None else requests
        resp = client.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            html = resp.text

            # 1. Parse Followers & Following count dari meta og:description
            m_counts = re.search(r'([\d.,KMkm]+)\s+Followers,\s*([\d.,KMkm]+)\s+Following', html, re.IGNORECASE)
            if m_counts:
                f_str = m_counts.group(1)
                g_str = m_counts.group(2)
                details["follower_count_str"] = f_str
                details["following_count_str"] = g_str
                details["follower_count"] = db_manager.parse_count_to_int(f_str)
                details["following_count"] = db_manager.parse_count_to_int(g_str)

            # 2. Extract Biography
            bio = ""
            m = re.search(r'\"xig_user_by_igid_v2\":(\{.*?\})\s*,\s*\"xig_logged_out', html)
            if m:
                try:
                    data = json.loads(m.group(1))
                    bio = data.get('biography', '')
                except Exception:
                    pass
            if not bio:
                m2 = re.search(r'\"biography\":\"(.*?)\"', html)
                if m2:
                    try:
                        bio = json.loads('"' + m2.group(1) + '"')
                    except Exception:
                        bio = m2.group(1)

            # 3. Search Email in decoded biography
            if bio:
                found = email_pattern.findall(bio)
                clean = [e for e in found if not e.endswith(('.png', '.jpg', '.jpeg', '.js', '.css', '.svg', '.webp'))]
                if clean:
                    details["email"] = clean[0].lower()
                else:
                    obf = re.findall(r'\b[A-Za-z0-9._%+-]+\s*(?:\[at\]|\(at\))\s*[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', bio, re.IGNORECASE)
                    if obf:
                        details["email"] = re.sub(r'\s*(?:\[at\]|\(at\))\s*', '@', obf[0]).lower()

            # 4. Fallback search mailto in HTML
            if not details["email"]:
                for mailto_match in re.finditer(r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', html, re.IGNORECASE):
                    details["email"] = mailto_match.group(1).lower()
                    break

    except Exception:
        pass
    return details


def process_batch_details(user_batch, http_session, target_username, scrape_type="followers", extract_email=True):
    """
    Memeriksa details (followers, following, email, kategori) secara concurrent
    dan langsung menyimpan ke database server dengan deduplikasi otomatis.
    """
    if not user_batch:
        return

    for u in user_batch:
        is_verified = bool(u.get("is_verified"))
        is_private = bool(u.get("is_private"))
        if is_verified:
            u["category_type"] = "Terverifikasi"
        elif is_private:
            u["category_type"] = "Akun Privat (Follower Biasa)"
        else:
            u["category_type"] = "Follower Biasa"

        u["target_source"] = target_username
        u["scrape_type"] = scrape_type
        if "follower_count_str" not in u:
            u["follower_count_str"] = "-"
        if "following_count_str" not in u:
            u["following_count_str"] = "-"

    # Concurrently fetch detailed follower count and email
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(extract_profile_details, u.get("username"), http_session): u
            for u in user_batch
        }
        for future in concurrent.futures.as_completed(future_map):
            u = future_map[future]
            try:
                res = future.result()
                u["follower_count_str"] = res["follower_count_str"]
                u["following_count_str"] = res["following_count_str"]
                u["follower_count"] = res["follower_count"]
                u["following_count"] = res["following_count"]
                if extract_email and res.get("email"):
                    u["email"] = res["email"]
                    with state_lock:
                        scraping_state["emails_found_count"] += 1
                    add_log(f"[📧] Email publik ditemukan: @{u.get('username')} -> {res['email']}")
                else:
                    if "email" not in u:
                        u["email"] = None
            except Exception:
                pass

    # Upsert directly to Database (PostgreSQL / SQLite) - Deduplication guaranteed!
    try:
        saved_count = db_manager.upsert_batch(user_batch, target_source=target_username, scrape_type=scrape_type)
        with state_lock:
            scraping_state["db_saved_count"] += saved_count
        add_log(f"[💾] +{saved_count} akun tersimpan ke Database ({db_manager.DB_TYPE.upper()}) tanpa duplikasi.")
    except Exception as dbe:
        add_log(f"[!] Error simpan database: {dbe}")


def run_scraper(target_username, scrape_limit, session_id, scrape_type="followers", speed="fast", extract_email=True):
    global stop_event
    is_following = (scrape_type == "following")
    type_label = "following" if is_following else "pengikut (followers)"
    scraper_mod = Get_Following if is_following else Get_Followers

    # Speed mode delays (min, max) in seconds
    delays = {
        "fast": (1.0, 1.5),
        "normal": (2.0, 3.0),
        "safe": (4.0, 5.0)
    }
    min_delay, max_delay = delays.get(speed, (1.0, 1.5))

    with state_lock:
        scraping_state["is_scraping"] = True
        scraping_state["scrape_type"] = scrape_type
        scraping_state["target"] = target_username
        scraping_state["total_target"] = scrape_limit
        scraping_state["current_count"] = 0
        scraping_state["progress_pct"] = 0
        scraping_state["error"] = None
        scraping_state["results"] = []
        scraping_state["emails_found_count"] = 0
        scraping_state["db_saved_count"] = 0
        scraping_state["status_text"] = f"Mempersiapkan koneksi..."

    speed_names = {"fast": "Cepat (1.0 - 1.5s)", "normal": "Normal (2.0 - 3.0s)", "safe": "Aman (4.0 - 5.0s)"}
    add_log(f"Memulai scraping {type_label} untuk @{target_username} (Target: {scrape_limit if scrape_limit > 0 else 'Semua'}, Mode: {speed_names.get(speed, speed)})...")

    http_session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
    http_session.mount("https://", adapter)
    http_session.mount("http://", adapter)

    try:
        # Step 1: Ambil User ID target
        with state_lock:
            scraping_state["status_text"] = f"Mencari User ID untuk @{target_username}..."

        user_id, count_total = scraper_mod.get_userid(target_username, session_id, http_session=http_session, log_callback=add_log)
        if not user_id:
            err_msg = f"User ID untuk @{target_username} tidak ditemukan atau akun di-private."
            with state_lock:
                scraping_state["is_scraping"] = False
                scraping_state["status_text"] = "Gagal menemukan target"
                scraping_state["error"] = err_msg
            add_log(f"[!] {err_msg}")
            return

        stat_label = "Total Following" if is_following else "Total Followers"
        add_log(f"[+] Ditemukan User ID: {user_id}" + (f" ({stat_label}: {count_total})" if count_total else ""))
        
        with state_lock:
            scraping_state["status_text"] = f"Mengambil data {type_label} (Batch 1)..."
            scraping_state["emails_found_count"] = 0

        # Step 2: Pagination scraping
        users = []
        existing_ids = set()
        seen_max_ids = set()
        limit = scrape_limit if scrape_limit > 0 else float("inf")
        params = {
            "count": "25",
        }
        if not is_following:
            params["search_surface"] = "follow_list_page"

        # First page request
        add_log(f"[i] Mengambil Halaman 1 dari Instagram...")
        resp = scraper_mod.req(params, user_id, target_username, session_id, http_session=http_session, log_callback=add_log)
        if not resp or resp.status_code != 200:
            err_msg = f"Request pertama gagal dengan status {resp.status_code if resp else 'koneksi error'}"
            with state_lock:
                scraping_state["is_scraping"] = False
                scraping_state["status_text"] = "Gagal menghubungi Instagram"
                scraping_state["error"] = err_msg
            add_log(f"[!] {err_msg}")
            return

        result = resp.json()
        new_users = result.get("users", [])
        page_1_users = []
        for u in new_users:
            uid = str(u.get("id") or u.get("pk"))
            if uid not in existing_ids:
                existing_ids.add(uid)
                page_1_users.append(u)
                users.append(u)
                if len(users) >= limit:
                    break

        if page_1_users:
            with state_lock:
                scraping_state["status_text"] = f"Mengekstrak followers, following & email (Halaman 1)..."
            process_batch_details(page_1_users, http_session, target_username, scrape_type, extract_email)

        with state_lock:
            scraping_state["current_count"] = len(users)
            scraping_state["results"] = list(users)
            if limit != float("inf"):
                scraping_state["progress_pct"] = min(100, int((len(users) / limit) * 100))
            else:
                scraping_state["progress_pct"] = min(95, int(len(users) / 5))

        target_display = f"/{scrape_limit}" if scrape_limit > 0 else ""
        add_log(f"[+] Halaman 1 selesai: +{len(users)} data (Total: {len(users)}{target_display}).")

        # Check verified limit for followers (Instagram restricts verified accounts to 50 max)
        if not is_following and result.get("page_size") == 50 and not result.get("big_list"):
            add_log(f"[!] Akun @{target_username} terverifikasi (Meta membatasi maks 50 follower via API).")

        # Pagination loop
        page_num = 1
        while result.get("next_max_id") and len(users) < limit and not stop_event.is_set():
            next_id = str(result.get("next_max_id"))
            if next_id in seen_max_ids:
                add_log(f"[i] Paginasi Instagram berulang (next_max_id: {next_id}). Scraping selesai.")
                break
            seen_max_ids.add(next_id)
            params["max_id"] = next_id

            page_num += 1

            # Live countdown delay to prevent stuck impression and avoid blocking
            delay = round(random.uniform(min_delay, max_delay), 1)
            end_time = time.time() + delay
            while time.time() < end_time and not stop_event.is_set():
                rem = max(0.0, end_time - time.time())
                with state_lock:
                    scraping_state["status_text"] = f"Jeda {rem:.1f}s sebelum mengambil Halaman {page_num}..."
                time.sleep(min(0.2, rem))

            if stop_event.is_set():
                break

            with state_lock:
                scraping_state["status_text"] = f"Mengambil Halaman {page_num}..."

            add_log(f"[i] Mengambil Halaman {page_num}...")
            resp = scraper_mod.req(params, user_id, target_username, session_id, http_session=http_session, log_callback=add_log)
            if not resp or resp.status_code != 200:
                add_log(f"[!] Gagal mengambil Halaman {page_num}. Menyimpan data yang sudah didapat.")
                break

            result = resp.json()
            batch = result.get("users", [])
            if not batch:
                add_log(f"[i] Halaman {page_num} kosong. Scraping selesai.")
                break

            new_in_batch_users = []
            for u in batch:
                uid = str(u.get("id") or u.get("pk"))
                if uid not in existing_ids:
                    existing_ids.add(uid)
                    new_in_batch_users.append(u)
                    users.append(u)
                    if len(users) >= limit:
                        break

            if not new_in_batch_users:
                add_log(f"[i] Tidak ada data pengguna baru di Halaman {page_num}. Scraping selesai.")
                break

            with state_lock:
                scraping_state["status_text"] = f"Mengekstrak followers, following & email (Halaman {page_num})..."
            process_batch_details(new_in_batch_users, http_session, target_username, scrape_type, extract_email)

            with state_lock:
                scraping_state["current_count"] = len(users)
                scraping_state["results"] = list(users)
                if limit != float("inf"):
                    scraping_state["progress_pct"] = min(100, int((len(users) / limit) * 100))

            add_log(f"[+] Halaman {page_num} selesai: +{len(new_in_batch_users)} data (Total: {len(users)}{target_display}).")

            if len(users) >= limit:
                break

        # Save to disk JSON file
        scraper_mod.write_json_data(users, target_username)

        with state_lock:
            scraping_state["is_scraping"] = False
            scraping_state["progress_pct"] = 100
            email_info = f" ({scraping_state['emails_found_count']} email publik)" if extract_email else ""
            db_info = f", {scraping_state['db_saved_count']} disimpan ke DB"
            if stop_event.is_set():
                scraping_state["status_text"] = f"Dihentikan pengguna. {len(users)} {type_label} didapat{email_info}{db_info}."
                add_log(f"[i] Scraping dihentikan. Berhasil mengumpulkan {len(users)} {type_label}{email_info}{db_info}.")
            else:
                scraping_state["status_text"] = f"Selesai! {len(users)} {type_label} berhasil diambil{email_info}{db_info}."
                add_log(f"[+] SELESAI! Berhasil mengumpulkan total {len(users)} {type_label}{email_info}{db_info}.")

    except Exception as e:
        with state_lock:
            scraping_state["is_scraping"] = False
            scraping_state["status_text"] = "Terjadi kesalahan"
            scraping_state["error"] = str(e)
        add_log(f"[!] Error saat scraping: {str(e)}")
    finally:
        try:
            http_session.close()
        except Exception:
            pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    with state_lock:
        return jsonify(scraping_state)


@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    sessions = Sessions_Manager.load_sessions()
    session_list = [{"username": s[0], "session_id": s[1]} for s in sessions]
    return jsonify({"sessions": session_list})


@app.route("/api/sessions/add", methods=["POST"])
def add_session():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    session_id = data.get("session_id", "").strip()

    if not session_id:
        return jsonify({"success": False, "message": "Session ID wajib diisi"}), 400

    is_valid, msg = Sessions_Manager.verify_session(username, session_id)
    if is_valid:
        sessions = Sessions_Manager.load_sessions()
        # Remove duplicate if exists
        sessions = [s for s in sessions if s[1] != session_id]
        clean_user = username or session_id.split(":")[0]
        sessions.insert(0, (clean_user, session_id))
        Sessions_Manager.save_sessions(sessions)
        return jsonify({"success": True, "message": msg})
    else:
        return jsonify({"success": False, "message": msg})


@app.route("/api/sessions/delete", methods=["POST"])
def delete_session():
    data = request.get_json() or {}
    idx = data.get("index")
    sessions = Sessions_Manager.load_sessions()
    if idx is not None and 0 <= idx < len(sessions):
        del sessions[idx]
        Sessions_Manager.save_sessions(sessions)
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Index tidak valid"}), 400


@app.route("/api/scrape/start", methods=["POST"])
def start_scrape():
    global scrape_thread, stop_event
    with state_lock:
        if scraping_state["is_scraping"]:
            if scrape_thread and not scrape_thread.is_alive():
                scraping_state["is_scraping"] = False
            else:
                return jsonify({"success": False, "message": "Scraping sedang berjalan! Silakan tunggu atau klik Stop."}), 400

    data = request.get_json() or {}
    target = data.get("target", "").strip().lstrip("@")
    limit = int(data.get("limit", 100))
    scrape_type = data.get("scrape_type", "followers").strip().lower()
    if scrape_type not in ["followers", "following"]:
        scrape_type = "followers"

    extract_email = bool(data.get("extract_email", True))

    if not target:
        return jsonify({"success": False, "message": "Username target tidak boleh kosong"}), 400

    sessions = Sessions_Manager.load_sessions()
    if not sessions:
        return jsonify({"success": False, "message": "Belum ada sesi tersimpan. Silakan tambahkan session ID terlebih dahulu!"}), 400

    active_session_id = sessions[0][1]

    speed = data.get("speed", "fast").strip().lower()
    if speed not in ["fast", "normal", "safe"]:
        speed = "fast"

    stop_event.clear()
    scrape_thread = threading.Thread(target=run_scraper, args=(target, limit, active_session_id, scrape_type, speed, extract_email), daemon=True)
    scrape_thread.start()

    type_name = "following" if scrape_type == "following" else "followers"
    email_note = " (ekstrak email & profil aktif)" if extract_email else ""
    return jsonify({"success": True, "message": f"Mulai scraping {type_name} untuk @{target}{email_note}"})


@app.route("/api/scrape/stop", methods=["POST"])
def stop_scrape():
    global stop_event
    stop_event.set()
    add_log("[User] Menerima instruksi penghentian...")
    return jsonify({"success": True})


@app.route("/api/database/stats", methods=["GET"])
def database_stats():
    """Mengembalikan statistik database server (PostgreSQL/SQLite)."""
    return jsonify(db_manager.get_stats())


@app.route("/api/database/users", methods=["GET"])
def database_users():
    """Mengembalikan daftar akun terbaru yang tersimpan di database."""
    limit = int(request.args.get("limit", 100))
    users = db_manager.get_recent_users(limit=limit)
    return jsonify({"users": users})


@app.route("/api/export/excel", methods=["GET"])
def export_excel():
    username = request.args.get("username", "").strip()
    scrape_type = request.args.get("scrape_type", "").strip().lower()

    with state_lock:
        if not scrape_type:
            scrape_type = scraping_state.get("scrape_type", "followers")
        users = list(scraping_state["results"])

    base_dir = "FOLLOWING_DATA" if scrape_type == "following" else "FOLLOWERS_DATA"
    json_name = "following.json" if scrape_type == "following" else "followers.json"

    # Fallback 1: File disk
    if not users and username:
        file_path = os.path.join(base_dir, username, json_name)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                users = json.load(f)

    # Fallback 2: Database Server
    if not users:
        users = db_manager.get_all_for_export(target_source=username if username else None, scrape_type=scrape_type if scrape_type else None)

    if not users:
        return jsonify({"error": "Tidak ada data untuk diexport ke Excel"}), 404

    buf = excel_exporter.generate_excel_data(users, target_username=username or "data", scrape_type=scrape_type)
    filename = f"{username or scrape_type}_{scrape_type}.xlsx"
    return Response(
        buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    username = request.args.get("username", "").strip()
    scrape_type = request.args.get("scrape_type", "").strip().lower()

    with state_lock:
        if not scrape_type:
            scrape_type = scraping_state.get("scrape_type", "followers")
        users = list(scraping_state["results"])

    base_dir = "FOLLOWING_DATA" if scrape_type == "following" else "FOLLOWERS_DATA"
    json_name = "following.json" if scrape_type == "following" else "followers.json"

    # If memory is empty, check if saved file exists
    if not users and username:
        file_path = os.path.join(base_dir, username, json_name)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                users = json.load(f)

    if not users:
        users = db_manager.get_all_for_export(target_source=username if username else None, scrape_type=scrape_type if scrape_type else None)

    if not users:
        return jsonify({"error": "Tidak ada data untuk diexport"}), 404

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow([
        "No", "Username", "Full Name", "Kategori / Status", "Followers", "Following",
        "Email", "Status Akun", "Is Verified", "User ID", "Target Source", "Profile URL"
    ])

    for i, u in enumerate(users):
        uname = u.get("username", "")
        writer.writerow([
            i + 1,
            uname,
            u.get("full_name", ""),
            u.get("category_type") or "Follower Biasa",
            u.get("follower_count_str") or u.get("follower_count") or "-",
            u.get("following_count_str") or u.get("following_count") or "-",
            u.get("email") or "-",
            "Private" if u.get("is_private") else "Public",
            "Yes" if u.get("is_verified") else "No",
            u.get("id") or u.get("pk", ""),
            u.get("target_source") or username,
            f"https://www.instagram.com/{uname}/"
        ])

    output = si.getvalue()
    filename = f"{username or scrape_type}_{scrape_type}.csv"
    return Response(
        output,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/api/export/json", methods=["GET"])
def export_json():
    username = request.args.get("username", "").strip()
    scrape_type = request.args.get("scrape_type", "").strip().lower()

    with state_lock:
        if not scrape_type:
            scrape_type = scraping_state.get("scrape_type", "followers")
        users = list(scraping_state["results"])

    base_dir = "FOLLOWING_DATA" if scrape_type == "following" else "FOLLOWERS_DATA"
    json_name = "following.json" if scrape_type == "following" else "followers.json"

    if not users and username:
        file_path = os.path.join(base_dir, username, json_name)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                users = json.load(f)

    if not users:
        users = db_manager.get_all_for_export(target_source=username if username else None, scrape_type=scrape_type if scrape_type else None)

    if not users:
        return jsonify({"error": "Tidak ada data untuk diexport"}), 404

    output = json.dumps(users, indent=2, ensure_ascii=False)
    filename = f"{username or scrape_type}_{scrape_type}.json"
    return Response(
        output,
        mimetype="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Instagram Scraper Suite Web Server")
    parser.add_argument("--port", "-p", type=int, default=int(os.environ.get("PORT", 5000)), help="Port to listen on")
    parser.add_argument("--host", "-H", type=str, default=os.environ.get("HOST", "127.0.0.1"), help="Host to listen on")
    args = parser.parse_args()

    print("\n" + "=" * 50)
    print("  [+] Instagram Scraper Suite Web Dashboard Berjalan")
    print(f"  [*] Database Active: {db_manager.DB_TYPE.upper()}")
    print(f"  [*] Buka di browser: http://{args.host}:{args.port}")
    print("=" * 50 + "\n")
    app.run(host=args.host, port=args.port, debug=False)
