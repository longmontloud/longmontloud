import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re

# --- CONFIG ---
OUTPUT_FILE = "longmont_music_final.ics"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
LOCAL_TZ = pytz.timezone("America/Denver")

# --- FILTERS ---
EXCLUDE = [
    'karaoke', 'open mic', 'canvas classic', 'dinner', 'paperback tour', 'open sing', 'trivia', 'bingo', 'workshop', 'meeting', 'retail', 'watercolor', 'exhibition', 'the golden bee', 'sing-along', 'easel', 'studio tour', 'art materials', 'seminar', 'documentary',
    'comedy', 'yoga', 'poker', 'drawing class', 'craft class', 'create club', 'teen', 'crochet', 'wine dinner', 'tasting', 'pairing', 'prix fixe', 'shakespeare', 'happy day plants', 'headshot', 'stitch', 'embroidery',
    'storytime', 'book club', 'knitting', 'market', 'board game', 'meditation', 'speaker series', 'stationery', 'wolf & wren', 'talk', 'tarot', 'blackbird house', 'barbed wire books', 'dining', 'crafts & cocktails', 
    'teacher', 'discussion', 'rogen', 'networking', 'discovery days', 'uke jam', 'painting', 'sip', 'wines', '720-453-4733', 'date night', '303-651-8374', 'open-house', 'open house', 'crackpots', 'bubbly', 'joke', 'potting',
    'your stage', 'tangerine', 'composition', 'ballet', 'dance class', 'movie', 'bubbles', 'sewing', 'brunch', 'mimosas', 'bellinis', 'denim day', 'poetry night', 'poetry slam', 'sewing', 'sew', 'guest speakers', 'bloody mary',
    'wrestling', 'smack down', 'rockymountainpro', 'plant sale', 'pop up', 'skincare' # Added specific safety nets
]

MUSIC_KEYWORDS = [
    'live music', 'live band', 'symphony', 'acoustic', 'jazz', 'supper club', 'sessions',
    'blues', 'rock', 'singer', 'songwriter', 'orchestra', 'dj',
    'rave', 'grunge', 'folk', 'metal', 'punk', 'hip-hop', 'brass'
]

GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band', 'bebop'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge', 'psychedelic', 'noise', 'experimental'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'americana'],
    'Blues': ['blues', 'harmonica', 'soul'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music', 'rave', 'edm', 'techno'],
    'Classical': ['orchestra', 'symphony', 'classical', 'quartet', 'chamber'],
    'Country': ['country', 'western', 'honky tonk', 'cowboy']
}

TRUSTED_DOMAINS = ['barnevents.info', 'johnsonsstation.com', 'supperclub']

def detect_genre(text):
    t = text.lower()
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", t) for k in keywords):
            return f"[{genre}] "
    return ""

def extract_time(text):
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)', text.lower())
    if match:
        hr = int(match.group(1))
        mn = int(match.group(2)) if match.group(2) else 0
        ampm = match.group(3).replace('.', '')
        if ampm == 'pm' and hr < 12: hr += 12
        if ampm == 'am' and hr == 12: hr = 0
        return hr, mn
    return 19, 0 

def parse_atc_date(date_str):
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %I:%M %p", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

def has_music_keyword(text):
    t = text.lower()
    return any(re.search(rf"\b{re.escape(m)}\b", t) for m in MUSIC_KEYWORDS)

