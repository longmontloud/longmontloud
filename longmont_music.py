import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re
import json

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
    'wrestling', 'smack down', 'rockymountainpro', 'plant sale', 'pop up', 'skincare' 
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
    now_dt = datetime.now(LOCAL_TZ) 
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

# --- 2. HUMANITIX LOCAL ICS MERGE ENGINE ---
    print("\n🔍 Reading Local Humanitix Calendar Payload (Bypassing Network Firewall)...")
    
    import os
    from ics import Calendar as IcsCalendar
    
    local_ics_file = "humanitix_live.ics"
    
    try:
        # Check if the GitHub Action successfully downloaded the file
        if os.path.exists(local_ics_file) and os.path.getsize(local_ics_file) > 0:
            
            with open(local_ics_file, 'r', encoding='utf-8') as f:
                raw_text = f.read()
                
            # If curl got caught by a 403 HTML page instead of an ICS file, catch it here
            if "BEGIN:VCALENDAR" not in raw_text:
                print("  [-] Error: The downloaded file contains firewall HTML rather than a calendar stream.")
            else:
                remote_cal = IcsCalendar(raw_text)
                print(f"  [!] Local file parsed successfully. Processing {len(remote_cal.events)} live entries...")
                
                for remote_event in remote_cal.events:
                    event_title = remote_event.name.strip()
                    raw_desc = remote_event.description or ""
                    combined_text = f"{event_title} {raw_desc}".lower()
                    
                    # --- MASTER MUSIC PRODUCTION FILTERS ---
                    if any(x in event_title.lower() for x in EXCLUDE): continue
                    if any(x in combined_text for x in EXCLUDE) and not has_music_keyword(event_title): continue
                    if not has_music_keyword(combined_text): continue
                    
                    # Natively read the exact localized date tracking parameters
                    start_dt = remote_event.begin.astimezone(LOCAL_TZ)
                    if start_dt.date() < now_dt.date(): continue
                    
                    # Production Cross-Site Deduplication Check
                    fingerprint = f"{start_dt.strftime('%Y%m%d')}_{event_title[:15].lower()}"
                    if fingerprint in seen_events: continue
                    seen_events.add(fingerprint)
                    
                    # Map parameters cleanly straight into your production output structure
                    e = Event()
                    e.name = f"🎵 {detect_genre(combined_text)}{event_title}"
                    e.begin = start_dt
                    e.end = remote_event.end.astimezone(LOCAL_TZ) if remote_event.end else start_dt + timedelta(hours=3)
                    e.location = remote_event.location or "Longmont, CO"
                    e.description = raw_desc if raw_desc.startswith("http") else f"Source: https://events.humanitix.com/host/lunar-lux-music-and-arts-festival"
                    
                    cal.events.add(e)
                    count += 1
                    print(f"  [+] Unified Live Sync: {start_dt.strftime('%B %d, %I:%M%p')} | {event_title}")
        else:
            print(f"  [-] Local data payload '{local_ics_file}' was missing or empty.")
            
    except Exception as e:
        print(f"Failed to cleanly merge Humanitix local ICS payload: {e}")

# --- 3. WIBBY BREWING UNPROTECTED ICS FILTRATION ENGINE ---
    print("\n🔍 Downloading and Filtering Wibby Brewing Calendar...")
    
    # Replace this placeholder string with Wibby's actual public .ics subscription link
    WIBBY_ICS_URL = "https://data.accentapi.com/widget_export_calendar/25605810"
    
    try:
        # Standard requests work perfectly here because the endpoint is an open data asset
        res = requests.get(WIBBY_ICS_URL, headers=HEADERS, timeout=15)
        
        if res.status_code == 200:
            from ics import Calendar as IcsCalendar
            
            wibby_cal = IcsCalendar(res.text)
            print(f"  [!] Stream accessed successfully. Scanning {len(wibby_cal.events)} raw brewery entries...")
            
            wibby_count = 0
            for remote_event in wibby_cal.events:
                event_title = remote_event.name.strip()
                raw_desc = remote_event.description or ""
                combined_text = f"{event_title} {raw_desc}".lower()
                
                # --- MASTER MUSIC PRODUCTION FILTERS ---
                # This completely isolates and trashes Trivia, Bingo, Running Clubs, and Yoga!
                if any(x in event_title.lower() for x in EXCLUDE): continue
                if any(x in combined_text for x in EXCLUDE) and not has_music_keyword(event_title): continue
                if not has_music_keyword(combined_text): continue
                
                # Natively read and convert timezone parameters
                start_dt = remote_event.begin.astimezone(LOCAL_TZ)
                if start_dt.date() < now_dt.date(): continue
                
                # Production Cross-Site Deduplication Check
                fingerprint = f"{start_dt.strftime('%Y%m%d')}_{event_title[:15].lower()}"
                if fingerprint in seen_events: continue
                seen_events.add(fingerprint)
                
                # Construct the filtered, music-only output event entry
                e = Event()
                e.name = f"🎵 {detect_genre(combined_text)}{event_title}"
                e.begin = start_dt
                e.end = remote_event.end.astimezone(LOCAL_TZ) if remote_event.end else start_dt + timedelta(hours=3)
                e.location = remote_event.location or "Wibby Brewing, 209 Emery St, Longmont, CO 80501"
                e.description = raw_desc if raw_desc.strip() else f"Source: {WIBBY_ICS_URL}"
                
                cal.events.add(e)
                wibby_count += 1
                count += 1
                print(f"  [+] Filter Accepted: {start_dt.strftime('%B %d, %I:%M%p')} | {event_title}")
                
            print(f"  [!] Wibby Sync complete. Kept {wibby_count} music events, discarded the rest.")
        else:
            print(f"  [-] Failed to download Wibby calendar feed. Status: {res.status_code}")
            
    except Exception as e:
        print(f"Failed to process Wibby Brewing open calendar pipeline: {e}")

