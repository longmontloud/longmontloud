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

# Filtering Logic
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'soundpost', 'sessions', 'orchestra', 'dj']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'wibby brewing', 'bricks on main', 'the dickens', 'abbott & wallace', 'johnsons station', 'the barn']

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'folksy'],
    'Blues': ['blues', 'harmonica'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music', 'EDM', 'dubstep', 'rave'],
    'Classical': ['orchestra', 'symphony', 'classical'],
    'Hip-Hop/R&B': ['hip-hop', 'hip hop', 'rap', 'soul', 'r&b', 'funk']
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
    try:
        time.sleep(0.3) # Politeness
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        content_area = soup.select_one('.ev-details-content, .eventlist-description, #event-details, .entry-content, .event-item-description')
        if not content_area:
            paragraphs = soup.find_all('p')
            return "\n".join([p.get_text() for p in paragraphs[:3]])
        return content_area.get_text(separator="\n", strip=True)
    except:
        return "Details available at venue website."

# --- SITE-SPECIFIC PARSERS ---

def parse_downtown_longmont():
    events = []
    url = "https://www.downtownlongmont.com/events/calendar"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.find_all('a', class_='evcard'):
            title = card.find(class_='evcard-content-headline').get_text(strip=True)
            venue = card.find(class_='evcard-content-venue').get_text(strip=True) if card.find(class_='evcard-content-venue') else "Downtown Longmont"
            href = card['href']
            full_url = "https://www.downtownlongmont.com" + href if href.startswith('/') else href
            day = card.find(class_='evcard-date-day').get_text(strip=True)
            mon = card.find(class_='evcard-date-month').get_text(strip=True)
            temp_dt = datetime.strptime(f"{mon} {day}", "%b %d")
            year = datetime.now().year if temp_dt.month >= datetime.now().month else datetime.now().year + 1
            event_date = temp_dt.replace(year=year)
            time_str = card.find(class_='evcard-content-time').get_text(strip=True) if card.find(class_='evcard-content-time') else "7:00 PM"
            events.append({"title": title, "venue": venue, "url": full_url, "date": event_date, "time_str": time_str})
    except: pass
    return events

def parse_johnsons_station():
    events = []
    url = "https://www.johnsonsstation.com/calendar"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('article.eventlist-event--upcoming'):
            link_tag = item.select_one('a.eventlist-title-link')
            title = link_tag.get_text(strip=True)
            full_url = "https://www.johnsonsstation.com" + link_tag['href']
            date_str = item.select_one('time.event-date')['datetime']
            event_date = datetime.strptime(date_str, "%Y-%m-%d")
            time_el = item.select_one('.eventlist-meta-time-start')
            time_str = time_el.get_text(strip=True) if time_el else "7:00 PM"
            events.append({"title": title, "venue": "Johnson's Station", "url": full_url, "date": event_date, "time_str": time_str})
    except: pass
    return events

def parse_the_barn():
    events = []
    url = "https://www.barnevents.info/events"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('article.eventlist-event--upcoming'):
            link_tag = item.select_one('a.eventlist-title-link')
            title = link_tag.get_text(strip=True)
            full_url = "https://www.barnevents.info" + link_tag['href']
            date_str = item.select_one('time.event-date')['datetime']
            event_date = datetime.strptime(date_str, "%Y-%m-%d")
            events.append({"title": title, "venue": "The Barn", "url": full_url, "date": event_date, "time_str": "6:00 PM"})
    except: pass
    return events

def parse_duets_bistro():
    events = []
    url = "https://duetsbistrodeli.com/events"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for item in soup.select('.event-item, .summary-item'):
            title_el = item.find(['h1', 'h2', 'h3'])
            if not title_el: continue
            title = title_el.get_text(strip=True)
            link_tag = item.find('a')
            full_url = "https://duetsbistrodeli.com" + link_tag['href'] if link_tag['href'].startswith('/') else link_tag['href']
            date_el = item.select_one('time.event-date, .summary-metadata-item--date')
            event_date = datetime.now() # Fallback
            if date_el and date_el.has_attr('datetime'):
                event_date = datetime.strptime(date_el['datetime'][:10], "%Y-%m-%d")
            events.append({"title": title, "venue": "Duets Bistro", "url": full_url, "date": event_date, "time_str": "6:30 PM"})
    except: pass
    return events

# --- MASTER ENGINE ---

def main():
    print("🚀 Starting Master Scraper for Longmont Music...")
    raw_collection = []
    
    # Run all parsers
    raw_collection.extend(parse_downtown_longmont())
    raw_collection.extend(parse_johnsons_station())
    -- raw_collection.extend(parse_wibby_brewing())
    raw_collection.extend(parse_the_barn())
    raw_collection.extend(parse_duets_bistro())
    
    cal = Calendar()
    seen_fingerprints = set()
    count = 0

    for data in raw_collection:
        title_low = data['title'].lower()
        venue_low = data['venue'].lower()

        # 1. Exclusion Check
        if any(x in title_low for x in EXCLUDE): continue

        # 2. Deduplication Check (Date + Venue name)
        fingerprint = f"{data['date'].strftime('%Y%m%d')}_{venue_low.replace(' ', '')[:10]}"
        if fingerprint in seen_fingerprints:
            continue

        # 3. Description & Genre Processing
        description = get_deep_description(data['url'])
        genre_tag = detect_genre(data['title'], description)

        # 4. Final Music Relevance Check
        is_music = any(m in title_low for m in MUSIC_KEYWORDS) or \
                   any(v in venue_low for v in TRUSTED_VENUES) or \
                   genre_tag != ""

        if not is_music: continue

        # 5. Build Event object
        try:
            # Simple Time Logic
            time_match = re.search(r'(\d+)(?::(\d+))?\s*(pm|am)', data['time_str'].lower())
            hr = int(time_match.group(1)) if time_match else 19
            if time_match and time_match.group(3) == 'pm' and hr != 12: hr += 12
            mn = int(time_match.group(2)) if time_match and time_match.group(2) else 0
            start_dt = LOCAL_TZ.localize(data['date'].replace(hour=hr, minute=mn))
        except:
            start_dt = LOCAL_TZ.localize(data['date'].replace(hour=19, minute=0))

        e = Event()
        e.name = f"🎵 {genre_tag}{data['title']}"
        e.begin = start_dt
        e.end = start_dt + timedelta(hours=2)
        e.location = data['venue']
        e.description = f"{description}\n\nLink: {data['url']}"
        
        cal.events.add(e)
        seen_fingerprints.add(fingerprint)
        count += 1
        print(f"  [+] Added: {data['title']} @ {data['venue']}")

    # Final Output
    if count > 0:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.writelines(cal.serialize_iter())
        print(f"\n✅ SUCCESS! {count} total unique music events saved.")
    else:
        print("\n❌ No music events passed the filters.")

if __name__ == "__main__":
    main()
