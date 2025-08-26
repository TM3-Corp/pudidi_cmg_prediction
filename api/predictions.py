"""
Vercel API Handler - Wrapper for the main prediction system
"""

import sys
import os

# Add src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))

# Import the main handler from our src
from src.api.predictions import handler

# Export the handler for Vercel
__all__ = ['handler']