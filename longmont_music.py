import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import time
import re

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- STRICT LOGIC ---
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'soundpost', 'sessions', 'orchestra', 'dj', 'performance']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'wibby brewing', 'bricks on main']

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'folksy'],
    'Blues': ['blues', 'harmonica'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music'],
    'Classical': ['orchestra', 'symphony', 'classical']
}

def detect_genre(title, description):
    combined_text = f"{title} {description}".lower()
    for genre, keywords in GENRE_MAP.items():
        for keyword in keywords:
            pattern = rf"\b{re.escape(keyword.lower())}\b"
            if re.search(pattern, combined_text):
                return f"[{genre}] "
    return ""

def get_deep_description(url):
    try:
        time.sleep(0.3)
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        content_area = soup.select_one('.ev-details-content, .eventlist-description, #event-details, .entry-content')
        return content_area.get_text(separator="\n", strip=True) if content_area else "Details at venue website."
    except:
        return "Details available at link."

# --- SITE PARSERS WITH ERROR HANDLING ---

def parse_downtown_longmont():
    events = []
    url = "https://www.downtownlongmont.com/events/calendar"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        cards = soup.select('a.evcard')
        for card in cards:
            try:
                title_el = card.find(class_=re.compile(r'headline|title'))
                day_el = card.find(class_=re.compile(r'day'))
                mon_el = card.find(class_=re.compile(r'month'))
                
                if not title_el or not day_el: continue
                
                title = title_el.get_text(strip=True)
                venue_el = card.find(class_=re.compile(r'venue'))
                venue = venue_el.get_text(strip=True) if venue_el else "Downtown Longmont"
                
                temp_dt = datetime.strptime(f"{mon_el.text.strip()} {day_el.text.strip()}", "%b %d")
                year = datetime.now().year if temp_dt.month >= datetime.now().month else datetime.now().year + 1
                event_date = temp_dt.replace(year=year)
                
                events.append({
                    "title": title, "venue": venue, 
                    "url": "https://www.downtownlongmont.com" + card['href'], 
                    "date": event_date
                })
            except Exception: continue # Skip individual messy events
    except Exception as e: print(f"Downtown Scrape Failed: {e}")
    return events

def parse_squarespace_site(url, venue_name):
    """Generic parser for The Barn and Johnson Station."""
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('article.eventlist-event--upcoming'):
            try:
                link = item.select_one('a.eventlist-title-link')
                date_str = item.select_one('time.event-date')['datetime']
                events.append({
                    "title": link.get_text(strip=True),
                    "venue": venue_name,
                    "url": (url.split('/calendar')[0] if '/calendar' in url else url.split('/events')[0]) + link['href'],
                    "date": datetime.strptime(date_str, "%Y-%m-%d")
                })
            except: continue
    except: pass
    return events

# --- ENGINE ---

def main():
    print("🚀 Running Safe Master Scraper...")
    raw_collection = []
    raw_collection.extend(parse_downtown_longmont())
    raw_collection.extend(parse_squarespace_site("https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    raw_collection.extend(parse_squarespace_site("https://www.barnevents.info/events", "The Barn"))
    
    cal = Calendar()
    seen_fingerprints = set()
    count = 0

    for data in raw_collection:
        try:
            title_low = data['title'].lower()
            venue_low = data['venue'].lower()

            if any(x in title_low for x in EXCLUDE): continue

            fingerprint = f"{data['date'].strftime('%Y%m%d')}_{venue_low[:5]}"
            if fingerprint in seen_fingerprints: continue

            description = get_deep_description(data['url'])
            genre_tag = detect_genre(data['title'], description)

            is_music = any(m in title_low for m in MUSIC_KEYWORDS) or \
                       any(v in venue_low for v in TRUSTED_VENUES) or \
                       genre_tag != ""

            if not is_music: continue

            e = Event()
            e.name = f"🎵 {genre_tag}{data['title']}"
            e.begin = LOCAL_TZ.localize(data['date'].replace(hour=19, minute=0))
            e.location = data['venue']
            e.description = f"{description}\n\nLink: {data['url']}"
            
            cal.events.add(e)
            seen_fingerprints.add(fingerprint)
            count += 1
            print(f"  [+] Added: {data['title']} @ {data['venue']}")
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Done. {count} events saved.")

if __name__ == "__main__":
    main()
