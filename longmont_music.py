import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime
import pytz
import re
import json
import time

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
LOCAL_TZ = pytz.timezone("America/Denver")

# --- GENRE & FILTER LOGIC (RESTORED) ---
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'performance', 'festival', 'rave', 'grunge', 'folk', 'metal', 'punk']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'bricks on main', 'the barn', 'johnsons station', 'hell yes', 'moshmont', 'lunar lux']

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'folksy'],
    'Blues': ['blues', 'harmonica'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music', 'rave', 'edm'],
    'Classical': ['orchestra', 'symphony', 'classical']
}

# --- UTILS ---

def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com/"
    })
    return s

def detect_genre(title, description):
    combined_text = f"{title} {description}".lower()
    for genre, keywords in GENRE_MAP.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", combined_text):
                return f"[{genre}] "
    return ""

def get_deep_description(session, url):
    if not url or url.startswith('#'): return ""
    try:
        time.sleep(0.5)
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Humanitix and Squarespace common content areas
        content = soup.select_one('.event-description, [data-testid="event-description"], .eventlist-description, .ev-details-content')
        return content.get_text(separator="\n", strip=True) if content else ""
    except:
        return ""

# --- PARSERS ---

def parse_humanitix(session, url, host_name):
    events = []
    try:
        res = session.get(url, timeout=15)
        # Humanitix embeds event data in a script tag as a JSON-LD list
        soup = BeautifulSoup(res.text, 'html.parser')
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else data.get('@graph', [data])
                for item in items:
                    if isinstance(item, dict) and item.get('@type') in ['Event', 'MusicEvent']:
                        start_str = item.get('startDate')
                        dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                        events.append({
                            "title": item.get('name'),
                            "venue": host_name,
                            "date": dt.astimezone(LOCAL_TZ),
                            "url": item.get('url', url)
                        })
            except: continue
    except Exception as e: print(f"⚠️ Humanitix Error ({host_name}): {e}")
    return events

def parse_squarespace(session, url, venue_name):
    events = []
    try:
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        base_domain = "https://" + url.split('//')[1].split('/')[0]
        for item in soup.select('article.eventlist-event, .eventlist-item'):
            try:
                link_tag = item.select_one('a[href*="/events/"]')
                date_tag = item.select_one('time[datetime]')
                dt_str = date_tag['datetime']
                events.append({
                    "title": link_tag.get_text(strip=True),
                    "venue": venue_name,
                    "date": LOCAL_TZ.localize(datetime.strptime(dt_str[:10], "%Y-%m-%d").replace(hour=19, minute=0)),
                    "url": base_domain + link_tag['href'] if link_tag['href'].startswith('/') else link_tag['href']
                })
            except: continue
    except: pass
    return events

def parse_downtown(session):
    events = []
    try:
        res = session.get("https://www.downtownlongmont.com/events/calendar")
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.select('a.evcard'):
            try:
                title = card.find(class_=re.compile(r'headline|title')).get_text(strip=True)
                day = card.find(class_=re.compile(r'day')).get_text(strip=True)
                mon = card.find(class_=re.compile(r'month')).get_text(strip=True)
                temp_dt = datetime.strptime(f"{mon} {day}", "%b %d")
                year = datetime.now().year if temp_dt.month >= datetime.now().month else datetime.now().year + 1
                events.append({
                    "title": title, "venue": "Downtown Longmont",
                    "date": LOCAL_TZ.localize(temp_dt.replace(year=year, hour=19, minute=0)),
                    "url": "https://www.downtownlongmont.com" + card['href']
                })
            except: continue
    except: pass
    return events

# --- MAIN ---

def main():
    print("🚀 Running Full-Power Scraper...")
    session = get_session()
    raw = []
    
    raw.extend(parse_downtown(session))
    raw.extend(parse_squarespace(session, "https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    raw.extend(parse_squarespace(session, "https://www.barnevents.info/events", "The Barn"))
    
    htix_hosts = [
        ("https://events.humanitix.com/host/hell-yes-music-promotions", "Hell Yes Music"),
        ("https://events.humanitix.com/host/moshmont-mafia-and-outlaw-production-collective", "Moshmont Mafia"),
        ("https://events.humanitix.com/host/lunar-lux-music-and-arts-festival", "Lunar Lux")
    ]
    for url, name in htix_hosts:
        raw.extend(parse_humanitix(session, url, name))
    
    cal = Calendar()
    seen = set()
    count = 0

    for data in raw:
        t_low = data['title'].lower()
        if any(x in t_low for x in EXCLUDE): continue
        
        # Deep Analysis (RESTORED)
        description = get_deep_description(session, data['url'])
        genre_tag = detect_genre(data['title'], description)

        # Gatekeeping
        is_music = any(m in t_low for m in MUSIC_KEYWORDS) or \
                   any(v in data['venue'].lower() for v in TRUSTED_VENUES) or \
                   genre_tag != ""

        if not is_music: continue

        fingerprint = f"{data['date'].strftime('%Y%m%d')}_{t_low[:15]}"
        if fingerprint in seen: continue

        e = Event()
        e.name = f"🎵 {genre_tag}{data['title']}"
        e.begin = data['date']
        e.location = data['venue']
        e.description = f"{description}\n\nLink: {data['url']}"
        cal.events.add(e)
        seen.add(fingerprint)
        count += 1
        print(f"  [+] Added: {data['title']} (@{data['venue']})")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Finished! {count} events saved.")

if __name__ == "__main__":
    main()
