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
# Expanded to catch the "noise" you're seeing
EXCLUDE = [
    'karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 
    'comedy', 'yoga', 'poker', 'drawing', 'craft', 'storytime', 'book club', 
    'knitting', 'market', 'meditation', 'ballet', 'dance class', 'film', 'movie',
    'bubbles', 'sewing', 'brunch', 'mimosas', 'bellinis', 'flow', 'fitness'
]
MUSIC_KEYWORDS = [
    'music', 'band', 'concert', 'symphony', 'acoustic', 'jazz', 'supper club',
    'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'solo', 'duo',
    'live music', 'trio', 'quartet', 'brass', 'bluegrass'
]
TRUSTED_VENUES = ['bricks on main', 'the barn', 'johnsons station', 'supper club']

# --- UTILS ---

def detect_genre(title, description):
    combined = f"{title} {description}".lower()
    genres = {
        'Jazz': ['jazz', 'swing', 'big band', 'bebop'],
        'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge'],
        'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'americana'],
        'Blues': ['blues', 'harmonica', 'soul'],
        'Electronic': ['dj', 'electronic', 'synth', 'house', 'rave', 'edm'],
        'Country': ['country', 'western', 'honky tonk']
    }
    for genre, keywords in genres.items():
        if any(re.search(rf"\b{re.escape(k)}\b", combined) for k in keywords):
            return f"[{genre}] "
    return ""

def find_times_strict(text):
    """Requires am/pm or a colon to prevent 'May 1' bugs."""
    pattern = r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))|(\d{1,2}:\d{2})'
    matches = re.findall(pattern, text)
    if not matches: return None, None, None
    
    times = []
    for m in matches:
        t_str = m[0] or m[1]
        h_m = re.findall(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', t_str.lower())
        if h_m:
            h, m, ampm = h_m[0]
            h, m = int(h), int(m) if m else 0
            if not ampm: ampm = 'pm' if 1 <= h <= 10 else 'am'
            if ampm == 'pm' and h < 12: h += 12
            if ampm == 'am' and h == 12: h = 0
            times.append((h, m))
            
    if times:
        start = times[0]
        end_h = times[1][0] if len(times) > 1 else (start[0] + 3) % 24
        return start[0], start[1], end_h
    return None, None, None

# --- PARSERS ---

def get_event_links(url, selector, domain=""):
    links = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.select(selector):
            if a.has_attr('href'):
                full_url = domain + a['href'] if a['href'].startswith('/') else a['href']
                links.append(full_url)
    except: pass
    return list(set(links))

# --- MAIN ---

def main():
    print("🚀 Running Ironclad Scraper (JSON-LD Mode)...")
    
    # Target URLs
    targets = [
        ("https://www.downtownlongmont.com/events/calendar", "a.evcard", "https://www.downtownlongmont.com"),
        ("https://www.johnsonsstation.com/calendar", "a.eventlist-column-window", "https://www.johnsonsstation.com"),
        ("https://www.barnevents.info/events", "a.eventlist-title-link", "https://www.barnevents.info")
    ]
    
    all_links = []
    for url, sel, dom in targets:
        all_links.extend(get_event_links(url, sel, dom))
    
    cal = Calendar()
    seen = set()
    count = 0

    for link in all_links:
        try:
            res = requests.get(link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 1. TRY JSON-LD DATA (The most accurate way)
            json_data = None
            scripts = soup.find_all('script', type='application/ld+json')
            for s in scripts:
                try:
                    data = json.loads(s.string)
                    # Handle lists of objects or single objects
                    if isinstance(data, list): data = data[0]
                    if data.get('@type') == 'Event':
                        json_data = data
                        break
                except: continue

            if not json_data: continue

            title = json_data.get('name', '')
            description = json_data.get('description', '') or soup.get_text()
            venue_name = json_data.get('location', {}).get('name', 'Longmont')
            
            # 2. FILTERS (Run on Title AND Description)
            title_low = title.lower()
            desc_low = description.lower()
            
            # Hard Exclude
            if any(x in title_low for x in EXCLUDE) or any(x in desc_low for x in EXCLUDE):
                continue
            
            # Must be music or trusted venue
            is_trusted = any(v in venue_name.lower() or v in title_low for v in TRUSTED_VENUES)
            has_music = any(m in title_low or m in desc_low for m in MUSIC_KEYWORDS)
            
            if not (is_trusted or has_music):
                continue

            # 3. DATE & TIME
            start_str = json_data.get('startDate') # Often 2026-05-01T18:00:00
            if start_str:
                # Strip timezone and parse
                dt_raw = datetime.fromisoformat(start_str.split('+')[0].split('Z')[0])
                # Ensure it is treated as Mountain Time
                start_dt = LOCAL_TZ.localize(datetime(dt_obj.year, dt_obj.month, dt_obj.day, dt_raw.hour, dt_raw.minute)) if 'dt_obj' in locals() else LOCAL_TZ.localize(dt_raw)
            else:
                continue

            # Check if times are in the text (overrides generic ISO times if needed)
            sh, sm, eh = find_times_strict(description[:500])
            if sh is not None:
                start_dt = LOCAL_TZ.localize(datetime(start_dt.year, start_dt.month, start_dt.day, sh, sm))
                end_dt = LOCAL_TZ.localize(datetime(start_dt.year, start_dt.month, start_dt.day, eh, 0))
            else:
                end_dt = start_dt + timedelta(hours=2)

            if end_dt <= start_dt: end_dt = start_dt + timedelta(hours=3)

            # 4. FINALIZE
            fingerprint = f"{start_dt.strftime('%Y%m%d%H')}_{title_low[:15]}"
            if fingerprint in seen: continue

            genre = detect_genre(title, description)
            e = Event()
            e.name = f"🎵 {genre}{title}"
            e.begin = start_dt
            e.end = end_dt
            e.location = venue_name
            e.description = f"Venue: {venue_name}\nLink: {link}"
            
            cal.events.add(e)
            seen.add(fingerprint)
            count += 1
            print(f"  [+] Added: {genre}{title} @ {venue_name}")

        except Exception as e:
            continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Done! {count} Music Events saved.")

if __name__ == "__main__":
    main()
