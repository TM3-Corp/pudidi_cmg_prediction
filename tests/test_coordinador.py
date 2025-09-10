#!/usr/bin/env python3
"""
Test navigation to Coordinador website
"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    print("Testing Coordinador website access...", flush=True)
    try:
        async with async_playwright() as p:
            print("1. Launching browser...", flush=True)
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            print("2. Creating context with user agent...", flush=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            page.set_default_timeout(30000)
            
            print("3. Navigating to Coordinador (domcontentloaded)...", flush=True)
            try:
                await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="domcontentloaded", timeout=15000)
                print("   ✓ Navigation successful with domcontentloaded", flush=True)
            except Exception as e:
                print(f"   ✗ Failed with domcontentloaded: {str(e)[:100]}", flush=True)
                print("   Trying with commit...", flush=True)
                await page.goto("https://www.coordinador.cl/costos-marginales/", wait_until="commit", timeout=10000)
                print("   ✓ Navigation successful with commit", flush=True)
            
            print(f"4. Current URL: {page.url}", flush=True)
            print(f"5. Page title: {await page.title()}", flush=True)
            
            # Check for tabs
            print("6. Looking for CMG tabs...", flush=True)
            
            # Count various tab links
            tabs_to_check = [
                ('a[href="#Costo-Marginal-en-L--nea"]', 'CMG en Línea by href'),
                ('a:has-text("Costo Marginal en Línea")', 'CMG en Línea by text'),
                ('a:has-text("Costo Marginal Programado")', 'CMG Programado'),
                ('a.nav-link', 'All nav links')
            ]
            
            for selector, description in tabs_to_check:
                count = await page.locator(selector).count()
                print(f"   - {description}: {count} found", flush=True)
                if count > 0 and count <= 3:
                    for i in range(count):
                        text = await page.locator(selector).nth(i).text_content()
                        print(f"     [{i}]: {text[:50]}", flush=True)
            
            # Check for iframes
            print("7. Checking for iframes...", flush=True)
            iframe_count = await page.locator("iframe").count()
            print(f"   Found {iframe_count} iframe(s)", flush=True)
            
            print("8. Closing browser...", flush=True)
            await browser.close()
            print("✅ Coordinador access successful!", flush=True)
            return True
            
    except Exception as e:
        print(f"❌ Test failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    exit(0 if success else 1)