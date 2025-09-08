#!/usr/bin/env python3
"""
Download CMG Online (en Línea) - Using correct tab name
Based on partner's working approach for CMG Programado
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
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(180_000)  # 3 minutes like partner

        try:
            # 1) Navigate
            print("Step 1: Navigating to page...")
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="load")
            print("   ✓ Page loaded")
            
            # 2) Click on "Costo Marginal en Línea" (the CORRECT name!)
            print("Step 2: Looking for 'Costo Marginal en Línea' tab...")
            await page.get_by_role("link", name="Costo Marginal en Línea").click()
            print("   ✓ Tab clicked")

            # 3) Wait for iframe to load
            print("Step 3: Waiting for iframe to load...")
            await asyncio.sleep(5)
        
        # Target PowerBI iframe - the section ID might be different
        # Try different possible IDs
        frame = None
        possible_ids = [
            "#Costo-Marginal-en-Linea iframe",
            "#Costo-Marginal-en-Línea iframe",  # With accent
            "#CMG-en-Linea iframe",
            "#cmg-online iframe",
            "iframe"  # Just try any iframe
        ]
        
        for frame_id in possible_ids:
            try:
                frame = page.frame_locator(frame_id).nth(1)
                # Test if we can access it
                await frame.locator("*").first.wait_for(timeout=2000)
                print(f"Found iframe with: {frame_id}")
                break
            except:
                continue
        
        if not frame:
            # Fallback: just use any iframe that looks like PowerBI
            frame = page.frame_locator("iframe").nth(1)

        # 4) Trigger download
        try:
            async with page.expect_download() as dl_info:
                await frame.get_by_title("Descargar").click()
            download = await dl_info.value
        except PlaywrightTimeoutError:
            print("Download failed or timed out")
            await browser.close()
            return None

        # 5) Save file
        timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
        save_path = downloads_dir / f"cmg_online_{timestamp}.csv"
        await download.save_as(str(save_path))
        print(f"Saved file to: {save_path.resolve()}")

        await browser.close()
        return save_path

async def main():
    print("="*60)
    print("CMG EN LÍNEA DOWNLOADER")
    print("="*60)
    print(f"Timestamp: {datetime.now(santiago_tz)}")
    print()
    
    print("🚀 Starting download...")
    print("📍 Navigating to Coordinador...")
    print("🔍 Clicking on 'Costo Marginal en Línea'...")
    print("⏳ Waiting for PowerBI iframe...")
    print("⬇️ Downloading CSV...")
    
    result = await run()
    
    if result:
        print(f"\n✅ Success! Downloaded: {result}")
        
        # Quick check of the file
        try:
            import csv
            with open(result, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                print(f"   Rows: {len(rows)}")
                if rows:
                    print(f"   Columns: {list(rows[0].keys())}")
                    # Show first few rows
                    print("   Sample data:")
                    for i, row in enumerate(rows[:3]):
                        print(f"     {row}")
        except Exception as e:
            print(f"   Could not read CSV: {e}")
    else:
        print("\n❌ Download failed")
    
    return 0 if result else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)