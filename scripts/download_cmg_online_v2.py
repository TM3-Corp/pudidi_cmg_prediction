#!/usr/bin/env python3
"""
Download CMG Online data directly from Coordinador website using Playwright
Version 2: Better handling of popups and navigation
"""

from pathlib import Path
from datetime import datetime
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
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            accept_downloads=True,
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        page.set_default_timeout(30000)  # 30 seconds default timeout

        try:
            # 1) Navigate to the main page
            print("📍 Navigating to Coordinador CMG page...")
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="load")
            
            # 2) Handle potential survey popup
            print("🔍 Checking for survey popup...")
            await asyncio.sleep(3)  # Wait for popup to appear
            
            # Try to close any popup/modal/survey
            try:
                # Common close button selectors
                close_selectors = [
                    "button[aria-label='Close']",
                    "button[aria-label='Cerrar']",
                    "button.close",
                    "button:has-text('×')",
                    "button:has-text('X')",
                    "button:has-text('Cerrar')",
                    "button:has-text('Close')",
                    "[aria-label='close']",
                    ".modal-close",
                    ".survey-close",
                    "button[title='Close']"
                ]
                
                for selector in close_selectors:
                    try:
                        close_btn = page.locator(selector).first
                        if await close_btn.is_visible(timeout=1000):
                            await close_btn.click()
                            print(f"   ✓ Closed popup with: {selector}")
                            await asyncio.sleep(1)
                            break
                    except:
                        continue
            except:
                print("   ℹ️ No popup to close")
            
            # 3) Click on "Costo Marginal Online" tab
            print("🔍 Clicking on Costo Marginal Online...")
            
            # Wait for the tab to be available and click it
            online_tab = page.get_by_role("link", name="Costo Marginal Online")
            await online_tab.wait_for(state="visible", timeout=10000)
            await online_tab.click()
            
            # Wait for iframe to load
            print("⏳ Waiting for PowerBI iframe to load...")
            await asyncio.sleep(5)
            
            # 4) Target the PowerBI iframe
            print("🎯 Locating PowerBI iframe...")
            # The CMG Online iframe should be within the Costo-Marginal-Online section
            iframe_element = await page.wait_for_selector("#Costo-Marginal-Online iframe", timeout=10000)
            
            # Get all iframes and try the second one (index 1) as per partner's code
            frames = page.frames
            powerbi_frame = None
            
            # Find the PowerBI frame
            for frame in frames:
                if 'powerbi' in frame.url.lower() or 'pbix' in frame.url.lower():
                    powerbi_frame = frame
                    print(f"   ✓ Found PowerBI frame: {frame.url[:50]}...")
                    break
            
            if not powerbi_frame:
                # Fallback to frame locator
                frame_locator = page.frame_locator("#Costo-Marginal-Online iframe").nth(1)
                
                # Try to interact with the frame
                print("   ⚠️ Using frame locator fallback")
                
                # 5) Wait a bit for content to load
                await asyncio.sleep(3)
                
                # 6) Try to trigger download directly
                print("⬇️ Attempting to download CSV...")
                
                # Try various download button selectors
                download_selectors = [
                    "[title='Descargar']",
                    "[aria-label='Descargar']",
                    "[title='Download']",
                    "[aria-label='Download']",
                    "[title='Export']",
                    "[aria-label='Export']",
                    "button[title*='export']",
                    "button[aria-label*='export']",
                    "div[title='Descargar']",
                    "div[aria-label='Descargar']"
                ]
                
                download_triggered = False
                for selector in download_selectors:
                    try:
                        print(f"   Trying selector: {selector}")
                        async with page.expect_download(timeout=5000) as dl_info:
                            element = frame_locator.locator(selector).first
                            await element.click(timeout=3000)
                            download = await dl_info.value
                            download_triggered = True
                            print(f"   ✓ Download triggered with: {selector}")
                            break
                    except Exception as e:
                        continue
                
                if not download_triggered:
                    # Try with the main page context
                    print("   Trying download from main page context...")
                    for selector in download_selectors:
                        try:
                            async with page.expect_download(timeout=5000) as dl_info:
                                await page.locator(selector).first.click(timeout=3000)
                                download = await dl_info.value
                                download_triggered = True
                                print(f"   ✓ Download triggered from main page with: {selector}")
                                break
                        except:
                            continue
                
                if not download_triggered:
                    print("❌ Could not trigger download")
                    await browser.close()
                    return None
            
            else:
                # We have the PowerBI frame directly
                print("📊 Interacting with PowerBI frame...")
                
                # Wait for content to load
                await asyncio.sleep(3)
                
                # Try to download
                print("⬇️ Attempting to download CSV...")
                
                download_triggered = False
                download_selectors = [
                    "[title='Descargar']",
                    "[aria-label='Descargar']",
                    "[title='Download']",
                    "[title='Export']",
                    "button[title*='export' i]"
                ]
                
                for selector in download_selectors:
                    try:
                        async with page.expect_download(timeout=5000) as dl_info:
                            await powerbi_frame.locator(selector).first.click()
                            download = await dl_info.value
                            download_triggered = True
                            print(f"   ✓ Download triggered with: {selector}")
                            break
                    except:
                        continue
                
                if not download_triggered:
                    print("❌ Could not trigger download")
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
            import traceback
            traceback.print_exc()
            await browser.close()
            return None


