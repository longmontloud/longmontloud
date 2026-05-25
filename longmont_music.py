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
    'karaoke', 'open mic', 'canvas classic', 'dinner', 'paperback tour', 'open sing', 'trivia', 'bingo', 'workshop', 'meeting', 'retail', 'watercolor', 'exhibition', 'the golden bee', 'sing-along', 'easel', 'studio tour', 'art materials', 'seminar', 'documentary',
    'comedy', 'yoga', 'poker', 'drawing class', 'craft class', 'create club', 'teen', 'crochet', 'wine dinner', 'tasting', 'pairing', 'prix fixe', 'shakespeare', 'happy day plants', 'headshot', 'stitch', 'embroidery',
    'storytime', 'book club', 'knitting', 'market', 'board game', 'meditation', 'speaker series', 'stationery', 'wolf & wren', 'talk', 'tarot', 'blackbird house', 'barbed wire books', 'dining', 'crafts & cocktails', 
    'teacher', 'discussion', 'ragen', 'networking', 'discovery days', 'uke jam', 'painting', 'sip', 'wines', '720-453-4733', 'date night', '303-651-8374', 'open-house', 'open house', 'crackpots', 'bubbly', 'joke', 'potting',
    'your stage', 'tangerine', 'composition', 'ballet', 'dance class', 'movie', 'bubbles', 'sewing', 'brunch', 'mimosas', 'bellinis', 'denim day', 'poetry night', 'poetry slam', 'sewing', 'sew', 'guest speakers', 'bloody mary',
]

MUSIC_KEYWORDS = [
    'live music', 'live band', 'symphony', 'acoustic', 'jazz', 'supper club', 'sessions',
    'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'live',
    'rave', 'grunge', 'folk', 'metal', 'punk', 'hip-hop', 'brass'
]

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band', 'bebop'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge', 'psychedelic', 'noise', 'experimental'],
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

def extract_time(text):
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)', text.lower())
    if match:
        hr = int(match.group(1))
        mn = int(match.group(2)) if match.group(2) else 0
        ampm = match.group(3).replace('.', '')
        if ampm == 'pm' and hr < 12: hr += 12
        if ampm == 'am' and hr == 12: hr = 0
        return hr, mn
    return 19, 0 

def main():
    print("🚀 Running Precision Time/Date Context Scraper...")
    targets = [
        ("https://www.downtownlongmont.com/events/calendar", "https://www.downtownlongmont.com"),
        ("https://www.johnsonsstation.com/calendar", "https://www.johnsonsstation.com"),
        ("https://www.barnevents.info/events", "https://www.barnevents.info")
    ]
    
    cal = Calendar()
    seen_links, seen_events = set(), set()
    count = 0

    for base_url, domain in targets:
        try:
            res = requests.get(base_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            links = [domain + a['href'] if a['href'].startswith('/') else a['href'] 
                     for a in soup.find_all('a', href=True) 
                     if any(p in a['href'] for p in ['/do/', '/events/', '/calendar/'])]

            for full_url in list(set(links)):
                if full_url in seen_links or full_url.strip('/') == base_url.strip('/'): continue
                seen_links.add(full_url)

                try:
                    ev_res = requests.get(full_url, headers=HEADERS, timeout=10)
                    ev_soup = BeautifulSoup(ev_res.text, 'html.parser')
                    
                    # --- TITLE (Preserving your Cross-Eyed Possum hyphen fix!) ---
                    event_title = ""
                    sqs_title = ev_soup.find(class_="eventitem-title")
                    if sqs_title: event_title = sqs_title.get_text(strip=True)
                    if not event_title:
                        h1 = ev_soup.find('h1')
                        if h1: event_title = h1.get_text(strip=True)
                    
                    if not event_title or event_title.lower() in ["barn events", "johnson's station", "calendar"]: continue
                    event_title = event_title.split('|')[0].strip()

                   # --- TARGETED DATE & TIME FIX ---
                    date_time_block = ""
                    start_hr, start_min = 19, 0  # Defaults
                    month_val, day_val = None, None

                    # If it's Downtown Longmont, use the exact precision spans you found!
                    dl_date_span = ev_soup.find('span', class_='dldate')
                    dl_time_span = ev_soup.find('span', class_='dltime')

                    if dl_date_span and dl_time_span:
                        date_time_block = dl_date_span.get_text(" ", strip=True)
                        time_text = dl_time_span.get_text(" ", strip=True)
                        start_hr, start_min = extract_time(time_text)
                    else:
                        # Fallback for other domains (The Barn / Johnson's Station)
                        main_content = ev_soup.select_one('.description, .details, .eventitem-description, .sqs-block-content, article')
                        date_time_block = main_content.get_text(" ", strip=True) if main_content else ev_soup.get_text(" ", strip=True)[:1000]
                        start_hr, start_min = extract_time(date_time_block)

                    # --- FILTERS ---

                    # --- FILTERS ---
                    body_text = ev_soup.get_text(" ", strip=True)[:2000]
                    combined_text = (event_title + " " + body_text).lower()
                    if any(x in event_title.lower() for x in EXCLUDE): continue
                    
                    is_trusted = any(d in full_url for d in TRUSTED_DOMAINS)
                    has_music = any(m in combined_text for m in MUSIC_KEYWORDS)
                    if not (is_trusted or has_music): continue
                    
                    if any(x in combined_text for x in EXCLUDE):
                        if not any(m in event_title.lower() for m in MUSIC_KEYWORDS):
                            continue

                    # --- DATE PARSING FROM PINPOINTED BLOCK ---
                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})', date_time_block)
                    if not date_match: continue
                    
                    month_val = datetime.strptime(date_match.group(1)[:3], "%b").month
                    start_dt = LOCAL_TZ.localize(datetime(2026, month_val, int(date_match.group(2)), start_hr, start_min))

                    # --- VENUE FIX ---
                    venue_loc = "Longmont, CO"
                    if "barnevents.info" in full_url:
                        venue_loc = "The Barn"
                    elif "johnsonsstation.com" in full_url:
                        venue_loc = "Johnson's Station, 1111 Neon Forest Circle, Longmont, CO 80501"
                    else:
                        loc_header = ev_soup.find('h2', class_='on-detail', string=re.compile('Location', re.I))
                        if loc_header:
                            venue_candidate = loc_header.find_next()
                            if venue_candidate:
                                venue_loc = venue_candidate.get_text(", ", strip=True)

                    fingerprint = f"{start_dt.strftime('%Y%m%d')}_{event_title[:15].lower()}"
                    if fingerprint in seen_events: continue
                    seen_events.add(fingerprint)

                    e = Event()
                    e.name = f"🎵 {detect_genre(combined_text)}{event_title}"
                    e.begin = start_dt
                    e.end = start_dt + timedelta(hours=2)
                    e.location = venue_loc
                    e.description = f"Source: {full_url}"
                    cal.events.add(e)
                    count += 1
                    print(f"  [+] {start_dt.strftime('%B %d, %I:%M%p')} | {event_title} @ {venue_loc}")

                except: continue
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Success! {count} Music Events saved.")

if __name__ == "__main__":
    main()
