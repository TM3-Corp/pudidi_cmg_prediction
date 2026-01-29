#!/usr/bin/env python3
"""
Simple CMG Programado downloader - Direct approach
Uses the direct URL: https://www.coordinador.cl/operacion/graficos/operacion-programada/costo-marginal-programado/
"""
from pathlib import Path
from datetime import datetime
import asyncio
import pytz
from playwright.async_api import async_playwright
import time
import os

# Configuration
HEADLESS = os.environ.get('GITHUB_ACTIONS', 'false').lower() == 'true'  # Auto-detect GitHub Actions
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)
santiago_tz = pytz.timezone('America/Santiago')

async def close_popups(page):
    """Try to close any popups/surveys"""
    try:
        # Try to find and close survey popups
        close_selectors = [
            "button.close",
            "[aria-label='close']",
            "[aria-label='cerrar']", 
            "button:has-text('X')",
            "button:has-text('×')",
            ".modal-close",
            ".survey-close"
        ]
        
        for selector in close_selectors:
            try:
                elements = await page.locator(selector).all()
                for element in elements:
                    if await element.is_visible():
                        await element.click()
                        print(f"   ✓ Closed popup using: {selector}", flush=True)
                        await asyncio.sleep(1)
            except:
                pass
                
        # Also try ESC key
        await page.keyboard.press("Escape")
        
    except Exception as e:
        pass

