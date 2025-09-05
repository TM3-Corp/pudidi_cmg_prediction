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
HEADLESS = False  # Visible browser like partner's code
date_suffix = datetime.now().strftime("-%m-%d")
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

# Fixed filename (always overwrite this one)
FIXED_NAME = "costo_marginal_programado.csv"

async def run():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(180_000)

        # 1) Navigate
        print("Navigating to Coordinador website...")
        await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="load")
        
        print("Clicking on Costo Marginal Programado...")
        await page.get_by_role("link", name="Costo Marginal Programado").click()

        # 2) Target PowerBI iframe
        print("Waiting for iframe...")
        await page.wait_for_timeout(5000)  # Give it time to load
        frame = page.frame_locator("#Costo-Marginal-Programado iframe").nth(1)

        # 3) Trigger download
        print("Triggering download...")
        try:
            async with page.expect_download() as dl_info:
                await frame.get_by_title("Descargar").click()
            download = await dl_info.value
            print("Download completed!")
        except PlaywrightTimeoutError:
            print("Download failed or timed out")
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