#!/usr/bin/env python3
"""
Quick test to see if Playwright works at all
"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    print("Testing Playwright...", flush=True)
    try:
        print("1. Starting async_playwright...", flush=True)
        async with async_playwright() as p:
            print("2. Launching browser...", flush=True)
            browser = await p.chromium.launch(headless=True)
            print("3. Creating context...", flush=True)
            context = await browser.new_context()
            print("4. Creating page...", flush=True)
            page = await context.new_page()
            print("5. Navigating to example.com...", flush=True)
            await page.goto("https://example.com", wait_until="domcontentloaded", timeout=10000)
            print("6. Getting title...", flush=True)
            title = await page.title()
            print(f"7. Page title: {title}", flush=True)
            print("8. Closing browser...", flush=True)
            await browser.close()
            print("✅ Playwright works!", flush=True)
            return True
    except Exception as e:
        print(f"❌ Playwright failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test())
    exit(0 if success else 1)