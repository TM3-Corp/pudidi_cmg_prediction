#!/usr/bin/env python3
"""
Force click the download button in iframe
Handles overlapping elements by using force click or JavaScript
"""

import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
from datetime import datetime
import pytz

santiago_tz = pytz.timezone('America/Santiago')
downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

async def force_download():
    """Force click the download button despite overlapping elements"""
    
    async with async_playwright() as p:
        print("💪 FORCE CLICK DOWNLOADER")
        print("="*60)
        
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        
        url = "https://www.coordinador.cl/operacion/graficos/operacion-programada/costo-marginal-programado/"
        print(f"📍 Navigating to: {url}\n")
        
        await page.goto(url, wait_until="networkidle")
        print("✅ Page loaded")
        
        # Wait for QlikView
        print("⏳ Waiting 30 seconds for QlikView to load...")
        for i in range(3):
            await asyncio.sleep(10)
            print(f"   {(i+1)*10} seconds...")
        
        # Find the iframe with QlikView dashboard
        print("\n🕰️ Finding QlikView iframe...")
        iframe_selector = 'iframe#grafico_2'
        
        try:
            await page.wait_for_selector(iframe_selector, timeout=10000)
            iframe_element = await page.query_selector(iframe_selector)
            
            if not iframe_element:
                # Try alternative selector
                iframe_selector = 'iframe[src*="mashup_Plataforma_Programacion_App_Costo_Marginal_Programado_PCP"]'
                iframe_element = await page.query_selector(iframe_selector)
            
            if not iframe_element:
                print("❌ Could not find iframe")
                await browser.close()
                return None
            
            frame = await iframe_element.content_frame()
            if not frame:
                print("❌ Could not access iframe content")
                await browser.close()
                return None
            
            print("✅ Accessed iframe content")
            
            # Method 1: Force click (ignores overlapping elements)
            print("\n🎯 METHOD 1: Force click on button")
            try:
                button = frame.locator('#buttonQV100').first
                if await button.count() > 0:
                    print("  Found button, force clicking...")
                    
                    async with page.expect_download(timeout=15000) as download_info:
                        await button.click(force=True)  # Force click ignores overlapping elements
                        print("  ✅ Force clicked! Waiting for download...")
                        download = await download_info.value
                    
                    # Save the file
                    timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
                    save_path = downloads_dir / f"cmg_programado_{timestamp}.csv"
                    await download.save_as(str(save_path))
                    
                    print(f"\n🎉 SUCCESS with force click!")
                    print(f"  Downloaded: {save_path}")
                    print(f"  Size: {save_path.stat().st_size:,} bytes")
                    
                    await browser.close()
                    return save_path
            except Exception as e:
                print(f"  Force click failed: {e}")
            
            # Method 2: JavaScript click
            print("\n🎯 METHOD 2: JavaScript click")
            try:
                result = await frame.evaluate("""
                    () => {
                        const button = document.getElementById('buttonQV100');
                        if (button) {
                            button.click();
                            return 'Clicked via JavaScript';
                        }
                        return 'Button not found';
                    }
                """)
                print(f"  JavaScript result: {result}")
                
                if result == 'Clicked via JavaScript':
                    # Wait for download
                    await asyncio.sleep(5)
                    
                    # Check if download started
                    # Note: This might not trigger page.expect_download
                    print("  Waiting for potential download...")
                    await asyncio.sleep(10)
            except Exception as e:
                print(f"  JavaScript click failed: {e}")
            
            # Method 3: Dispatch click event
            print("\n🎯 METHOD 3: Dispatch click event")
            try:
                result = await frame.evaluate("""
                    () => {
                        const button = document.getElementById('buttonQV100');
                        if (button) {
                            const event = new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            });
                            button.dispatchEvent(event);
                            return 'Event dispatched';
                        }
                        return 'Button not found';
                    }
                """)
                print(f"  Dispatch result: {result}")
                await asyncio.sleep(5)
            except Exception as e:
                print(f"  Dispatch event failed: {e}")
            
            # Method 4: Remove overlapping elements and then click
            print("\n🎯 METHOD 4: Remove overlapping elements")
            try:
                # Remove overlapping header
                await page.evaluate("""
                    () => {
                        const header = document.querySelector('header.affix');
                        if (header) header.style.display = 'none';
                        
                        const navbar = document.querySelector('.eemv_mobile_navbar_div');
                        if (navbar) navbar.style.display = 'none';
                        
                        // Also hide other iframes that might overlap
                        const iframes = document.querySelectorAll('iframe');
                        iframes.forEach((iframe, index) => {
                            if (index > 0) {  // Keep first iframe (our target)
                                iframe.style.zIndex = '-1';
                            }
                        });
                    }
                """)
                print("  Removed overlapping elements")
                
                # Now try regular click
                button = frame.locator('#buttonQV100').first
                if await button.count() > 0:
                    async with page.expect_download(timeout=15000) as download_info:
                        await button.click()
                        print("  ✅ Clicked after removing overlaps! Waiting for download...")
                        download = await download_info.value
                    
                    timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
                    save_path = downloads_dir / f"cmg_programado_{timestamp}.csv"
                    await download.save_as(str(save_path))
                    
                    print(f"\n🎉 SUCCESS after removing overlaps!")
                    print(f"  Downloaded: {save_path}")
                    
                    await browser.close()
                    return save_path
            except Exception as e:
                print(f"  Remove overlaps method failed: {e}")
            
            # Method 5: Click using coordinates
            print("\n🎯 METHOD 5: Click using button coordinates")
            try:
                button = frame.locator('#buttonQV100').first
                if await button.count() > 0:
                    # Get button position
                    box = await button.bounding_box()
                    if box:
                        # Click at the center of the button
                        x = box['x'] + box['width'] / 2
                        y = box['y'] + box['height'] / 2
                        print(f"  Clicking at coordinates ({x}, {y})")
                        
                        async with page.expect_download(timeout=15000) as download_info:
                            await page.mouse.click(x, y)
                            print("  ✅ Coordinate click successful! Waiting for download...")
                            download = await download_info.value
                        
                        timestamp = datetime.now(santiago_tz).strftime("%Y%m%d_%H%M%S")
                        save_path = downloads_dir / f"cmg_programado_{timestamp}.csv"
                        await download.save_as(str(save_path))
                        
                        print(f"\n🎉 SUCCESS with coordinate click!")
                        print(f"  Downloaded: {save_path}")
                        
                        await browser.close()
                        return save_path
            except Exception as e:
                print(f"  Coordinate click failed: {e}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        
        # Take screenshot
        await page.screenshot(path=downloads_dir / "force_click_attempts.png", full_page=True)
        print("\n📸 Screenshot saved: force_click_attempts.png")
        
        print("\n⏸️ Keeping browser open for manual inspection...")
        await asyncio.sleep(30)
        
        await browser.close()
        return None

async def main():
    print("="*60)
    print("CMG PROGRAMADO - FORCE CLICK DOWNLOADER")
    print("="*60)
    print(f"Time: {datetime.now(santiago_tz)}\n")
    print("This version uses multiple methods to click the button:")
    print("1. Force click (ignores overlapping elements)")
    print("2. JavaScript direct click")
    print("3. Dispatch mouse event")
    print("4. Remove overlapping elements first")
    print("5. Click using coordinates\n")
    
    result = await force_download()
    
    if result:
        print(f"\n🎉 SUCCESS! Downloaded: {result}")
        
        # Check content
        with open(result, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
            print(f"\nFile has {len(lines)} lines")
            print("First 5 lines:")
            for i, line in enumerate(lines[:5]):
                print(f"  {i+1}: {line.strip()[:80]}")
        
        return 0
    else:
        print("\n📋 Could not download using any method")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)