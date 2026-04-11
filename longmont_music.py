import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime
import pytz
import re
import json

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
# Enhanced Headers to look more like a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- LOGIC ---
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'performance', 'festival', 'rave', 'grunge', 'folk']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'bricks on main', 'the barn', 'johnsons station', 'hell yes', 'moshmont', 'lunar lux']

# --- PARSERS ---

def parse_hybrid(url, host_name):
    """Tries JSON-LD first, falls back to HTML scraping if empty"""
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # PATH 1: JSON-LD (The clean way)
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else data.get('@graph', [data])
                for item in items:
                    if isinstance(item, dict) and item.get('@type') in ['Event', 'MusicEvent']:
                        start_str = item.get('startDate')
                        if start_str:
                            dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                            events.append({
                                "title": item.get('name'),
                                "venue": host_name,
                                "date": dt.astimezone(LOCAL_TZ),
                                "url": item.get('url', url)
                            })
            except: continue
        
        # PATH 2: HTML Fallback (If Path 1 found nothing)
        if not events:
            # Look for common Squarespace/Humanitix patterns
            for item in soup.select('article, .eventlist-event, .summary-item, a[href*="/events/"]'):
                title_el = item.find(['h1', 'h2', 'h3', 'strong']) or item
                title = title_el.get_text(strip=True)
                if len(title) < 3: continue
                
                link = item.get('href') or (item.find('a')['href'] if item.find('a') else url)
                if link.startswith('/'):
                    base = "https://" + url.split('//')[1].split('/')[0]
                    link = base + link

                # Since HTML fallback is harder to get dates from, we'll default to 'Today'
                # and let the deep-scrape logic handle it or skip if it's too vague.
                events.append({
                    "title": title, "venue": host_name, "date": datetime.now(LOCAL_TZ), "url": link
                })
    except Exception as e:
        print(f"⚠️ Error on {host_name}: {e}")
    return events

def parse_downtown_longmont():
    events = []
    url = "https://www.downtownlongmont.com/events/calendar"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.select('a.evcard'):
            try:
                title = card.find(class_=re.compile(r'headline|title')).get_text(strip=True)
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
    print("🚀 Running Fail-Safe Scraper...")
    raw_collection = []
    
    # 1. Downtown Longmont
    raw_collection.extend(parse_downtown_longmont())
    
    # 2. Hybrid Sites
    hybrid_targets = [
        ("https://www.johnsonsstation.com/calendar", "Johnson's Station"),
        ("https://www.barnevents.info/events", "The Barn"),
        ("https://events.humanitix.com/host/hell-yes-music-promotions", "Hell Yes Music"),
        ("https://events.humanitix.com/host/moshmont-mafia-and-outlaw-production-collective", "Moshmont Mafia"),
        ("https://events.humanitix.com/host/lunar-lux-music-and-arts-festival", "Lunar Lux")
    ]
    for url, name in hybrid_targets:
        raw_collection.extend(parse_hybrid(url, name))
    
    cal = Calendar()
    seen = set()
    count = 0

    for data in raw_collection:
        title_low = data['title'].lower()
        if any(x in title_low for x in EXCLUDE): continue

        # Fingerprint to avoid duplicates
        fingerprint = f"{data['date'].strftime('%Y%m%d')}_{title_low[:20]}"
        if fingerprint in seen: continue

        # Trust vs Keyword logic
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
    print(f"\n✅ Finished! Found {count} unique music events.")

if __name__ == "__main__":
    main()