def process_csv_to_json(csv_path):
    """Process the downloaded CSV into JSON format"""
    
    print("📊 Processing CSV data...")
    
    # Read CSV with different encodings
    encodings = ['utf-8', 'latin-1', 'iso-8859-1']
    content = None
    
    for encoding in encodings:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                content = f.read()
            print(f"   ✓ Read CSV with {encoding} encoding")
            break
        except UnicodeDecodeError:
            continue
    
    if not content:
        print("   ❌ Could not read CSV with any encoding")
        return None
    
    # Parse CSV
    reader = csv.DictReader(StringIO(content))
    
    # Process data
    data_by_node = {}
    row_count = 0
    
    for row in reader:
        row_count += 1
        # Parse fields - handle different possible column names
        fecha_minuto = row.get('fecha_minuto', '') or row.get('Fecha', '') or row.get('DateTime', '')
        barra = row.get('Barra', '') or row.get('Node', '') or row.get('Nodo', '')
        
        # Handle CMG value with different column names
        cmg_str = row.get('CMg(USD/MWh)', '0') or row.get('CMG', '0') or row.get('Price', '0')
        
        if not fecha_minuto or not barra:
            continue
        
        # Clean CMG value (handle comma as decimal separator)
        cmg_value = float(cmg_str.replace(',', '.').replace('$', '').strip())
        
        # Parse datetime
        try:
            # Try different datetime formats
            for fmt in ['%Y-%m-%d %H:%M', '%d-%m-%Y %H:%M', '%Y/%m/%d %H:%M']:
                try:
                    dt = datetime.strptime(fecha_minuto.split('.')[0], fmt)  # Remove milliseconds if present
                    break
                except:
                    continue
            else:
                # If no format worked, skip this row
                continue
                
            date_str = dt.strftime('%Y-%m-%d')
            hour = dt.hour
            minute = dt.minute
        except Exception as e:
            print(f"   ⚠️ Could not parse date '{fecha_minuto}': {e}")
            continue
        
        # Map node names
        if 'P.MONTT' in barra.upper() and '220' in barra:
            node = 'PMontt220'
        elif 'DALCAHUE' in barra.upper():
            node = 'Dalcahue'
        elif 'NVA_P.MONTT' in barra:
            node = 'PMontt220'
        elif 'PIDPID' in barra:
            node = 'PidPid'
        else:
            # Keep original node name
            node = barra.replace('_', '').replace('.', '').replace(' ', '')
        
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
    
    print(f"   ℹ️ Processed {row_count} rows")
    print(f"   ℹ️ Found nodes: {list(data_by_node.keys())}")
    
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
                avg_value = sum(v['value'] for v in values) / len(values) if values else 0
                
                result['data'].append({
                    'datetime': f"{date_str}T{hour:02d}:00:00",
                    'date': date_str,
                    'hour': hour,
                    'node': node,
                    'cmg_usd': round(avg_value, 2),
                    'num_samples': len(values)
                })
    
    # Sort by datetime
    result['data'].sort(key=lambda x: (x['datetime'], x['node']))
    
    print(f"✅ Processed {len(result['data'])} hourly records")
    
    return result


async def main():
    """Main function to download and process CMG Online data"""
    
    print("="*60)
    print("CMG ONLINE DOWNLOADER V2")
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
    
    if not json_data:
        print("❌ Failed to process CSV data")
        return 1
    
    # Save JSON
    json_path = downloads_dir / "cmg_online_latest.json"
    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"💾 Saved JSON to: {json_path}")
    print()
    print("✅ CMG Online download completed successfully!")
    
    # Show summary
    if json_data and json_data['data']:
        dates = set(d['date'] for d in json_data['data'])
        nodes = set(d['node'] for d in json_data['data'])
        print(f"\n📊 Summary:")
        print(f"   Dates: {', '.join(sorted(dates))}")
        print(f"   Nodes: {', '.join(sorted(nodes))}")
        print(f"   Total records: {len(json_data['data'])}")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)