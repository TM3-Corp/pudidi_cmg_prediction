#!/usr/bin/env python3
"""
Debug version of CMG Programado scraper with verbose logging
Based on the working partner's code but with added debugging
Run locally to identify issues
"""

from pathlib import Path
from datetime import datetime
import asyncio
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import os
import sys

# === CONFIG ===
HEADLESS = False  # Show browser for debugging (like partner's code)
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

# GitHub configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GIST_ID = "a63a3a10479bafcc29e10aaca627bc73"  # We'll create our own later

# Fixed filename (like partner's code)
FIXED_NAME = "costo_marginal_programado.csv"

def log_step(step_num, message):
    """Print timestamped debug message"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] STEP {step_num}: {message}")

async def run_debug():
    """Debug version with extensive logging"""
    
    log_step(0, "Starting CMG Programado scraper (DEBUG MODE)")
    log_step(0.1, f"Browser mode: {'HEADLESS' if HEADLESS else 'VISIBLE'}")
    log_step(0.2, f"Downloads directory: {downloads_dir.resolve()}")
    
    async with async_playwright() as p:
        try:
            # 1. Launch browser
            log_step(1, "Launching Chromium browser...")
            browser = await p.chromium.launch(
                headless=HEADLESS,
                args=['--disable-blink-features=AutomationControlled']
            )
            log_step(1.1, "✓ Browser launched successfully")
            
            # 2. Create context
            log_step(2, "Creating browser context with download permissions...")
            context = await browser.new_context(
                accept_downloads=True,
                viewport={'width': 1920, 'height': 1080}
            )
            log_step(2.1, "✓ Context created")
            
            # 3. Create page
            log_step(3, "Creating new page...")
            page = await context.new_page()
            page.set_default_timeout(180_000)  # 3 minutes default
            log_step(3.1, f"✓ Page created with 3-minute timeout")
            
            # 4. Navigate to main page
            log_step(4, "Navigating to Coordinador website...")
            log_step(4.1, "URL: https://www.coordinador.cl/costos-marginales/")
            
            try:
                await page.goto(
                    "https://www.coordinador.cl/costos-marginales/", 
                    wait_until="load",
                    timeout=60000  # 1 minute for initial load
                )
                log_step(4.2, "✓ Main page loaded")
            except Exception as e:
                log_step(4.3, f"✗ Failed to load main page: {e}")
                raise
            
            # 5. Wait for page to stabilize
            log_step(5, "Waiting for page to stabilize (3 seconds)...")
            await page.wait_for_timeout(3000)
            log_step(5.1, "✓ Page stabilized")
            
            # 6. Look for and click the link
            log_step(6, "Looking for 'Costo Marginal Programado' link...")
            try:
                link = page.get_by_role("link", name="Costo Marginal Programado")
                await link.wait_for(state="visible", timeout=10000)
                log_step(6.1, "✓ Link found and visible")
                
                log_step(6.2, "Clicking the link...")
                await link.click()
                log_step(6.3, "✓ Link clicked")
            except Exception as e:
                log_step(6.4, f"✗ Failed to find/click link: {e}")
                # Take screenshot for debugging
                await page.screenshot(path="debug_screenshot_1.png")
                log_step(6.5, "Screenshot saved as debug_screenshot_1.png")
                raise
            
            # 7. Wait for iframe to load
            log_step(7, "Waiting for PowerBI iframe to load (5 seconds)...")
            await page.wait_for_timeout(5000)
            log_step(7.1, "✓ Wait completed")
            
            # 8. Locate the iframe
            log_step(8, "Locating PowerBI iframe...")
            try:
                # Try to find iframes on the page
                iframes = page.frames
                log_step(8.1, f"Found {len(iframes)} frames total")
                
                # Look for the specific iframe locator
                frame_locator = page.frame_locator("#Costo-Marginal-Programado iframe")
                log_step(8.2, "Looking for #Costo-Marginal-Programado iframe")
                
                # Try to access the second iframe (nth(1))
                frame = frame_locator.nth(1)
                log_step(8.3, "✓ Target iframe locator created")
            except Exception as e:
                log_step(8.4, f"✗ Failed to locate iframe: {e}")
                await page.screenshot(path="debug_screenshot_2.png")
                log_step(8.5, "Screenshot saved as debug_screenshot_2.png")
                raise
            
            # 9. Trigger download
            log_step(9, "Attempting to trigger download...")
            log_step(9.1, "Setting up download handler...")
            
            try:
                # Set up download expectation
                async with page.expect_download(timeout=120000) as dl_info:
                    log_step(9.2, "Download handler ready")
                    log_step(9.3, "Looking for 'Descargar' button in iframe...")
                    
                    # Click the download button
                    download_button = frame.get_by_title("Descargar")
                    log_step(9.4, "Clicking download button...")
                    await download_button.click()
                    log_step(9.5, "✓ Download button clicked")
                
                # Wait for download to complete
                log_step(9.6, "Waiting for download to complete...")
                download = await dl_info.value
                log_step(9.7, "✓ Download completed")
                
            except PlaywrightTimeoutError:
                log_step(9.8, "✗ Download timed out after 2 minutes")
                await page.screenshot(path="debug_screenshot_3.png")
                log_step(9.9, "Screenshot saved as debug_screenshot_3.png")
                await browser.close()
                return None
            except Exception as e:
                log_step(9.10, f"✗ Download failed: {e}")
                await page.screenshot(path="debug_screenshot_3.png")
                log_step(9.11, "Screenshot saved as debug_screenshot_3.png")
                await browser.close()
                return None
            
            # 10. Save the file
            log_step(10, "Saving downloaded file...")
            save_path = downloads_dir / FIXED_NAME
            await download.save_as(str(save_path))
            log_step(10.1, f"✓ File saved to: {save_path.resolve()}")
            
            # 11. Verify file
            log_step(11, "Verifying downloaded file...")
            if save_path.exists():
                file_size = save_path.stat().st_size
                log_step(11.1, f"✓ File exists, size: {file_size:,} bytes")
                
                # Read first few lines
                with open(save_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[:5]
                    log_step(11.2, f"First line: {lines[0].strip() if lines else 'Empty'}")
                    log_step(11.3, f"Total lines in file: {len(f.readlines()) + 5}")
            else:
                log_step(11.4, "✗ File not found after save!")
            
            # 12. Close browser
            log_step(12, "Closing browser...")
            await browser.close()
            log_step(12.1, "✓ Browser closed")
            
            return save_path
            
        except Exception as e:
            log_step(99, f"✗ FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                await browser.close()
            except:
                pass
            
            return None

async def main():
    """Main execution"""
    print("="*60)
    print("CMG PROGRAMADO SCRAPER - DEBUG MODE")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print("="*60)
    print()
    
    # Run the debug scraper
    result = await run_debug()
    
    print()
    print("="*60)
    if result:
        print(f"✅ SUCCESS! File downloaded to: {result}")
        print()
        print("Next steps:")
        print("1. Check the CSV file in the downloads folder")
        print("2. Verify it contains the expected data")
        print("3. Run the history merger to preserve old data")
    else:
        print("✗ FAILED to download CMG Programado data")
        print()
        print("Debugging tips:")
        print("1. Check screenshot files if created")
        print("2. Try with HEADLESS=False to see browser")
        print("3. Increase timeouts if needed")
        print("4. Check if website structure changed")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())