# --- 4. OSKAR BLUES LONGMONT HARVESTER (WIDGET EXTRACTOR) ---
    print("\n🔍 Extracting Oskar Blues Live Events from JavaScript Widget...")
    
    # This public widget bundle serves the live event arrays directly to the layout
    ob_widget_url = "https://api.popmenu.com/widgets/events/location/2334"
    
    WIDGET_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://www.oskarbluesfooderies.com/"
    }
    
    try:
        res = requests.get(ob_widget_url, headers=WIDGET_HEADERS, timeout=15)
        if res.status_code == 200:
            js_content = res.text
            
            # Use regex to find all titles, descriptions, and start dates embedded in the JS strings
            # Look for patterns like "title":"...", "description":"...", "start_at":"..."
            titles = re.findall(r'"title"\s*:\s*"([^"]+)"', js_content)
            descriptions = re.findall(r'"description"\s*:\s*"([^"]*)"', js_content)
            start_times = re.findall(r'"start_at"\s*:\s*"([^"]+)"', js_content)
            end_times = re.findall(r'"end_at"\s*:\s*"([^"]+)"', js_content)
            
            # Align the matches cleanly into a zip loop array frame
            min_length = min(len(titles), len(start_times))
            print(f"  [!] Widget data block unpacked. Processing {min_length} discovered timeline rows...")
            
            ob_count = 0
            for i in range(min_length):
                event_title = titles[i].encode().decode('unicode-escape').strip()
                raw_desc = descriptions[i].encode().decode('unicode-escape') if i < len(descriptions) else ""
                combined_text = f"{event_title} {raw_desc}".lower()
                
                # --- MASTER MUSIC PRODUCTION FILTERS ---
                if any(x in event_title.lower() for x in EXCLUDE): continue
                if any(x in combined_text for x in EXCLUDE) and not has_music_keyword(event_title): continue
                if not has_music_keyword(combined_text): continue
                
                start_str = start_times[i]
                try:
                    # Parse standard ISO timestamp markers natively
                    base_time = start_str.split('.')[0].replace('Z', '')
                    start_dt = datetime.fromisoformat(base_time)
                    
                    if start_dt.tzinfo is None:
                        start_dt = LOCAL_TZ.localize(start_dt)
                    else:
                        start_dt = start_dt.astimezone(LOCAL_TZ)
                except Exception:
                    continue
                    
                if start_dt.date() < now_dt.date(): continue
                
                # Cross-Site Deduplication Check
                fingerprint = f"{start_dt.strftime('%Y%m%d')}_{event_title[:15].lower()}"
                if fingerprint in seen_events: continue
                seen_events.add(fingerprint)
                
                # Build master output parameters
                e = Event()
                e.name = f"🎵 {detect_genre(combined_text)}{event_title}"
                e.begin = start_dt
                
                # Assign end dates if provided in the text payload
                if i < len(end_times):
                    try:
                        base_end = end_times[i].split('.')[0].replace('Z', '')
                        end_dt = datetime.fromisoformat(base_end)
                        e.end = LOCAL_TZ.localize(end_dt) if end_dt.tzinfo is None else end_dt.astimezone(LOCAL_TZ)
                    except Exception:
                        e.end = start_dt + timedelta(hours=2, minutes=30)
                else:
                    e.end = start_dt + timedelta(hours=2, minutes=30)
                    
                e.location = "Oskar Blues Home Made Liquids & Solids, 1555 Hover St, Longmont, CO 80501"
                e.description = f"{raw_desc}\n\nSource: https://www.oskarbluesfooderies.com/longmont-happenings"
                
                cal.events.add(e)
                ob_count += 1
                count += 1
                print(f"  [+] Widget Live Sync: {start_dt.strftime('%B %d, %I:%M%p')} | {event_title}")
                
            print(f"  [!] Oskar Blues Sync complete. Added {ob_count} live music events.")
        else:
            print(f"  [-] Popmenu public script asset frame rejected. Code: {res.status_code}")
            
    except Exception as e:
        print(f"Failed to extract records using public widget tracker channel: {e}")
    
    # --- 5. MULTI-PAGE TARGETS ---
    print("\n🔍 Scanning Multi-Page Targets...")
    multi_targets = [
        ("https://www.downtownlongmont.com/events/calendar", "https://www.downtownlongmont.com"),
        ("https://www.johnsonsstation.com/calendar", "https://www.johnsonsstation.com"),
        ("https://www.barnevents.info/events", "https://www.barnevents.info"),
        ("https://www.stvraincidery.com/events", "https://www.stvraincidery.com")
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

                    # Adaptive Engine Filter
                    explicit_music = False
                    skip_event = False
                    if '|' in event_title:
                        parts = [p.strip() for p in event_title.split('|')]
                        prefix = parts[0].lower()
                        if prefix in ['music', 'live music']:
                            explicit_music = True
                            event_title = parts[1]
                        elif prefix in ['class', 'discussion', 'workshop', 'art', 'pop up', 'event']:
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

                    content_block = ev_soup.select_one('.eventitem-description, .sqs-block-content, article')
                    body_text = content_block.get_text(" ", strip=True)[:2000] if content_block else ev_soup.get_text(" ", strip=True)[:1500]
                    combined_text = (raw_title + " " + body_text).lower()
                    
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
