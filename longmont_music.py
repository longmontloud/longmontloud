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

def get_links(url, domain):
    print(f"  🔍 Scanning {url}...")
    links = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Look for any links inside common event containers
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Only keep links that look like event sub-pages
            if '/do/' in href or '/events/' in href or '/calendar/' in href:
                if len(href.split('/')) > 2: # Ignore the main /events/ page
                    full_url = domain + href if href.startswith('/') else href
                    links.append(full_url)
    except Exception as e:
        print(f"  ⚠️ Error scanning {url}: {e}")
    return list(set(links))

# --- MAIN ---

def main():
    print("🚀 Starting Fail-Safe Scraper...")
    
    all_links = []
    all_links.extend(get_links("https://www.downtownlongmont.com/events/calendar", "https://www.downtownlongmont.com"))
    all_links.extend(get_links("https://www.johnsonsstation.com/calendar", "https://www.johnsonsstation.com"))
    all_links.extend(get_links("https://www.barnevents.info/events", "https://www.barnevents.info"))
    
    print(f"Found {len(all_links)} total potential links. Analyzing each...")

    cal = Calendar()
    seen = set()
    count = 0

    for link in all_links:
        try:
            res = requests.get(link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # --- STEP 1: GET DATA (JSON-LD OR HTML) ---
            title, description, start_dt, venue_name = None, "", None, "Longmont"
            
            # Try JSON-LD first
            scripts = soup.find_all('script', type='application/ld+json')
            for s in scripts:
                try:
                    data = json.loads(s.string)
                    if isinstance(data, list): data = data[0]
                    if data.get('@type') == 'Event':
                        title = data.get('name')
                        description = data.get('description', '')
                        venue_name = data.get('location', {}).get('name', 'Longmont')
                        start_str = data.get('startDate')
                        if start_str:
                            dt_raw = datetime.fromisoformat(start_str.split('+')[0].split('Z')[0])
                            start_dt = LOCAL_TZ.localize(dt_raw)
                        break
                except: continue

            # Fallback to HTML if JSON-LD failed
            if not title:
                title_tag = soup.find('h1') or soup.find('title')
                title = title_tag.get_text(strip=True) if title_tag else ""
                description = soup.get_text(separator=" ", strip=True)

            if not title or len(title) < 3: continue

            # --- STEP 2: FILTERS ---
            t_low, d_low = title.lower(), description.lower()
            if any(x in t_low for x in EXCLUDE) or any(x in d_low for x in EXCLUDE): continue
            
            is_trusted = any(v in venue_name.lower() or v in t_low for v in TRUSTED_VENUES)
            has_music = any(m in t_low or m in d_low for m in MUSIC_KEYWORDS)
            if not (is_trusted or has_music): continue

            # --- STEP 3: RE-SYNC TIME ---
            # If start_dt is still missing (standard HTML), look for it in text
            if not start_dt:
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(202\d)', description)
                if date_match:
                    dt_obj = datetime.strptime(f"{date_match.group(1)[:3]} {date_match.group(2)} {date_match.group(3)}", "%b %d %Y")
                    start_dt = LOCAL_TZ.localize(datetime(dt_obj.year, dt_obj.month, dt_obj.day, 19, 0))
                else: continue

            # Refine time with regex
            sh, sm, eh = find_times_strict(description[:1000])
            if sh is not None:
                start_dt = LOCAL_TZ.localize(datetime(start_dt.year, start_dt.month, start_dt.day, sh, sm))
                end_dt = LOCAL_TZ.localize(datetime(start_dt.year, start_dt.month, start_dt.day, eh, 0))
            else:
                end_dt = start_dt + timedelta(hours=2)

            if end_dt <= start_dt: end_dt = start_dt + timedelta(hours=3)

            # --- STEP 4: ADD TO CALENDAR ---
            fingerprint = f"{start_dt.strftime('%Y%m%d%H')}_{t_low[:15]}"
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
            print(f"  [+] Added: {title} ({start_dt.strftime('%b %d @ %I:%M %p')})")

        except Exception as e:
            # Removed the silent 'continue' so you can see errors in the log
            print(f"  ❌ Error processing {link}: {e}")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Finished! {count} Music Events saved.")

if __name__ == "__main__":
    main()
