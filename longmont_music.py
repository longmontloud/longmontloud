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

# --- FILTER LOGIC ---
EXCLUDE = [
    'karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'retail',
    'comedy', 'yoga', 'poker', 'drawing', 'craft', 'create club', 'teen', 
    'storytime', 'book club', 'knitting', 'market', 'board game', 'meditation', 
    'teacher', 'discussion', 'ragen', 'networking', 'discovery days', 'uke jam', 
    'your stage', 'tangerine', 'composition', 'ballet', 'dance class', 
    'film', 'movie', 'bubbles', 'sewing', 'brunch', 'mimosas', 'bellinis'
]
# Added 'supper club', 'solo', 'duo', 'trio' to catch artist-only listings
MUSIC_KEYWORDS = [
    'music', 'band', 'concert', 'symphony', 'acoustic', 'jazz', 'supper club',
    'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj', 'solo', 'duo',
    'rave', 'grunge', 'folk', 'metal', 'punk', 'hip-hop', 'live music', 'brass'
]
TRUSTED_VENUES = ['bricks on main', 'the barn', 'johnsons station', 'supper club']

# --- TIME PARSING ---
def find_times(text):
    time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?'
    matches = re.findall(time_pattern, text)
    if not matches: return None, None, None

    def convert_to_24h(hour, minute, ampm):
        h, m = int(hour), int(minute) if minute else 0
        ampm = ampm.lower() if ampm else ""
        if not ampm: ampm = 'pm' if 1 <= h <= 10 else 'am' # Shifted range to 10 for late shows
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
        # Search for any block that looks like an event
        for item in soup.select('article, .eventlist-item, .summary-item, .sqs-events-collection-list'):
            try:
                # RECOVERY: Try multiple title locations
                title_el = item.find(class_=re.compile(r'title|headline|link'))
                if not title_el: continue
                title = title_el.get_text(strip=True)
                
                # If title is still empty, check for an aria-label or nested span
                if not title:
                    link = item.find('a')
                    title = link.get('aria-label') or link.get_text(strip=True)
                
                if not title: continue
                
                link_tag = item.find('a', href=True)
                date_tag = item.select_one('time[datetime], .event-date, [date]')
                if not date_tag: continue
                
                dt_val = date_tag.get('datetime') or date_tag.get('date') or date_tag.get_text(strip=True)
                
                events.append({
                    "title": title, "venue": venue_name,
                    "time_text": item.get_text(),
                    "date": datetime.strptime(dt_val[:10], "%Y-%m-%d"),
                    "url": base_domain + link_tag['href'] if link_tag['href'].startswith('/') else link_tag['href']
                })
            except: continue
    except: pass
    return events

# --- MAIN ---

def main():
    print("🚀 Running Ultimate Longmont Scraper...")
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
            v_low = data['venue'].lower()
            
            if any(x in t_low for x in EXCLUDE): continue
            
            res_detail = requests.get(data['url'], headers=HEADERS, timeout=10)
            soup_detail = BeautifulSoup(res_detail.text, 'html.parser')
            
            # Target description but fall back to body if needed
            detail_area = soup_detail.select_one('.eventlist-description, .event-item-description, .sqs-block-content, #page-content, main')
            detail_text = detail_area.get_text(separator=" ", strip=True).lower() if detail_area else ""

            if any(x in detail_text for x in EXCLUDE): continue

            # The "Trusted" check: If it's a trusted venue, we are MUCH more lenient with keywords
            is_trusted = any(v in v_low for v in TRUSTED_VENUES) or any(v in t_low for v in TRUSTED_VENUES)
            has_music_keywords = any(m in t_low for m in MUSIC_KEYWORDS) or any(m in detail_text for m in MUSIC_KEYWORDS)

            if not (is_trusted or has_music_keywords):
                continue

            sh, sm, eh = find_times(f"{data['title']} {detail_text}")
            time_warning = ""
            if sh is not None:
                start_dt = LOCAL_TZ.localize(data['date'].replace(hour=sh, minute=sm))
                end_dt = LOCAL_TZ.localize(data['date'].replace(hour=eh, minute=0))
            else:
                start_dt = LOCAL_TZ.localize(data['date'].replace(hour=19, minute=0))
                end_dt = start_dt + timedelta(hours=2)
                time_warning = "⚠️ Time not confirmed. Check link for info.\n\n"

            fingerprint = f"{start_dt.strftime('%Y%m%d')}_{t_low[:10]}"
            if fingerprint in seen: continue

            e = Event()
            e.name = f"🎵 {data['title']}"
            e.begin = start_dt
            e.end = end_dt
            e.location = data['venue']
            e.description = f"{time_warning}Venue: {data['venue']}\nLink: {data['url']}\n\n{detail_text[:300]}..."
            
            cal.events.add(e)
            seen.add(fingerprint)
            count += 1
            print(f"  [+] Added: {data['title']} @ {data['venue']}")
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ SUCCESS: {count} events processed.")

if __name__ == "__main__":
    main()
