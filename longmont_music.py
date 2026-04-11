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
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- GENRE & FILTER LOGIC ---
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'performance', 'festival', 'rave', 'grunge', 'folk', 'metal', 'punk']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'bricks on main', 'the barn', 'johnsons station']

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'folksy'],
    'Blues': ['blues', 'harmonica'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music', 'rave', 'edm', 'dubstep', 'rave'],
    'Classical': ['orchestra', 'symphony', 'classical']
}

# --- UTILS ---

def detect_genre(title, description):
    combined_text = f"{title} {description}".lower()
    for genre, keywords in GENRE_MAP.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword.lower())}\b", combined_text):
                return f"[{genre}] "
    return ""

def get_deep_description(url):
    if not url or url.startswith('#'): return ""
    try:
        time.sleep(0.3)
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Target common Squarespace and generic event detail areas
        content = soup.select_one('.eventlist-description, .ev-details-content, .event-item-description, #event-details')
        return content.get_text(separator="\n", strip=True) if content else ""
    except:
        return ""

# --- PARSERS ---

def parse_squarespace(url, venue_name):
    """Handles The Barn and Johnson's Station with high reliability"""
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        base_domain = "https://" + url.split('//')[1].split('/')[0]
        
        # Look for the classic Squarespace event article structure
        for item in soup.select('article.eventlist-event, .eventlist-item, .summary-item'):
            try:
                link_tag = item.select_one('a[href*="/events/"], a.eventlist-title-link')
                date_tag = item.select_one('time[datetime], time.event-date')
                
                if not link_tag or not date_tag: continue
                
                dt_str = date_tag.get('datetime', date_tag.get('date'))
                title = link_tag.get_text(strip=True)
                link = link_tag['href']
                
                events.append({
                    "title": title, 
                    "venue": venue_name,
                    "date": LOCAL_TZ.localize(datetime.strptime(dt_str[:10], "%Y-%m-%d").replace(hour=19, minute=0)),
                    "url": base_domain + link if link.startswith('/') else link
                })
            except: continue
    except Exception as e:
        print(f"⚠️ Error parsing {venue_name}: {e}")
    return events

def parse_downtown():
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

# --- MAIN ENGINE ---

def main():
    print("🚀 Starting Clean Scrape (Downtown, Barn, Johnson's)...")
    raw_collection = []
    
    raw_collection.extend(parse_downtown())
    raw_collection.extend(parse_squarespace("https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    raw_collection.extend(parse_squarespace("https://www.barnevents.info/events", "The Barn"))
    
    cal = Calendar()
    seen = set()
    count = 0

    for data in raw_collection:
        try:
            t_low = data['title'].lower()
            if any(x in t_low for x in EXCLUDE): continue
            
            # Deep Analysis for Genres & Description
            description = get_deep_description(data['url'])
            genre_tag = detect_genre(data['title'], description)

            # Strict Music Gate
            is_music = any(m in t_low for m in MUSIC_KEYWORDS) or \
                       any(v in data['venue'].lower() for v in TRUSTED_VENUES) or \
                       genre_tag != ""

            if not is_music: continue

            # Prevent Duplicates
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
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Success! {count} music events saved to {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
