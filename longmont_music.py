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

def detect_genre(text):
    t = text.lower()
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", t) for k in keywords):
            return f"[{genre}] "
    return ""

def main():
    print("🚀 Running Tunnel-Vision Scraper...")
    
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
            res = requests.get(base_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(path in href for path in ['/do/', '/events/', '/calendar-1']):
                    if len(href.split('/')) > 2:
                        links.append(domain + href if href.startswith('/') else href)
            
            for full_url in set(links):
                if full_url in seen_links: continue
                seen_links.add(full_url)

                try:
                    ev_res = requests.get(full_url, headers=HEADERS, timeout=10)
                    ev_soup = BeautifulSoup(ev_res.text, 'html.parser')
                    
                    # --- TUNNEL VISION: TARGET ONLY THE EVENT AREA ---
                    # This avoids footers and sidebars
                    main_content = ev_soup.select_one('.details, .event-item-description, .sqs-block-content, article, main')
                    
                    title = (ev_soup.find('h1') or ev_soup.find('title')).get_text(strip=True)
                    # If we found a main content area, use it. Otherwise, use title + first bit of page.
                    if main_content:
                        body_text = main_content.get_text(" ", strip=True)
                    else:
                        body_text = ev_soup.get_text(" ", strip=True)[:1000] 
                    
                    combined_text = (title + " " + body_text).lower()
                    
                    # --- FILTER BRAIN ---
                    # 1. Immediate Exclude (Check Title first for higher accuracy)
                    if any(x in title.lower() for x in EXCLUDE): continue
                    
                    # 2. Trusted Venue Bypass
                    is_trusted = any(v in combined_text or v in full_url for v in TRUSTED_VENUES)
                    
                    # 3. Music keyword check
                    has_music = any(m in combined_text for m in MUSIC_KEYWORDS)
                    
                    # If it's a board game at a trusted venue, we still want to filter it out
                    # So we check EXCLUDE again on the combined text
                    if any(x in combined_text for x in EXCLUDE):
                        # Special exception: if the title is clearly music, ignore the exclude-word in body
                        if not any(m in title.lower() for m in MUSIC_KEYWORDS):
                            continue

                    if not (is_trusted or has_music): continue

                    # --- DATE DETECTION ---
                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})', body_text)
                    if not date_match: continue
                    
                    month_str = date_match.group(1)[:3]
                    day_val = int(date_match.group(2))
                    start_dt = LOCAL_TZ.localize(datetime(2026, datetime.strptime(month_str, "%b").month, day_val, 19, 0))

                    fingerprint = f"{start_dt.strftime('%Y%m%d')}_{title[:15].lower()}"
                    if fingerprint in seen_events: continue
                    seen_events.add(fingerprint)

                    genre_tag = detect_genre(combined_text)
                    e = Event()
                    e.name = f"🎵 {genre_tag}{title}"
                    e.begin = start_dt
                    e.end = start_dt + timedelta(hours=2)
                    e.location = "Longmont, CO"
                    e.description = f"Source: {full_url}"
                    
                    cal.events.add(e)
                    count += 1
                    print(f"  [+] Added: {title}")

                except: continue
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Finished! Found {count} Music Events.")

if __name__ == "__main__":
    main()
