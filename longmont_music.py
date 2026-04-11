import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime
import pytz
import re
import json

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- LOGIC ---
EXCLUDE = ['karaoke', 'open mic', 'trivia', 'bingo', 'workshop', 'class', 'meeting', 'comedy', 'yoga', 'poker', 'drawing']
TRUSTED_VENUES = ['hell yes', 'moshmont', 'lunar lux', 'the barn', 'johnsons station', 'bootstrap', '300 suns']

# --- NEW HUMANITIX PARSER ---

def parse_humanitix(url, host_name):
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        # Humanitix often hides event data in a JSON script tag
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Search for any script tag containing "startDate" or "MusicEvent"
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and ('startDate' in script.string or 'MusicEvent' in script.string):
                try:
                    # Clean the script string if it's wrapped in extra JS
                    clean_js = re.search(r'({.*})', script.string).group(1)
                    data = json.loads(clean_js)
                    
                    # Dig through nested data (Humanitix can be messy)
                    items = data.get('@graph', [data]) if isinstance(data, dict) else data
                    for item in items:
                        if isinstance(item, dict) and 'name' in item:
                            # Parse date - handle Humanitix ISO format
                            raw_date = item.get('startDate', datetime.now().isoformat())
                            dt = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
                            
                            events.append({
                                "title": item['name'],
                                "venue": host_name,
                                "date": dt.astimezone(LOCAL_TZ),
                                "url": item.get('url', url)
                            })
                except: continue

        # BACKUP: If JSON fails, look for 'event-card' links
        if not events:
            for link in soup.select('a[href*="/events/"]'):
                title = link.get_text(strip=True)
                if len(title) > 5 and not any(x in title.lower() for x in EXCLUDE):
                    full_url = "https://events.humanitix.com" + link['href'] if link['href'].startswith('/') else link['href']
                    events.append({
                        "title": title, "venue": host_name, "date": datetime.now(LOCAL_TZ), "url": full_url
                    })
    except Exception as e: print(f"⚠️ Humanitix Error ({host_name}): {e}")
    return events

# --- RE-OPTIMIZED SQUARESPACE & DOWNTOWN ---

def parse_squarespace(url, venue_name):
    events = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Target the specific 'article' tag Squarespace uses for events
        for item in soup.select('article.eventlist-event, .eventlist-item'):
            try:
                title = item.select_one('.eventlist-title, h1, h2').get_text(strip=True)
                date_tag = item.select_one('time[datetime]')
                link = item.select_one('a')['href']
                
                dt_str = date_tag['datetime']
                events.append({
                    "title": title, "venue": venue_name,
                    "date": LOCAL_TZ.localize(datetime.strptime(dt_str[:10], "%Y-%m-%d").replace(hour=19, minute=0)),
                    "url": ("https://" + url.split('//')[1].split('/')[0]) + link if link.startswith('/') else link
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
    print("🚀 Running All-Site Scrape...")
    raw = []
    raw.extend(parse_downtown())
    raw.extend(parse_squarespace("https://www.johnsonsstation.com/calendar", "Johnson's Station"))
    raw.extend(parse_squarespace("https://www.barnevents.info/events", "The Barn"))
    
    # Humanitix Loop
    hosts = [
        ("https://events.humanitix.com/host/hell-yes-music-promotions", "Hell Yes Music"),
        ("https://events.humanitix.com/host/moshmont-mafia-and-outlaw-production-collective", "Moshmont Mafia"),
        ("https://events.humanitix.com/host/lunar-lux-music-and-arts-festival", "Lunar Lux")
    ]
    for url, name in hosts:
        raw.extend(parse_humanitix(url, name))
    
    cal = Calendar()
    seen = set()
    count = 0

    for data in raw:
        t_low = data['title'].lower()
        if any(x in t_low for x in EXCLUDE): continue
        
        fingerprint = f"{data['date'].strftime('%Y%m%d')}_{t_low[:10]}"
        if fingerprint in seen: continue

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
    print(f"\n✅ Finished! {count} events saved.")

if __name__ == "__main__":
    main()
