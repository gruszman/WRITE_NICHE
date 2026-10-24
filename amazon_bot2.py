import time
import requests
import xml.etree.ElementTree as ET

# --- KONFIGURACJA ---
TELEGRAM_TOKEN = "8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1"  # Twój token z BotFather
TELEGRAM_CHAT_ID = "@promo_2_0_2_6"                              # Twój kanał
AMAZON_TAG = "tak0ee59-21"                                       # Twój tag afiliacyjny Amazon

# Globalne i lokalne źródła RSS z promocjami i elektroniką
FEED_URLS = [
    "https://lowcygier.pl/feed/",
    "https://dealdump.com/rss.php",
    "https://9to5toys.com/feed/",
    "https://bgr.com/deals/feed/",
    "https://www.engadget.com/rss.xml",
    "https://www.tomsguide.com/rss.xml",
    "https://www.androidcentral.com/rss.xml"
]

# Zbiór zapobiegający wysyłaniu duplikatów
seen_deals = set()

def generate_amazon_affiliate_link(original_url: str) -> str:
    """Dokleja Twój tag afiliacyjny do linku Amazon."""
    if not original_url:
        return ""
    if "amazon." in original_url:
        base_url = original_url.split("?")[0]
        return f"{base_url}?tag={AMAZON_TAG}"
    return original_url

def send_telegram_message(text: str):
    """Wysyła sformatowaną wiadomość HTML na kanał Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Błąd wysyłania na Telegram: {e}")
        return None

def fetch_and_post_deals():
    """Pobiera okazje ze wszystkich źródeł, filtruje Amazon i publikuje."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for feed_url in FEED_URLS:
        try:
            response = requests.get(feed_url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"[Pomijano] Źródło {feed_url} zwróciło status: {response.status_code}")
                continue
            
            root = ET.fromstring(response.content)
            items = root.findall(".//item")  # Uniwersalne wyszukiwanie elementów item w RSS/Atom
            
            for item in reversed(items):
                title_elem = item.find("title")
                link_elem = item.find("link")
                date_elem = item.find("pubDate")
                
                title = title_elem.text if title_elem is not None and title_elem.text else "Nowa okazja!"
                
                # Czasami w RSS link jest zapisany w innej strukturze lub atrybucie
                raw_link = ""
                if link_elem is not None and link_elem.text:
                    raw_link = link_elem.text.strip()
                
                pub_date = date_elem.text if date_elem is not None and date_elem.text else ""
                
                # Filtr: bierzemy pod uwagę tylko linki prowadzące do Amazonu
                if "amazon." not in raw_link:
                    continue
                
                # Automatyczna zamiana na Twój reflink
                link = generate_amazon_affiliate_link(raw_link)
                
                if link and link not in seen_deals:
                    seen_deals.add(link)
                    
                    message = (
                        f"🔥 <b>GLOBALNA OKAZJA AMAZON!</b>\n\n"
                        f"📦 <b>{title}</b>\n\n"
                        f"🔗 <a href='{link}'>Przejdź do oferty</a>\n\n"
                        f"<i>Data: {pub_date[:25]}</i>"
                    )
                    
                    wynik = send_telegram_message(message)
                    print(f"[Wysłano Amazon]: {title}")
                    time.sleep(2)
                    
        except Exception as e:
            # Ignorujemy błędy parsowania pojedynczego feedu, aby skrypt działał stabilnie
            pass

# --- PĘTLA GŁÓWNA 24/7 ---
if __name__ == "__main__":
    print("Globalny bot afiliacyjny Amazon uruchomiony w tle...")
    while True:
        fetch_and_post_deals()
        # Sprawdzaj wszystkie źródła co 15 minut (900 sekund)
        time.sleep(900)