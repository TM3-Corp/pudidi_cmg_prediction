#!/usr/bin/env python3
"""
Update CMG Programado data from Coordinador website
Preserves historical values while updating future predictions
"""

from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import requests
import csv
import json
import os
from io import StringIO
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# === CONFIG ===
HEADLESS = True  # Headless is safer for automated runs
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

# GitHub configuration
# Try to get token from environment, but allow running without it for testing
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    print("⚠️  Warning: GITHUB_TOKEN not set. Gist updates will fail.")
    print("   Set it with: export GITHUB_TOKEN='your_token_here'")
    # For testing, you could temporarily set a token here (remove before committing!)
    # GITHUB_TOKEN = "ghp_YOUR_TOKEN_HERE"
    
GIST_ID = "a63a3a10479bafcc29e10aaca627bc73"
GIST_FILENAME = "cmg_programado_historical.json"

def parse_csv_content(csv_content):
    """Parse CSV content and return structured data"""
    data = {}
    reader = csv.DictReader(StringIO(csv_content))
    
    current_time = datetime.now()
    
    for row in reader:
        # Parse date and time from 'Fecha Hora' column
        fecha_hora = None
        barra = None
        costo = None
        
        for key, value in row.items():
            if 'fecha hora' in key.lower():
                fecha_hora = value
            elif 'barra' in key.lower():
                barra = value
            elif 'costo marginal' in key.lower():
                try:
                    costo = float(value) if value else None
                except:
                    costo = None
        
        if not fecha_hora or not barra or costo is None:
            continue
            
        # Parse datetime (format: '2025-08-29 00:00:00.000000')
        try:
            dt = datetime.strptime(fecha_hora[:19], '%Y-%m-%d %H:%M:%S')
            date_str = dt.strftime('%Y-%m-%d')
            hour = dt.hour
        except:
            continue
        
        # Filter for PMontt220 node only (our main node for comparison)
        if barra != 'PMontt220':
            continue
        
        # Initialize date entry if needed
        if date_str not in data:
            data[date_str] = {}
        
        # Store with metadata about when this forecast was made
        if hour not in data[date_str]:
            data[date_str][hour] = {
                'value': costo,
                'forecasted_at': current_time.isoformat(),
                'is_historical': dt < current_time  # Mark if this is past data
            }
        
    return data

def merge_with_existing(new_data, existing_data):
    """Merge new data with existing, preserving historical values"""
    merged = existing_data.copy() if existing_data else {}
    current_time = datetime.now()
    
    for date_str, hours in new_data.items():
        if date_str not in merged:
            merged[date_str] = {}
        
        for hour, new_info in hours.items():
            # Parse the date and hour to check if it's in the past
            try:
                dt = datetime.strptime(f"{date_str} {hour:02d}:00:00", '%Y-%m-%d %H:%M:%S')
                is_past = dt < current_time
            except:
                is_past = False
            
            # If this hour doesn't exist in merged data, add it
            if hour not in merged[date_str]:
                merged[date_str][hour] = new_info
            # If this is a future hour, update it (forecasts can change)
            elif not is_past:
                # Keep history of changes if significant
                old_value = merged[date_str][hour].get('value')
                if old_value and abs(old_value - new_info['value']) > 0.1:
                    # Store previous forecast in history
                    if 'history' not in merged[date_str][hour]:
                        merged[date_str][hour]['history'] = []
                    merged[date_str][hour]['history'].append({
                        'value': old_value,
                        'forecasted_at': merged[date_str][hour].get('forecasted_at'),
                        'replaced_at': current_time.isoformat()
                    })
                # Update with new forecast
                merged[date_str][hour]['value'] = new_info['value']
                merged[date_str][hour]['forecasted_at'] = new_info['forecasted_at']
                merged[date_str][hour]['is_historical'] = False
            # If this is a past hour and marked as historical, don't update
            elif merged[date_str][hour].get('is_historical', False):
                # Past data should not be overwritten
                pass
            else:
                # Mark as historical now that it's in the past
                merged[date_str][hour]['is_historical'] = True
    
    return merged

