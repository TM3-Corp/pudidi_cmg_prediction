#!/usr/bin/env python3
"""
Populate test data in the database for testing the API
"""

import sqlite3
from datetime import datetime, timedelta
import pytz
import random

def populate_test_data():
    """Populate database with test data"""
    import os
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cmg_data.db')
    conn = sqlite3.connect(db_path)
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
        CREATE TABLE IF NOT EXISTS weather_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
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
    
    # Get current time in Santiago
    santiago_tz = pytz.timezone('America/Santiago')
    now = datetime.now(santiago_tz)
    
    print("Populating test data...")
    
    # Populate last 7 days of CMG data
    for days_ago in range(7):
        date = now - timedelta(days=days_ago)
        date_str = date.strftime('%Y-%m-%d')
        
        # Add data for each hour
        for hour in range(24):
            # CMG value varies by hour (typical pattern)
            base_value = 60
            if 6 <= hour <= 9:  # Morning peak
                base_value = 80
            elif 18 <= hour <= 21:  # Evening peak
                base_value = 90
            elif 0 <= hour <= 5:  # Night low
                base_value = 45
            
            # Add some randomness
            cmg_value = base_value + random.uniform(-10, 10)
            
            # Insert CMG data for different sources
            for source in ['real', 'online']:
                cursor.execute('''
                    INSERT OR REPLACE INTO cmg_data (date, hour, node, source, cmg_value)
                    VALUES (?, ?, ?, ?, ?)
                ''', (date_str, hour, 'CHILOE________220', source, cmg_value))
            
            # Add weather data
            temp = 15 + random.uniform(-5, 10)
            wind = random.uniform(2, 15)
            rain = random.choice([0, 0, 0, 2, 5])  # Mostly no rain
            cloud = random.uniform(20, 80)
            
            cursor.execute('''
                INSERT OR REPLACE INTO weather_data (date, hour, temperature, wind_speed, precipitation, cloud_cover)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (date_str, hour, temp, wind, rain, cloud))
        
        # Add fetch log entry
        cursor.execute('''
            INSERT INTO fetch_log (date, source, pages_fetched, records_found, hours_covered, fetch_time_seconds, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date_str, 'real', 440, 384, 24, 1080, 1))
        
        print(f"  Added data for {date_str}")
    
    conn.commit()
    
    # Show summary
    cursor.execute('''
        SELECT date, source, COUNT(*) as records, COUNT(DISTINCT hour) as hours
        FROM cmg_data
        WHERE node = 'CHILOE________220'
        GROUP BY date, source
        ORDER BY date DESC, source
        LIMIT 10
    ''')
    
    print("\nDatabase populated with test data:")
    print("="*50)
    for row in cursor.fetchall():
        print(f"{row[0]} {row[1]:8s}: {row[2]:3d} records, {row[3]:2d}/24 hours")
    
    conn.close()
    print("\nTest data population complete!")

if __name__ == "__main__":
    populate_test_data()