"""
Production Daily Fetch Script
Based on test_data_integrity.ipynb approach
Fetches complete 24-hour data for Chiloé and stores it

Run daily at 3 AM via cron:
0 3 * * * /usr/bin/python3 /path/to/fetch_complete_daily.py
"""

import json
import requests
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pytz
import sqlite3
from typing import Dict, List, Tuple
import os

# Configuration
SIP_API_KEY = os.environ.get('SIP_API_KEY', '1a81177c8ff4f69e7dd5bb8c61bc08b4')
SIP_BASE_URL = 'https://sipub.api.coordinador.cl:443'
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'cmg_data.db')

# Chiloé nodes configuration
CHILOE_NODES = {
    'CMG_REAL': [
        'QUELLON_______013',
        'QUELLON_______110', 
        'CHILOE________220',  # Main node
        'CHILOE________110',
        'CHONCHI_______110',
        'DALCAHUE______023'
    ],
    'CMG_PID': [
        'BA S/E CHONCHI 110KV BP1',
        'BA S/E CHILOE 110KV BP1',
        'BA S/E CHILOE 220KV BP1',
        'BA S/E QUELLON 110KV BP1',
        'BA S/E QUELLON 13KV BP1',
        'BA S/E DALCAHUE 23KV BP1'
    ]
}

# Weather location
CHILOE_LAT = -42.4472
CHILOE_LON = -73.6506

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fetch_daily.log'),
        logging.StreamHandler()
    ]
)

