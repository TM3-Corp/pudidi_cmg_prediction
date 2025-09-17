#!/usr/bin/env python3
"""
CMG Programado Pipeline - Download and process PMontt220 data
Runs hourly to update forecast data
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import pytz
import os

# Import our scripts
sys.path.insert(0, str(Path(__file__).parent))
from download_cmg_programado_simple import run as download_cmg
from process_pmontt_programado import main as process_pmontt

santiago_tz = pytz.timezone('America/Santiago')

async def main():
    """Main pipeline function"""
    print("="*60)
    print("🚀 CMG PROGRAMADO PIPELINE - PMONTT220")
    print("="*60)
    print(f"Time: {datetime.now(santiago_tz)}")
    print(f"Mode: {'GitHub Actions' if os.environ.get('GITHUB_ACTIONS') else 'Local'}\n")
    
    # Step 1: Download CMG Programado data
    print("📥 STEP 1: Downloading CMG Programado...")
    print("-"*40)
    
    try:
        csv_path = await download_cmg()
        if csv_path:
            print(f"✅ Downloaded: {csv_path}\n")
        else:
            print("❌ Download failed\n")
            return 1
    except Exception as e:
        print(f"❌ Download error: {e}\n")
        return 1
    
    # Step 2: Process PMontt220 data and update Gist
    print("🔄 STEP 2: Processing PMontt220 data...")
    print("-"*40)
    
    try:
        result = process_pmontt()
        if result == 0:
            print("✅ Processing complete\n")
        else:
            print("⚠️ Processing had issues\n")
            return result
    except Exception as e:
        print(f"❌ Processing error: {e}\n")
        return 1
    
    # Final summary
    print("="*60)
    print("🎉 PIPELINE COMPLETE")
    print("="*60)
    print(f"Completed at: {datetime.now(santiago_tz)}")
    print(f"🎯 Check results at: https://pudidicmgprediction.vercel.app/index.html")
    print(f"   Look for '🔮 Datos Programados Disponibles' section")
    
    return 0

if __name__ == "__main__":
    # Set headless mode for GitHub Actions
    if os.environ.get('GITHUB_ACTIONS'):
        import download_cmg_programado_simple
        download_cmg_programado_simple.HEADLESS = True
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)