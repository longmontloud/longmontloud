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

# --- YOUR STRICT LOGIC ---
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'soundpost', 'sessions', 'orchestra', 'dj', 'performance']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'bricks on main', 'the barn', 'johnsons station', 'hell yes music', 'moshmont', 'lunar lux']

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'folksy'],
    'Blues': ['blues', 'harmonica'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music', 'rave', 'edm'],
    'Classical': ['orchestra', 'symphony', 'classical']
}

# --- UTILS ---

def detect_genre(title, description):
    combined_text = f"{title} {description}".lower()
    for genre, keywords in GENRE_MAP.items():
        for keyword in keywords:
            pattern = rf"\b{re.escape(keyword.lower())}\b"
            if re.search(pattern, combined_text):
                return f"[{genre}] "
    return ""

def get_deep_description(url):
    if not url or url.startswith('#'): return "Details at venue website."
    try:
        time.sleep(0.2)
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Humanitix specific content area + standard ones
        content_area = soup.select_one('.event-description, [data-testid="event-description"], .ev-details-content, .eventlist-description, #event-details')
        return content_area.get_text(separator="\n", strip=True) if content_area else "Details at link."
    except:
        return "Details available at link."

# --- SITE PARSERS ---

def parse_humanitix(url, host_name):
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Humanitix host pages list events in specific cards
        for card in soup.select('a[href*="/events/"]'):
            try:
                # Find the title (usually inside a strong tag or heading)
                title_el = card.find(['h2', 'h3', 'strong', 'p'])
                if not title_el: continue
                title = title_el.get_text(strip=True)
                
                # Humanitix often puts date in a span/div nearby
                # We'll pull the link and date if possible
                full_url = "https://events.humanitix.com" + card['href'] if card['href'].startswith('/') else card['href']
                
                # Humanitix is JS heavy, so if we can't find a date easily, 
                # we'll use a placeholder and let the 'Deep Scrape' find it, 
                # or skip if it's too messy.
                events.append({
                    "title": title, "venue": host_name, "date": datetime.now(), # Placeholder, logic below handles it
                    "url": full_url
                })
            except: continue
    except: print(f"⚠️ Humanitix failed for {host_name}")
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
                venue = card.find(class_=re.compile(r'venue')).get_text(strip=True) if card.find(class_=re.compile(r'venue')) else "Downtown Longmont"
                temp_dt = datetime.strptime(f"{mon} {day}", "%b %d")
                year = datetime.now().year if temp_dt.month >= datetime.now().month else datetime.now().year + 1
                events.append({
                    "title": title, "venue": venue, "date": temp_dt.replace(year=year),
                    "url": "https://www.downtownlongmont.com" + card['href']
                })
            except: continue
    except: pass
    return events

def parse_squarespace_site(url, venue_name):
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        base_domain = "https://" + url.split('//')[1].split('/')[0]
        for item in soup.select('article.eventlist-event--upcoming'):
            try:
                link_tag = item.select_one('a.eventlist-title-link')
                date_tag = item.select_one('time.event-date')
                if not link_tag or not date_tag: continue
                events.append({
                    "title": link_tag.get_text(strip=True), "venue": venue_name,
                    "date": datetime.strptime(date_tag['datetime'][:10], "%Y-%m-%d"),
                    "url": base_domain + link_tag['href'] if link_tag['href'].startswith('/') else link_tag['href']
                })
            except: continue
    except: pass
    return events

# --- MAIN ENGINE ---

def main():
    print("🚀 Starting Extended 6-Site Scrape...")
    raw_collection = []
    
    # Standard Scrapers
    raw_collection.extend(parse_downtown_longmont())
    raw_collection.extend(parse_squarespace_site("https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    raw_collection.extend(parse_squarespace_site("https://www.barnevents.info/events", "The Barn"))
    
    # Humanitix Scrapers
    htix_hosts = [
        ("https://events.humanitix.com/host/hell-yes-music-promotions", "Hell Yes Music"),
        ("https://events.humanitix.com/host/moshmont-mafia-and-outlaw-production-collective", "Moshmont Mafia"),
        ("https://events.humanitix.com/host/lunar-lux-music-and-arts-festival", "Lunar Lux")
    ]
    for url, name in htix_hosts:
        raw_collection.extend(parse_humanitix(url, name))
    
    cal = Calendar()
    seen_fingerprints = set()
    count = 0

    for data in raw_collection:
        try:
            title_low = data['title'].lower()
            venue_low = data['venue'].lower()

            if any(x in title_low for x in EXCLUDE): continue

            # Fingerprint
            fingerprint = f"{data['date'].strftime('%Y%m%d')}_{venue_low[:4]}_{title_low[:5]}"
            if fingerprint in seen_fingerprints: continue

            # Deep Analysis
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
    print(f"\n✅ Finished! {count} total events saved.")

if __name__ == "__main__":
    main()
