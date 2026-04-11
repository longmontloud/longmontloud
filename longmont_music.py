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

# --- LOGIC ---
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
MUSIC_KEYWORDS = ['music', 'band', 'concert', 'live', 'symphony', 'acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'performance', 'festival', 'rave', 'grunge', 'folk', 'metal', 'punk']
TRUSTED_VENUES = ['bootstrap brewing', '300 suns brewing', 'bricks on main', 'the barn', 'johnsons station']

# --- TIME PARSING LOGIC ---

def find_times(text):
    """
    Look for time patterns like '6pm', '6:30 PM', '6:00-9:00'
    Returns (start_hour, start_minute, end_hour)
    """
    # Regex to find things like 6:30pm, 7pm, 11:00 AM
    time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?'
    matches = re.findall(time_pattern, text)
    
    if not matches:
        return None, None, None

    def convert_to_24h(hour, minute, ampm):
        h = int(hour)
        m = int(minute) if minute else 0
        ampm = ampm.lower() if ampm else ""
        
        # Smart guess: if no AM/PM, and hour is 1-8, assume PM for concerts
        if not ampm:
            if 1 <= h <= 8: ampm = 'pm'
            else: ampm = 'am'
            
        if ampm == 'pm' and h < 12: h += 12
        if ampm == 'am' and h == 12: h = 0
        return h, m

    # Get start time from first match
    start_h, start_m = convert_to_24h(matches[0][0], matches[0][1], matches[0][2])
    
    # Get end time from second match if it exists
    if len(matches) > 1:
        end_h, _ = convert_to_24h(matches[1][0], matches[1][1], matches[1][2])
    else:
        end_h = (start_h + 3) % 24 # Default to 3 hours if no end time found
        
    return start_h, start_m, end_h

# --- UTILS ---

def get_deep_description(url):
    if not url or url.startswith('#'): return ""
    try:
        time.sleep(0.3)
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        content = soup.select_one('.eventlist-description, .ev-details-content, .event-item-description, #event-details')
        return content.get_text(separator="\n", strip=True) if content else ""
    except:
        return ""

# --- PARSERS ---

def parse_squarespace(url, venue_name):
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        base_domain = "https://" + url.split('//')[1].split('/')[0]
        for item in soup.select('article.eventlist-event, .eventlist-item, .summary-item'):
            try:
                link_tag = item.select_one('a[href*="/events/"], a.eventlist-title-link')
                date_tag = item.select_one('time[datetime], time.event-date')
                if not link_tag or not date_tag: continue
                
                dt_str = date_tag.get('datetime', date_tag.get('date'))
                title = link_tag.get_text(strip=True)
                # Squarespace often has the time right in the metadata text
                time_text = item.get_text()
                
                events.append({
                    "title": title, "venue": venue_name, "time_text": time_text,
                    "date": datetime.strptime(dt_str[:10], "%Y-%m-%d"),
                    "url": base_domain + link_tag['href'] if link_tag['href'].startswith('/') else link_tag['href']
                })
            except: continue
    except: pass
    return events

def parse_downtown():
    events = []
    try:
        res = requests.get("https://www.downtownlongmont.com/events/calendar", headers=HEADERS)
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.select('a.evcard'):
            try:
                title = card.find(class_=re.compile(r'headline|title')).get_text(strip=True)
                day = card.find(class_=re.compile(r'day')).get_text(strip=True)
                mon = card.find(class_=re.compile(r'month')).get_text(strip=True)
                # Downtown Longmont often lists time in a specific span
                time_info = card.get_text()
                
                temp_dt = datetime.strptime(f"{mon} {day}", "%b %d")
                year = datetime.now().year if temp_dt.month >= datetime.now().month else datetime.now().year + 1
                events.append({
                    "title": title, "venue": "Downtown Longmont", "time_text": time_info,
                    "date": temp_dt.replace(year=year),
                    "url": "https://www.downtownlongmont.com" + card['href']
                })
            except: continue
    except: pass
    return events

# --- MAIN ---

def main():
    print("🚀 Running Time-Sensitive Scraper...")
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
            if any(x in t_low for x in EXCLUDE): continue

            # Scrape deep for time and genre verification
            full_desc = get_deep_description(data['url'])
            
            # Combine all available text to hunt for a time
            search_text = f"{data['title']} {data['time_text']} {full_desc}"
            sh, sm, eh = find_times(search_text)

            # Determine if we found a reliable time
            time_warning = ""
            if sh is not None:
                start_dt = LOCAL_TZ.localize(data['date'].replace(hour=sh, minute=sm))
                end_dt = LOCAL_TZ.localize(data['date'].replace(hour=eh, minute=0))
                # Ensure end isn't before start
                if end_dt <= start_dt: end_dt = start_dt + timedelta(hours=3)
            else:
                # Default if no time found
                start_dt = LOCAL_TZ.localize(data['date'].replace(hour=19, minute=0))
                end_dt = start_dt + timedelta(hours=1)
                time_warning = "⚠️ NOTE: Start time not confirmed. Please check the venue link for exact details.\n\n"

            fingerprint = f"{start_dt.strftime('%Y%m%d')}_{t_low[:15]}"
            if fingerprint in seen: continue

            e = Event()
            e.name = f"🎵 {data['title']}"
            e.begin = start_dt
            e.end = end_dt
            e.location = data['venue']
            e.description = f"{time_warning}{full_desc}\n\nLink: {data['url']}"
            
            cal.events.add(e)
            seen.add(fingerprint)
            count += 1
            print(f"  [+] Added: {data['title']} @ {start_dt.strftime('%I:%M %p')}")
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Finished! {count} events with time-detection.")

if __name__ == "__main__":
    main()
