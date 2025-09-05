#!/usr/bin/env python3
"""
Simple CMG Programado scraper - just download the CSV
Based exactly on partner's working code
"""

from pathlib import Path
from datetime import datetime
import asyncio
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import os

# === CONFIG ===
# Use headless mode in GitHub Actions, visible mode locally
HEADLESS = os.environ.get('GITHUB_ACTIONS', 'false').lower() == 'true'
date_suffix = datetime.now().strftime("-%m-%d")
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

# Fixed filename (always overwrite this one)
FIXED_NAME = "costo_marginal_programado.csv"

async def run():
    async with async_playwright() as p:
        print(f"Launching browser (headless={HEADLESS})...")
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(300_000)  # Increase to 5 minutes

        # 1) Navigate
        print("Navigating to Coordinador website...")
        try:
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Warning: Initial navigation had issues: {e}")
            print("Continuing anyway...")
        print("Page loaded, waiting for content...")
        await page.wait_for_timeout(5000)
        
        print("Clicking on Costo Marginal Programado...")
        await page.get_by_role("link", name="Costo Marginal Programado").click()
        print("Link clicked, waiting for navigation...")

        # 2) Target PowerBI iframe
        print("Waiting for PowerBI iframe to load (10 seconds)...")
        await page.wait_for_timeout(10000)  # Increase wait for slow PowerBI
        frame = page.frame_locator("#Costo-Marginal-Programado iframe").nth(1)

        # 3) Trigger download
        print("Looking for download button...")
        try:
            download_button = frame.get_by_title("Descargar")
            await download_button.wait_for(state="visible", timeout=30000)
            print("Download button found, clicking...")
            
            async with page.expect_download(timeout=60000) as dl_info:
                await download_button.click()
            download = await dl_info.value
            print("Download completed!")
        except PlaywrightTimeoutError as e:
            print(f"Download failed: {e}")
            await browser.close()
            return None
        except Exception as e:
            print(f"Unexpected error during download: {e}")
            await browser.close()
            return None

        # 4) Save with fixed name (overwrite every time)
        save_path = downloads_dir / FIXED_NAME
        await download.save_as(str(save_path))
        print(f"Saved file to: {save_path.resolve()}")

        await browser.close()
        return save_path

async def main():
    """Main execution"""
    print("="*60)
    print(f"CMG PROGRAMADO SIMPLE SCRAPER")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    result = await run()
    
    if result and result.exists():
        print(f"\n✅ SUCCESS! CSV downloaded to: {result}")
        
        # Show file info
        file_size = result.stat().st_size
        print(f"File size: {file_size:,} bytes")
        
        # Show first few lines
        with open(result, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"Total lines: {len(lines)}")
            print("\nFirst 3 lines:")
            for line in lines[:3]:
                print(f"  {line.strip()}")
    else:
        print("\n✗ Failed to download CSV")
    
    print("="*60)
    return result

if __name__ == "__main__":
    asyncio.run(main())