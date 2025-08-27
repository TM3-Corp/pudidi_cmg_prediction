"""
Status endpoint - Returns system status and cache metadata
Used by frontend to check if updates are available
"""

from http.server import BaseHTTPRequestHandler
import json
import sys
import os
from pathlib import Path
from datetime import datetime
import pytz

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.cache_manager_readonly import CacheManagerReadOnly as CacheManager

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Return system status and cache information"""
        
        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'max-age=30')  # Short cache
        self.end_headers()
        
        try:
            santiago_tz = pytz.timezone('America/Santiago')
            now = datetime.now(santiago_tz)
            
            # Initialize cache manager
            cache_manager = CacheManager()
            
            # Get cache status
            status = cache_manager.get_cache_status()
            
            # Determine overall system status
            system_status = 'operational'
            status_color = 'green'
            
            if not status['overall']['ready']:
                system_status = 'initializing'
                status_color = 'yellow'
            elif status['overall']['needs_update']:
                # Check age to determine urgency
                max_age = max(
                    status['caches'].get('historical', {}).get('age_hours', 0) or 0,
                    status['caches'].get('programmed', {}).get('age_hours', 0) or 0
                )
                
                if max_age > 4:
                    system_status = 'stale'
                    status_color = 'red'
                elif max_age > 2:
                    system_status = 'updating'
                    status_color = 'yellow'
                else:
                    system_status = 'recent'
                    status_color = 'green'
            
            # Build response
            response = {
                'success': True,
                'timestamp': now.isoformat(),
                'system': {
                    'status': system_status,
                    'color': status_color,
                    'ready': status['overall']['ready'],
                    'needs_update': status['overall']['needs_update']
                },
                'caches': {
                    'historical': {
                        'exists': status['caches'].get('historical', {}).get('exists', False),
                        'age_hours': status['caches'].get('historical', {}).get('age_hours'),
                        'age_display': self._format_age(status['caches'].get('historical', {}).get('age_hours')),
                        'last_updated': status['caches'].get('historical', {}).get('last_updated'),
                        'records': status['caches'].get('historical', {}).get('records', 0),
                        'is_stale': status['caches'].get('historical', {}).get('is_stale', True)
                    },
                    'programmed': {
                        'exists': status['caches'].get('programmed', {}).get('exists', False),
                        'age_hours': status['caches'].get('programmed', {}).get('age_hours'),
                        'age_display': self._format_age(status['caches'].get('programmed', {}).get('age_hours')),
                        'last_updated': status['caches'].get('programmed', {}).get('last_updated'),
                        'records': status['caches'].get('programmed', {}).get('records', 0),
                        'is_stale': status['caches'].get('programmed', {}).get('is_stale', True)
                    }
                },
                'recommendations': self._get_recommendations(status)
            }
            
            self.wfile.write(json.dumps(response, default=str).encode())
            
        except Exception as e:
            # Error response
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Failed to retrieve status',
                'system': {
                    'status': 'error',
                    'color': 'red',
                    'ready': False
                }
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def _format_age(self, age_hours):
        """Format age in human-readable form"""
        if age_hours is None:
            return 'Never'
        elif age_hours < 0.017:  # Less than 1 minute
            return 'Just now'
        elif age_hours < 0.5:  # Less than 30 minutes
            minutes = int(age_hours * 60)
            return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
        elif age_hours < 1:
            return 'Less than 1 hour ago'
        elif age_hours < 24:
            hours = int(age_hours)
            return f'{hours} hour{"s" if hours != 1 else ""} ago'
        else:
            days = int(age_hours / 24)
            return f'{days} day{"s" if days != 1 else ""} ago'
    
    def _get_recommendations(self, status):
        """Get action recommendations based on status"""
        recommendations = []
        
        if not status['overall']['ready']:
            recommendations.append({
                'type': 'warning',
                'message': 'System is initializing. Please wait for first data fetch.'
            })
        
        if status['overall']['needs_update']:
            hist_age = status['caches'].get('historical', {}).get('age_hours', 0) or 0
            prog_age = status['caches'].get('programmed', {}).get('age_hours', 0) or 0
            
            if hist_age > 4 or prog_age > 4:
                recommendations.append({
                    'type': 'error',
                    'message': 'Data is significantly outdated. Refresh urgently needed.'
                })
            elif hist_age > 2 or prog_age > 2:
                recommendations.append({
                    'type': 'warning',
                    'message': 'Data is becoming stale. Refresh recommended.'
                })
            else:
                recommendations.append({
                    'type': 'info',
                    'message': 'Minor update available.'
                })
        else:
            recommendations.append({
                'type': 'success',
                'message': 'All systems operational. Data is up to date.'
            })
        
        return recommendations
    
    def do_OPTIONS(self):
        """Handle preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()