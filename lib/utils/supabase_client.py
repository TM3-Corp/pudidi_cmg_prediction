"""
Supabase Client for CMG Prediction System
==========================================

Handles all database operations for:
- CMG Online (historical data)
- CMG Programado (forecast data)
- ML Predictions (24-hour forecasts)

Replaces GitHub Gist storage to avoid rate limiting.
"""

import os
import requests
import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import pytz

class SupabaseClient:
    """Client for interacting with Supabase PostgreSQL database"""
    
    def __init__(self):
        """Initialize Supabase client with credentials from environment"""
        self.supabase_url = os.environ.get('SUPABASE_URL')
        self.supabase_key = os.environ.get('SUPABASE_SERVICE_KEY')  # Use service_role key for writes
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError(
                "Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables."
            )
        
        self.base_url = f"{self.supabase_url}/rest/v1"
        self.headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"  # Don't return inserted data by default
        }
    
    # ========================================
    # CMG ONLINE (HISTORICAL DATA)
    # ========================================
    
    def insert_cmg_online_batch(self, records: List[Dict[str, Any]]) -> bool:
        """
        Insert batch of CMG Online records.
        Uses UPSERT to handle duplicates gracefully.

        Args:
            records: List of dicts with keys: datetime, date, hour, node, cmg_usd

        Returns:
            True if successful, False otherwise
        """
        if not records:
            print("⚠️  No records to insert")
            return True

        try:
            # Use on_conflict query parameter to specify UPSERT behavior
            # This tells PostgREST to update existing records instead of failing
            url = f"{self.base_url}/cmg_online?on_conflict=datetime,node"
            headers = self.headers.copy()
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

            response = requests.post(url, json=records, headers=headers)

            if response.status_code in [200, 201, 204]:
                print(f"✅ Inserted {len(records)} CMG Online records")
                return True
            else:
                print(f"❌ Failed to insert CMG Online: {response.status_code}")
                print(f"   Response: {response.text}")
                # Still return True if it's just duplicate errors (script should continue)
                if response.status_code == 409:
                    print("   Note: Some records already exist (this is OK)")
                    return True
                return False
        except Exception as e:
            print(f"❌ Error inserting CMG Online: {e}")
            return False
    
    def get_cmg_online(
        self, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        node: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get CMG Online records with optional filters.
        
        Args:
            start_date: Filter by date >= this (YYYY-MM-DD)
            end_date: Filter by date <= this (YYYY-MM-DD)
            node: Filter by specific node
            limit: Max records to return
        
        Returns:
            List of CMG Online records
        """
        try:
            url = f"{self.base_url}/cmg_online"

            # Build params as list of tuples to allow multiple values for same key
            # This is required for PostgREST to AND multiple filters on the same column
            params = [("order", "datetime.desc"), ("limit", limit)]

            # Handle date range filters properly (PostgREST syntax)
            if start_date:
                params.append(("date", f"gte.{start_date}"))
            if end_date:
                params.append(("date", f"lte.{end_date}"))

            if node:
                params.append(("node", f"eq.{node}"))

            response = requests.get(url, params=params, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Failed to get CMG Online: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting CMG Online: {e}")
            return []
    
    # ========================================
    # CMG PROGRAMADO (FORECAST DATA)
    # ========================================
    
    def insert_cmg_programado_batch(self, records: List[Dict[str, Any]]) -> bool:
        """
        Insert batch of CMG Programado records.
        Uses UPSERT to handle duplicates.

        Args:
            records: List of dicts with keys:
                - forecast_datetime: When forecast was made
                - forecast_date: Date when forecast was made
                - forecast_hour: Hour when forecast was made
                - target_datetime: What hour is being predicted
                - target_date: Date being predicted
                - target_hour: Hour being predicted
                - node: Node name
                - node_id: Node ID (required after migration 002)
                - cmg_usd: CMG value in USD

        Returns:
            True if successful
        """
        try:
            # FIXED: Use node_id instead of node to match unique constraint
            # unique_cmg_prog_forecast_target_node_id (forecast_datetime, target_datetime, node_id)
            url = f"{self.base_url}/cmg_programado?on_conflict=forecast_datetime,target_datetime,node_id"
            headers = self.headers.copy()
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

            response = requests.post(url, json=records, headers=headers)

            if response.status_code in [200, 201, 204]:
                print(f"✅ Inserted {len(records)} CMG Programado records")
                return True
            else:
                print(f"❌ Failed to insert CMG Programado: {response.status_code}")
                print(f"   Response: {response.text}")
                # Still return True if it's just duplicate errors (script should continue)
                if response.status_code == 409:
                    print("   Note: Some records already exist (this is OK)")
                    return True
                return False
        except Exception as e:
            print(f"❌ Error inserting CMG Programado: {e}")
            return False

    def get_cmg_programado(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        node: Optional[str] = None,
        limit: int = 10000,
        latest_forecast_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get CMG Programado forecast records.

        Args:
            start_date: Filter by target_date >= this (YYYY-MM-DD)
            end_date: Filter by target_date <= this (YYYY-MM-DD)
            node: Filter by specific node
            limit: Max records to return
            latest_forecast_only: If True, only return records from the latest forecast (prevents duplicates)

        Returns:
            List of forecast records with forecast_datetime and target_datetime
        """
        try:
            url = f"{self.base_url}/cmg_programado"

            if latest_forecast_only:
                # STEP 1: Get the latest forecast_datetime for this node
                params_latest = [
                    ("select", "forecast_datetime"),
                    ("order", "forecast_datetime.desc"),
                    ("limit", "1")
                ]
                if node:
                    params_latest.append(("node", f"eq.{node}"))

                response_latest = requests.get(url, params=params_latest, headers=self.headers)

                if response_latest.status_code != 200 or not response_latest.json():
                    print("⚠️ No forecasts found")
                    return []

                latest_forecast_dt = response_latest.json()[0]['forecast_datetime']

                # STEP 2: Get all records from this specific forecast
                params = [
                    ("forecast_datetime", f"eq.{latest_forecast_dt}"),
                    ("order", "target_datetime.asc"),
                    ("limit", limit)
                ]
            else:
                # Original behavior: get multiple forecasts (may contain duplicates)
                params = [("order", "forecast_datetime.desc,target_datetime.asc"), ("limit", limit)]

            # Handle date range filters properly (PostgREST syntax)
            if start_date:
                params.append(("target_date", f"gte.{start_date}"))
            if end_date:
                params.append(("target_date", f"lte.{end_date}"))
            if node:
                params.append(("node", f"eq.{node}"))

            response = requests.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Failed to get CMG Programado: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting CMG Programado: {e}")
            return []
    
    # ========================================
    # ML PREDICTIONS (24H FORECAST)
    # ========================================
    
    def insert_ml_predictions_batch(self, records: List[Dict[str, Any]]) -> bool:
        """
        Insert batch of ML prediction records.
        Uses UPSERT to handle duplicates (when same forecast is run multiple times).

        Args:
            records: List of dicts with keys:
                     forecast_datetime, target_datetime, horizon,
                     cmg_predicted, prob_zero, threshold, model_version

        Returns:
            True if successful
        """
        try:
            # FIXED: Add on_conflict to match unique constraint
            # ml_predictions_forecast_datetime_target_datetime_key (forecast_datetime, target_datetime)
            url = f"{self.base_url}/ml_predictions?on_conflict=forecast_datetime,target_datetime"
            headers = self.headers.copy()
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

            response = requests.post(url, json=records, headers=headers)

            if response.status_code in [200, 201, 204]:
                print(f"✅ Inserted {len(records)} ML prediction records")
                return True
            else:
                print(f"❌ Failed to insert ML predictions: {response.status_code}")
                print(f"   Response: {response.text}")
                # Still return True if it's just duplicate errors (script should continue)
                if response.status_code == 409:
                    print("   Note: Some predictions already exist (this is OK)")
                    return True
                return False
        except Exception as e:
            print(f"❌ Error inserting ML predictions: {e}")
            return False
    
    def get_nodes(self) -> List[Dict[str, Any]]:
        """
        Get all nodes from the nodes table.

        Returns:
            List of node records with id, code, name, etc.
        """
        try:
            url = f"{self.base_url}/nodes"
            params = {"order": "code.asc"}

            response = requests.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Failed to get nodes: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting nodes: {e}")
            return []

    def get_node_id_map(self) -> Dict[str, int]:
        """
        Get mapping of node code -> node_id for efficient lookups.

        Returns:
            Dict mapping node codes to their IDs
        """
        nodes = self.get_nodes()
        return {node['code']: node['id'] for node in nodes}

    def get_latest_ml_predictions(self, limit: int = 24) -> List[Dict[str, Any]]:
        """
        Get the most recent ML forecast (latest 24 predictions).

        Returns:
            List of ML prediction records from most recent forecast
        """
        try:
            # First, get the latest forecast_datetime
            url = f"{self.base_url}/ml_predictions"
            params = {
                "select": "forecast_datetime",
                "order": "forecast_datetime.desc",
                "limit": 1
            }

            response = requests.get(url, params=params, headers=self.headers)

            if response.status_code != 200 or not response.json():
                print("❌ No ML predictions found")
                return []

            latest_forecast = response.json()[0]["forecast_datetime"]

            # Now get all predictions from that forecast
            params = {
                "forecast_datetime": f"eq.{latest_forecast}",
                "order": "target_datetime.asc",
                "limit": limit
            }

            response = requests.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Failed to get ML predictions: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting ML predictions: {e}")
            return []

    def get_ml_predictions(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10000
    ) -> List[Dict[str, Any]]:
        """
        Get ML predictions with date range filtering.

        Args:
            start_date: Filter by target_datetime >= this (YYYY-MM-DD)
            end_date: Filter by target_datetime <= this (YYYY-MM-DD)
            limit: Max records to return

        Returns:
            List of ML prediction records
        """
        try:
            url = f"{self.base_url}/ml_predictions"

            # Build params as list of tuples to allow multiple values for same key
            params = [
                ("order", "forecast_datetime.desc,target_datetime.asc"),
                ("limit", limit)
            ]

            # Handle date range filters properly (PostgREST syntax)
            if start_date:
                params.append(("target_datetime", f"gte.{start_date}"))
            if end_date:
                params.append(("target_datetime", f"lte.{end_date}"))

            response = requests.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Failed to get ML predictions: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting ML predictions: {e}")
            return []

    # ========================================
    # METADATA
    # ========================================
    
    def update_metadata(self, key: str, value: Dict[str, Any]) -> bool:
        """Update system metadata"""
        try:
            url = f"{self.base_url}/system_metadata"
            params = {"key": f"eq.{key}"}
            data = {
                "value": value,
                "updated_at": datetime.now(pytz.UTC).isoformat()
            }
            
            response = requests.patch(url, params=params, json=data, headers=self.headers)
            
            if response.status_code in [200, 201, 204]:
                print(f"✅ Updated metadata: {key}")
                return True
            else:
                print(f"❌ Failed to update metadata: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error updating metadata: {e}")
            return False


    # ========================================
    # FORMAT HELPERS (for API compatibility)
    # ========================================

    def format_cmg_online_as_cache(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Format Supabase CMG Online records to match cache file structure.
        Used by API endpoints for backward compatibility.
        """
        daily_data = {}
        santiago_tz = pytz.timezone('America/Santiago')

        for record in records:
            date_str = record['date'] if isinstance(record['date'], str) else str(record['date'])
            node = record['node']
            hour = record['hour']

            if date_str not in daily_data:
                daily_data[date_str] = {
                    'hours': [],
                    'cmg_online': {}
                }

            if node not in daily_data[date_str]['cmg_online']:
                daily_data[date_str]['cmg_online'][node] = {
                    'cmg_usd': [None] * 24
                }

            daily_data[date_str]['cmg_online'][node]['cmg_usd'][hour] = float(record['cmg_usd'])

            if hour not in daily_data[date_str]['hours']:
                daily_data[date_str]['hours'].append(hour)

        # Sort hours
        for date_data in daily_data.values():
            date_data['hours'].sort()

        return {
            'metadata': {
                'last_update': datetime.now(santiago_tz).isoformat(),
                'total_records': len(records),
                'source': 'supabase'
            },
            'daily_data': daily_data
        }

    def format_cmg_programado_as_cache(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Format Supabase CMG Programado records to match cache file structure.
        """
        daily_data = {}
        santiago_tz = pytz.timezone('America/Santiago')

        for record in records:
            date_str = record['date'] if isinstance(record['date'], str) else str(record['date'])
            hour = record['hour']

            if date_str not in daily_data:
                daily_data[date_str] = {
                    'cmg_programado': [None] * 24
                }

            daily_data[date_str]['cmg_programado'][hour] = float(record['cmg_programmed'])

        return {
            'metadata': {
                'last_update': datetime.now(santiago_tz).isoformat(),
                'total_records': len(records),
                'source': 'supabase'
            },
            'daily_data': daily_data
        }


def get_supabase_client() -> SupabaseClient:
    """Get initialized Supabase client"""
    return SupabaseClient()
