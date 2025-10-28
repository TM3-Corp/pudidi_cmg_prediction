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
        try:
            url = f"{self.base_url}/cmg_online"
            headers = self.headers.copy()
            headers["Prefer"] = "resolution=merge-duplicates"

            response = requests.post(url, json=records, headers=headers)
            
            if response.status_code in [200, 201, 204]:
                print(f"✅ Inserted {len(records)} CMG Online records")
                return True
            else:
                print(f"❌ Failed to insert CMG Online: {response.status_code}")
                print(f"   Response: {response.text}")
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
            params = {"order": "datetime.desc", "limit": limit}
            
            if start_date:
                params["date"] = f"gte.{start_date}"
            if end_date:
                params["date"] = f"lte.{end_date}"
            if node:
                params["node"] = f"eq.{node}"
            
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
            records: List of dicts with keys: datetime, date, hour, node, cmg_programmed
        
        Returns:
            True if successful
        """
        try:
            url = f"{self.base_url}/cmg_programado"
            headers = self.headers.copy()
            headers["Prefer"] = "resolution=merge-duplicates"
            
            response = requests.post(url, json=records, headers=headers)
            
            if response.status_code in [200, 201, 204]:
                print(f"✅ Inserted {len(records)} CMG Programado records")
                return True
            else:
                print(f"❌ Failed to insert CMG Programado: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error inserting CMG Programado: {e}")
            return False
    
    def get_cmg_programado(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get CMG Programado records"""
        try:
            url = f"{self.base_url}/cmg_programado"
            params = {"order": "datetime.desc", "limit": limit}
            
            if start_date:
                params["date"] = f"gte.{start_date}"
            if end_date:
                params["date"] = f"lte.{end_date}"
            
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

        Args:
            records: List of dicts with keys:
                     forecast_datetime, target_datetime, horizon,
                     cmg_predicted, prob_zero, threshold, model_version

        Returns:
            True if successful
        """
        try:
            url = f"{self.base_url}/ml_predictions"
            headers = self.headers.copy()
            headers["Prefer"] = "resolution=merge-duplicates"
            
            response = requests.post(url, json=records, headers=headers)
            
            if response.status_code in [200, 201, 204]:
                print(f"✅ Inserted {len(records)} ML prediction records")
                return True
            else:
                print(f"❌ Failed to insert ML predictions: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error inserting ML predictions: {e}")
            return False
    
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


def get_supabase_client() -> SupabaseClient:
    """Get initialized Supabase client"""
    return SupabaseClient()
