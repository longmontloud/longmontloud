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
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'wibby brewing', 'bricks on main']

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'folksy'],
    'Blues': ['blues', 'harmonica'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music'],
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
    if not url or url == "#": return "Details at venue website."
    try:
        time.sleep(0.3)
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        content_area = soup.select_one('.ev-details-content, .eventlist-description, #event-details, .entry-content, .event-item-description')
        return content_area.get_text(separator="\n", strip=True) if content_area else "Details at venue website."
    except:
        return "Details available at link."

# --- SITE PARSERS ---

def parse_downtown_longmont():
    events = []
    url = "https://www.downtownlongmont.com/events/calendar"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.select('a.evcard'):
            try:
                title_el = card.find(class_=re.compile(r'headline|title'))
                day_el = card.find(class_=re.compile(r'day'))
                mon_el = card.find(class_=re.compile(r'month'))
                if not title_el or not day_el: continue
                
                temp_dt = datetime.strptime(f"{mon_el.text.strip()} {day_el.text.strip()}", "%b %d")
                year = datetime.now().year if temp_dt.month >= datetime.now().month else datetime.now().year + 1
                
                events.append({
                    "title": title_el.get_text(strip=True),
                    "venue": card.find(class_=re.compile(r'venue')).get_text(strip=True) if card.find(class_=re.compile(r'venue')) else "Downtown Longmont",
                    "url": "https://www.downtownlongmont.com" + card['href'],
                    "date": temp_dt.replace(year=year)
                })
            except: continue
    except: pass
    return events

def parse_squarespace_site(url, venue_name):
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('article.eventlist-event--upcoming, .eventlist-event'):
            try:
                link = item.select_one('a.eventlist-title-link, a[href*="/events/"]')
                if not link: continue
                date_tag = item.select_one('time.event-date')
                date_str = date_tag['datetime'] if date_tag else datetime.now().strftime("%Y-%m-%d")
                
                base_url = url.split('.com')[0] + ".com"
                events.append({
                    "title": link.get_text(strip=True),
                    "venue": venue_name,
                    "url": base_url + link['href'] if link['href'].startswith('/') else link['href'],
                    "date": datetime.strptime(date_str[:10], "%Y-%m-%d")
                })
            except: continue
    except: pass
    return events

def parse_wibby_brewing():
    events = []
    url = "https://www.wibbybrewing.com/events"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Wibby pattern: "Saturday, April 11"
        for item in soup.select('.event-item, .summary-item'):
            try:
                title = item.select_one('.event-title, .summary-title').get_text(strip=True)
                date_text = item.select_one('.event-date, .summary-metadata-item--date').get_text(strip=True)
                # Clean date: "April 11, 2026"
                clean_date = re.sub(r'^[A-Za-z]+,\s*', '', date_text) 
                event_date = datetime.strptime(f"{clean_date} {datetime.now().year}", "%B %d %Y")
                link = item.find('a')['href']
                events.append({
                    "title": title, "venue": "Wibby Brewing", "date": event_date,
                    "url": "https://www.wibbybrewing.com" + link if link.startswith('/') else link
                })
            except: continue
    except: pass
    return events

def parse_duets_bistro():
    events = []
    url = "https://duetsbistrodeli.com/events"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Duets layout uses summary-v2-block
        for item in soup.select('.summary-item'):
            try:
                title = item.select_one('.summary-title').get_text(strip=True)
                link = item.select_one('.summary-title a')['href']
                date_tag = item.select_one('time.summary-metadata-item--date')
                date_str = date_tag['datetime'] if date_tag else datetime.now().strftime("%Y-%m-%d")
                events.append({
                    "title": title, "venue": "Duets Bistro", "date": datetime.strptime(date_str[:10], "%Y-%m-%d"),
                    "url": "https://duetsbistrodeli.com" + link if link.startswith('/') else link
                })
            except: continue
    except: pass
    return events

# --- MAIN ENGINE ---

def main():
    print("🚀 Running Combined Master Scraper...")
    raw_collection = []
    
    # 1. Gather all data
    raw_collection.extend(parse_downtown_longmont())
    raw_collection.extend(parse_squarespace_site("https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    raw_collection.extend(parse_squarespace_site("https://www.barnevents.info/events", "The Barn"))
    raw_collection.extend(parse_wibby_brewing())
    raw_collection.extend(parse_duets_bistro())
    
    cal = Calendar()
    seen_fingerprints = set()
    count = 0

    for data in raw_collection:
        try:
            title_low = data['title'].lower()
            venue_low = data['venue'].lower()

            if any(x in title_low for x in EXCLUDE): continue

            # Fingerprint: YYYYMMDD + first 5 chars of venue
            fingerprint = f"{data['date'].strftime('%Y%m%d')}_{venue_low[:5]}"
            if fingerprint in seen_fingerprints: continue

            # Deep Analysis
            description = get_deep_description(data['url'])
            genre_tag = detect_genre(data['title'], description)

            # Triple Gate Check (OR logic)
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
    print(f"\n✅ Finished! {count} unique events saved to {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
