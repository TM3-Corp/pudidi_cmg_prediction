#!/usr/bin/env python3
"""
Download CMG Online data directly from Coordinador website using Playwright
Based on the CMG Programado downloader but adapted for CMG Online
"""

from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import json
import csv
from io import StringIO
import pytz
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# === CONFIG ===
HEADLESS = True  # Set to False for debugging
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

# Santiago timezone
santiago_tz = pytz.timezone('America/Santiago')

async def download_cmg_online():
    """Download CMG Online data for today from Coordinador website"""
    
    async with async_playwright() as p:
        print("🚀 Launching browser...")
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(180_000)  # 3 minutes timeout

        try:
            # 1) Navigate to the main page
            print("📍 Navigating to Coordinador CMG page...")
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="networkidle")
            await asyncio.sleep(2)  # Wait for page to settle
            
            # 2) Click on "Costo Marginal Online" tab
            print("🔍 Clicking on Costo Marginal Online...")
            await page.get_by_role("link", name="Costo Marginal Online").click()
            await asyncio.sleep(3)  # Wait for iframe to load
            
            # 3) Target the PowerBI iframe
            print("🎯 Locating PowerBI iframe...")
            # The CMG Online iframe is usually the first one (index 0)
            frame = page.frame_locator("#Costo-Marginal-Online iframe").first
            
            # 4) Select date (Today)
            print("📅 Selecting today's date...")
            try:
                # Try to find and click the date selector
                date_selector = frame.locator("span.slicer-value").first
                await date_selector.wait_for(timeout=10000)
                await date_selector.click()
                await asyncio.sleep(1)
                
                # Select "Hoy" (Today)
                hoy_option = frame.locator("div:has-text('Hoy')").first
                await hoy_option.click()
                await asyncio.sleep(2)
            except Exception as e:
                print(f"⚠️ Could not select date, continuing anyway: {e}")
            
            # 5) Select nodes (P.MONTT_______220 and DALCAHUE______023)
            print("🔌 Selecting nodes...")
            try:
                # Look for Barra selector - it might be in different places
                barra_selectors = [
                    "div[aria-label='Barra']",
                    "div:has-text('Barra')",
                    "div.slicer-dropdown-menu",
                    "div[title*='Barra']"
                ]
                
                clicked = False
                for selector in barra_selectors:
                    try:
                        element = frame.locator(selector).first
                        await element.click(timeout=5000)
                        clicked = True
                        print(f"   ✓ Found Barra selector with: {selector}")
                        break
                    except:
                        continue
                
                if clicked:
                    await asyncio.sleep(1)
                    
                    # Try to select P.MONTT_______220
                    try:
                        await frame.locator("span:has-text('P.MONTT'):has-text('220')").first.click()
                        print("   ✓ Selected P.MONTT_______220")
                    except:
                        print("   ⚠️ Could not select P.MONTT_______220")
                    
                    await asyncio.sleep(0.5)
                    
                    # Try to select DALCAHUE______023
                    try:
                        await frame.locator("span:has-text('DALCAHUE')").first.click()
                        print("   ✓ Selected DALCAHUE______023")
                    except:
                        print("   ⚠️ Could not select DALCAHUE______023")
                    
                    await asyncio.sleep(2)
                else:
                    print("   ⚠️ Could not find Barra selector, will download all available data")
            except Exception as e:
                print(f"   ⚠️ Error selecting nodes: {e}")
            
            # 6) Trigger download
            print("⬇️ Downloading CSV...")
            try:
                # Look for download button with various selectors
                download_selectors = [
                    "[title='Descargar']",
                    "[aria-label='Descargar']",
                    "button:has-text('Descargar')",
                    "[title='Download']",
                    "[aria-label='Export']",
                    "button[title*='Export']"
                ]
                
                download_clicked = False
                for selector in download_selectors:
                    try:
                        async with page.expect_download(timeout=5000) as dl_info:
                            await frame.locator(selector).first.click()
                            download = await dl_info.value
                            download_clicked = True
                            print(f"   ✓ Download triggered with: {selector}")
                            break
                    except:
                        continue
                
                if not download_clicked:
                    print("❌ Could not find download button")
                    await browser.close()
                    return None
                    
            except Exception as e:
                print(f"❌ Download failed: {e}")
                await browser.close()
                return None

            # 7) Save the file
            timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
            save_path = downloads_dir / f"cmg_online_{timestamp}.csv"
            await download.save_as(str(save_path))
            print(f"✅ Saved file to: {save_path.resolve()}")

            await browser.close()
            return save_path
            
        except Exception as e:
            print(f"❌ Error during download: {e}")
            await browser.close()
            return None


