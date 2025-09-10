#!/usr/bin/env python3
"""
Test clicking the CMG en Línea tab and finding the iframe
"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    print("Testing tab click and iframe access...", flush=True)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            page.set_default_timeout(30000)
            
            print("1. Navigating to Coordinador...", flush=True)
            await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="domcontentloaded", timeout=15000)
            print("   ✓ Page loaded", flush=True)
            
            await asyncio.sleep(3)
            
            print("2. Clicking on CMG en Línea tab...", flush=True)
            # Use the href selector which we confirmed exists
            tab_link = page.locator('a[href="#Costo-Marginal-en-L--nea"]')
            count = await tab_link.count()
            print(f"   Found {count} tab link(s)", flush=True)
            
            if count > 0:
                await tab_link.first.click()
                print("   ✓ Tab clicked", flush=True)
            else:
                print("   ✗ Tab not found!", flush=True)
                return False
            
            # Wait for content to load
            await asyncio.sleep(5)
            
            print("3. Checking iframes after tab click...", flush=True)
            iframe_count = await page.locator("iframe").count()
            print(f"   Total iframes: {iframe_count}", flush=True)
            
            # Check iframes in the tab content
            tab_iframe_count = await page.locator("#Costo-Marginal-en-L--nea iframe").count()
            print(f"   Iframes in tab content: {tab_iframe_count}", flush=True)
            
            # List first few iframes
            for i in range(min(3, iframe_count)):
                iframe = page.locator("iframe").nth(i)
                src = await iframe.get_attribute("src") or "no src"
                title = await iframe.get_attribute("title") or "no title"
                print(f"   Iframe {i}:", flush=True)
                print(f"     Title: {title[:80]}", flush=True)
                print(f"     Src: {src[:100]}", flush=True)
            
            print("4. Testing iframe access...", flush=True)
            if tab_iframe_count > 1:
                print("   Trying to access iframe at index 1...", flush=True)
                frame = page.frame_locator("#Costo-Marginal-en-L--nea iframe").nth(1)
                
                # Try to count divs in the iframe
                try:
                    div_count = await frame.locator("div").count()
                    print(f"   ✓ Found {div_count} divs in iframe", flush=True)
                    
                    # Look for specific elements
                    show_range = await frame.locator("div.show-range").count()
                    print(f"   Date selectors (div.show-range): {show_range}", flush=True)
                    
                    download_btns = await frame.get_by_title("Descargar").count()
                    print(f"   Download buttons: {download_btns}", flush=True)
                    
                except Exception as e:
                    print(f"   ✗ Could not access iframe content: {str(e)[:100]}", flush=True)
            
            print("5. Closing browser...", flush=True)
            await browser.close()
            print("✅ Tab click test successful!", flush=True)
            return True
            
    except Exception as e:
        print(f"❌ Test failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    exit(0 if success else 1)