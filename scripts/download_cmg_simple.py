#!/usr/bin/env python3
"""
Simple working CMG download script based on our successful test
"""
from pathlib import Path
from datetime import datetime
import asyncio
import pytz
from playwright.async_api import async_playwright

# Configuration
HEADLESS = True
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)
santiago_tz = pytz.timezone('America/Santiago')

async def download_cmg_csv():
    """Download CMG en Línea CSV from Coordinador"""
    
    async with async_playwright() as p:
        print("🚀 Launching browser...", flush=True)
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            accept_downloads=True,
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = await context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # Navigate to Coordinador
            print("📍 Navigating to Coordinador...", flush=True)
            await page.goto("https://www.coordinador.cl/costos-marginales/", 
                          wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            
            # Click CMG en Línea tab
            print("🔍 Clicking CMG en Línea tab...", flush=True)
            tab_link = page.locator('a[href="#Costo-Marginal-en-L--nea"]')
            await tab_link.first.click()
            await asyncio.sleep(5)
            
            # Access iframe
            print("🎯 Accessing PowerBI iframe...", flush=True)
            frame = page.frame_locator("#Costo-Marginal-en-L--nea iframe").nth(1)
            
            # Trigger download
            print("⬇️ Downloading CSV...", flush=True)
            download_btn = frame.get_by_title("Descargar")
            
            async with page.expect_download(timeout=15000) as dl_info:
                await download_btn.first.click()
            download = await dl_info.value
            
            # Save file
            timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
            save_path = downloads_dir / f"cmg_en_linea_{timestamp}.csv"
            await download.save_as(str(save_path))
            
            print(f"✅ Downloaded: {save_path}", flush=True)
            await browser.close()
            return save_path
            
        except Exception as e:
            print(f"❌ Download failed: {e}", flush=True)
            await browser.close()
            return None

async def main():
    """Main function"""
    print("="*60, flush=True)
    print("CMG EN LÍNEA SIMPLE DOWNLOADER", flush=True)
    print("="*60, flush=True)
    print(f"Time: {datetime.now(santiago_tz)}", flush=True)
    print("", flush=True)
    
    csv_path = await download_cmg_csv()
    
    if csv_path:
        # Check file
        size = csv_path.stat().st_size
        print(f"\n📊 File size: {size:,} bytes", flush=True)
        
        # Read first few lines
        with open(csv_path, 'r') as f:
            lines = f.readlines()
            print(f"📊 Total lines: {len(lines)}", flush=True)
            
        return 0
    else:
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)