#!/usr/bin/env python3
"""
CMG en Línea download with survey removal via DOM manipulation
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

async def remove_surveys(page):
    """Remove survey popups from DOM entirely"""
    try:
        # Check if survey exists
        survey_count = await page.locator("iframe[src*='survey'], iframe[src*='e-survey']").count()
        
        if survey_count > 0:
            print(f"   📋 Found {survey_count} survey(s), removing from DOM...", flush=True)
            
            # Remove via JavaScript
            removed = await page.evaluate("""
                () => {
                    let removed = 0;
                    
                    // Remove all survey iframes
                    const surveyIframes = document.querySelectorAll('iframe[src*="survey"], iframe[src*="e-survey"]');
                    surveyIframes.forEach(iframe => {
                        iframe.remove();
                        removed++;
                    });
                    
                    // Remove survey containers
                    const surveyContainers = document.querySelectorAll('[class*="survey"], [id*="survey"]');
                    surveyContainers.forEach(container => {
                        // Only remove if it looks like a modal/popup
                        if (container.querySelector('iframe') || 
                            container.style.position === 'fixed' || 
                            container.style.position === 'absolute' ||
                            container.classList.contains('modal')) {
                            container.remove();
                            removed++;
                        }
                    });
                    
                    return removed;
                }
            """)
            
            # Also inject CSS to hide any remaining survey elements
            await page.add_style_tag(content="""
                iframe[src*="survey"],
                iframe[src*="e-survey"],
                [class*="survey-modal"],
                [id*="survey-container"],
                .survey-popup {
                    display: none !important;
                    visibility: hidden !important;
                    pointer-events: none !important;
                }
            """)
            
            print(f"   ✓ Removed {removed} survey element(s) from DOM", flush=True)
            return True
        else:
            print("   No surveys detected", flush=True)
            return False
    except Exception as e:
        print(f"   ⚠️ Error removing surveys: {str(e)[:100]}", flush=True)
        return False

async def run():
    """Download CMG en Línea CSV with survey removal"""
    
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
        
        # Block survey domain at context level
        await context.route("**/*e-survey.cl/**", lambda route: route.abort())
        
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
                
                # Wait for page to stabilize
                await asyncio.sleep(3)
                
                # Remove any surveys
                print("Step 3.5: Checking for surveys...", flush=True)
                await remove_surveys(page)
                await asyncio.sleep(1)
                
                # Click CMG en Línea tab
                print("Step 4: Clicking CMG en Línea tab...", flush=True)
                tab_link = page.locator('a[href="#Costo-Marginal-en-L--nea"]')
                tab_count = await tab_link.count()
                
                if tab_count == 0:
                    print("   ⚠️ Tab not found, removing surveys again...", flush=True)
                    await remove_surveys(page)
                    await asyncio.sleep(2)
                    
                    # Try again
                    tab_count = await tab_link.count()
                    
                    if tab_count == 0:
                        # Try alternative selectors
                        alt_selectors = [
                            'a:has-text("Costo Marginal en Línea")',
                            'text="Costo Marginal en Línea"'
                        ]
                        
                        for selector in alt_selectors:
                            alt_link = page.locator(selector)
                            if await alt_link.count() > 0:
                                await alt_link.first.click()
                                print(f"   ✓ Tab clicked using: {selector}", flush=True)
                                tab_count = 1
                                break
                        
                        if tab_count == 0:
                            print("   ⚠️ Navigating directly to tab URL...", flush=True)
                            await page.goto("https://www.coordinador.cl/costos-marginales/#Costo-Marginal-en-L--nea",
                                          wait_until="domcontentloaded", timeout=20000)
                else:
                    await tab_link.first.click()
                    print("   ✓ Tab clicked", flush=True)
                
                # Wait for iframe to load
                print("Step 5: Waiting for iframe to load...", flush=True)
                await asyncio.sleep(5)
                
                # Remove surveys again if they reappeared
                await remove_surveys(page)
                
                # Access iframe
                print("Step 6: Accessing PowerBI iframe...", flush=True)
                
                # Try multiple iframe selection methods
                frame = None
                iframe_methods = [
                    ("Tab-specific iframe", lambda: page.frame_locator("#Costo-Marginal-en-L--nea iframe").nth(1)),
                    ("Second iframe on page", lambda: page.frame_locator("iframe").nth(1)),
                    ("PowerBI by QAP", lambda: page.frame_locator("iframe[src*='qap-prd']").first),
                    ("Any coordinador iframe", lambda: page.frame_locator("iframe[src*='coordinador']").first)
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
                    # Try alternative selectors
                    alt_download = [
                        frame.locator("[title*='escargar']"),
                        frame.locator("[aria-label*='escargar']"),
                        frame.locator("[title='Download']"),
                        frame.locator("[title='Export']")
                    ]
                    
                    for alt_btn in alt_download:
                        if await alt_btn.count() > 0:
                            download_btn = alt_btn
                            btn_count = await alt_btn.count()
                            print(f"   Found {btn_count} alternative download button(s)", flush=True)
                            break
                
                if btn_count == 0:
                    raise Exception("No download button found")
                
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
                    except:
                        pass
        
        await browser.close()
        return None

async def main():
    """Main function for testing"""
    print("="*60, flush=True)
    print("CMG EN LÍNEA DOWNLOADER - SURVEY REMOVAL VERSION", flush=True)
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