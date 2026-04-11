import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re
import time

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- REFINED FILTER LOGIC ---
# Added even more non-music "clutter" keywords
EXCLUDE = [
    'karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 
    'comedy', 'yoga', 'poker', 'drawing', 'craft', 'create club', 'teen', 
    'storytime', 'book club', 'knitting', 'market', 'board game', 'meditation'
]
MUSIC_KEYWORDS = [
    'music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 
    'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'performance', 
    'festival', 'rave', 'grunge', 'folk', 'metal', 'punk', 'quartet', 'duo', 'trio'
]
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'bricks on main', 'the barn', 'johnsons station']

# --- TIME PARSING ---
def find_times(text):
    time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?'
    matches = re.findall(time_pattern, text)
    if not matches: return None, None, None

    def convert_to_24h(hour, minute, ampm):
        h, m = int(hour), int(minute) if minute else 0
        ampm = ampm.lower() if ampm else ""
        if not ampm: ampm = 'pm' if 1 <= h <= 8 else 'am'
        if ampm == 'pm' and h < 12: h += 12
        if ampm == 'am' and h == 12: h = 0
        return h, m

    start_h, start_m = convert_to_24h(matches[0][0], matches[0][1], matches[0][2])
    end_h = convert_to_24h(matches[1][0], matches[1][1], matches[1][2])[0] if len(matches) > 1 else (start_h + 3) % 24
    return start_h, start_m, end_h

# --- PARSERS ---

def parse_downtown():
    events = []
    try:
        res = requests.get("https://www.downtownlongmont.com/events/calendar", headers=HEADERS)
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.select('a.evcard'):
            try:
                title = card.find(class_=re.compile(r'headline|title')).get_text(strip=True)
                
                # FIX: Targeted Venue Extraction
                # Look for the specific 'venue' class or the 'location' span
                venue_el = card.find(class_=re.compile(r'venue|location|sub-headline'))
                venue_name = venue_el.get_text(strip=True) if venue_el else "Downtown Longmont"
                
                day = card.find(class_=re.compile(r'day')).get_text(strip=True)
                mon = card.find(class_=re.compile(r'month')).get_text(strip=True)
                temp_dt = datetime.strptime(f"{mon} {day}", "%b %d")
                year = datetime.now().year if temp_dt.month >= datetime.now().month else datetime.now().year + 1
                
                events.append({
                    "title": title, "venue": venue_name, "time_text": card.get_text(),
                    "date": temp_dt.replace(year=year),
                    "url": "https://www.downtownlongmont.com" + card['href']
                })
            except: continue
    except: pass
    return events

def parse_squarespace(url, venue_name):
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        base_domain = "https://" + url.split('//')[1].split('/')[0]
        for item in soup.select('article.eventlist-event, .eventlist-item'):
            try:
                link_tag = item.select_one('a[href*="/events/"]')
                date_tag = item.select_one('time[datetime]')
                if not link_tag or not date_tag: continue
                events.append({
                    "title": link_tag.get_text(strip=True), "venue": venue_name,
                    "time_text": item.get_text(),
                    "date": datetime.strptime(date_tag['datetime'][:10], "%Y-%m-%d"),
                    "url": base_domain + link_tag['href'] if link_tag['href'].startswith('/') else link_tag['href']
                })
            except: continue
    except: pass
    return events

# --- MAIN ---

def main():
    print("🚀 Running Filtered Community Scraper...")
    raw = []
    raw.extend(parse_downtown())
    raw.extend(parse_squarespace("https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    raw.extend(parse_squarespace("https://www.barnevents.info/events", "The Barn"))
    
    cal = Calendar()
    seen = set()
    count = 0

    for data in raw:
        try:
            t_low = data['title'].lower()
            
            # FIX 1: Aggressive Filter
            if any(x in t_low for x in EXCLUDE): continue
            
            # Fetch details to check for more music keywords
            res_detail = requests.get(data['url'], headers=HEADERS, timeout=10)
            soup_detail = BeautifulSoup(res_detail.text, 'html.parser')
            detail_text = soup_detail.get_text(separator=" ", strip=True).lower()

            # The "Two-Factor" Check: 
            # Must be a trusted venue OR have music keywords in title/description
            is_music = any(v in data['venue'].lower() for v in TRUSTED_VENUES) or \
                       any(m in t_low for m in MUSIC_KEYWORDS) or \
                       any(m in detail_text for m in MUSIC_KEYWORDS)

            if not is_music: continue

            # Time Logic
            sh, sm, eh = find_times(f"{data['title']} {detail_text}")
            time_warning = ""
            if sh is not None:
                start_dt = LOCAL_TZ.localize(data['date'].replace(hour=sh, minute=sm))
                end_dt = LOCAL_TZ.localize(data['date'].replace(hour=eh, minute=0))
            else:
                start_dt = LOCAL_TZ.localize(data['date'].replace(hour=19, minute=0))
                end_dt = start_dt + timedelta(hours=1)
                time_warning = "⚠️ Start time not confirmed. Check link.\n\n"

            fingerprint = f"{start_dt.strftime('%Y%m%d')}_{t_low[:15]}"
            if fingerprint in seen: continue

            e = Event()
            e.name = f"🎵 {data['title']}"
            e.begin = start_dt
            e.end = end_dt
            e.location = data['venue']
            e.description = f"{time_warning}Venue: {data['venue']}\nLink: {data['url']}"
            
            cal.events.add(e)
            seen.add(fingerprint)
            count += 1
            print(f"  [+] Added: {data['title']} @ {data['venue']}")
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Finished! {count} curated events saved.")

if __name__ == "__main__":
    main()
