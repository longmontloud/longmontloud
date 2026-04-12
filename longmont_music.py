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
    'karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'retail',
    'comedy', 'yoga', 'poker', 'drawing', 'craft', 'create club', 'teen', 
    'storytime', 'book club', 'knitting', 'market', 'board game', 'meditation', 
    'teacher', 'discussion', 'ragen', 'networking', 'discovery days', 'uke jam', 
    'your stage', 'tangerine', 'composition', 'ballet', 'dance class', 
    'film', 'movie', 'bubbles', 'sewing', 'brunch', 'mimosas', 'bellinis', 'denim day', 'art'
]

MUSIC_KEYWORDS = [
    'music', 'band', 'concert', 'symphony', 'acoustic', 'jazz', 'supper club',
    'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'solo', 'duo',
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

TRUSTED_DOMAINS = ['barnevents.info', 'johnsonsstation.com']

def detect_genre(text):
    t = text.lower()
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", t) for k in keywords):
            return f"[{genre}] "
    return ""

def main():
    print("🚀 Running All-In Scraper (Targeting Johnson's Station)...")
    
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
                # Added '/calendar/' to the paths to catch individual Johnson's Station events
                if any(path in href for path in ['/do/', '/events/', '/calendar/', '/calendar-1']):
                    # Ensure we aren't just linking back to the main calendar
                    if len(href.strip('/').split('/')) >= 2:
                        links.append(domain + href if href.startswith('/') else href)
            
            unique_links = list(set(links))
            print(f"   Found {len(unique_links)} potential event links...")

            for full_url in unique_links:
                if full_url in seen_links or full_url.strip('/') == base_url.strip('/'): 
                    continue
                seen_links.add(full_url)

                try:
                    # Set referer to bypass some Squarespace bot-blocks
                    current_headers = HEADERS.copy()
                    current_headers['Referer'] = base_url
                    
                    ev_res = requests.get(full_url, headers=current_headers, timeout=10)
                    ev_soup = BeautifulSoup(ev_res.text, 'html.parser')
                    
                    # --- TITLE EXTRACTION ---
                    event_title = ""
                    script = ev_soup.find('script', type='application/ld+json')
                    if script:
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, list): data = data[0]
                            event_title = data.get('name', '')
                        except: pass
                    
                    if not event_title or event_title.lower() in ["barn events", "calendar"]:
                        h1 = ev_soup.find('h1')
                        event_title = h1.get_text(strip=True) if h1 else ""

                    if not event_title:
                        title_tag = ev_soup.find('title')
                        event_title = title_tag.get_text(strip=True) if title_tag else ""

                    # Clean title
                    event_title = event_title.split('|')[0].split('-')[0].strip()
                    if not event_title or len(event_title) < 3: continue

                    # --- DESCRIPTION & FILTERS ---
                    main_content = ev_soup.select_one('.details, .event-item-description, .sqs-block-content, article, section')
                    body_text = main_content.get_text(" ", strip=True) if main_content else ev_soup.get_text(" ", strip=True)[:2000]
                    combined_text = (event_title + " " + body_text).lower()
                    
                    # Trust logic for JS and The Barn
                    is_trusted_site = any(d in full_url for d in TRUSTED_DOMAINS)
                    
                    if any(x in event_title.lower() for x in EXCLUDE): continue
                    
                    has_music = any(m in combined_text for m in MUSIC_KEYWORDS)
                    
                    if not (is_trusted_site or has_music): continue
                    
                    # Secondary safety: if it's a known non-music event at a trusted site
                    if any(x in combined_text for x in EXCLUDE) and not any(m in event_title.lower() for m in MUSIC_KEYWORDS):
                        continue

                    # --- DATE ---
                    # Look for Month + Day
                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})', body_text)
                    if not date_match: continue
                    
                    month_str = date_match.group(1)[:3]
                    day_val = int(date_match.group(2))
                    # Use 2026 as default
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
    print(f"\n✅ Finished! Found {count} Music Events.")

if __name__ == "__main__":
    main()