def get_existing_gist_data():
    """Fetch existing data from GitHub Gist"""
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers)
        
        if response.status_code == 200:
            gist_data = response.json()
            if GIST_FILENAME in gist_data.get('files', {}):
                content = gist_data['files'][GIST_FILENAME].get('content', '{}')
                return json.loads(content)
        return {}
    except Exception as e:
        print(f"Error fetching existing gist: {e}")
        return {}

def update_gist(data):
    """Update GitHub Gist with merged data"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    # Prepare the data with metadata
    output = {
        'metadata': {
            'last_update': datetime.now().isoformat(),
            'node': 'PMontt220',
            'description': 'CMG Programado historical data with preserved past values'
        },
        'data': data
    }
    
    # Create/update gist
    payload = {
        'description': f"CMG Programado Historical Data - Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        'files': {
            GIST_FILENAME: {
                'content': json.dumps(output, indent=2, ensure_ascii=False)
            }
        }
    }
    
    response = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=payload)
    
    if response.status_code in (200, 201):
        print(f"✅ Gist updated successfully: {response.json()['html_url']}")
        return True
    else:
        print(f"❌ Failed to update gist: {response.status_code} - {response.text}")
        return False

async def download_cmg_programado():
    """Download CMG Programado from Coordinador website"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(180_000)

        try:
            # Navigate to the page
            print("📊 Navigating to Coordinador website...")
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="load")
            await page.get_by_role("link", name="Costo Marginal Programado").click()

            # Target PowerBI iframe
            frame = page.frame_locator("#Costo-Marginal-Programado iframe").nth(1)

            # Trigger download
            print("⬇️ Downloading CMG Programado data...")
            async with page.expect_download() as dl_info:
                await frame.get_by_title("Descargar").click()
            download = await dl_info.value

            # Save temporarily
            temp_path = downloads_dir / "temp_cmg_programado.csv"
            await download.save_as(str(temp_path))
            print(f"📁 Downloaded to: {temp_path}")

            # Read content
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()

            await browser.close()
            return content

        except PlaywrightTimeoutError:
            print("⏱️ Download timeout")
            await browser.close()
            return None
        except Exception as e:
            print(f"❌ Error downloading: {e}")
            await browser.close()
            return None

async def main():
    """Main execution"""
    print(f"🕐 Starting CMG Programado update at {datetime.now()}")
    
    # 1. Get existing data from Gist
    print("📥 Fetching existing historical data...")
    existing_data = get_existing_gist_data()
    if existing_data and 'data' in existing_data:
        existing_data = existing_data['data']
        print(f"   Found {len(existing_data)} days of existing data")
    else:
        existing_data = {}
        print("   No existing data found, starting fresh")
    
    # 2. Download new CMG Programado data
    csv_content = await download_cmg_programado()
    if not csv_content:
        print("❌ Failed to download new data")
        return
    
    # 3. Parse new data
    print("🔄 Parsing new CMG Programado data...")
    new_data = parse_csv_content(csv_content)
    print(f"   Parsed {len(new_data)} days of new data")
    
    # 4. Merge with existing data
    print("🔀 Merging with historical data...")
    merged_data = merge_with_existing(new_data, existing_data)
    
    # Count statistics
    total_hours = sum(len(hours) for hours in merged_data.values())
    historical_hours = sum(
        1 for hours in merged_data.values() 
        for hour_data in hours.values() 
        if hour_data.get('is_historical', False)
    )
    print(f"   Total hours: {total_hours}")
    print(f"   Historical (preserved): {historical_hours}")
    print(f"   Forecast (updateable): {total_hours - historical_hours}")
    
    # 5. Update Gist
    print("📤 Updating GitHub Gist...")
    if update_gist(merged_data):
        print("✅ CMG Programado update completed successfully!")
    else:
        print("❌ Failed to update Gist")

if __name__ == "__main__":
    asyncio.run(main())