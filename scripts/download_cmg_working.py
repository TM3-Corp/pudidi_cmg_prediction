#!/usr/bin/env python3
"""
Working CMG en Línea download script - tested and confirmed
"""
from pathlib import Path
from datetime import datetime
import asyncio
import pytz
from playwright.async_api import async_playwright

# Configuration
HEADLESS = True  # Must be True for GitHub Actions
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)
santiago_tz = pytz.timezone('America/Santiago')

async def run():
    """Download CMG en Línea CSV from Coordinador"""
    
    async with async_playwright() as p:
        print("Step 1: Launching browser...", flush=True)
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        print("Step 2: Creating context...", flush=True)
        context = await browser.new_context(
            accept_downloads=True,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = await context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # Navigate to Coordinador
            print("Step 3: Navigating to Coordinador...", flush=True)
            await page.goto("https://www.coordinador.cl/costos-marginales/", 
                          wait_until="domcontentloaded", timeout=20000)
            print("   ✓ Page loaded", flush=True)
            
            # Wait for page to stabilize
            await asyncio.sleep(3)
            
            # Click CMG en Línea tab
            print("Step 4: Clicking CMG en Línea tab...", flush=True)
            tab_link = page.locator('a[href="#Costo-Marginal-en-L--nea"]')
            count = await tab_link.count()
            
            if count == 0:
                print("   ⚠️ Tab not found, trying direct navigation...", flush=True)
                await page.goto("https://www.coordinador.cl/costos-marginales/#Costo-Marginal-en-L--nea",
                              wait_until="domcontentloaded", timeout=20000)
            else:
                await tab_link.first.click()
                print("   ✓ Tab clicked", flush=True)
            
            # Wait for iframe to load
            print("Step 5: Waiting for iframe to load...", flush=True)
            await asyncio.sleep(5)
            
            # Access iframe
            print("Step 6: Accessing PowerBI iframe...", flush=True)
            # Try the confirmed working approach
            frame = page.frame_locator("#Costo-Marginal-en-L--nea iframe").nth(1)
            
            # Verify iframe is accessible
            try:
                div_count = await frame.locator("div").count()
                print(f"   ✓ Iframe accessed ({div_count} divs found)", flush=True)
            except:
                # Fallback to generic iframe
                print("   Trying fallback iframe selector...", flush=True)
                frame = page.frame_locator("iframe").nth(1)
            
            # Trigger download
            print("Step 7: Triggering download...", flush=True)
            download_btn = frame.get_by_title("Descargar")
            btn_count = await download_btn.count()
            print(f"   Found {btn_count} download button(s)", flush=True)
            
            if btn_count == 0:
                print("   ❌ No download button found", flush=True)
                await browser.close()
                return None
            
            download = None
            async with page.expect_download(timeout=15000) as dl_info:
                await download_btn.first.click()
                print("   ⏳ Waiting for download...", flush=True)
            download = await dl_info.value
            print("   ✓ Download triggered!", flush=True)
            
            # Save file
            print("Step 8: Saving file...", flush=True)
            timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
            save_path = downloads_dir / f"cmg_en_linea_{timestamp}.csv"
            await download.save_as(str(save_path))
            print(f"   ✓ Saved to: {save_path}", flush=True)
            
            # Check file size
            file_size = save_path.stat().st_size
            print(f"   File size: {file_size:,} bytes", flush=True)
            
            await browser.close()
            return save_path
            
        except Exception as e:
            print(f"❌ Error: {e}", flush=True)
            
            # Try to capture screenshot for debugging
            try:
                screenshot_path = downloads_dir / f"error_{datetime.now(santiago_tz).strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=str(screenshot_path))
                print(f"   📸 Screenshot saved: {screenshot_path}", flush=True)
            except:
                pass
            
            await browser.close()
            return None

async def main():
    """Main function for testing"""
    print("="*60, flush=True)
    print("CMG EN LÍNEA DOWNLOADER", flush=True)
    print("="*60, flush=True)
    print(f"Timestamp: {datetime.now(santiago_tz)}", flush=True)
    print(f"Headless mode: {HEADLESS}", flush=True)
    print("", flush=True)
    
    result = await run()
    
    if result:
        print(f"\n✅ SUCCESS! Downloaded: {result}", flush=True)
        return 0
    else:
        print("\n❌ FAILED to download CSV", flush=True)
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)