class CompleteDailyFetcher:
    def __init__(self, db_path=None, cache_dir='daily_cache'):
        self.db_path = db_path or DB_PATH
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.setup_database()
        
    def setup_database(self):
        """Initialize SQLite database for storing CMG data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cmg_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
                hour INTEGER,
                node TEXT,
                source TEXT,
                cmg_value REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, hour, node, source)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weather_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
                hour INTEGER,
                temperature REAL,
                wind_speed REAL,
                precipitation REAL,
                cloud_cover REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, hour)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
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
        
    def fetch_with_retry(self, url, params, max_retries=3, initial_wait=2):
        """Fetch with exponential backoff retry logic"""
        wait_time = initial_wait
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    if attempt < max_retries - 1:
                        logging.warning(f"Got {response.status_code}, waiting {wait_time}s...")
                        time.sleep(wait_time)
                        wait_time = min(wait_time * 2, 30)
                        continue
                else:
                    logging.error(f"Unexpected status: {response.status_code}")
                    return None
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    logging.warning(f"Timeout, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    wait_time = min(wait_time * 2, 30)
                    continue
                    
            except Exception as e:
                logging.error(f"Request error: {e}")
                return None
                
        return None
        
    def fetch_cmg_complete(self, date_str: str, source: str = 'real') -> Dict:
        """
        Fetch complete CMG data for a specific date and source
        This fetches ALL pages to ensure 24-hour coverage
        """
        logging.info(f"Fetching CMG {source} for {date_str}")
        
        if source == 'real':
            url = f"{SIP_BASE_URL}/costo-marginal-real/v4/findByDate"
            node_field = 'barra_transf'
            cmg_field = 'cmg_clp_kwh_'
            target_nodes = CHILOE_NODES['CMG_REAL']
        elif source == 'pid':
            url = f"{SIP_BASE_URL}/cmg-programado-pid/v4/findByDate"
            node_field = 'nmb_barra_info'
            cmg_field = 'cmg_usd_mwh'
            target_nodes = CHILOE_NODES['CMG_PID']
        elif source == 'online':
            url = f"{SIP_BASE_URL}/costo-marginal-online/v4/findByDate"
            node_field = 'barra_transf'
            cmg_field = 'cmg_usd_mwh_'
            target_nodes = CHILOE_NODES['CMG_REAL']
        else:
            logging.error(f"Unknown source: {source}")
            return {}
            
        all_data = {}
        page = 1
        limit = 1000
        total_pages = 0
        chiloe_records = 0
        start_time = time.time()
        
        # Keep fetching until we get all pages
        while True:
            params = {
                'startDate': date_str,
                'endDate': date_str,
                'page': page,
                'limit': limit,
                'user_key': SIP_API_KEY
            }
            
            data = self.fetch_with_retry(url, params)
            
            if data and 'data' in data:
                records = data.get('data', [])
                page_chiloe = 0
                
                # Process each record
                for record in records:
                    node = record.get(node_field, '')
                    
                    # Check if it's a Chiloé node
                    if node in target_nodes:
                        # Extract hour
                        if 'hra' in record:
                            hour = record['hra']
                        elif 'fecha_hora' in record:
                            hour = int(record['fecha_hora'][11:13])
                        else:
                            continue
                            
                        # Store data
                        key = f"{hour:02d}_{node}"
                        all_data[key] = {
                            'hour': hour,
                            'node': node,
                            'value': float(record.get(cmg_field, 0)),
                            'source': source
                        }
                        page_chiloe += 1
                        chiloe_records += 1
                
                logging.info(f"    Page {page}: {page_chiloe} records")
                total_pages = page
                page += 1
                
                # Stop if last page (incomplete)
                if len(records) < limit:
                    break
                    
                # Safety limit
                if page > 500:  # ~500,000 records max
                    logging.warning("Reached safety limit of 500 pages")
                    break
            else:
                # API failed
                break
                
        fetch_time = time.time() - start_time
        
        # Log fetch results
        hours_covered = len(set(d['hour'] for d in all_data.values()))
        logging.info(f"✅ CMG {source}: {chiloe_records} records, {hours_covered}/24 hours, {fetch_time:.1f}s")
        
        # Store in database
        self.store_fetch_log(date_str, source, total_pages, chiloe_records, hours_covered, fetch_time)
        
        return all_data
        
    def fetch_weather_complete(self, date_str: str) -> Dict:
        """Fetch complete weather data for the date"""
        logging.info(f"Fetching weather for {date_str}")
        
        try:
            # Parse date
            date = datetime.strptime(date_str, '%Y-%m-%d')
            
            # Weather API (Open-Meteo historical)
            url = "https://archive-api.open-meteo.com/v1/era5"
            params = {
                "latitude": CHILOE_LAT,
                "longitude": CHILOE_LON,
                "start_date": date_str,
                "end_date": date_str,
                "hourly": "temperature_2m,windspeed_10m,precipitation,cloudcover",
                "timezone": "America/Santiago"
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                weather_data = {}
                if 'hourly' in data:
                    hourly = data['hourly']
                    times = hourly.get('time', [])
                    
                    for i, time_str in enumerate(times):
                        hour = int(time_str[11:13])
                        weather_data[hour] = {
                            'hour': hour,
                            'temperature': hourly['temperature_2m'][i] if i < len(hourly['temperature_2m']) else None,
                            'wind_speed': hourly['windspeed_10m'][i] if i < len(hourly['windspeed_10m']) else None,
                            'precipitation': hourly['precipitation'][i] if i < len(hourly['precipitation']) else None,
                            'cloud_cover': hourly['cloudcover'][i] if i < len(hourly['cloudcover']) else None
                        }
                
                logging.info(f"✅ Weather: {len(weather_data)}/24 hours")
                return weather_data
            else:
                logging.error(f"Weather API error: {response.status_code}")
                return {}
                
        except Exception as e:
            logging.error(f"Weather fetch error: {e}")
            return {}
            
    def store_cmg_data(self, date_str: str, cmg_data: Dict):
        """Store CMG data in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for key, data in cmg_data.items():
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO cmg_data 
                    (date, hour, node, source, cmg_value)
                    VALUES (?, ?, ?, ?, ?)
                ''', (date_str, data['hour'], data['node'], data['source'], data['value']))
            except Exception as e:
                logging.error(f"Error storing CMG data: {e}")
                
        conn.commit()
        conn.close()
        
    def store_weather_data(self, date_str: str, weather_data: Dict):
        """Store weather data in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for hour, data in weather_data.items():
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO weather_data
                    (date, hour, temperature, wind_speed, precipitation, cloud_cover)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (date_str, hour, data['temperature'], data['wind_speed'], 
                     data['precipitation'], data['cloud_cover']))
            except Exception as e:
                logging.error(f"Error storing weather data: {e}")
                
        conn.commit()
        conn.close()
        
    def store_fetch_log(self, date_str: str, source: str, pages: int, records: int, hours: int, fetch_time: float):
        """Log fetch statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO fetch_log
            (date, source, pages_fetched, records_found, hours_covered, fetch_time_seconds, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date_str, source, pages, records, hours, fetch_time, hours >= 20))
        
        conn.commit()
        conn.close()
        
    def fetch_complete_day(self, date_str: str) -> Dict:
        """
        Main function to fetch complete 24-hour data
        Combines multiple sources for best coverage
        """
        logging.info(f"\n{'='*60}")
        logging.info(f"FETCHING COMPLETE DATA FOR {date_str}")
        logging.info(f"{'='*60}")
        
        results = {
            'date': date_str,
            'cmg': {},
            'weather': {},
            'integrity': {
                'complete': False,
                'cmg_hours': 0,
                'weather_hours': 0
            }
        }
        
        # Fetch CMG from multiple sources (priority order)
        # 1. Try CMG Real first (most accurate)
        cmg_real = self.fetch_cmg_complete(date_str, 'real')
        if cmg_real:
            results['cmg'].update(cmg_real)
            self.store_cmg_data(date_str, cmg_real)
            
        # 2. Fill gaps with CMG PID
        cmg_pid = self.fetch_cmg_complete(date_str, 'pid')
        if cmg_pid:
            # Only add hours not already covered
            for key, data in cmg_pid.items():
                hour_key = f"{data['hour']:02d}_CHILOE________220"
                if hour_key not in results['cmg']:
                    results['cmg'][key] = data
            self.store_cmg_data(date_str, cmg_pid)
            
        # 3. Fill remaining gaps with CMG Online
        cmg_online = self.fetch_cmg_complete(date_str, 'online')
        if cmg_online:
            for key, data in cmg_online.items():
                hour_key = f"{data['hour']:02d}_CHILOE________220"
                if hour_key not in results['cmg']:
                    results['cmg'][key] = data
            self.store_cmg_data(date_str, cmg_online)
            
        # Fetch weather data
        weather = self.fetch_weather_complete(date_str)
        if weather:
            results['weather'] = weather
            self.store_weather_data(date_str, weather)
            
        # Check integrity
        cmg_hours = len(set(d['hour'] for d in results['cmg'].values()))
        weather_hours = len(weather)
        
        results['integrity']['cmg_hours'] = cmg_hours
        results['integrity']['weather_hours'] = weather_hours
        results['integrity']['complete'] = (cmg_hours == 24 and weather_hours == 24)
        
        # Final summary
        status = "✅ COMPLETE" if results['integrity']['complete'] else "⚠️ INCOMPLETE"
        logging.info(f"\n{status} - Overall data integrity for {date_str}")
        logging.info(f"  CMG: {cmg_hours}/24 hours")
        logging.info(f"  Weather: {weather_hours}/24 hours")
        
        return results
        
    def fetch_multiple_days(self, days_back: int = 30):
        """Fetch multiple days of historical data"""
        santiago_tz = pytz.timezone('America/Santiago')
        now = datetime.now(santiago_tz)
        
        for i in range(days_back):
            date = now - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            
            logging.info(f"\n{'='*60}")
            logging.info(f"Processing day {i+1}/{days_back}: {date_str}")
            
            try:
                self.fetch_complete_day(date_str)
                
                # Delay between days to avoid overwhelming API
                if i < days_back - 1:
                    logging.info("Waiting 30 seconds before next day...")
                    time.sleep(30)
                    
            except Exception as e:
                logging.error(f"Failed to fetch {date_str}: {e}")
                continue
                
    def get_stored_data(self, start_date: str, end_date: str) -> Tuple:
        """Retrieve stored data from database"""
        conn = sqlite3.connect(self.db_path)
        
        # Get CMG data
        cmg_query = '''
            SELECT date, hour, node, source, cmg_value
            FROM cmg_data
            WHERE date BETWEEN ? AND ?
            ORDER BY date, hour
        '''
        cmg_df = pd.read_sql_query(cmg_query, conn, params=(start_date, end_date))
        
        # Get weather data
        weather_query = '''
            SELECT date, hour, temperature, wind_speed, precipitation, cloud_cover
            FROM weather_data
            WHERE date BETWEEN ? AND ?
            ORDER BY date, hour
        '''
        weather_df = pd.read_sql_query(weather_query, conn, params=(start_date, end_date))
        
        conn.close()
        
        return cmg_df, weather_df


def main():
    """Main execution function"""
    fetcher = CompleteDailyFetcher()
    
    # Get yesterday's date (we fetch historical data)
    santiago_tz = pytz.timezone('America/Santiago')
    yesterday = (datetime.now(santiago_tz) - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Fetch complete data for yesterday
    results = fetcher.fetch_complete_day(yesterday)
    
    if results['integrity']['complete']:
        logging.info(f"\n✅ Successfully fetched complete data for {yesterday}")
        logging.info(f"  CMG records: {len(results['cmg'])}")
        logging.info(f"  Weather records: {len(results['weather'])}")
    else:
        logging.warning(f"\n⚠️ Incomplete data for {yesterday}")
        logging.warning(f"  CMG hours: {results['integrity']['cmg_hours']}/24")
        logging.warning(f"  Weather hours: {results['integrity']['weather_hours']}/24")
        
    # Optional: Fetch multiple days on first run
    # fetcher.fetch_multiple_days(30)
    
    return results


if __name__ == "__main__":
    main()