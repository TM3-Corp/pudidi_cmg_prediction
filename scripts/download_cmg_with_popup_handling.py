#!/usr/bin/env python3
"""
Robust CMG en Línea download with popup/survey detection and handling
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

async def dismiss_popups(page):
    """Check for and dismiss any popups or surveys"""
    dismissed = False
    
    # Common popup selectors
    popup_selectors = [
        # Survey popups
        "iframe[src*='survey']",
        "iframe[src*='e-survey']",
        "div[class*='survey']",
        "div[id*='survey']",
        
        # Cookie/privacy popups
        "button:has-text('Aceptar')",
        "button:has-text('Acepto')",
        "button:has-text('Accept')",
        
        # Close buttons
        "button[aria-label*='close']",
        "button[aria-label*='cerrar']",
        "button.close",
        "a.close",
        "[class*='close-button']",
        "[class*='modal-close']"
    ]
    
    for selector in popup_selectors:
        try:
            count = await page.locator(selector).count()
            if count > 0:
                print(f"   📋 Found popup/survey: {selector}", flush=True)
                
                # For iframes, try to close parent container
                if "iframe" in selector:
                    # Look for close button in parent
                    parent_close = page.locator(f"{selector} ~ button, {selector} ~ a.close")
                    if await parent_close.count() > 0:
                        await parent_close.first.click()
                        print(f"   ✓ Closed popup container", flush=True)
                        dismissed = True
                    # Also try clicking outside
                    await page.mouse.click(10, 10)  # Click in corner
                else:
                    # Try to click the element
                    await page.locator(selector).first.click(timeout=2000)
                    print(f"   ✓ Dismissed popup", flush=True)
                    dismissed = True
                    
                await asyncio.sleep(1)
        except:
            continue
    
    # Check for survey iframe specifically (your observation)
    try:
        survey_frame = page.frame_locator("iframe[src*='e-survey']")
        if await survey_frame.locator("body").count() > 0:
            print("   📋 Survey detected in iframe", flush=True)
            # Try pressing Escape
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
            # Click outside
            await page.mouse.click(10, 10)
            dismissed = True
    except:
        pass
    
    return dismissed

async def run():
    """Download CMG en Línea CSV with popup handling"""
    
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
        
        # Try up to 3 times
        for attempt in range(3):
            try:
                print(f"\n{'='*40}", flush=True)
                print(f"ATTEMPT {attempt + 1} OF 3", flush=True)
                print(f"{'='*40}", flush=True)
                
                # Navigate to Coordinador
                print("Step 3: Navigating to Coordinador...", flush=True)
                await page.goto("https://www.coordinador.cl/costos-marginales/", 
                              wait_until="domcontentloaded", timeout=20000)
                print("   ✓ Page loaded", flush=True)
                
                # Wait and check for popups
                await asyncio.sleep(3)
                
                # Dismiss any popups
                print("Step 3.5: Checking for popups/surveys...", flush=True)
                if await dismiss_popups(page):
                    print("   ✓ Popups dismissed", flush=True)
                    await asyncio.sleep(2)
                else:
                    print("   No popups detected", flush=True)
                
                # Click CMG en Línea tab
                print("Step 4: Clicking CMG en Línea tab...", flush=True)
                tab_link = page.locator('a[href="#Costo-Marginal-en-L--nea"]')
                tab_count = await tab_link.count()
                
                if tab_count == 0:
                    print("   ⚠️ Tab not found, checking for survey overlay...", flush=True)
                    
                    # Check if survey is blocking
                    await dismiss_popups(page)
                    await asyncio.sleep(2)
                    
                    # Try again
                    tab_count = await tab_link.count()
                    
                    if tab_count == 0:
                        print("   ⚠️ Tab still not found, trying alternative selectors...", flush=True)
                        
                        # Try alternative selectors
                        alt_selectors = [
                            'a:has-text("Costo Marginal en Línea")',
                            'text="Costo Marginal en Línea"'
                        ]
                        
                        for selector in alt_selectors:
                            alt_link = page.locator(selector)
                            alt_count = await alt_link.count()
                            if alt_count > 0:
                                await alt_link.first.click()
                                print(f"   ✓ Tab clicked using: {selector}", flush=True)
                                tab_count = 1
                                break
                        
                        if tab_count == 0:
                            print("   ⚠️ Tab still not found, navigating directly...", flush=True)
                            await page.goto("https://www.coordinador.cl/costos-marginales/#Costo-Marginal-en-L--nea",
                                          wait_until="domcontentloaded", timeout=20000)
                else:
                    await tab_link.first.click()
                    print("   ✓ Tab clicked", flush=True)
                
                # Wait for iframe to load
                print("Step 5: Waiting for iframe to load...", flush=True)
                await asyncio.sleep(5)
                
                # Check for popups again
                await dismiss_popups(page)
                await asyncio.sleep(2)
                
                # Access iframe
                print("Step 6: Accessing PowerBI iframe...", flush=True)
                
                # Try multiple iframe selection methods
                frame = None
                iframe_methods = [
                    ("Tab-specific iframe", lambda: page.frame_locator("#Costo-Marginal-en-L--nea iframe").nth(1)),
                    ("Second iframe on page", lambda: page.frame_locator("iframe").nth(1)),
                    ("Any PowerBI iframe", lambda: page.frame_locator("iframe[src*='coordinador']").first),
                    ("Iframe by QAP source", lambda: page.frame_locator("iframe[src*='qap-prd']").first)
                ]
                
                for method_name, get_frame in iframe_methods:
                    try:
                        print(f"   Trying: {method_name}...", flush=True)
                        test_frame = get_frame()
                        div_count = await test_frame.locator("div").count()
                        
                        if div_count > 0:
                            frame = test_frame
                            print(f"   ✓ Iframe accessed via {method_name} ({div_count} divs found)", flush=True)
                            break
                        else:
                            print(f"   Empty iframe with {method_name}", flush=True)
                    except Exception as e:
                        print(f"   Failed with {method_name}: {str(e)[:50]}", flush=True)
                        continue
                
                if not frame:
                    raise Exception("Could not access any iframe with content")
                
                # Verify iframe has content
                div_count = await frame.locator("div").count()
                if div_count == 0:
                    print(f"   ⚠️ Iframe is empty, waiting more...", flush=True)
                    await asyncio.sleep(5)
                    div_count = await frame.locator("div").count()
                    
                if div_count == 0:
                    raise Exception("Iframe remains empty after waiting")
                
                # Trigger download
                print("Step 7: Triggering download...", flush=True)
                download_btn = frame.get_by_title("Descargar")
                btn_count = await download_btn.count()
                print(f"   Found {btn_count} download button(s)", flush=True)
                
                if btn_count == 0:
                    # Try alternative download selectors
                    print("   Trying alternative download selectors...", flush=True)
                    alt_download = [
                        frame.locator("[title*='escargar']"),
                        frame.locator("[aria-label*='escargar']"),
                        frame.locator("button:has-text('Descargar')"),
                        frame.locator("[title='Download']"),
                        frame.locator("[title='Export']")
                    ]
                    
                    for alt_btn in alt_download:
                        alt_count = await alt_btn.count()
                        if alt_count > 0:
                            download_btn = alt_btn
                            btn_count = alt_count
                            print(f"   Found {btn_count} alternative download button(s)", flush=True)
                            break
                
                if btn_count == 0:
                    raise Exception("No download button found after trying alternatives")
                
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
                
                if file_size < 1000:
                    raise Exception(f"Downloaded file too small: {file_size} bytes")
                
                await browser.close()
                return save_path
                
            except Exception as e:
                print(f"\n❌ Attempt {attempt + 1} failed: {e}", flush=True)
                
                if attempt < 2:
                    print(f"   Retrying in 5 seconds...", flush=True)
                    await asyncio.sleep(5)
                    
                    # Reload page for next attempt
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=20000)
                    except:
                        pass
                else:
                    # Last attempt failed, capture screenshot
                    try:
                        screenshot_path = downloads_dir / f"error_{datetime.now(santiago_tz).strftime('%Y%m%d_%H%M%S')}.png"
                        await page.screenshot(path=str(screenshot_path), full_page=True)
                        print(f"   📸 Screenshot saved: {screenshot_path}", flush=True)
                        
                        # Also log all iframes on page
                        iframe_count = await page.locator("iframe").count()
                        print(f"   Debug: Page has {iframe_count} iframes:", flush=True)
                        for i in range(min(iframe_count, 5)):
                            src = await page.locator("iframe").nth(i).get_attribute("src") or "no src"
                            print(f"     Iframe {i}: {src[:100]}", flush=True)
                    except:
                        pass
        
        await browser.close()
        return None

async def main():
    """Main function for testing"""
    print("="*60, flush=True)
    print("CMG EN LÍNEA DOWNLOADER WITH POPUP HANDLING", flush=True)
    print("="*60, flush=True)
    print(f"Timestamp: {datetime.now(santiago_tz)}", flush=True)
    print(f"Headless mode: {HEADLESS}", flush=True)
    print("", flush=True)
    
    result = await run()
    
    if result:
        print(f"\n✅ SUCCESS! Downloaded: {result}", flush=True)
        return 0
    else:
        print("\n❌ FAILED to download CSV after 3 attempts", flush=True)
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)