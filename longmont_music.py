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
# Words that prove it's NOT a music event
HARD_EXCLUDE = [
    'workshop', 'class', 'yoga', 'sip', 'paint', 'watercolor', 'meeting', 'sale', 
    'market', 'plant', 'meditation', 'knit', 'storytime', 'trivia', 'bingo', 
    'poetry', 'film', 'movie', 'poker', 'discussion', 'fitness', 'wellness'
]

# Words that mean it is definitely music
STRONG_MUSIC = ['concert', 'band', 'symphony', 'live music', 'orchestra', 'tribute band', 'gig']

# General music context
SOFT_MUSIC = ['acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'dj', 'solo', 'duo', 'trio', 'bluegrass', 'folk']

TRUSTED_VENUES = ['bricks on main', 'the barn', 'johnsons station', 'supper club', 'abbott & wallace', 'wibby', 'left hand']

# --- UTILS ---

def calculate_music_score(title, description, venue):
    score = 0
    t_low = title.lower()
    d_low = description.lower()
    v_low = venue.lower()

    # 1. Check for deal-breakers (Hard Exclude)
    if any(x in t_low for x in HARD_EXCLUDE): return -10
    if any(x in d_low for x in HARD_EXCLUDE): score -= 5

    # 2. Check Title (High weight)
    if any(x in t_low for x in STRONG_MUSIC): score += 5
    if any(x in t_low for x in SOFT_MUSIC): score += 3

    # 3. Check Description (Lower weight to avoid footer noise)
    if any(x in d_low for x in STRONG_MUSIC): score += 2
    if any(x in d_low for x in SOFT_MUSIC): score += 1

    # 4. Venue Check
    if any(v in v_low for v in TRUSTED_VENUES): score += 1
    
    return score

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
    links = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Target specific event links to avoid nav-bar links
        for a in soup.select('a[href*="/do/"], a[href*="/events/"]'):
            href = a['href']
            if len(href.split('/')) > 2:
                full_url = domain + href if href.startswith('/') else href
                links.append(full_url)
    except: pass
    return list(set(links))

# --- MAIN ---

def main():
    print("🚀 Running Scorer-Based Music Filter...")
    
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
            
            # Identify the actual CONTENT of the event, ignoring headers/footers
            content_area = soup.select_one('.details, .event-item-description, .sqs-block-content, #page-content, main article')
            description = content_area.get_text(separator=" ", strip=True) if content_area else ""
            
            title_tag = soup.find('h1') or soup.find('title')
            title = title_tag.get_text(strip=True) if title_tag else ""
            
            # Venue Logic
            venue_el = soup.select_one('.location, .venue, .sub-headline')
            venue_name = venue_el.get_text(strip=True) if venue_el else "Longmont"

            # --- SCORING ENGINE ---
            music_score = calculate_music_score(title, description, venue_name)
            
            if music_score < 2:
                # print(f"  [-] Skipped (Score {music_score}): {title}")
                continue

            # --- DATE & TIME ---
            start_dt = None
            # Try JSON-LD first for the date
            script = soup.find('script', type='application/ld+json')
            if script:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list): data = data[0]
                    start_str = data.get('startDate')
                    if start_str:
                        start_dt = LOCAL_TZ.localize(datetime.fromisoformat(start_str.split('+')[0].split('Z')[0]))
                except: pass

            if not start_dt:
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(202\d)', description)
                if date_match:
                    dt_obj = datetime.strptime(f"{date_match.group(1)[:3]} {date_match.group(2)} {date_match.group(3)}", "%b %d %Y")
                    start_dt = LOCAL_TZ.localize(datetime(dt_obj.year, dt_obj.month, dt_obj.day, 19, 0))
                else: continue

            # Refine time
            sh, sm, eh = find_times_strict(description[:1000])
            if sh is not None:
                start_dt = LOCAL_TZ.localize(datetime(start_dt.year, start_dt.month, start_dt.day, sh, sm))
                end_dt = LOCAL_TZ.localize(datetime(start_dt.year, start_dt.month, start_dt.day, eh, 0))
            else:
                end_dt = start_dt + timedelta(hours=2)

            # --- FINALIZE ---
            fingerprint = f"{start_dt.strftime('%Y%m%d%H')}_{title[:15].lower()}"
            if fingerprint in seen: continue

            e = Event()
            e.name = f"🎵 {title}"
            e.begin = start_dt
            e.end = end_dt
            e.location = venue_name
            e.description = f"Venue: {venue_name}\nLink: {link}"
            
            cal.events.add(e)
            seen.add(fingerprint)
            count += 1
            print(f"  [+] Added (Score {music_score}): {title}")

        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Finished! {count} Verified Music Events saved.")

if __name__ == "__main__":
    main()
