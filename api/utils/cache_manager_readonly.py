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
        """Get combined data for frontend display"""
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