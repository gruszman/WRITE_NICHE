import time
import requests
import xml.etree.ElementTree as ET
import urllib.parse
from datetime import datetime

# --- KONFIGURACJA ---
TELEGRAM_TOKEN = "8488356348:AAHpjRHW4X-NPJV0C-BJVV21-30RoLctu1Q"  # Twój token z BotFather
TELEGRAM_CHAT_ID = "@promo_2_0_2_6"                              # Twój kanał Telegram

# Twoje identyfikatory afiliacyjne
AMAZON_TAG = "tak0ee59-21"                                       # Twój tag Amazon
XKOM_SM_CODE = "Smo7twy8"                                        # Twój kod kampanii SalesMasters dla x-kom
WEBEPARTNERS_BASE_LINK = "https://webep1.com/go/56b35ffd87"      # Twój bazowy link Webepartners

# Sprawdzone i stabilne źródła RSS (bez błędów 404)
FEED_URLS = [
    "https://lowcygier.pl/feed/",
    "https://9to5toys.com/feed/",
    "https://www.engadget.com/rss.xml",
    "https://www.tomsguide.com/rss.xml",
    "https://www.androidcentral.com/rss.xml"
]

# Zbiór zapobiegający wysyłaniu duplikatów
seen_deals = set()

def build_smart_affiliate_link(original_url: str) -> str:
    """
    Rozpoznaje sklep i automatycznie dopasowuje odpowiedni reflink:
    - Amazon -> tag afiliacyjny
    - x-kom / al.to -> parametr SalesMasters (?sm=...)
    - Inne polskie sklepy -> Webepartners (Deep Link)
    """
    if not original_url:
        return ""
    
    # 1. Obsługa Amazonu
    if "amazon." in original_url:
        base_url = original_url.split("?")[0]
        return f"{base_url}?tag={AMAZON_TAG}"
    
    # 2. Obsługa x-kom / al.to (SalesMasters z parametrem ?sm=)
    if "x-kom.pl" in original_url or "al.to" in original_url:
        clean_url = original_url.split("?")[0]
        return f"{clean_url}?sm={XKOM_SM_CODE}"
    
    # 3. Obsługa pozostałych sklepów w Polsce przez Webepartners (Deep Link)
    supported_shops = ["mediaexpert.pl", "euro.com.pl", "komputronik.pl", "empik.com", "mediamarkt.pl"]
    if any(shop in original_url for shop in supported_shops):
        encoded_url = urllib.parse.quote(original_url, safe='')
        return f"{WEBEPARTNERS_BASE_LINK}?url={encoded_url}"
        
    return None

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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Błąd wysyłania na Telegram: {e}")
        return None

def fetch_and_post_deals():
    """Pobiera okazje ze wszystkich źródeł, filtruje, sprawdza duplikaty i publikuje."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    print(f"\n--- [{datetime.now().strftime('%H:%M:%S')}] Rozpoczynam sprawdzanie źródeł RSS ---")
    
    new_deals_count = 0
    
    for feed_url in FEED_URLS:
        try:
            response = requests.get(feed_url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"[POMINIĘTO] Źródło {feed_url} zwróciło status: {response.status_code}")
                continue
            
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError:
                print(f"[POMINIĘTO] Źródło {feed_url} zwróciło niepoprawny format XML.")
                continue
            
            items = root.findall(".//item")
            
            for item in reversed(items):
                title_elem = item.find("title")
                link_elem = item.find("link")
                date_elem = item.find("pubDate")
                
                title = title_elem.text if title_elem is not None and title_elem.text else "Nowa okazja!"
                raw_link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                pub_date = date_elem.text if date_elem is not None and date_elem.text else ""
                
                # Generowanie inteligentnego reflinku dopasowanego do sklepu
                link = build_smart_affiliate_link(raw_link)
                
                # Warunek: link musi obsługiwać afiliację ORAZ nie być duplikatem
                if link and link not in seen_deals:
                    seen_deals.add(link)
                    new_deals_count += 1
                    
                    message = (
                        f"🔥 <b>GORĄCA PROMOCJA!</b>\n\n"
                        f"📦 <b>{title}</b>\n\n"
                        f"🔗 <a href='{link}'>Przejdź do oferty</a>\n\n"
                        f"<i>Data: {pub_date[:25]}</i>"
                    )
                    
                    send_telegram_message(message)
                    print(f"[WYSŁANO OKAZJĘ]: {title[:50]}...")
                    time.sleep(2)
                    
        except Exception as e:
            print(f"[BŁĄD] Problem ze źródłem {feed_url}: {e}")
            
    print(f"--- Sprawdzanie zakończone. Wysłano nowych ofert: {new_deals_count} ---")

# --- PĘTLA GŁÓWNA 24/7 ---
if __name__ == "__main__":
    print("Wieloplatformowy bot afiliacyjny (Amazon + x-kom + Webepartners) uruchomiony 24/7...")
    
    while True:
        try:
            fetch_and_post_deals()
        except Exception as e:
            print(f"Wystąpił nieoczekiwany błąd w pętli głównej: {e}")
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Bot zasypia na 15 minut...")
        time.sleep(900)