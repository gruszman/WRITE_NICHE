import os
import sqlite3
import requests
import subprocess
from datetime import datetime

# Konfiguracja
DB_PATH = "mogul_database.db"
TELEGRAM_BOT_TOKEN = "8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q"  # Podmień na swój token z BotFather
TELEGRAM_CHAT_ID = "738220792"          # Podmień na swój Chat ID
NICHE_FILE = "nisze.txt"

def init_db():
    """Inicjalizacja lokalnej bazy danych SQLite"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            content TEXT,
            status TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_next_niche():
    """Pobiera pierwszą niszę z pliku nisze.txt, której jeszcze nie ma w bazie"""
    if not os.path.exists(NICHE_FILE):
        # Tworzy przykładowy plik z niszami, jeśli go nie ma
        with open(NICHE_FILE, "w", encoding="utf-8") as f:
            f.write("commercial solar panel cleaning services in Austin TX\n")
            f.write("emergency commercial locksmith services in Denver CO\n")
            f.write("industrial epoxy floor coating contractors in Chicago IL\n")
            f.write("commercial kitchen hood cleaning services Seattle WA\n")
            f.write("commercial asphalt paving contractors Phoenix AZ\n")
            
    with open(NICHE_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for niche in lines:
        slug = niche.lower().replace(" ", "-").replace(",", "").replace("/", "-")
        cursor.execute("SELECT id FROM pages WHERE slug = ?", (slug,))
        if not cursor.fetchone():
            conn.close()
            return niche, slug
            
    conn.close()
    return None, None

def generate_page_content(niche_topic):
    """Generuje strukturę i treść strony pod kątem pSEO dla rynku angielskiego"""
    title = f"Best 2026 Guide for {niche_topic}"
    markdown_content = f"""---
title: "{title}"
date: "{datetime.now().isoformat()}"
description: "Comprehensive automated guide and directory for {niche_topic}."
---

# {title}

Welcome to the definitive, data-driven guide for **{niche_topic}**. 

## Top Verified Providers & Data Breakdown
* **Primary Focus:** High-intent local search queries matching English-speaking commercial requirements.
* **Average Market Rate:** Verified benchmarks aggregated in real-time.
* **Key Recommendation:** [Check Top Partner Offer Here](https://affiliate-link.com)

---
*Generated automatically by Mogul Bot Engine.*
"""
    return title, markdown_content

def save_and_publish(slug, title, content):
    """Zapisuje stronę jako plik Markdown i aktualizuje bazę danych"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    created_at = datetime.now().isoformat()
    
    cursor.execute("""
        INSERT INTO pages (slug, title, content, status, created_at) 
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET 
            title = excluded.title,
            content = excluded.content,
            created_at = excluded.created_at
    """, (slug, title, content, 'published', created_at))
    
    conn.commit()
    conn.close()
        
    # Zapisz plik do folderu projektu strony (np. Astro /src/content/ lub /content/)
    file_path = f"./output_site/content/{slug}.md"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"[SUKCES] Zapisano plik i zaktualizowano bazę: {slug}")

def git_auto_commit_push(slug):
    """Automatycznie wykonuje git add, commit i push przy użyciu Git Portable"""
    GIT_PATH = r"D:\archiwum\PortableGit\cmd\git.exe"
    try:
        subprocess.run([GIT_PATH, "add", "."], check=True)
        subprocess.run([GIT_PATH, "commit", "-m", f"Mogul Bot: Auto-published page {slug}"], check=True)
        subprocess.run([GIT_PATH, "push", "origin", "main"], check=True)
        print("[GIT] Zmiany pomyślnie wysłane na GitHub!")
    except Exception as e:
        print(f"[GIT BŁĄD]: {e}")


def send_telegram_alert(message):
    """Wysyła powiadomienie na Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Błąd wysyłania Telegrama: {e}")

if __name__ == "__main__":
    init_db()
    
    # 1. Pobierz kolejną nieprzetworzoną niszę z pliku
    niche, slug = get_next_niche()
    
    if niche:
        print(f"[INFO] Przetwarzam niszę: {niche}")
        # 2. Wygeneruj treść
        title, content = generate_page_content(niche)
        # 3. Zapisz w bazie i jako plik Markdown
        save_and_publish(slug, title, content)
        # 4. Wyślij automatycznie na GitHub (co uruchomi Cloudflare Pages)
        git_auto_commit_push(slug)
        # 5. Powiadom na Telegramie
        send_telegram_alert(f"🚀 *Mogul Bot Alert*\nStrona wygenerowana i wdrożona:\n`{title}`")
    else:
        print("[INFO] Wszystkie nisze z pliku nisze.txt zostały już przetworzone!")