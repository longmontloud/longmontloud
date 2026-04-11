import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re
import time

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- LOGIC ---
EXCLUDE = [
    'karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'retail',
    'comedy', 'yoga', 'poker', 'drawing', 'craft', 'create club', 'teen', 
    'storytime', 'book club', 'knitting', 'market', 'board game', 'meditation', 
    'teacher', 'discussion', 'ragen', 'networking', 'discovery days', 'uke jam', 
    'your stage', 'tangerine', 'composition', 'ballet', 'dance class', 
    'film', 'movie', 'bubbles', 'sewing', 'brunch', 'mimosas', 'bellinis'
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
TRUSTED_VENUES = ['bricks on main', 'the barn', 'johnsons station', 'supper club']

# --- UTILS ---

def detect_genre(title, description):
    combined_text = f"{title} {description}".lower()
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in keywords):
            return f"[{genre}] "
    return ""

def find_times_strict(text):
    """
    Only extracts times that have am/pm or a colon. 
    Prevents 'May 1' from becoming '1:00 PM'.
    """
    # Pattern: Digit(s) + optional :minutes + mandatory AM/PM OR Digit(s) + mandatory :minutes
    pattern = r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))|(\d{1,2}:\d{2})'
    matches = re.findall(pattern, text)
    
    found_times = []
    for m in matches:
        time_str = m[0] if m[0] else m[1]
        
        # Convert to 24h
        h_m = re.findall(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?', time_str, re.I)
        if h_m:
            h, m, ampm = h_m[0]
            h = int(h)
            m = int(m) if m else 0
            ampm = ampm.lower() if ampm else ""
            
            if not ampm: ampm = 'pm' if 1 <= h <= 10 else 'am'
            if ampm == 'pm' and h < 12: h += 12
            if ampm == 'am' and h == 12: h = 0
            found_times.append((h, m))
            
    if len(found_times) >= 1:
        start = found_times[0]
        end_h = found_times[1][0] if len(found_times) > 1 else (start[0] + 3) % 24
        return start[0], start[1], end_h
    return None, None, None

# --- PARSERS ---

def parse_downtown():
    events = []
    try:
        res = requests.get("https://www.downtownlongmont.com/events/calendar", headers=HEADERS)
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.select('a.evcard'):
            try:
                title = card.find(class_=re.compile(r'headline|title')).get_text(strip=True)
                url = "https://www.downtownlongmont.com" + card['href']
                events.append({"title": title, "url": url})
            except: continue
    except: pass
    return events

# --- MAIN ---

def main():
    print("🚀 Running Multi-Date & Time-Fixed Scraper...")
    raw_links = []
    raw_links.extend(parse_downtown())
    # Note: parse_squarespace logic remains similar but link-focused for the loop below
    
    cal = Calendar()
    seen = set()
    count = 0

    for data in raw_links:
        try:
            res_detail = requests.get(data['url'], headers=HEADERS, timeout=10)
            soup_detail = BeautifulSoup(res_detail.text, 'html.parser')
            
            # 1. Get Venue
            venue_el = soup_detail.select_one('.location, .venue, .sub-headline')
            venue_name = venue_el.get_text(strip=True) if venue_el else "Downtown Longmont"
            
            # 2. Get Description Area
            detail_area = soup_detail.select_one('.details, .description, .sqs-block-content, #page-content')
            detail_text = detail_area.get_text(separator=" ", strip=True).lower() if detail_area else ""
            
            # 3. Filters
            title_low = data['title'].lower()
            if any(x in title_low for x in EXCLUDE) or any(x in detail_text for x in EXCLUDE):
                continue
            
            is_trusted = any(v in venue_name.lower() for v in TRUSTED_VENUES)
            has_music = any(m in title_low for m in MUSIC_KEYWORDS) or any(m in detail_text for m in MUSIC_KEYWORDS)
            if not (is_trusted or has_music): continue

            # 4. MULTI-DATE EXTRACTION
            # Downtown Longmont uses a specific list for multi-dates
            date_items = soup_detail.select('.dates-times li, .date-time-list li')
            # Fallback to single date if list not found
            if not date_items:
                date_items = [soup_detail.select_one('.date-time, .dates-times')]

            for item in date_items:
                if not item: continue
                item_text = item.get_text(strip=True)
                
                # Parse date from text (e.g., "Friday, May 1, 2026")
                # Look for Month Day Year
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\202\d)', item_text)
                if not date_match: continue
                
                event_date = datetime.strptime(f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}", "%b %d %Y")
                
                # Parse time from THIS SPECIFIC line
                sh, sm, eh = find_times_strict(item_text)
                if sh is None: 
                    # If time isn't in the line, check the general description
                    sh, sm, eh = find_times_strict(detail_text)
                
                # Build DateTimes
                if sh is not None:
                    start_dt = LOCAL_TZ.localize(datetime(event_date.year, event_date.month, event_date.day, sh, sm))
                    end_dt = LOCAL_TZ.localize(datetime(event_date.year, event_date.month, event_date.day, eh, 0))
                    if end_dt <= start_dt: end_dt = start_dt + timedelta(hours=3)
                else:
                    start_dt = LOCAL_TZ.localize(datetime(event_date.year, event_date.month, event_date.day, 19, 0))
                    end_dt = start_dt + timedelta(hours=2)

                fingerprint = f"{start_dt.strftime('%Y%m%d%H')}_{title_low[:10]}"
                if fingerprint in seen: continue

                genre_tag = detect_genre(data['title'], detail_text)
                e = Event()
                e.name = f"🎵 {genre_tag}{data['title']}"
                e.begin = start_dt
                e.end = end_dt
                e.location = venue_name
                e.description = f"Venue: {venue_name}\nLink: {data['url']}"
                
                cal.events.add(e)
                seen.add(fingerprint)
                count += 1
                print(f"  [+] Added: {data['title']} on {start_dt.strftime('%b %d @ %I:%M %p')}")

        except Exception as e:
            continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ SUCCESS: {count} event instances processed.")

if __name__ == "__main__":
    main()