def process_csv_to_json(csv_path):
    """Process the downloaded CSV into JSON format"""
    
    print("📊 Processing CSV data...")
    
    # Read CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse CSV
    reader = csv.DictReader(StringIO(content))
    
    # Process data
    data_by_node = {}
    
    for row in reader:
        # Parse fields
        fecha_minuto = row.get('fecha_minuto', '')
        barra = row.get('Barra', '')
        cmg_str = row.get('CMg(USD/MWh)', '0')
        
        # Clean CMG value (remove comma, convert to float)
        cmg_value = float(cmg_str.replace(',', '.'))
        
        # Parse datetime
        dt = datetime.strptime(fecha_minuto, '%Y-%m-%d %H:%M')
        date_str = dt.strftime('%Y-%m-%d')
        hour = dt.hour
        minute = dt.minute
        
        # Map node names
        if 'P.MONTT' in barra and '220' in barra:
            node = 'PMontt220'
        elif 'DALCAHUE' in barra:
            node = 'Dalcahue'
        else:
            continue  # Skip other nodes
        
        # Initialize node data structure
        if node not in data_by_node:
            data_by_node[node] = {}
        if date_str not in data_by_node[node]:
            data_by_node[node][date_str] = {}
        if hour not in data_by_node[node][date_str]:
            data_by_node[node][date_str][hour] = []
        
        # Add data point
        data_by_node[node][date_str][hour].append({
            'minute': minute,
            'value': cmg_value,
            'timestamp': fecha_minuto
        })
    
    # Calculate hourly averages
    result = {
        'timestamp': datetime.now(santiago_tz).isoformat(),
        'source': 'playwright_download',
        'data': []
    }
    
    for node, dates in data_by_node.items():
        for date_str, hours in dates.items():
            for hour, values in hours.items():
                # Calculate average for the hour
                avg_value = sum(v['value'] for v in values) / len(values)
                
                result['data'].append({
                    'datetime': f"{date_str}T{hour:02d}:00:00",
                    'date': date_str,
                    'hour': hour,
                    'node': node,
                    'cmg_usd': round(avg_value, 2),
                    'detail': values  # Keep 15-minute detail if needed
                })
    
    # Sort by datetime
    result['data'].sort(key=lambda x: x['datetime'])
    
    print(f"✅ Processed {len(result['data'])} hourly records")
    
    return result


async def main():
    """Main function to download and process CMG Online data"""
    
    print("="*60)
    print("CMG ONLINE DOWNLOADER")
    print("="*60)
    print(f"Timestamp: {datetime.now(santiago_tz)}")
    print()
    
    # Download CSV
    csv_path = await download_cmg_online()
    
    if not csv_path:
        print("❌ Failed to download CMG Online data")
        return 1
    
    # Process to JSON
    json_data = process_csv_to_json(csv_path)
    
    # Save JSON
    json_path = downloads_dir / "cmg_online_latest.json"
    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"💾 Saved JSON to: {json_path}")
    
    # Update cache file for API
    cache_path = Path("data/cache/cmg_historical_latest.json")
    if cache_path.parent.exists():
        # Merge with existing cache if it exists
        if cache_path.exists():
            with open(cache_path, 'r') as f:
                existing = json.load(f)
            
            # Merge new data
            existing_dates = {(d['date'], d['hour'], d['node']) for d in existing.get('data', [])}
            
            for record in json_data['data']:
                key = (record['date'], record['hour'], record['node'])
                if key not in existing_dates:
                    existing['data'].append(record)
            
            # Update timestamp
            existing['timestamp'] = json_data['timestamp']
            
            # Sort and save
            existing['data'].sort(key=lambda x: (x['date'], x['hour'], x['node']))
            
            with open(cache_path, 'w') as f:
                json.dump(existing, f, indent=2)
        else:
            # Create new cache file
            with open(cache_path, 'w') as f:
                json.dump(json_data, f, indent=2)
        
        print(f"✅ Updated cache: {cache_path}")
    
    print()
    print("✅ CMG Online download completed successfully!")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)