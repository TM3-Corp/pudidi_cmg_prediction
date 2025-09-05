#!/usr/bin/env python3
"""
CMG Programado scraper with date selection attempt
Tries to interact with PowerBI controls to get historical data
"""

from pathlib import Path
from datetime import datetime, timedelta
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# === CONFIG ===
HEADLESS = False  # Need to see what's happening
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

async def try_date_selection():
    async with async_playwright() as p:
        print("🌐 Launching browser (visible mode for debugging)...")
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(180_000)

        try:
            # Navigate to the page
            print("📍 Navigating to Coordinador website...")
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="load")
            await page.wait_for_timeout(2000)
            
            print("🔗 Clicking on Costo Marginal Programado...")
            await page.get_by_role("link", name="Costo Marginal Programado").click()
            await page.wait_for_timeout(8000)  # Give PowerBI time to load
            
            # Get the PowerBI iframe
            print("🔍 Locating PowerBI iframe...")
            frame = page.frame_locator("#Costo-Marginal-Programado iframe").nth(1)
            
            # Try to find date/time controls
            print("\n🗓️ Looking for date/time controls in PowerBI...")
            print("   (This may take a moment...)")
            
            # Common PowerBI date selector patterns
            date_selectors = [
                "button:has-text('Fecha')",
                "div[role='button']:has-text('Fecha')",
                "[aria-label*='fecha']",
                "[aria-label*='Fecha']",
                "[title*='fecha']",
                "[title*='Fecha']",
                "div.slicer-dropdown-menu",
                "div[class*='slicer']",
                "div[class*='date']",
                "button[class*='calendar']"
            ]
            
            found_control = False
            for selector in date_selectors:
                try:
                    element = frame.locator(selector).first
                    if await element.is_visible(timeout=2000):
                        print(f"   ✓ Found potential date control: {selector}")
                        found_control = True
                        # Try to click it
                        await element.click()
                        await page.wait_for_timeout(2000)
                        break
                except:
                    continue
            
            if not found_control:
                print("   ℹ️ No interactive date controls found")
                print("   The dashboard may only show fixed forecast data")
            
            # Check if there are any filter options visible
            print("\n🔍 Checking for filter options...")
            try:
                # Look for any dropdowns or filter panels
                filters = frame.locator("div[role='listbox'], select, div.dropdown")
                count = await filters.count()
                if count > 0:
                    print(f"   Found {count} potential filter controls")
                    for i in range(min(count, 3)):  # Check first 3
                        filter_elem = filters.nth(i)
                        text = await filter_elem.text_content()
                        if text:
                            print(f"   Filter {i+1}: {text[:50]}...")
            except:
                print("   No filter controls accessible")
            
            # Try downloading current data to see what's available
            print("\n📥 Downloading current data...")
            try:
                async with page.expect_download() as dl_info:
                    await frame.get_by_title("Descargar").click()
                download = await dl_info.value
                
                # Save with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = downloads_dir / f"cmg_programado_{timestamp}.csv"
                await download.save_as(str(save_path))
                print(f"   ✓ Downloaded to: {save_path}")
                
                # Check what dates are in the file
                import csv
                with open(save_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    dates_found = set()
                    for row in reader:
                        for key, value in row.items():
                            if 'fecha' in key.lower() and value:
                                date_part = value.split(' ')[0]
                                dates_found.add(date_part)
                                if len(dates_found) >= 10:  # Sample check
                                    break
                    
                    if dates_found:
                        sorted_dates = sorted(dates_found)
                        print(f"\n📅 Dates found in downloaded data:")
                        print(f"   First: {sorted_dates[0]}")
                        print(f"   Last: {sorted_dates[-1]}")
                        print(f"   Total unique dates: {len(sorted_dates)}")
                        
                        # Check if Sept 1-3 are included
                        sept_dates = ['2025-09-01', '2025-09-02', '2025-09-03']
                        missing = [d for d in sept_dates if d not in dates_found]
                        if missing:
                            print(f"\n   ⚠️  Sept 1-3 data not available in current view")
                            print(f"   Missing dates: {', '.join(missing)}")
                        else:
                            print(f"\n   ✅ Sept 1-3 data is available!")
                
            except Exception as e:
                print(f"   ❌ Download failed: {e}")
            
            print("\n" + "="*60)
            print("ANALYSIS:")
            print("="*60)
            print("The CMG Programado dashboard appears to show:")
            print("• A rolling 72-hour forecast window")
            print("• Updated daily with new predictions")
            print("• Historical data (Sept 1-3) is no longer available")
            print("\nTo get Sept 1-3 data, you would need:")
            print("• Access to archived forecasts from those dates")
            print("• Or wait for a historical data export option")
            print("• Or check if Coordinador has a separate historical API")
            
            # Keep browser open for manual inspection
            print("\n⏸️  Browser will close in 10 seconds...")
            print("   (You can interact with the page manually)")
            await page.wait_for_timeout(10000)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await browser.close()
            print("\n✅ Browser closed")

async def main():
    """Main execution"""
    print("="*60)
    print("CMG PROGRAMADO DATE SELECTION EXPLORER")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    await try_date_selection()

if __name__ == "__main__":
    asyncio.run(main())