async def run():
    """Download CMG Programado CSV"""
    
    async with async_playwright() as p:
        print("Step 1: Launching browser...", flush=True)
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        print("Step 2: Creating context...", flush=True)
        context = await browser.new_context(
            accept_downloads=True,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = await context.new_page()
        page.set_default_timeout(30000)
        
        # Try up to 10 times
        MAX_ATTEMPTS = 10
        for attempt in range(MAX_ATTEMPTS):
            try:
                print(f"\n{'='*40}", flush=True)
                print(f"ATTEMPT {attempt + 1} OF {MAX_ATTEMPTS}", flush=True)
                print(f"{'='*40}", flush=True)
                
                # Navigate directly to CMG Programado page
                url = "https://www.coordinador.cl/operacion/graficos/operacion-programada/costo-marginal-programado/"
                print(f"Step 3: Navigating to CMG Programado page...", flush=True)
                print(f"   URL: {url}", flush=True)
                
                # Use domcontentloaded instead of networkidle to avoid timeout
                # The page has continuous network activity that never settles
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                print("   ✓ Initial page loaded, waiting for QlikView...", flush=True)
                
                # Wait for QlikView to load 
                print("   ⏳ Waiting for QlikView to load (30 seconds)...", flush=True)
                for i in range(3):
                    await asyncio.sleep(10)
                    print(f"      {(i+1)*10} seconds...", flush=True)
                
                # Additional wait to ensure everything is rendered
                await asyncio.sleep(2)
                
                # Try to close any popups
                print("Step 4: Checking for popups...", flush=True)
                await close_popups(page)
                await asyncio.sleep(2)
                
                # Access the iframe with QlikView dashboard
                print("Step 5: Accessing QlikView iframe...", flush=True)
                iframe_selector = 'iframe#grafico_2'
                iframe_element = await page.query_selector(iframe_selector)
                
                if not iframe_element:
                    # Try alternative selector
                    iframe_selector = 'iframe[src*="mashup_Plataforma_Programacion_App_Costo_Marginal_Programado_PCP"]'
                    iframe_element = await page.query_selector(iframe_selector)
                
                if not iframe_element:
                    # Take screenshot for debugging
                    screenshot_path = downloads_dir / f"debug_no_iframe_{attempt}_{datetime.now().strftime('%H%M%S')}.png"
                    await page.screenshot(path=str(screenshot_path))
                    print(f"   📸 Debug screenshot: {screenshot_path}", flush=True)
                    raise Exception("Could not find QlikView iframe")
                
                frame = await iframe_element.content_frame()
                if not frame:
                    raise Exception("Could not access iframe content")
                
                print("   ✅ Accessed iframe content", flush=True)
                
                # Find download button in iframe
                print("Step 6: Looking for download button in iframe...", flush=True)
                download_btn = frame.locator('#buttonQV100').first
                
                if await download_btn.count() == 0:
                    # Take screenshot for debugging
                    screenshot_path = downloads_dir / f"debug_no_button_{attempt}_{datetime.now().strftime('%H%M%S')}.png"
                    await page.screenshot(path=str(screenshot_path))
                    print(f"   📸 Debug screenshot: {screenshot_path}", flush=True)
                    raise Exception("Download button not found in iframe")
                
                print("   ✅ Found download button!", flush=True)
                
                # Click with force=True to ignore overlapping elements
                print("Step 7: Clicking download button...", flush=True)
                async with page.expect_download(timeout=30000) as download_info:
                    await download_btn.click(force=True)
                    print("   ⏳ Waiting for download...", flush=True)
                    download = await download_info.value
                
                print("   ✓ Download started!", flush=True)
                
                # Save the file
                print("Step 8: Saving file...", flush=True)
                timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
                save_path = downloads_dir / f"cmg_programado_{timestamp}.csv"
                await download.save_as(str(save_path))
                
                # Check file size
                file_size = save_path.stat().st_size
                print(f"   ✓ Saved to: {save_path}", flush=True)
                print(f"   File size: {file_size:,} bytes", flush=True)
                
                if file_size < 100:
                    raise Exception(f"Downloaded file too small: {file_size} bytes")
                
                await browser.close()
                return save_path
                
            except Exception as e:
                print(f"\n❌ Attempt {attempt + 1} failed: {e}", flush=True)
                
                if attempt < MAX_ATTEMPTS - 1:
                    # Close browser and start fresh for next attempt
                    print(f"   Closing browser and starting fresh...", flush=True)
                    await browser.close()
                    
                    # Progressive delay
                    delay = min(5 + (attempt * 2), 20)
                    print(f"   Waiting {delay} seconds before retry...", flush=True)
                    await asyncio.sleep(delay)
                    
                    # Launch new browser for next attempt
                    browser = await p.chromium.launch(
                        headless=HEADLESS,
                        args=['--disable-blink-features=AutomationControlled']
                    )
                    context = await browser.new_context(
                        accept_downloads=True,
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        viewport={'width': 1920, 'height': 1080}
                    )
                    page = await context.new_page()
                    page.set_default_timeout(30000)
                else:
                    # Last attempt failed
                    try:
                        screenshot_path = downloads_dir / f"error_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        await page.screenshot(path=str(screenshot_path), full_page=True)
                        print(f"   📸 Final error screenshot: {screenshot_path}", flush=True)
                    except:
                        pass
        
        await browser.close()
        return None

async def main():
    """Main function for testing"""
    print("="*60, flush=True)
    print("CMG PROGRAMADO SIMPLE DOWNLOADER", flush=True)
    print("="*60, flush=True)
    print(f"Timestamp: {datetime.now(santiago_tz)}", flush=True)
    print(f"Target URL: https://www.coordinador.cl/operacion/graficos/operacion-programada/costo-marginal-programado/", flush=True)
    print(f"Headless mode: {HEADLESS}", flush=True)
    print("", flush=True)
    
    result = await run()
    
    if result:
        print(f"\n✅ SUCCESS! Downloaded: {result}", flush=True)
        
        # Show first few lines of the CSV
        try:
            with open(result, 'r', encoding='utf-8') as f:
                lines = f.readlines()[:5]
                print("\nFirst 5 lines of CSV:")
                for i, line in enumerate(lines):
                    print(f"  {i+1}: {line.strip()}")
        except:
            pass
            
        return 0
    else:
        print(f"\n❌ FAILED to download CSV after all attempts", flush=True)
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)