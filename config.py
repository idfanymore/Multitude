import os
import sqlite3
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from geoip2 import database as gdb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, 'multitude_storage')
DB_PATH = os.path.join(STORAGE_DIR, 'proxies.db')
GEOIP_PATH = os.path.join(STORAGE_DIR, 'GeoLite2-City.mmdb')
CONFIG_PATH = os.path.join(STORAGE_DIR, 'config.json')
os.makedirs(STORAGE_DIR, exist_ok=True)

PROXY_SOURCES = [
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt',
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt'
]

def get_proxy_count_from_source(source_url):
    try:
        response = requests.get(source_url, timeout=5)
        proxies = [line.strip() for line in response.text.split('\n') if ':' in line.strip()]
        return len(proxies)
    except:
        return 0

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS proxies (
            proxy TEXT PRIMARY KEY,
            type TEXT,
            country TEXT,
            last_check TEXT,
            is_active INTEGER DEFAULT 1
        )''')
        conn.commit()

def save_custom_sources(sources):
    config = load_config()
    config['custom_sources'] = sources
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f)

def load_custom_sources():
    config = load_config()
    return config.get('custom_sources', [])

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {'update_threads': 100, 'check_threads': 50, 'custom_sources': []}

def detect_proxy_type(proxy):
    proxy = proxy.split('://')[-1].split('@')[-1]
    for ptype in ['socks5', 'socks4', 'https', 'http']:
        try:
            test_url = 'https://www.google.com' if ptype != 'http' else 'http://www.google.com'
            requests.get(test_url, proxies={'http': f"{ptype}://{proxy}"}, timeout=5)
            return ptype
        except:
            continue
    return None

def check_proxy(proxy, reader=None):
    ptype = detect_proxy_type(proxy)
    if not ptype:
        return (proxy, None, 'Unknown', 0)
    
    try:
        test_url = 'https://www.google.com' if ptype != 'http' else 'http://www.google.com'
        requests.get(test_url, proxies={'http': f"{ptype}://{proxy}"}, timeout=10)
        
        country = 'Unknown'
        if reader:
            try:
                ip = proxy.split(':')[0]
                country = reader.city(ip).country.names.get('en', 'Unknown')
            except:
                pass
        return (proxy, ptype, country, 1)
    except:
        return (proxy, ptype, 'Unknown', 0)

def get_random_proxy(region=None, active_only=True):
    query = 'SELECT proxy FROM proxies'
    params = []
    conditions = []
    
    if active_only:
        conditions.append('is_active = 1')
    if region:
        conditions.append('country = ?')
        params.append(region)
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    with get_db_connection() as conn:
        row = conn.execute(query + ' ORDER BY RANDOM() LIMIT 1', params).fetchone()
        return row['proxy'] if row else None

def check_all_proxies(threads=50, progress_callback=None):
    reader = gdb.Reader(GEOIP_PATH) if os.path.exists(GEOIP_PATH) else None
    
    with get_db_connection() as conn:
        proxies = [row['proxy'] for row in conn.execute('SELECT proxy FROM proxies')]
        total = len(proxies)
        if total == 0:
            return 0
    
    update_batch = []
    active_count = 0
    
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(check_proxy, p, reader): p for p in proxies}
        
        for i, future in enumerate(as_completed(futures), 1):
            proxy, ptype, country, is_active = future.result()
            update_batch.append((ptype, country, is_active, proxy))
            if is_active:
                active_count += 1
            
            if i % 100 == 0 or i == total:
                with get_db_connection() as conn:
                    conn.executemany('''
                        UPDATE proxies 
                        SET type = ?, country = ?, is_active = ?, last_check = datetime('now')
                        WHERE proxy = ?
                    ''', update_batch)
                    conn.commit()
                update_batch = []
            
            if progress_callback and total > 0:
                progress = int((i / total) * 100)
                progress_callback(progress)
    
    return active_count

def update_proxies(sources=None, threads=100, progress_callback=None):
    selected_sources = sources if sources else PROXY_SOURCES + load_custom_sources()
    reader = gdb.Reader(GEOIP_PATH) if os.path.exists(GEOIP_PATH) else None
    
    all_proxies = set()
    for source in selected_sources:
        try:
            response = requests.get(source, timeout=30)
            proxies = [line.strip() for line in response.text.split('\n') if ':' in line.strip()]
            all_proxies.update(p.split('://')[-1].split('@')[-1] for p in proxies)
        except Exception as e:
            print(f"Error fetching {source}: {str(e)}")
            continue
    
    with get_db_connection() as conn:
        existing = {row['proxy'] for row in conn.execute('SELECT proxy FROM proxies')}
        new_proxies = [p for p in all_proxies if p not in existing]
        total = len(new_proxies)
        if total == 0:
            return 0
    
    working_proxies = []
    checked = 0
    
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(check_proxy, p, reader): p for p in new_proxies}
        
        for future in as_completed(futures):
            proxy, ptype, country, is_active = future.result()
            checked += 1
            
            if is_active:
                working_proxies.append((proxy, ptype, country))
            
            if progress_callback and total > 0:
                progress = int((checked / total) * 100)
                progress_callback(progress)
    
    if working_proxies:
        with get_db_connection() as conn:
            conn.executemany('''
                INSERT INTO proxies 
                (proxy, type, country, last_check, is_active) 
                VALUES (?, ?, ?, datetime('now'), 1)
            ''', working_proxies)
            conn.commit()
    
    return len(working_proxies)

def get_proxies_by_region(active_only=True):
    query = '''
        SELECT country, COUNT(*) as count 
        FROM proxies 
        WHERE country IS NOT NULL
    '''
    if active_only:
        query += ' AND is_active = 1'
    query += ' GROUP BY country ORDER BY count DESC'
    
    with get_db_connection() as conn:
        return [dict(row) for row in conn.execute(query)]

init_db()