import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime
import pytz
import time
import re
import json

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- LOGIC ---
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'performance', 'festival', 'rave', 'grunge', 'folk']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'bricks on main', 'the barn', 'johnsons station', 'hell yes', 'moshmont', 'lunar lux']

# --- PARSERS ---

def parse_json_ld_events(url, host_name):
    """Universal parser for sites that use JSON-LD (Humanitix and Squarespace)"""
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                # Some sites wrap events in a '@graph' list
                items = data.get('@graph', [data]) if isinstance(data, dict) else data
                for item in items:
                    if isinstance(item, dict) and item.get('@type') in ['Event', 'MusicEvent']:
                        start_str = item.get('startDate')
                        if not start_str: continue
                        
                        # Handle varied date formats
                        start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                        events.append({
                            "title": item.get('name', 'Untitled Event'),
                            "venue": host_name,
                            "date": start_dt.astimezone(LOCAL_TZ),
                            "url": item.get('url', url)
                        })
            except: continue
    except Exception as e: print(f"⚠️ Error on {host_name}: {e}")
    return events

def parse_downtown_longmont():
    """Specific fix for the 2026 Downtown Longmont Calendar structure"""
    events = []
    url = "https://www.downtownlongmont.com/events/calendar"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Targeting the 'evcard' which contains all the info in its data attributes or text
        for card in soup.find_all('a', class_=re.compile(r'evcard|event-card')):
            try:
                title = card.find(class_=re.compile(r'headline|title')).get_text(strip=True)
                # Extracting date from the text/tags
                day = card.find(class_=re.compile(r'day')).get_text(strip=True)
                mon = card.find(class_=re.compile(r'month')).get_text(strip=True)
                
                temp_dt = datetime.strptime(f"{mon} {day}", "%b %d")
                year = datetime.now().year if temp_dt.month >= datetime.now().month else datetime.now().year + 1
                
                events.append({
                    "title": title,
                    "venue": card.find(class_=re.compile(r'venue')).get_text(strip=True) if card.find(class_=re.compile(r'venue')) else "Downtown Longmont",
                    "date": LOCAL_TZ.localize(temp_dt.replace(year=year, hour=19, minute=0)),
                    "url": "https://www.downtownlongmont.com" + card['href']
                })
            except: continue
    except: pass
    return events

# --- MAIN ---

def main():
    print("🚀 Running JSON-Enabled Master Scraper...")
    raw_collection = []
    
    # 1. Downtown Longmont (Custom structure)
    raw_collection.extend(parse_downtown_longmont())
    
    # 2. Squarespace Sites (JSON-LD targets)
    raw_collection.extend(parse_json_ld_events("https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    raw_collection.extend(parse_json_ld_events("https://www.barnevents.info/events", "The Barn"))
    
    # 3. Humanitix Hosts (JSON-LD targets)
    htix_hosts = [
        ("https://events.humanitix.com/host/hell-yes-music-promotions", "Hell Yes Music"),
        ("https://events.humanitix.com/host/moshmont-mafia-and-outlaw-production-collective", "Moshmont Mafia"),
        ("https://events.humanitix.com/host/lunar-lux-music-and-arts-festival", "Lunar Lux")
    ]
    for url, name in htix_hosts:
        raw_collection.extend(parse_json_ld_events(url, name))
    
    cal = Calendar()
    seen = set()
    count = 0

    for data in raw_collection:
        title_low = data['title'].lower()
        if any(x in title_low for x in EXCLUDE): continue

        fingerprint = f"{data['date'].strftime('%Y%m%d')}_{title_low[:15]}"
        if fingerprint in seen: continue

        # Trust Check
        is_music = any(m in title_low for m in MUSIC_KEYWORDS) or \
                   any(v in data['venue'].lower() for v in TRUSTED_VENUES)

        if is_music:
            e = Event()
            e.name = f"🎵 {data['title']}"
            e.begin = data['date']
            e.location = data['venue']
            e.description = f"Link: {data['url']}"
            cal.events.add(e)
            seen.add(fingerprint)
            count += 1
            print(f"  [+] Added: {data['title']} (@{data['venue']})")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Success! Found {count} unique music events.")

if __name__ == "__main__":
    main()
