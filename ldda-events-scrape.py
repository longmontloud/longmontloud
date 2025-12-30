import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import time
import re

# --- CONFIG ---
BASE_URL = "https://www.downtownlongmont.com"
CALENDAR_URL = f"{BASE_URL}/events/calendar"
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# Refined Logic
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'your stage', 'meeting', 'comedy', 'yoga', 'drawing', 'jam session', 'uke jam', 'poker']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'tribute', 'performance', 'punk', 'noise', 'experimental', 'hip-hop', 'rap', 'electronic']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'wibby brewing', 'bricks on main', 'the dickens', 'abbott & wallace']

# --- GENRE CONFIG ---
GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'unplugged', 'banjo'],
    'Blues': ['blues', 'harmonica'],
    'Electronic': ['dj', 'electronic', 'synth', 'techno', 'house music'],
    'Classical': ['orchestra', 'symphony', 'classical', 'chamber', 'choir'],
	'Hip-Hop': ['hip-hop', 'hip hop', 'rap'],
	'R&B': ['R&B', 'soul'],
	'Funk': ['funk']
}

def detect_genre(title, description):
    """Scans text for keywords and returns a bracketed tag like [Rock]."""
    combined_text = f"{title} {description}".lower()
    for genre, keywords in GENRE_MAP.items():
        if any(word in combined_text for word in keywords):
            return f"[{genre}] "
    return "" # Returns empty if no match found

def get_event_description(url):
    """Deep scrapes the event page for the actual description text."""
    try:
        time.sleep(0.4) # Be nice to the server
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Strategy A: Look for the specific Picnic 'Details' block
        # Usually, Picnic uses a <div> with a specific ID or a heading 'Details'
        content = ""
        details_header = soup.find(lambda tag: tag.name in ['h2', 'h3', 'h4', 'strong'] and "Details" in tag.text)
        
        if details_header:
            # Grab all siblings after the 'Details' header
            for sibling in details_header.find_next_siblings():
                if sibling.name == 'div' or sibling.name == 'p':
                    content += sibling.get_text(separator="\n", strip=True) + "\n"
        
        # Strategy B: Fallback to general content containers if Strategy A found nothing
        if not content.strip():
            detail_div = soup.select_one('.ev-details-content, .event-detail-content, #event-details, .entry-content')
            if detail_div:
                content = detail_div.get_text(separator="\n", strip=True)
        
        return content.strip() if content.strip() else "No description found on page."
    except:
        return "Error fetching description."

def parse_time(time_str, base_date):
    """Timezone-aware time parsing."""
    default_start = LOCAL_TZ.localize(base_date.replace(hour=19, minute=0, second=0, microsecond=0))
    start_dt, end_dt = default_start, default_start + timedelta(hours=2)
    if not time_str: return start_dt, end_dt
    try:
        clean_str = time_str.lower().replace(" ", "")
        parts = re.split(r'-|—|to', clean_str)
        def to_dt(s):
            fmt = "%I:%M%p" if ":" in s else "%I%p"
            t_obj = datetime.strptime(s, fmt)
            return LOCAL_TZ.localize(base_date.replace(hour=t_obj.hour, minute=t_obj.minute, second=0, microsecond=0))
        if parts[0]: start_dt = to_dt(parts[0])
        if len(parts) > 1 and parts[1]:
            end_dt = to_dt(parts[1])
            if end_dt <= start_dt: end_dt += timedelta(days=1)
        else: end_dt = start_dt + timedelta(hours=2)
    except: pass
    return start_dt, end_dt

def main():
    print(f"Connecting to {CALENDAR_URL}...")
    res = requests.get(CALENDAR_URL, headers=HEADERS)
    soup = BeautifulSoup(res.text, 'html.parser')
    event_links = soup.find_all('a', class_='evcard')
    print(f"Found {len(event_links)} total events. Scanning for music...")

    cal = Calendar()
    now = datetime.now()
    count = 0

    for link_tag in event_links:
        title_div = link_tag.find(class_='evcard-content-headline')
        venue_div = link_tag.find(class_='evcard-content-venue')
        if not title_div: continue
        
        title = title_div.get_text(strip=True)
        venue = venue_div.get_text(strip=True) if venue_div else "Downtown Longmont"
        
        # Inclusion/Exclusion Logic
        title_low, venue_low = title.lower(), venue.lower()
        if any(x in title_low for x in EXCLUDE): continue
        
        is_music = any(m in title_low for m in MUSIC_KEYWORDS) or \
                   any(v in venue_low for v in TRUSTED_VENUES)
        if not is_music: continue

        # Date & URL
        try:
            day = link_tag.find(class_='evcard-date-day').get_text(strip=True)
            mon = link_tag.find(class_='evcard-date-month').get_text(strip=True)
            temp_date = datetime.strptime(f"{mon} {day}", "%b %d")
            year = now.year if temp_date.month >= now.month else now.year + 1
            base_date = temp_date.replace(year=year)
            event_url = BASE_URL + link_tag['href'] if link_tag['href'].startswith('/') else link_tag['href']
        except: continue

        # Final Processing
        time_div = link_tag.find(class_='evcard-content-time')
        start_dt, end_dt = parse_time(time_div.get_text(strip=True) if time_div else "", base_date)

        print(f"  [+] {title} - Scraping details...")
        description = get_event_description(event_url)

        # 5. Fetch Details
        description = get_event_description(event_url)
        
        # --- NEW GENRE TAGGING ---
        genre_tag = detect_genre(title, description)

        # 6. Add to Calendar
        e = Event()
        # This will result in: 🎵 [Rock] Band Name
        e.name = f"🎵 {genre_tag}{title}"
        e.begin = start_dt
        e.end = end_dt

    if count > 0:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.writelines(cal.serialize_iter())
        print(f"\n✅ SUCCESS! {count} events with descriptions saved to {OUTPUT_FILE}.")
    else:
        print("\n❌ No music events found.")

if __name__ == "__main__":
    main()