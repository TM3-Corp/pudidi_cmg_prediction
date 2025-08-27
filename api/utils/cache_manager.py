"""
Cache Manager for CMG Data
Handles all caching operations including file-based storage for Vercel deployment
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import pytz

class CacheManager:
    """
    Manages caching for CMG data with file-based storage.
    Designed for Vercel serverless environment.
    """
    
    def __init__(self, cache_dir: str = "data/cache"):
        """Initialize cache manager with cache directory"""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hourly_dir = self.cache_dir / "hourly"
        self.hourly_dir.mkdir(exist_ok=True)
        self.santiago_tz = pytz.timezone('America/Santiago')
        
    def get_cache_path(self, cache_type: str) -> Path:
        """Get path for specific cache file"""
        cache_files = {
            'historical': 'cmg_historical_latest.json',
            'programmed': 'cmg_programmed_latest.json',
            'metadata': 'metadata.json',
            'current': 'current_combined.json'
        }
        return self.cache_dir / cache_files.get(cache_type, f'{cache_type}.json')
    
    def read_cache(self, cache_type: str) -> Optional[Dict]:
        """Read cache file if exists and is valid"""
        cache_path = self.get_cache_path(cache_type)
        
        if not cache_path.exists():
            return None
            
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
                
            # Check if cache is still valid (< 2 hours old)
            if 'timestamp' in data:
                cache_time = datetime.fromisoformat(data['timestamp'])
                now = datetime.now(self.santiago_tz)
                
                # Make cache_time timezone aware if it isn't
                if cache_time.tzinfo is None:
                    cache_time = self.santiago_tz.localize(cache_time)
                
                age_hours = (now - cache_time).total_seconds() / 3600
                
                # Return cache with age information
                data['cache_age_hours'] = age_hours
                data['is_stale'] = age_hours > 2
                
            return data
        except Exception as e:
            print(f"Error reading cache {cache_type}: {e}")
            return None
    
    def write_cache(self, cache_type: str, data: Dict) -> bool:
        """Write data to cache file"""
        cache_path = self.get_cache_path(cache_type)
        
        try:
            # Add timestamp if not present
            if 'timestamp' not in data:
                data['timestamp'] = datetime.now(self.santiago_tz).isoformat()
            
            # Ensure directory exists
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write atomically (write to temp file then rename)
            temp_path = cache_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            # Atomic rename
            temp_path.replace(cache_path)
            return True
            
        except Exception as e:
            print(f"Error writing cache {cache_type}: {e}")
            return False
    
    def get_hourly_cache(self, date: str, hour: int) -> Optional[Dict]:
        """Get cache for specific hour"""
        filename = f"{date}-{hour:02d}.json"
        hourly_path = self.hourly_dir / filename
        
        if not hourly_path.exists():
            return None
            
        try:
            with open(hourly_path, 'r') as f:
                return json.load(f)
        except:
            return None
    
    def write_hourly_cache(self, date: str, hour: int, data: Dict) -> bool:
        """Write cache for specific hour"""
        filename = f"{date}-{hour:02d}.json"
        hourly_path = self.hourly_dir / filename
        
        try:
            with open(hourly_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            return True
        except:
            return False
    
    def merge_historical_data(self, new_data: List[Dict], 
                            window_hours: int = 24) -> Dict:
        """
        Merge new data with existing cache, maintaining rolling window.
        """
        # Read existing cache
        existing = self.read_cache('historical')
        if existing and 'data' in existing:
            existing_data = existing['data']
        else:
            existing_data = []
        
        # Combine and deduplicate
        combined = existing_data + new_data
        
        # Remove duplicates based on datetime
        seen = set()
        unique_data = []
        for record in combined:
            dt_key = record.get('datetime', '')
            if dt_key and dt_key not in seen:
                seen.add(dt_key)
                unique_data.append(record)
        
        # Sort by datetime
        unique_data.sort(key=lambda x: x.get('datetime', ''))
        
        # Keep only last window_hours
        now = datetime.now(self.santiago_tz)
        cutoff_time = now - timedelta(hours=window_hours)
        
        windowed_data = []
        for record in unique_data:
            try:
                record_time = datetime.fromisoformat(record['datetime'])
                if record_time.tzinfo is None:
                    record_time = self.santiago_tz.localize(record_time)
                
                if record_time >= cutoff_time:
                    windowed_data.append(record)
            except:
                continue
        
        # Calculate statistics
        coverage_hours = len(set(r.get('hour', -1) for r in windowed_data))
        coverage_pct = (coverage_hours / 24) * 100
        
        return {
            'timestamp': datetime.now(self.santiago_tz).isoformat(),
            'data': windowed_data,
            'statistics': {
                'total_records': len(windowed_data),
                'coverage_hours': coverage_hours,
                'coverage_percentage': coverage_pct,
                'oldest_record': windowed_data[0]['datetime'] if windowed_data else None,
                'newest_record': windowed_data[-1]['datetime'] if windowed_data else None
            }
        }
    
    def get_cache_status(self) -> Dict:
        """Get overall cache status and metadata"""
        status = {
            'timestamp': datetime.now(self.santiago_tz).isoformat(),
            'caches': {}
        }
        
        # Check each cache type
        for cache_type in ['historical', 'programmed', 'metadata']:
            cache_data = self.read_cache(cache_type)
            
            if cache_data:
                status['caches'][cache_type] = {
                    'exists': True,
                    'age_hours': cache_data.get('cache_age_hours', 0),
                    'is_stale': cache_data.get('is_stale', False),
                    'last_updated': cache_data.get('timestamp'),
                    'records': len(cache_data.get('data', [])) if 'data' in cache_data else 0
                }
            else:
                status['caches'][cache_type] = {
                    'exists': False,
                    'age_hours': None,
                    'is_stale': True,
                    'last_updated': None,
                    'records': 0
                }
        
        # Overall status
        all_exist = all(c['exists'] for c in status['caches'].values())
        any_stale = any(c['is_stale'] for c in status['caches'].values())
        
        status['overall'] = {
            'ready': all_exist,
            'needs_update': any_stale,
            'status': 'ready' if all_exist and not any_stale else 'stale' if any_stale else 'initializing'
        }
        
        return status
    
    def cleanup_old_caches(self, days: int = 7) -> int:
        """Remove cache files older than specified days"""
        now = datetime.now(self.santiago_tz)
        cutoff = now - timedelta(days=days)
        removed = 0
        
        # Clean hourly caches
        for cache_file in self.hourly_dir.glob("*.json"):
            try:
                # Parse date from filename (YYYY-MM-DD-HH.json)
                date_str = cache_file.stem[:-3]  # Remove -HH part
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                file_date = self.santiago_tz.localize(file_date)
                
                if file_date < cutoff:
                    cache_file.unlink()
                    removed += 1
            except:
                continue
        
        return removed
    
    def get_combined_display_data(self) -> Dict:
        """
        Get combined data for frontend display.
        Includes both historical and programmed data.
        """
        historical = self.read_cache('historical')
        programmed = self.read_cache('programmed')
        
        display_data = {
            'timestamp': datetime.now(self.santiago_tz).isoformat(),
            'historical': {
                'available': historical is not None,
                'data': historical.get('data', []) if historical else [],
                'coverage': historical.get('statistics', {}).get('coverage_percentage', 0) if historical else 0,
                'last_updated': historical.get('timestamp') if historical else None,
                'is_stale': historical.get('is_stale', True) if historical else True
            },
            'programmed': {
                'available': programmed is not None,
                'data': programmed.get('data', []) if programmed else [],
                'hours_ahead': len(programmed.get('data', [])) if programmed else 0,
                'last_updated': programmed.get('timestamp') if programmed else None,
                'is_stale': programmed.get('is_stale', True) if programmed else True
            },
            'status': self.get_cache_status()
        }
        
        return display_data