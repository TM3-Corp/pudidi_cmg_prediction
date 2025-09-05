"""
Cache Manager for Read-Only Environment (Vercel)
Reads pre-built cache files from deployment
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import pytz

class CacheManagerReadOnly:
    """
    Read-only cache manager for Vercel deployment.
    Reads from deployed cache files, doesn't try to write.
    """
    
    def __init__(self, cache_dir: str = None):
        """Initialize cache manager for read-only access"""
        # In Vercel, files are in the deployment directory
        if cache_dir is None:
            # Try different possible locations
            possible_paths = [
                Path("data/cache"),
                Path("/var/task/data/cache"),
                Path(os.path.dirname(os.path.abspath(__file__))).parent.parent / "data" / "cache",
                Path(os.getcwd()) / "data" / "cache"
            ]
            
            for path in possible_paths:
                if path.exists():
                    self.cache_dir = path
                    break
            else:
                # Default to relative path
                self.cache_dir = Path("data/cache")
        else:
            self.cache_dir = Path(cache_dir)
            
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
        """Read cache file if exists"""
        cache_path = self.get_cache_path(cache_type)
        
        try:
            # Try to read the file
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    data = json.load(f)
            else:
                # Try alternative paths in Vercel environment
                alt_paths = [
                    f"/var/task/data/cache/{cache_path.name}",
                    f"data/cache/{cache_path.name}",
                    cache_path.name
                ]
                
                for alt_path in alt_paths:
                    try:
                        with open(alt_path, 'r') as f:
                            data = json.load(f)
                            break
                    except:
                        continue
                else:
                    return None
            
            # Check if timestamp is stale and metadata is fresher
            if cache_type in ['historical', 'programmed'] and 'timestamp' in data:
                try:
                    # Try to read metadata for fresher timestamp
                    metadata_path = self.get_cache_path('metadata')
                    if metadata_path.exists():
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                            if 'timestamp' in metadata:
                                # Compare timestamps
                                cache_time = datetime.fromisoformat(data['timestamp'])
                                meta_time = datetime.fromisoformat(metadata['timestamp'])
                                
                                # If metadata is newer, use its timestamp
                                if meta_time > cache_time:
                                    data['timestamp'] = metadata['timestamp']
                                    data['metadata_updated'] = True
                except:
                    pass  # Keep original timestamp if metadata check fails
            
            # Add cache age information
            if 'timestamp' in data:
                try:
                    cache_time = datetime.fromisoformat(data['timestamp'])
                    now = datetime.now(self.santiago_tz)
                    
                    # Make cache_time timezone aware if it isn't
                    if cache_time.tzinfo is None:
                        cache_time = self.santiago_tz.localize(cache_time)
                    
                    age_hours = (now - cache_time).total_seconds() / 3600
                    
                    data['cache_age_hours'] = age_hours
                    # Consider cache fresh if it was updated via metadata (within last 24h)
                    if data.get('metadata_updated'):
                        data['is_stale'] = age_hours > 24  # More lenient for metadata-updated caches
                    else:
                        data['is_stale'] = age_hours > 2
                except:
                    data['cache_age_hours'] = 0
                    data['is_stale'] = False
                
            return data
            
        except Exception as e:
            print(f"Error reading cache {cache_type}: {e}")
            return None
    
    def get_cache_status(self) -> Dict:
        """Get overall cache status"""
        status = {
            'timestamp': datetime.now(self.santiago_tz).isoformat(),
            'caches': {},
            'environment': 'read-only'
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
        all_exist = all(c['exists'] for c in status['caches'].values() if cache_type in ['historical', 'programmed'])
        any_stale = any(c['is_stale'] for c in status['caches'].values() if c['exists'])
        
        status['overall'] = {
            'ready': all_exist,
            'needs_update': any_stale,
            'status': 'ready' if all_exist and not any_stale else 'stale' if any_stale else 'initializing'
        }
        
        return status
    
    def get_combined_display_data(self) -> Dict:
        """Get combined data for frontend display with proper time filtering"""
        historical = self.read_cache('historical')
        programmed = self.read_cache('programmed')
        
        # Get current time in Santiago
        now = datetime.now(self.santiago_tz)
        current_hour = now.hour
        current_date = now.strftime('%Y-%m-%d')
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Filter historical data for last 24 hours
        filtered_historical = []
        if historical and historical.get('data'):
            for record in historical.get('data', []):
                record_date = record.get('date', '')
                record_hour = record.get('hour', 0)
                
                # Include records from last 24 hours:
                # - Yesterday: hours > current_hour (e.g., if now is 12:00, include 13:00-23:00)
                # - Today: hours <= current_hour (e.g., if now is 12:00, include 00:00-12:00)
                if (record_date == yesterday and record_hour > current_hour) or \
                   (record_date == current_date and record_hour <= current_hour):
                    filtered_historical.append(record)
        
        # Filter programmed data for future hours only (next hour onwards)
        filtered_programmed = []
        next_hour = current_hour + 1
        tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        
        if programmed and programmed.get('data'):
            for record in programmed.get('data', []):
                record_date = record.get('date', '')
                record_hour = record.get('hour', 0)
                
                # Include only future records:
                # - Today: hours >= next_hour (from next hour onwards)
                # - Tomorrow and beyond: ALL hours
                if record_date == current_date and record_hour >= next_hour:
                    filtered_programmed.append(record)
                elif record_date >= tomorrow:
                    # Include ALL hours from tomorrow onwards
                    filtered_programmed.append(record)
        
        # Calculate coverage for filtered historical data
        hist_coverage = 0
        if filtered_historical:
            unique_hours = len(set((r['date'], r['hour']) for r in filtered_historical))
            # Coverage is based on expected 24 hours
            hist_coverage = min((unique_hours / 24) * 100, 100)
        
        display_data = {
            'timestamp': now.isoformat(),
            'current_hour': current_hour,
            'historical': {
                'available': len(filtered_historical) > 0,
                'data': filtered_historical,
                'coverage': hist_coverage,
                'last_updated': historical.get('timestamp') if historical else None,
                'is_stale': historical.get('is_stale', True) if historical else True,
                'window': f"{yesterday} {current_hour+1:02d}:00 to {current_date} {current_hour:02d}:00"
            },
            'programmed': {
                'available': len(filtered_programmed) > 0,
                'data': filtered_programmed,
                'hours_ahead': len(filtered_programmed),
                'last_updated': programmed.get('timestamp') if programmed else None,
                'is_stale': programmed.get('is_stale', True) if programmed else True,
                'window': f"From {current_date} {next_hour:02d}:00 onwards" if next_hour < 24 else "From tomorrow onwards"
            },
            'status': self.get_cache_status()
        }
        
        return display_data