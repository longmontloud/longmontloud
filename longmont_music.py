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

# --- SCORING & FILTERS ---
HARD_EXCLUDE = ['workshop', 'class', 'yoga', 'sip', 'paint', 'watercolor', 'meeting', 'sale', 'market', 'plant', 'meditation', 'trivia', 'bingo', 'poker', 'fitness']
STRONG_MUSIC = ['concert', 'band', 'symphony', 'live music', 'orchestra', 'trio', 'quartet', 'quintet']
SOFT_MUSIC = ['acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'dj', 'solo', 'duo', 'bluegrass', 'folk', 'americana']
TRUSTED_VENUES = ['bricks on main', 'the barn', 'johnsons station', 'supper club', 'wibby', 'left hand', 'abbott & wallace']

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
    combined_text = text.lower()
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in keywords):
            return f"[{genre}] "
    return ""

def get_links(url, domain):
    links = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if any(path in href for path in ['/do/', '/events/', '/calendar-1']):
                if len(href.split('/')) > 2:
                    links.append(domain + href if href.startswith('/') else href)
    except:
        pass
    return list(set(links))

def main():
    print("🚀 Running Scraper (Syntax Fixed)...")
    targets = [
        ("https://www.downtownlongmont.com/events/calendar", "https://www.downtownlongmont.com"),
        ("https://www.johnsonsstation.com/calendar", "https://www.johnsonsstation.com"),
        ("https://www.barnevents.info/events", "https://www.barnevents.info")
    ]
    
    all_links = []
    for url, dom in targets:
        all_links.extend(get_links(url, dom))
    
    cal = Calendar()
    seen = set()
    count = 0

    for link in all_links:
        try:
            res = requests.get(link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 1. Content Extraction
            content = soup.select_one('.details, .event-item-description, .sqs-block-content, article')
            description = content.get_text(" ", strip=True) if content else soup.get_text(" ", strip=True)
            title_tag = soup.find('h1') or soup.find('title')
            title = title_tag.get_text(strip=True) if title_tag else "Unknown Event"
            
            # 2. Filtering
            t_low, d_low = title.lower(), description.lower()
            if any(x in t_low for x in HARD_EXCLUDE): 
                continue
            
            is_trusted = any(v in d_low or v in t_low or v in link for v in TRUSTED_VENUES)
            has_music = any(m in t_low or m in d_low for m in STRONG_MUSIC + SOFT_MUSIC)
            
            if not (is_trusted or has_music): 
                continue

            # 3. Time & Date Logic
            start_dt = None
            script = soup.find('script', type='application/ld+json')
            
            if script:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list): 
                        data = data[0]
                    start_str = data.get('startDate')
                    if start_str:
                        # Clean string and parse
                        iso_str = start_str.split('+')[0].split('Z')[0]
                        raw_dt = datetime.fromisoformat(iso_str)
                        start_dt = LOCAL_TZ.localize(datetime(raw_dt.year, raw_dt.month, raw_dt.day, raw_dt.hour, raw_dt.minute))
                except:
                    pass

            if not start_dt:
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(202\d)', d_low)
                if not date_match: 
                    continue
                dt_obj = datetime.strptime(f"{date_match.group(1)[:3]} {date_match.group(2)} {date_match.group(3)}", "%b %d %Y")
                start_dt = LOCAL_TZ.localize(datetime(dt_obj.year, dt_obj.month, dt_obj.day, 19, 0))

            # 4. Finalize and Add
            genre = detect_genre(title + " " + description)
            fingerprint = f"{start_dt.strftime('%Y%m%d%H')}_{title[:10].lower()}"
            if fingerprint in seen: 
                continue

            e = Event()
            e.name = f"🎵 {genre}{title}"
            e.begin = start_dt
            e.end = start_dt + timedelta(hours=2)
            e.location = "Longmont, CO"
            e.description = f"Link: {link}"
            
            cal.events.add(e)
            seen.add(fingerprint)
            count += 1
            print(f"  [+] Added: {genre}{title}")

        except Exception:
            continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Finished! {count} events saved to {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
