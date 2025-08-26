#!/usr/bin/env python3
"""
Populate initial data - fetches last few days of data
This is a faster version that only gets essential data
"""

import sqlite3
import requests
import os
from datetime import datetime, timedelta
import pytz
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# API configuration
SIP_API_KEY = os.environ.get('SIP_API_KEY', '1a81177c8ff4f69e7dd5bb8c61bc08b4')
CHILOE_NODE = 'CHILOE________220'
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'

def init_database():
    """Initialize database tables"""
    conn = sqlite3.connect('cmg_data.db')
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cmg_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            hour INTEGER,
            node TEXT,
            source TEXT,
            cmg_value REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, hour, node, source)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            source TEXT,
            pages_fetched INTEGER,
            records_found INTEGER,
            hours_covered INTEGER,
            fetch_time_seconds REAL,
            success BOOLEAN,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logging.info("Database initialized")

def fetch_day_quick(date_str, source='online', max_pages=50):
    """Fetch data for one day with page limit"""
    logging.info(f"Fetching {source} for {date_str} (max {max_pages} pages)")
    
    if source == 'real':
        endpoint = '/costo-marginal-real/v4/findByDate'
    elif source == 'pid':
        endpoint = '/cmg-programado-pid/v4/findByDate'
    else:  # online
        endpoint = '/costo-marginal-online/v4/findByDate'
    
    url = f"{SIP_BASE_URL}{endpoint}"
    
    all_chiloe_records = []
    page = 1
    start_time = time.time()
    
    while page <= max_pages:
        params = {
            'startDate': date_str,
            'endDate': date_str,
            'page': page,
            'limit': 1000,
            'user_key': SIP_API_KEY
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                records = data.get('data', [])
                
                # Filter Chiloé records
                for record in records:
                    if record.get('barra_transf') == CHILOE_NODE:
                        all_chiloe_records.append(record)
                
                # Log progress
                if page % 10 == 0:
                    logging.info(f"  Page {page}: Found {len(all_chiloe_records)} Chiloé records so far")
                
                # Check if last page
                if len(records) < 1000:
                    logging.info(f"  Last page reached at page {page}")
                    break
                
                page += 1
                
            else:
                logging.warning(f"  Error {response.status_code} on page {page}")
                break
                
        except Exception as e:
            logging.error(f"  Exception on page {page}: {e}")
            break
    
    elapsed = time.time() - start_time
    
    # Store in database
    if all_chiloe_records:
        store_records(date_str, source, all_chiloe_records)
    
    # Log fetch
    log_fetch(date_str, source, page - 1, len(all_chiloe_records), elapsed)
    
    hours_covered = len(set(r['fecha_hora'][11:13] for r in all_chiloe_records))
    logging.info(f"  ✅ {source}: {len(all_chiloe_records)} records, {hours_covered}/24 hours, {elapsed:.1f}s")
    
    return all_chiloe_records

def store_records(date_str, source, records):
    """Store records in database"""
    conn = sqlite3.connect('cmg_data.db')
    cursor = conn.cursor()
    
    for record in records:
        try:
            fecha_hora = record.get('fecha_hora', '')
            hour = int(fecha_hora[11:13]) if len(fecha_hora) > 13 else 0
            cmg_value = float(record.get('cmg', 0))
            
            cursor.execute('''
                INSERT OR REPLACE INTO cmg_data (date, hour, node, source, cmg_value)
                VALUES (?, ?, ?, ?, ?)
            ''', (date_str, hour, CHILOE_NODE, source, cmg_value))
            
        except Exception as e:
            logging.warning(f"Error storing record: {e}")
    
    conn.commit()
    conn.close()

def log_fetch(date_str, source, pages, records, elapsed):
    """Log fetch results"""
    conn = sqlite3.connect('cmg_data.db')
    cursor = conn.cursor()
    
    hours_covered = 0
    if records > 0:
        cursor.execute('''
            SELECT COUNT(DISTINCT hour) FROM cmg_data 
            WHERE date = ? AND source = ? AND node = ?
        ''', (date_str, source, CHILOE_NODE))
        hours_covered = cursor.fetchone()[0]
    
    cursor.execute('''
        INSERT INTO fetch_log (date, source, pages_fetched, records_found, 
                              hours_covered, fetch_time_seconds, success)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (date_str, source, pages, records, hours_covered, elapsed, records > 0))
    
    conn.commit()
    conn.close()

def main():
    """Main function"""
    logging.info("Starting initial data population")
    
    # Initialize database
    init_database()
    
    # Get dates to fetch
    santiago_tz = pytz.timezone('America/Santiago')
    today = datetime.now(santiago_tz).date()
    
    # Fetch last 3 days (quick test)
    days_to_fetch = 3
    
    for days_ago in range(days_to_fetch):
        fetch_date = today - timedelta(days=days_ago)
        date_str = fetch_date.strftime('%Y-%m-%d')
        
        logging.info(f"\n{'='*60}")
        logging.info(f"Fetching {date_str}")
        logging.info('='*60)
        
        # Try each source
        for source in ['online']:  # Start with just online for speed
            fetch_day_quick(date_str, source, max_pages=100)
        
        time.sleep(1)  # Brief pause between days
    
    # Show summary
    conn = sqlite3.connect('cmg_data.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT date, source, COUNT(*) as records, COUNT(DISTINCT hour) as hours
        FROM cmg_data
        WHERE node = ?
        GROUP BY date, source
        ORDER BY date DESC, source
    ''', (CHILOE_NODE,))
    
    print("\n" + "="*60)
    print("DATABASE SUMMARY")
    print("="*60)
    
    for row in cursor.fetchall():
        print(f"{row[0]} {row[1]:8s}: {row[2]:4d} records, {row[3]:2d}/24 hours")
    
    conn.close()
    
    logging.info("\nInitial data population complete!")

if __name__ == "__main__":
    main()