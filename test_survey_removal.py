#!/usr/bin/env python3
"""
Test removing survey popup from DOM entirely
"""
import asyncio
from playwright.async_api import async_playwright
import pytz
from datetime import datetime

santiago_tz = pytz.timezone('America/Santiago')

async def test():
    print("Testing survey removal methods...", flush=True)
    print("="*60, flush=True)
    
    async with async_playwright() as p:
        # Launch with GUI to see what happens
        browser = await p.chromium.launch(
            headless=False,  # Show browser to see the survey
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = await context.new_page()
        
        try:
            print("1. Navigating to Coordinador...", flush=True)
            await page.goto("https://www.coordinador.cl/costos-marginales/", 
                          wait_until="domcontentloaded", timeout=20000)
            
            await asyncio.sleep(3)
            
            print("2. Looking for survey iframe...", flush=True)
            
            # Method 1: Count survey iframes
            survey_count = await page.locator("iframe[src*='e-survey']").count()
            print(f"   Found {survey_count} survey iframe(s)", flush=True)
            
            if survey_count > 0:
                # Get the survey iframe details
                survey_src = await page.locator("iframe[src*='e-survey']").first.get_attribute("src")
                print(f"   Survey URL: {survey_src}", flush=True)
                
                print("\n3. Attempting removal methods:", flush=True)
                
                # Method 1: Remove survey iframe using JavaScript
                print("   Method 1: Removing iframe via JavaScript...", flush=True)
                removed = await page.evaluate("""
                    () => {
                        let removed = 0;
                        // Find all survey iframes
                        const surveys = document.querySelectorAll('iframe[src*="survey"], iframe[src*="e-survey"]');
                        surveys.forEach(iframe => {
                            console.log('Removing survey iframe:', iframe.src);
                            iframe.remove();
                            removed++;
                        });
                        
                        // Also try to remove parent containers that might be survey-related
                        const surveyContainers = document.querySelectorAll('[class*="survey"], [id*="survey"]');
                        surveyContainers.forEach(container => {
                            // Only remove if it contains an iframe or looks like a modal
                            if (container.querySelector('iframe') || 
                                container.style.position === 'fixed' || 
                                container.style.position === 'absolute') {
                                console.log('Removing survey container:', container.className || container.id);
                                container.remove();
                                removed++;
                            }
                        });
                        
                        return removed;
                    }
                """)
                print(f"   ✓ Removed {removed} survey element(s)", flush=True)
                
                # Method 2: Hide survey using CSS injection
                print("   Method 2: Injecting CSS to hide surveys...", flush=True)
                await page.add_style_tag(content="""
                    iframe[src*="survey"],
                    iframe[src*="e-survey"],
                    [class*="survey-modal"],
                    [id*="survey-container"] {
                        display: none !important;
                        visibility: hidden !important;
                        opacity: 0 !important;
                        pointer-events: none !important;
                        position: fixed !important;
                        top: -9999px !important;
                        left: -9999px !important;
                    }
                """)
                print("   ✓ CSS injection applied", flush=True)
                
                # Method 3: Block survey domain at context level (for future pages)
                print("   Method 3: Setting up route blocking for survey domain...", flush=True)
                await context.route("**/*e-survey.cl/**", lambda route: route.abort())
                await context.route("**/*survey*", lambda route: route.abort() if "coordinador" not in route.request.url else route.continue_())
                print("   ✓ Survey domain blocking configured", flush=True)
                
                await asyncio.sleep(2)
                
                # Check if survey is gone
                survey_count_after = await page.locator("iframe[src*='e-survey']").count()
                print(f"\n4. Survey iframes after removal: {survey_count_after}", flush=True)
                
                if survey_count_after == 0:
                    print("   ✅ Survey successfully removed!", flush=True)
                else:
                    print("   ⚠️ Survey still present, trying more aggressive removal...", flush=True)
                    
                    # More aggressive: Remove ALL iframes except PowerBI
                    await page.evaluate("""
                        () => {
                            const iframes = document.querySelectorAll('iframe');
                            iframes.forEach(iframe => {
                                if (!iframe.src.includes('qap-prd.coordinador.cl')) {
                                    console.log('Force removing iframe:', iframe.src);
                                    iframe.remove();
                                }
                            });
                        }
                    """)
                    print("   ✓ Force removed non-PowerBI iframes", flush=True)
            else:
                print("   No survey found on this load", flush=True)
            
            # Now try to access the tab
            print("\n5. Testing tab access after survey removal...", flush=True)
            tab_link = page.locator('a[href="#Costo-Marginal-en-L--nea"]')
            tab_count = await tab_link.count()
            print(f"   CMG en Línea tab found: {tab_count > 0}", flush=True)
            
            if tab_count > 0:
                await tab_link.first.click()
                print("   ✓ Tab clicked successfully!", flush=True)
            
            print("\n6. Checking all iframes on page:", flush=True)
            all_iframes = await page.locator("iframe").count()
            print(f"   Total iframes: {all_iframes}", flush=True)
            
            for i in range(min(all_iframes, 5)):
                src = await page.locator("iframe").nth(i).get_attribute("src") or "no src"
                print(f"   Iframe {i}: {src[:80]}...", flush=True)
            
            print("\n✅ Test complete! Press Enter to close browser...", flush=True)
            input()  # Wait for user to see the result
            
        except Exception as e:
            print(f"❌ Error: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())