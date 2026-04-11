import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- FILTERS ---
EXCLUDE = [
    'karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 
    'comedy', 'yoga', 'poker', 'drawing', 'craft', 'storytime', 'book club', 
    'knitting', 'market', 'meditation', 'ballet', 'dance class', 'film', 'movie'
]
MUSIC_KEYWORDS = [
    'music', 'band', 'concert', 'symphony', 'acoustic', 'jazz', 'supper club',
    'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'solo', 'duo'
]
GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band', 'bebop'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'americana'],
    'Blues': ['blues', 'harmonica', 'soul'],
    'Electronic': ['dj', 'electronic', 'synth', 'house', 'rave', 'edm'],
    'Classical': ['orchestra', 'symphony', 'classical', 'quartet']
}
TRUSTED_VENUES = ['bricks on main', 'the barn', 'johnsons station', 'supper club']

# --- UTILS ---

def detect_genre(title, description):
    combined = f"{title} {description}".lower()
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", combined) for k in keywords):
            return f"[{genre}] "
    return ""

def find_times_strict(text):
    """Prevents 'May 1' from being 1pm. Requires am/pm or a colon."""
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

def parse_downtown():
    links = []
    try:
        res = requests.get("https://www.downtownlongmont.com/events/calendar", headers=HEADERS)
        soup = BeautifulSoup(res.text, 'html.parser')
        for a in soup.select('a.evcard'):
            links.append({"title": a.find(class_=re.compile(r'title|headline')).get_text(strip=True), 
                          "url": "https://www.downtownlongmont.com" + a['href']})
    except: pass
    return links

def parse_squarespace(url, venue_name):
    links = []
    try:
        res = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('article, .eventlist-item, .summary-item'):
            a = item.find('a', href=True)
            title = a.get_text(strip=True) or a.get('aria-label')
            if a and title:
                full_url = url.split('.com')[0] + ".com" + a['href'] if a['href'].startswith('/') else a['href']
                links.append({"title": title, "url": full_url})
    except: pass
    return links

# --- MAIN ---

def main():
    print("🚀 Running Scraper (Fixing Year & Multi-Date logic)...")
    all_targets = []
    all_targets.extend(parse_downtown())
    all_targets.extend(parse_squarespace("https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    all_targets.extend(parse_squarespace("https://www.barnevents.info/events", "The Barn"))
    
    cal = Calendar()
    seen = set()
    count = 0

    for target in all_targets:
        try:
            res = requests.get(target['url'], headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Identify venue and description
            venue = soup.select_one('.location, .venue, .sub-headline')
            venue_name = venue.get_text(strip=True) if venue else "Longmont"
            body = soup.get_text(separator=" ", strip=True).lower()
            
            # Keywords & Filters
            if any(x in target['title'].lower() for x in EXCLUDE) or any(x in body for x in EXCLUDE): continue
            is_trusted = any(v in venue_name.lower() or v in target['title'].lower() for v in TRUSTED_VENUES)
            has_music = any(m in target['title'].lower() or m in body for m in MUSIC_KEYWORDS)
            if not (is_trusted or has_music): continue

            # MULTI-DATE LOGIC: Look for any line that looks like "Month Day, Year"
            # Fixed regex: 202\d instead of \202\d
            date_lines = re.findall(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+202\d[^\n]*', soup.get_text())
            
            # If no specific date lines found, try to find a single date
            if not date_lines:
                date_lines = [target['title'] + " " + body] # Fallback to search whole text

            for line in date_lines:
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(202\d)', line)
                if not date_match: continue
                
                # Create standard date
                dt_obj = datetime.strptime(f"{date_match.group(1)[:3]} {date_match.group(2)} {date_match.group(3)}", "%b %d %Y")
                
                # Time detection on that specific line or fallback to body
                sh, sm, eh = find_times_strict(line)
                if sh is None: sh, sm, eh = find_times_strict(body)
                
                # Default to 7pm if none found
                sh, sm, eh = (sh, sm, eh) if sh is not None else (19, 0, 21)
                
                start_dt = LOCAL_TZ.localize(datetime(dt_obj.year, dt_obj.month, dt_obj.day, sh, sm))
                end_dt = LOCAL_TZ.localize(datetime(dt_obj.year, dt_obj.month, dt_obj.day, eh, 0))
                if end_dt <= start_dt: end_dt = start_dt + timedelta(hours=3)

                fingerprint = f"{start_dt.strftime('%Y%m%d%H')}_{target['title'][:10]}"
                if fingerprint in seen: continue

                genre = detect_genre(target['title'], body)
                e = Event()
                e.name = f"🎵 {genre}{target['title']}"
                e.begin = start_dt
                e.end = end_dt
                e.location = venue_name
                e.description = f"Link: {target['url']}"
                
                cal.events.add(e)
                seen.add(fingerprint)
                count += 1
                print(f"  [+] Added: {target['title']} ({start_dt.strftime('%b %d @ %I:%M%p')})")

        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Done! {count} events saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
