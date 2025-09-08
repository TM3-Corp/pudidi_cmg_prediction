#!/usr/bin/env python3
"""
Download CMG en Línea - Using exact selectors from the actual page
"""

from pathlib import Path
from datetime import datetime
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import pytz

# === CONFIG ===
HEADLESS = True  # Set to False for debugging
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)
santiago_tz = pytz.timezone('America/Santiago')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(180_000)  # 3 minutes

        try:
            # 1) Navigate
            print("Step 1: Navigating to Coordinador...")
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="load")
            print("   ✓ Page loaded")
            
            # 2) Click on "Costo Marginal en Línea" - use exact match to avoid confusion with Dashboard
            print("Step 2: Clicking on 'Costo Marginal en Línea'...")
            # Use the href to target the exact link we want
            await page.locator('a[href="#Costo-Marginal-en-L--nea"]').click()
            # Alternative: await page.get_by_role("link", name="Costo Marginal en Línea", exact=True).click()
            print("   ✓ Tab clicked")
            
            # 3) Wait for iframe to load
            print("Step 3: Waiting for PowerBI iframe to load...")
            await asyncio.sleep(5)
            
            # 4) Target the iframe - use the ID from the href
            print("Step 4: Locating iframe...")
            # The href is #Costo-Marginal-en-L--nea so use that as the ID
            frame = page.frame_locator("#Costo-Marginal-en-L--nea iframe").nth(1)
            
            # Alternative: if the ID doesn't work, try generic iframe
            # frame = page.frame_locator("iframe").nth(1)
            
            print("   ✓ Iframe located")
            
            # 5) Select date using the exact selector you provided
            print("Step 5: Selecting date...")
            try:
                # Look for the date selector div with calendar icon
                # The selector has class "show-range" and contains a span with the date
                date_selector = frame.locator("div.show-range").first
                await date_selector.wait_for(state="visible", timeout=10000)
                await date_selector.click()
                print("   ✓ Date selector clicked")
                
                # Wait for date options to appear
                await asyncio.sleep(1)
                
                # Select "Hoy" (Today) - this should be in a dropdown or popup
                try:
                    await frame.locator("text=Hoy").first.click()
                    print("   ✓ Selected 'Hoy' (Today)")
                except:
                    # If "Hoy" doesn't work, try clicking on today's date directly
                    today = datetime.now(santiago_tz).strftime("%d-%m-%Y")
                    await frame.locator(f"text={today}").first.click()
                    print(f"   ✓ Selected today's date: {today}")
                
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"   ⚠️ Could not select date: {e}")
                # Continue anyway - might already be on today's date
            
            # 6) Select nodes (Barra)
            print("Step 6: Selecting nodes (Barra)...")
            try:
                # Look for the Barra selector using the exact structure you provided
                # It's a div with data-testid="collapsed-title-Barra"
                barra_selector = frame.locator("div[data-testid='collapsed-title-Barra']").first
                await barra_selector.wait_for(state="visible", timeout=10000)
                await barra_selector.click()
                print("   ✓ Barra selector clicked")
                
                # Wait for options to appear
                await asyncio.sleep(2)
                
                # Clear any existing selections
                try:
                    clear_btn = frame.locator("button:has-text('Borrar')").first
                    if await clear_btn.is_visible():
                        await clear_btn.click()
                        print("   ✓ Cleared existing selections")
                        await asyncio.sleep(1)
                except:
                    pass
                
                # Select P.MONTT_______220
                try:
                    # Try to find and click P.MONTT in the dropdown
                    pmontt = frame.locator("text=P.MONTT").first
                    await pmontt.wait_for(state="visible", timeout=5000)
                    await pmontt.click()
                    print("   ✓ Selected P.MONTT_______220")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"   ⚠️ Could not select P.MONTT: {e}")
                
                # Select DALCAHUE______023
                try:
                    # Try to find and click DALCAHUE in the dropdown
                    dalcahue = frame.locator("text=DALCAHUE").first
                    await dalcahue.wait_for(state="visible", timeout=5000)
                    await dalcahue.click()
                    print("   ✓ Selected DALCAHUE______023")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"   ⚠️ Could not select DALCAHUE: {e}")
                
                await asyncio.sleep(2)
                
                # Close the selector if needed
                try:
                    # Click outside or press Escape to close the dropdown
                    await page.keyboard.press("Escape")
                except:
                    pass
                    
            except Exception as e:
                print(f"   ⚠️ Could not select nodes: {e}")
                # Continue anyway - might download all nodes
            
            # 7) Trigger download
            print("Step 7: Triggering download...")
            
            # Wait a moment for any dropdowns to close
            await asyncio.sleep(2)
            
            download = None
            
            # Try the partner's exact approach first
            try:
                print("   Trying partner's approach (get_by_title)...")
                async with page.expect_download(timeout=15000) as dl_info:
                    await frame.get_by_title("Descargar").click()
                download = await dl_info.value
                print("   ✓ Download triggered!")
            except Exception as e:
                print(f"   Failed with get_by_title: {str(e)[:100]}")
                
                # Try alternative methods
                download_selectors = [
                    "[title='Descargar']",
                    "[aria-label='Descargar']",
                    "button:has-text('Descargar')",
                    "[title='Download']",
                    "[title='Export']",
                    "button[title*='export' i]",
                    "button[title*='descargar' i]"
                ]
                
                for selector in download_selectors:
                    try:
                        print(f"   Trying selector: {selector}")
                        async with page.expect_download(timeout=10000) as dl_info:
                            await frame.locator(selector).first.click()
                        download = await dl_info.value
                        print(f"   ✓ Download triggered with: {selector}")
                        break
                    except Exception as e:
                        continue
            
            if not download:
                print("   ❌ Could not trigger download")
                await browser.close()
                return None
            
            # 8) Save file
            print("Step 8: Saving file...")
            timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
            save_path = downloads_dir / f"cmg_en_linea_{timestamp}.csv"
            await download.save_as(str(save_path))
            print(f"   ✓ Saved to: {save_path}")
            
            await browser.close()
            return save_path
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            await browser.close()
            return None

def process_csv(csv_path):
    """Process the downloaded CSV"""
    import csv
    
    print("\nProcessing CSV...")
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        print(f"   Rows: {len(rows)}")
        if rows:
            print(f"   Columns: {list(rows[0].keys())}")
            
            # Show sample data
            print("   Sample data (first 3 rows):")
            for i, row in enumerate(rows[:3]):
                print(f"     Row {i+1}: {row}")
                
            # Count nodes
            nodes = set()
            for row in rows:
                if 'Barra' in row:
                    nodes.add(row['Barra'])
            print(f"   Nodes found: {nodes}")
            
        return True
    except Exception as e:
        print(f"   Error processing CSV: {e}")
        return False

async def main():
    print("="*60)
    print("CMG EN LÍNEA DOWNLOADER - FINAL VERSION")
    print("="*60)
    print(f"Timestamp: {datetime.now(santiago_tz)}")
    print(f"Using exact selectors from page inspection")
    print()
    
    # Run the download
    result = await run()
    
    if result:
        print(f"\n✅ SUCCESS! Downloaded: {result}")
        
        # Process the CSV
        process_csv(result)
        
        return 0
    else:
        print("\n❌ FAILED to download")
        print("\nTroubleshooting:")
        print("1. Check if 'Costo Marginal en Línea' tab exists")
        print("2. Check if date selector is visible")
        print("3. Check if Barra selector is accessible")
        print("4. Check if download button is available")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)