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

# --- SCORING & FILTERS ---
HARD_EXCLUDE = ['workshop', 'class', 'yoga', 'sip', 'paint', 'watercolor', 'meeting', 'sale', 'market', 'plant', 'meditation', 'trivia', 'bingo', 'poker', 'fitness']
STRONG_MUSIC = ['concert', 'band', 'symphony', 'live music', 'orchestra', 'trio', 'quartet', 'quintet']
SOFT_MUSIC = ['acoustic', 'jazz', 'blues', 'rock', 'singer', 'songwriter', 'dj', 'solo', 'duo', 'bluegrass', 'folk', 'americana']
TRUSTED_VENUES = ['bricks on main', 'the barn', 'johnsons station', 'supper club', 'wibby', 'left hand', 'abbott & wallace']

# RESTORED FULL GENRE MAP
GENRE_MAP = {
    'Jazz': ['jazz', 'swing', 'big band', 'bebop'],
    'Rock': ['rock', 'punk', 'metal', 'electric guitar', 'indie', 'grunge', 'psychedelic'],
    'Folk/Acoustic': ['folk', 'acoustic', 'bluegrass', 'singer-songwriter', 'banjo', 'americana'],
    'Blues': ['blues', 'harmonica', 'soul'],
    'Electronic': ['dj', 'electronic', 'synth', 'house music', 'rave', 'edm', 'techno'],
    'Classical': ['orchestra', 'symphony', 'classical', 'quartet', 'chamber'],
    'Country': ['country', 'western', 'honky tonk', 'cowboy']
}

def detect_genre(text):
    combined_text = text.lower()
    for genre, keywords in GENRE_MAP.items():
        if any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in keywords):
            return f"[{genre}] "
    return ""

def get_links(url, domain):
    links = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Catching Downtown Longmont (/do/) and Squarespace (/events/ or /calendar-1)
        for a in soup.find_all('a', href=True):
            href = a['href']
            if any(path in href for path in ['/do/', '/events/', '/calendar-1']):
                # Filter out the main directory pages
                if len(href.split('/')) > 2:
                    links.append(domain + href if href.startswith('/') else href)
    except: pass
    return list(set(links))

def main():
    print("🚀 Running Scraper with Full Genre Mapping...")
    targets = [
        ("https://www.downtownlongmont.com/events/calendar", "https://www.downtownlongmont.com"),
        ("https://www.johnsonsstation.com/calendar", "https://www.johnsonsstation.com"),
        ("https://www.barnevents.info/events", "https://www.barnevents.info")
    ]
    
    all_links = []
    for url, dom in targets:
        all_links.extend(get_links(url, dom))
    
    cal = Calendar()
    seen = set()
    count = 0

    for link in all_links:
        try:
            res = requests.get(link, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 1. Content Extraction
            content = soup.select_one('.details, .event-item-description, .sqs-block-content, article')
            description = content.get_text(" ", strip=True) if content else soup.get_text(" ", strip=True)
            title = (soup.find('h1') or soup.find('title')).get_text(strip=True)
            
            # 2. Filtering
            t_low, d_low = title.lower(), description.lower()
            if any(x in t_low for x in HARD_EXCLUDE): continue
            
            is_trusted = any(v in d_low or v in t_low or v in link for v in TRUSTED_VENUES)
            has_music = any(m in t_low or m in d_low for m in STRONG_MUSIC + SOFT_MUSIC)
            
            if not (is_trusted or has_music): continue

            # 3. Time & Date (JSON-LD priority for Squarespace stability)
            start_dt = None
            script = soup.find('script', type='application/ld+json')
            if script:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list): data = data[0]
                    start_str = data.get('startDate')
                    if start_str:
                        raw_dt = datetime.fromisoformat
