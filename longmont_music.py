import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re
import json

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- FILTERS ---
HARD_EXCLUDE = ['workshop', 'class', 'yoga', 'sip', 'paint', 'watercolor', 'meeting', 'sale', 'market', 'plant', 'meditation', 'trivia', 'bingo', 'poker', 'fitness']
MUSIC_KEYS = ['music', 'band', 'concert', 'live music', 'singer', 'songwriter', 'jazz', 'rock', 'blues', 'dj', 'trio', 'duo', 'acoustic']
TRUSTED_DOMAINS = ['barnevents.info', 'johnsonsstation.com', 'supperclub']

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band', 'bebop'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge', 'psychedelic'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'americana'],
    'Blues': ['blues', 'harmonica', 'soul'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music', 'rave', 'edm', 'techno'],
    'Classical': ['orchestra', 'symphony', 'classical', 'quartet', 'chamber'],
    'Country': ['country', 'western', 'honky tonk', 'cowboy']
}

def detect_genre(text):
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", text.lower()) for k in keywords):
            return f"[{genre}] "
    return ""

def get_links(url, domain):
    links = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if any(path in href for path in ['/do/', '/events/', '/calendar']):
                if len(href.split('/')) > 2:
                    links.append(domain + href if href.startswith('/') else href)
    except Exception as e:
        print(f"Error fetching links from {url}: {e}")
    return list(set(links))

def main():
    print("🚀 Starting Diagnostic Scraper...")
    targets = [
        ("https://www.downtownlongmont.com/events/calendar", "https://www.downtownlongmont.com"),
        ("https://www.johnsonsstation.com/calendar", "https://www.johnsonsstation.com"),
        ("https://www.barnevents.info/events", "https://www.barnevents.info")
    ]
    
    all_links = []
    for url, dom in targets:
        all_links.extend(get_links(url, dom))
    
    print(f"Found {len(all_links)} potential links. Analyzing...")

    cal = Calendar()
    seen = set()
    count = 0

    for link in all_links:
        try:
            res = requests.get(link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Content Extraction
            title_tag = soup.find('h1') or soup.find('title')
            title = title_tag.get_text(strip=True) if title_tag else "Unknown"
            description = soup.get_text(" ", strip=True).lower()
            
            # Diagnostic Log
            # print(f"Checking: {title[:30]}...")

            # 1. Exclusion Check
            if any(x in title.lower() for x in HARD_EXCLUDE):
                continue
            
            # 2. Inclusion Check
            is_trusted = any(d in link for d in TRUSTED_DOMAINS)
            is_music = any(m in title.lower() or m in description for m in MUSIC_KEYS)
            
            if not (is_trusted or is_music):
                continue

            # 3. Date Discovery
            start_dt = None
            
            # Method A: JSON-LD (The gold standard)
            script = soup.find('script', type='application/ld+json')
            if script:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list): data = data[0]
                    s_str = data.get('startDate') or data.get('datePublished')
                    if s_str:
                        raw = datetime.fromisoformat(s_str.split('+')[0].split('Z')[0])
                        start_dt = LOCAL_TZ.localize(raw)
                except: pass

            # Method B: Regex (The fallback)
            if not start_dt:
                # Look for Month + Day
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})', description)
                if date_match:
                    month_str = date_match.group(1)[:3].title()
                    day_val = int(date_match.group(2))
                    # Use current year (2026)
                    start_dt = LOCAL_TZ.localize(datetime(2026, datetime.strptime(month_str, "%b").month, day_val, 19, 0))

            if not start_dt:
                # print(f"  Skipped: Could not find date for {title}")
                continue

            # 4. Finalize
            genre = detect_genre(title + " " + description)
            fingerprint = f"{start_dt.strftime('%Y%m%d')}_{title[:15].lower()}"
            
            if fingerprint in seen: continue

            e = Event()
            e.name = f"🎵 {genre}{title}"
            e.begin = start_dt
            e.end = start_dt + timedelta(hours=2)
            e.location = "Longmont, CO"
            e.description = f"Source: {link}"
            
            cal.events.add(e)
            seen.add(fingerprint)
            count += 1
            print(f"  [+] Added: {title} on {start_dt.strftime('%b %d')}")

        except Exception as e:
            continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Total Events Found: {count}")

if __name__ == "__main__":
    main()
