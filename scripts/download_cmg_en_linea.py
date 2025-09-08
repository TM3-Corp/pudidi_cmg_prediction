#!/usr/bin/env python3
"""
Download CMG en Línea - Exact copy of partner's approach but for CMG en Línea
"""

from pathlib import Path
from datetime import datetime
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import pytz

# === CONFIG ===
HEADLESS = False  # Set False for debugging
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)
santiago_tz = pytz.timezone('America/Santiago')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(30_000)  # 30 seconds for testing

        try:
            # 1) Navigate
            print("Navigating to Coordinador...")
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="load")
            print("✓ Page loaded")
            
            # 2) Click on "Costo Marginal en Línea" instead of "Costo Marginal Programado"
            print("Clicking on 'Costo Marginal en Línea'...")
            await page.get_by_role("link", name="Costo Marginal en Línea").click()
            print("✓ Tab clicked")
        except Exception as e:
            print(f"Error in navigation: {e}")
            await browser.close()
            return None

        # 3) Wait a bit for iframe to load
        await asyncio.sleep(5)
        
        # 4) Target PowerBI iframe - try different selectors
        print("Looking for iframe...")
        frame = None
        
        # Try the exact pattern as partner but with different section IDs
        try:
            # Try with the section ID (might be #Costo-Marginal-en-Linea)
            frame = page.frame_locator("#Costo-Marginal-en-Linea iframe").nth(1)
            await frame.locator("*").first.wait_for(timeout=2000)
            print("Found iframe with #Costo-Marginal-en-Linea")
        except:
            try:
                # Try with accent
                frame = page.frame_locator("#Costo-Marginal-en-Línea iframe").nth(1)
                await frame.locator("*").first.wait_for(timeout=2000)
                print("Found iframe with #Costo-Marginal-en-Línea (with accent)")
            except:
                try:
                    # Just try any iframe as fallback
                    frame = page.frame_locator("iframe").nth(1)
                    print("Using generic iframe selector")
                except:
                    print("Could not find iframe")
                    await browser.close()
                    return None

        # 5) Trigger download
        print("Attempting download...")
        try:
            async with page.expect_download() as dl_info:
                await frame.get_by_title("Descargar").click()
            download = await dl_info.value
            print("Download triggered!")
        except PlaywrightTimeoutError:
            print("Download failed - timeout")
            await browser.close()
            return None
        except Exception as e:
            print(f"Download failed: {e}")
            await browser.close()
            return None

        # 6) Save file
        timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
        save_path = downloads_dir / f"cmg_en_linea_{timestamp}.csv"
        await download.save_as(str(save_path))
        print(f"Saved file to: {save_path.resolve()}")

        await browser.close()
        return save_path

if __name__ == "__main__":
    print("="*60)
    print("CMG EN LÍNEA DOWNLOADER")
    print("="*60)
    print(f"Starting at: {datetime.now(santiago_tz)}")
    print()
    
    result = asyncio.run(run())
    
    if result:
        print(f"\n✅ SUCCESS! File: {result}")
    else:
        print("\n❌ FAILED to download")
    
    exit(0 if result else 1)