def main():
    print("🚀 Running Production Context Match Scraper...")
    cal = Calendar()
    seen_links, seen_events = set(), set()
    now_dt = datetime.now(LOCAL_TZ) # Establish today's horizon line
    count = 0

    # --- 1. SINGLE-PAGE TARGETS (Summit Tacos) ---
    print("\n🔍 Scanning Single-Page Targets...")
    summit_url = "https://eatsummittacos.com/longmont-downtown-longmont-summit-tacos-events"
    try:
        res = requests.get(summit_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        atc_titles = soup.find_all('var', class_=re.compile('atc_title'))
        
        for title_var in atc_titles:
            try:
                container = title_var.find_parent() 
                event_title = title_var.get_text(strip=True)
                if not event_title: continue
                
                start_var = title_var.find_next_sibling('var', class_=re.compile('atc_date_start')) or container.find('var', class_=re.compile('atc_date_start'))
                desc_var = title_var.find_next_sibling('var', class_=re.compile('atc_description')) or container.find('var', class_=re.compile('atc_description'))
                
                body_text = desc_var.get_text(" ", strip=True) if desc_var else ""
                combined_text = (event_title + " " + body_text).lower()
                
                if any(x in event_title.lower() for x in EXCLUDE): continue
                if any(x in combined_text for x in EXCLUDE) and not has_music_keyword(event_title): continue
                if not has_music_keyword(combined_text): continue
                
                start_str = start_var.get_text(strip=True) if start_var else ""
                parsed_dt = parse_atc_date(start_str)
                if not parsed_dt: continue
                
                if parsed_dt.year != 2026:
                    parsed_dt = parsed_dt.replace(year=2026)
                    
                start_dt = LOCAL_TZ.localize(parsed_dt)
                
                # --- PAST EVENT GATEKEEPER ---
                if start_dt.date() < now_dt.date(): continue

                venue_loc = "Summit Tacos, 237 Collyer St, Longmont CO 80501"
                fingerprint = f"{start_dt.strftime('%Y%m%d')}_{event_title[:15].lower()}"
                if fingerprint in seen_events: continue
                seen_events.add(fingerprint)

                e = Event()
                e.name = f"🎵 {detect_genre(combined_text)}{event_title}"
                e.begin = start_dt
                e.end = start_dt + timedelta(hours=2)
                e.location = venue_loc
                e.description = f"Source: {summit_url}"
                cal.events.add(e)
                count += 1
                print(f"  [+] {start_dt.strftime('%B %d, %I:%M%p')} | {event_title} @ {venue_loc}")
            except Exception:
                continue
    except Exception as e:
        print(f"Failed to scan Summit Tacos: {e}")

    # --- 2. MULTI-PAGE TARGETS ---
    print("\n🔍 Scanning Multi-Page Targets...")
    multi_targets = [
        ("https://www.downtownlongmont.com/events/calendar", "https://www.downtownlongmont.com"),
        ("https://www.johnsonsstation.com/calendar", "https://www.johnsonsstation.com"),
        ("https://www.barnevents.info/events", "https://www.barnevents.info"),
        ("https://www.stvraincidery.com/events", "https://www.stvraincidery.com")]

    # --- 3. HUMANITIX SCHEMATIC TARGETS ---
    print("\n🔍 Scanning Humanitix Targets...")
    humanitix_urls = [
        "https://events.humanitix.com/host/lunar-lux-music-and-arts-festival"
    ]
    
    import json  # Ensure json is imported at the top of your file

    for hx_url in humanitix_urls:
        try:
            res = requests.get(hx_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Find all SEO/Schema structured data blocks on the page
            script_tags = soup.find_all('script', type='application/ld+json')
            
            for tag in script_tags:
                try:
                    data = json.loads(tag.string)
                    
                    # Humanitix often wraps listings inside an ItemList element
                    events_list = []
                    if isinstance(data, dict):
                        if data.get("@type") == "ItemList" and "itemListElement" in data:
                            events_list = [el.get("item") for el in data["itemListElement"] if el.get("item")]
                        elif data.get("@type") == "Event":
                            events_list = [data]
                    
                    for ev in events_list:
                        if not ev or ev.get("@type") != "Event": continue
                        
                        event_title = ev.get("name", "").strip()
                        raw_desc = ev.get("description", "")
                        combined_text = f"{event_title} {raw_desc}".lower()
                        
                        # --- STRICT MUSIC FILTERS ---
                        if any(x in event_title.lower() for x in EXCLUDE): continue
                        if any(x in combined_text for x in EXCLUDE) and not has_music_keyword(event_title): continue
                        if not has_music_keyword(combined_text): continue
                        
                        # Parse out the clean ISO 8601 Timestamp (e.g., 2026-07-11T19:00:00-0600)
                        start_str = ev.get("startDate")
                        if not start_str: continue
                        
                        # Strip trailing timezone offsets if Python's fromisoformat needs a cleaner string
                        # split on '-' or '+' for the timezone offset if needed, or parse directly:
                        try:
                            # fromisoformat handles offsets like -06:00, we replace -0600 to -06:00 if necessary
                            if re.search(r'[-+]\d{4}$', start_str):
                                start_str = start_str[:-2] + ":" + start_str[-2:]
                            parsed_dt = datetime.fromisoformat(start_str)
                        except ValueError:
                            continue
                        
                        # Ensure timezone awareness matches Mountain Time
                        start_dt = parsed_dt.astimezone(LOCAL_TZ)
                        if start_dt.date() < now_dt.date(): continue
                        
                        # Extract the exact location metadata nested in the schema
                        loc_data = ev.get("location", {})
                        venue_name = loc_data.get("name", "Lunar Lux Festival Location")
                        address_data = loc_data.get("address", {})
                        street = address_data.get("streetAddress", "Longmont, CO")
                        venue_loc = f"{venue_name}, {street}"
                        
                        # Deduplication Engine Fingerprint
                        fingerprint = f"{start_dt.strftime('%Y%m%d')}_{event_title[:15].lower()}"
                        if fingerprint in seen_events: continue
                        seen_events.add(fingerprint)
                        
                        # Build and save standard ICS Event
                        e = Event()
                        e.name = f"🎵 {detect_genre(combined_text)}{event_title}"
                        e.begin = start_dt
                        e.end = start_dt + timedelta(hours=3) # Music events/festivals run a bit longer
                        e.location = venue_loc
                        e.description = f"Source: {ev.get('url', hx_url)}"
                        
                        cal.events.add(e)
                        count += 1
                        print(f"  [+] {start_dt.strftime('%B %d, %I:%M%p')} | {event_title} @ {venue_name}")
                        
                except (json.JSONDecodeError, TypeError, AttributeError):
                    continue
        except Exception as e:
            print(f"Failed to scan Humanitix target {hx_url}: {e}")
    ]

    for base_url, domain in multi_targets:
        try:
            res = requests.get(base_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            links = [domain + a['href'] if a['href'].startswith('/') else a['href'] 
                     for a in soup.find_all('a', href=True) 
                     if any(p in a['href'] for p in ['/do/', '/events/', '/calendar/'])]

            for full_url in list(set(links)):
                if full_url in seen_links or full_url.strip('/') == base_url.strip('/'): continue
                seen_links.add(full_url)

                try:
                    ev_res = requests.get(full_url, headers=HEADERS, timeout=10)
                    ev_soup = BeautifulSoup(ev_res.text, 'html.parser')
                    
                    event_title = ""
                    sqs_title = ev_soup.find(class_="eventitem-title")
                    if sqs_title: event_title = sqs_title.get_text(strip=True)
                    if not event_title:
                        h1 = ev_soup.find('h1')
                        if h1: event_title = h1.get_text(strip=True)
                    
                    if not event_title or event_title.lower() in ["barn events", "johnson's station", "calendar"]: continue
                    raw_title = event_title

                    # Adaptive "Smart-Pipe" Engine & Venue Taxonomy Filter
                    explicit_music = False
                    skip_event = False
                    if '|' in event_title:
                        parts = [p.strip() for p in event_title.split('|')]
                        prefix = parts[0].lower()
                        if prefix in ['music', 'live music']:
                            explicit_music = True
                            event_title = parts[1]
                        elif prefix in ['class', 'discussion', 'workshop', 'art', 'pop up', 'event']:
                            # Trust venue structure: if tagged explicitly non-music, drop it unless title fights back
                            if not has_music_keyword(parts[1]):
                                skip_event = True
                            event_title = parts[1]
                        else:
                            event_title = parts[0]
                    
                    if skip_event: continue

                    date_time_block = ""
                    start_hr, start_min = 19, 0  
                    
                    dl_date_span = ev_soup.find('span', class_='dldate')
                    dl_time_span = ev_soup.find('span', class_='dltime')

                    if dl_date_span and dl_time_span:
                        date_time_block = dl_date_span.get_text(" ", strip=True)
                        time_text = dl_time_span.get_text(" ", strip=True)
                        start_hr, start_min = extract_time(time_text)
                    else:
                        main_content = ev_soup.select_one('.eventitem-description, .description, .details, .sqs-block-content, article')
                        date_time_block = main_content.get_text(" ", strip=True) if main_content else ev_soup.get_text(" ", strip=True)[:1000]
                        start_hr, start_min = extract_time(date_time_block)

                    # --- ISOLATED DESCRIPTION PARSING (Stops Sidebar Leaks) ---
                    content_block = ev_soup.select_one('.eventitem-description, .sqs-block-content, article')
                    body_text = content_block.get_text(" ", strip=True)[:2000] if content_block else ev_soup.get_text(" ", strip=True)[:1500]
                    combined_text = (raw_title + " " + body_text).lower()
                    
                    # --- STRICT FILTERS ---
                    if any(x in event_title.lower() for x in EXCLUDE) or any(x in raw_title.lower() for x in EXCLUDE): 
                        continue
                    
                    is_trusted = any(d in full_url for d in TRUSTED_DOMAINS)
                    has_music = explicit_music or has_music_keyword(combined_text)
                    if not (is_trusted or has_music): continue
                    
                    if any(x in combined_text for x in EXCLUDE):
                        if not (explicit_music or has_music_keyword(event_title)):
                            continue

                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})', date_time_block)
                    if not date_match: continue
                    
                    month_val = datetime.strptime(date_match.group(1)[:3], "%b").month
                    start_dt = LOCAL_TZ.localize(datetime(2026, month_val, int(date_match.group(2)), start_hr, start_min))

                    # --- PAST EVENT GATEKEEPER ---
                    if start_dt.date() < now_dt.date(): continue

                    venue_loc = "Longmont, CO"
                    if "barnevents.info" in full_url:
                        venue_loc = "The Barn"
                    elif "johnsonsstation.com" in full_url:
                        venue_loc = "Johnson's Station, 1111 Neon Forest Circle, Longmont, CO 80501"
                    elif "stvraincidery.com" in full_url:
                        venue_loc = "St. Vrain Cidery, 350 Terry St #130, Longmont, CO 80501"
                    else:
                        loc_header = ev_soup.find('h2', class_='on-detail', string=re.compile('Location', re.I))
                        if loc_header:
                            venue_candidate = loc_header.find_next()
                            if venue_candidate:
                                venue_loc = venue_candidate.get_text(", ", strip=True)

                    fingerprint = f"{start_dt.strftime('%Y%m%d')}_{event_title[:15].lower()}"
                    if fingerprint in seen_events: continue
                    seen_events.add(fingerprint)

                    e = Event()
                    e.name = f"🎵 {detect_genre(combined_text)}{event_title}"
                    e.begin = start_dt
                    e.end = start_dt + timedelta(hours=2)
                    e.location = venue_loc
                    e.description = f"Source: {full_url}"
                    cal.events.add(e)
                    count += 1
                    print(f"  [+] {start_dt.strftime('%B %d, %I:%M%p')} | {event_title} @ {venue_loc}")

                except: continue
        except: continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize_iter())
    print(f"\n✅ Success! {count} Music Events saved to {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
