#!/usr/bin/env python3
"""
Backup all 3 Gists before migration
Safety measure to preserve data before any modifications
"""

import json
import requests
from datetime import datetime
import pytz
from pathlib import Path

# Gist IDs
GISTS = {
    'ml_predictions': '38b3f9b1cdae5362d3676911ab27f606',
    'cmg_programado': 'd68bb21360b1ac549c32a80195f99b09',
    'cmg_online': '8d7864eb26acf6e780d3c0f7fed69365'
}

FILENAMES = {
    'ml_predictions': 'ml_predictions_historical.json',
    'cmg_programado': 'cmg_programado_historical.json',
    'cmg_online': 'cmg_online_historical.json'
}

def backup_gist(gist_id, gist_name, filename):
    """Backup a single Gist to local file"""
    try:
        url = f'https://gist.githubusercontent.com/PVSH97/{gist_id}/raw/{filename}'

        print(f"📥 Fetching {gist_name}...")
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            data = response.json()

            # Create backup directory
            backup_dir = Path('data/backups/gists')
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Timestamp for backup
            santiago_tz = pytz.timezone('America/Santiago')
            timestamp = datetime.now(santiago_tz).strftime('%Y%m%d_%H%M%S')

            # Save backup
            backup_file = backup_dir / f'{gist_name}_{timestamp}.json'
            with open(backup_file, 'w') as f:
                json.dump(data, f, indent=2)

            # Also save latest copy
            latest_file = backup_dir / f'{gist_name}_latest.json'
            with open(latest_file, 'w') as f:
                json.dump(data, f, indent=2)

            # Calculate size
            file_size = backup_file.stat().st_size / 1024  # KB

            print(f"✅ Backed up {gist_name}")
            print(f"   Size: {file_size:.1f} KB")
            print(f"   File: {backup_file}")

            # Show data summary
            if 'daily_data' in data:
                dates = list(data['daily_data'].keys())
                if dates:
                    print(f"   Dates: {min(dates)} to {max(dates)} ({len(dates)} days)")
            if 'historical_data' in data:
                dates = list(data['historical_data'].keys())
                if dates:
                    print(f"   Historical: {min(dates)} to {max(dates)} ({len(dates)} days)")

            return True

        else:
            print(f"❌ Error fetching {gist_name}: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error backing up {gist_name}: {e}")
        return False

def main():
    print("="*60)
    print("BACKUP ALL GISTS BEFORE MIGRATION")
    print("="*60)
    print()

    success_count = 0

    for gist_name, gist_id in GISTS.items():
        filename = FILENAMES[gist_name]
        if backup_gist(gist_id, gist_name, filename):
            success_count += 1
        print()

    print("="*60)
    if success_count == len(GISTS):
        print("✅ ALL GISTS BACKED UP SUCCESSFULLY")
        print(f"   Backups saved to: data/backups/gists/")
    else:
        print(f"⚠️ {success_count}/{len(GISTS)} Gists backed up")
    print("="*60)

    return 0 if success_count == len(GISTS) else 1

if __name__ == "__main__":
    exit(main())
