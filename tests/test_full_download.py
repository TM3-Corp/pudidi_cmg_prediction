#!/usr/bin/env python3
"""
Test the full download process step by step
"""
import asyncio
from pathlib import Path
from datetime import datetime
import pytz
from playwright.async_api import async_playwright

santiago_tz = pytz.timezone('America/Santiago')
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

async def test():
    print("Testing FULL CMG download process...", flush=True)
    print("="*60, flush=True)
    
    try:
        async with async_playwright() as p:
            print("1. Launching browser...", flush=True)
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            print("2. Creating context...", flush=True)
            context = await browser.new_context(
                accept_downloads=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            page.set_default_timeout(30000)
            
            print("3. Navigating to Coordinador...", flush=True)
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="domcontentloaded", timeout=15000)
            print(f"   URL: {page.url}", flush=True)
            print(f"   Title: {await page.title()}", flush=True)
            
            await asyncio.sleep(3)
            
            print("4. Clicking CMG en Línea tab...", flush=True)
            tab_link = page.locator('a[href="#Costo-Marginal-en-L--nea"]')
            await tab_link.first.click()
            print("   ✓ Tab clicked", flush=True)
            
            await asyncio.sleep(5)
            
            print("5. Accessing iframe...", flush=True)
            # We know index 1 works from our test
            frame = page.frame_locator("#Costo-Marginal-en-L--nea iframe").nth(1)
            
            # Verify we can access the iframe
            div_count = await frame.locator("div").count()
            print(f"   ✓ Iframe accessed ({div_count} divs)", flush=True)
            
            print("6. Looking for download button...", flush=True)
            download_btn = frame.get_by_title("Descargar")
            btn_count = await download_btn.count()
            print(f"   Found {btn_count} download button(s)", flush=True)
            
            if btn_count == 0:
                print("   ✗ No download button found!", flush=True)
                return False
            
            print("7. Triggering download...", flush=True)
            download = None
            try:
                async with page.expect_download(timeout=15000) as dl_info:
                    await download_btn.first.click()
                    print("   Button clicked, waiting for download...", flush=True)
                download = await dl_info.value
                print("   ✓ Download triggered!", flush=True)
            except Exception as e:
                print(f"   ✗ Download failed: {str(e)[:100]}", flush=True)
                return False
            
            print("8. Saving file...", flush=True)
            timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
            save_path = downloads_dir / f"test_cmg_{timestamp}.csv"
            await download.save_as(str(save_path))
            print(f"   ✓ Saved to: {save_path}", flush=True)
            
            # Check file size
            file_size = save_path.stat().st_size
            print(f"   File size: {file_size:,} bytes", flush=True)
            
            # Read first few lines
            print("9. Checking CSV content...", flush=True)
            with open(save_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                print(f"   Total lines: {len(lines)}", flush=True)
                print("   First 3 lines:", flush=True)
                for i, line in enumerate(lines[:3]):
                    print(f"     [{i}]: {line[:100].strip()}", flush=True)
            
            print("10. Closing browser...", flush=True)
            await browser.close()
            
            print("="*60, flush=True)
            print("✅ FULL DOWNLOAD TEST SUCCESSFUL!", flush=True)
            print(f"✅ CSV saved to: {save_path}", flush=True)
            return True
            
    except Exception as e:
        print(f"❌ Test failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    exit(0 if success else 1)