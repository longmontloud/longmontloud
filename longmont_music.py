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
EXCLUDE = [
    'karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'meeting', 'retail', 'watercolor', 'exhibition', 'the golden bee', 'sing-along', 'easel', 'studio tour', 'art materials', 'seminar', 'documentary',
    'comedy', 'yoga', 'poker', 'drawing class', 'craft class', 'create club', 'teen', 'crochet', 'wine dinner', 'tasting', 'pairing', 'prix fixe', 'shakespeare', 'happy day plants', 'headshot', 'stitch', 'embroidery',
    'storytime', 'book club', 'knitting', 'market', 'board game', 'meditation', 'speaker series', 'stationery', 'wolf & wren', 'talk', 'tarot', 'blackbird house', 'barbed wire books', 'dining', 'crafts & cocktails', 
    'teacher', 'discussion', 'ragen', 'networking', 'discovery days', 'uke jam', 'painting', 'sip', 'wines', '720-453-4733', 'date night', '303-651-8374', 'open-house', 'open house', 'crackpots', 'bubbly', 'joke', 'potting',
    'your stage', 'tangerine', 'composition', 'ballet', 'dance class', 'movie', 'bubbles', 'sewing', 'brunch', 'mimosas', 'bellinis', 'denim day', 'poetry night', 'poetry slam', 'sewing', 'sew', 'guest speakers', 'bloody mary',
]

MUSIC_KEYWORDS = [
    'live music', 'band', 'concert', 'symphony', 'acoustic', 'jazz', 'supper club',
    'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj',
    'rave', 'grunge', 'folk', 'metal', 'punk', 'hip-hop', 'live music', 'brass'
]

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band', 'bebop'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge', 'psychedelic'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'americana'],
    'Blues': ['blues', 'harmonica', 'soul'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music', 'rave', 'edm', 'techno'],
    'Classical': ['orchestra', 'symphony', 'classical', 'quartet', 'chamber'],
    'Country': ['country', 'western', 'honky tonk', 'cowboy']
}

TRUSTED_DOMAINS = ['barnevents.info', 'johnsonsstation.com', 'supperclub']

def detect_genre(text):
    t = text.lower()
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", t) for k in keywords):
            return f"[{genre}] "
    return ""

def main():
    print("🚀 Running Targeted Title Scraper...")
    
    targets = [
        ("https://www.downtownlongmont.com/events/calendar", "https://www.downtownlongmont.com"),
        ("https://www.johnsonsstation.com/calendar", "https://www.johnsonsstation.com"),
        ("https://www.barnevents.info/events", "https://www.barnevents.info")
    ]
    
    cal = Calendar()
    seen_links = set()
    seen_events = set()
    count = 0

    for base_url, domain in targets:
        try:
            print(f"🔍 Scanning: {base_url}")
            res = requests.get(base_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(path in href for path in ['/do/', '/events/', '/calendar/', '/calendar-1']):
                    if len(href.strip('/').split('/')) >= 2:
                        links.append(domain + href if href.startswith('/') else href)
            
            unique_links = list(set(links))

            for full_url in unique_links:
                if full_url in seen_links or full_url.strip('/') == base_url.strip('/'): 
                    continue
                seen_links.add(full_url)

                try:
                    current_headers = HEADERS.copy()
                    current_headers['Referer'] = base_url
                    ev_res = requests.get(full_url, headers=current_headers, timeout=10)
                    ev_soup = BeautifulSoup(ev_res.text, 'html.parser')
                    
                    # --- NEW TARGETED TITLE EXTRACTION ---
                    event_title = ""
                    
                    # Priority 1: Specific Squarespace Event Title Class
                    sqs_title = ev_soup.find(class_="eventitem-title")
                    if sqs_title:
                        event_title = sqs_title.get_text(strip=True)
                    
                    # Priority 2: JSON-LD Metadata
                    if not event_title:
                        script = ev_soup.find('script', type='application/ld+json')
                        if script:
                            try:
                                data = json.loads(script.string)
                                if isinstance(data, list): data = data[0]
                                event_title = data.get('name', '')
                            except: pass
                    
                    # Priority 3: Standard H1 inside the body (avoiding headers)
                    if not event_title:
                        main_area = ev_soup.find('main') or ev_soup.find('article')
                        if main_area:
                            h1 = main_area.find('h1')
                            if h1: event_title = h1.get_text(strip=True)

                    # Final Cleanup: Remove generic placeholders
                    if event_title.lower() in ["barn events", "johnson's station", "calendar", "events"]:
                        event_title = ""

                    if not event_title: continue

                    # Clean title formatting
                    event_title = event_title.split('|')[0].split('-')[0].strip()

                    # --- DESCRIPTION & FILTERS ---
                    main_content = ev_soup.select_one('.details, .eventitem-description, .sqs-block-content, article')
                    body_text = main_content.get_text(" ", strip=True) if main_content else ev_soup.get_text(" ", strip=True)[:1000]
                    combined_text = (event_title + " " + body_text).lower()
                    
                    if any(x in event_title.lower() for x in EXCLUDE): continue
                    
                    is_trusted_site = any(d in full_url for d in TRUSTED_DOMAINS)
                    has_music = any(m in combined_text for m in MUSIC_KEYWORDS)
                    
                    if not (is_trusted_site or has_music): continue
                    if any(x in combined_text for x in EXCLUDE) and not any(m in event_title.lower() for m in MUSIC_KEYWORDS):
                        continue

                    # --- DATE ---
                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})', body_text)
                    if not date_match: continue
                    
                    month_str = date_match.group(1)[:3]
                    day_val = int(date_match.group(2))
                    start_dt = LOCAL_TZ.localize(datetime(2026, datetime.strptime(month_str, "%b").month, day_val, 19, 0))

                    fingerprint = f"{start_dt.strftime('%Y%m%d')}_{event_title[:15].lower()}"
                    if fingerprint in seen_events: continue
                    seen_events.add(fingerprint)

                    genre_tag = detect_genre(combined_text)
                    e = Event()
                    e.name = f"🎵 {genre_tag}{event_title}"
                    e.begin = start_dt
                    e.end = start_dt + timedelta(hours=2)
                    e.location = "Longmont, CO"
                    e.description = f"Source: {full_url}"
                    
                    cal.events.add(e)
                    count += 1
                    print(f"  [+] Added: {event_title}")

                except: continue
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Finished! {count} Music Events with corrected titles.")

if __name__ == "__main__":
    main()
