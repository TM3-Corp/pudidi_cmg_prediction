#!/usr/bin/env python3
"""
Download CMG Online - Simple approach mimicking partner's strategy
"""

from pathlib import Path
from datetime import datetime
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import pytz

# === CONFIG ===
HEADLESS = True  # Set False for debugging
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)
santiago_tz = pytz.timezone('America/Santiago')

async def run():
    async with async_playwright() as p:
        print("🚀 Launching browser...")
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        # KEY: Set LONG timeout like partner does
        page.set_default_timeout(180_000)  # 3 minutes
        
        try:
            # 1) Navigate to page
            print("📍 Navigating to Coordinador...")
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="load")
            
            # 2) Click on CMG Online tab (try both Spanish and possible variations)
            print("🔍 Looking for CMG Online tab...")
            
            # Try different possible link texts
            tab_names = [
                "Costo Marginal Online",
                "Costo Marginal On Line",
                "CMG Online",
                "CMG On Line",
                "Costos Marginales Online"
            ]
            
            tab_clicked = False
            for name in tab_names:
                try:
                    print(f"   Trying: {name}")
                    link = page.get_by_role("link", name=name)
                    if await link.count() > 0:
                        await link.first.click()
                        tab_clicked = True
                        print(f"   ✓ Clicked on: {name}")
                        break
                except:
                    continue
            
            if not tab_clicked:
                # Try with partial text match
                print("   Trying partial text match...")
                try:
                    await page.locator("a:has-text('Online')").first.click()
                    print("   ✓ Clicked using partial match")
                except:
                    print("   ❌ Could not find CMG Online tab")
            
            # 3) Wait for iframe to load
            print("⏳ Waiting for PowerBI to load...")
            await asyncio.sleep(5)  # Give it time
            
            # 4) Target PowerBI iframe using partner's approach
            print("🎯 Targeting iframe...")
            
            # Try both possible section IDs
            iframe_selectors = [
                "#Costo-Marginal-Online iframe",
                "#Costo-Marginal-On-Line iframe",
                "#CMG-Online iframe",
                "iframe[title*='Power BI']",
                "iframe[src*='powerbi']"
            ]
            
            frame = None
            for selector in iframe_selectors:
                try:
                    # Use nth(1) to get SECOND iframe like partner does
                    frame = page.frame_locator(selector).nth(1)
                    # Test if we can access it
                    await frame.locator("*").first.wait_for(timeout=5000)
                    print(f"   ✓ Found iframe with: {selector}")
                    break
                except:
                    # Try first iframe (nth(0))
                    try:
                        frame = page.frame_locator(selector).first
                        await frame.locator("*").first.wait_for(timeout=5000)
                        print(f"   ✓ Found iframe (first) with: {selector}")
                        break
                    except:
                        continue
            
            if not frame:
                print("   ❌ Could not find PowerBI iframe")
                await browser.close()
                return None
            
            # 5) Wait a bit more for content to stabilize
            await asyncio.sleep(3)
            
            # 6) Trigger download using partner's simple approach
            print("⬇️ Attempting download...")
            
            download = None
            download_methods = [
                # Method 1: Exact match like partner
                lambda: frame.get_by_title("Descargar").click(),
                # Method 2: Try "Download" in English
                lambda: frame.get_by_title("Download").click(),
                # Method 3: Try aria-label
                lambda: frame.locator("[aria-label='Descargar']").first.click(),
                # Method 4: Try any element with download icon/text
                lambda: frame.locator("button:has-text('Descargar')").first.click(),
                lambda: frame.locator("div[title='Descargar']").first.click(),
            ]
            
            for i, method in enumerate(download_methods):
                try:
                    async with page.expect_download(timeout=10000) as dl_info:
                        await method()
                    download = await dl_info.value
                    print(f"   ✓ Download triggered with method {i+1}")
                    break
                except Exception as e:
                    continue
            
            if not download:
                print("❌ Could not trigger download")
                await browser.close()
                return None
            
            # 7) Save file
            timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
            save_path = downloads_dir / f"cmg_online_{timestamp}.csv"
            await download.save_as(str(save_path))
            print(f"✅ Saved to: {save_path}")
            
            await browser.close()
            return save_path
            
        except PlaywrightTimeoutError as e:
            print(f"⏱️ Timeout: {e}")
            await browser.close()
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            await browser.close()
            return None

async def main():
    print("="*60)
    print("CMG ONLINE DOWNLOADER - SIMPLE")
    print("="*60)
    print(f"Using partner's strategy")
    print()
    
    result = await run()
    
    if result:
        print(f"\n✅ Success! File downloaded: {result}")
        
        # Try to process it
        try:
            import csv
            with open(result, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                print(f"   Rows in CSV: {len(rows)}")
                if rows:
                    print(f"   Columns: {list(rows[0].keys())}")
        except Exception as e:
            print(f"   Could not read CSV: {e}")
    else:
        print("\n❌ Download failed")
        print("\nPossible issues:")
        print("1. The tab might be named differently")
        print("2. The iframe structure might be different for CMG Online")
        print("3. The download button might be in a different location")
        print("4. A popup might be blocking interaction")
    
    return 0 if result else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)