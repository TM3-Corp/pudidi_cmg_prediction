# CMG Data System Requirements

## MUST Requirements

### 1. Fetch Last 24 Hours Data (Rolling Window)
**Current Time Example**: 2025-08-29 10:40 Santiago
**Required Historical Window**: 2025-08-28 11:00 to 2025-08-29 10:00

- Backend fetches ALL available data from yesterday and today
- Frontend displays only the last 24 hours (rolling window)
- If gaps exist due to API lag, show what's available

### 2. Fetch Future CMG Programado
**Current Time Example**: 2025-08-29 10:40 Santiago  
**Required Future Data**: 2025-08-29 11:00 onwards (all available)

- Fetch today's remaining hours (11:00 to 23:00)
- Fetch tomorrow's full day if available
- Fetch day after tomorrow if available

### 3. Ensure Data Completeness

**Critical Issue**: API doesn't allow node filtering, must fetch ALL then filter

**Node Coverage Analysis** (from recent runs):
- ✅ **CHILOE_110**: Usually 100% coverage
- ✅ **CHILOE_220**: Usually 100% coverage  
- ✅ **CHONCHI_110**: Usually 100% coverage
- ✅ **DALCAHUE_023**: Usually 100% coverage
- ⚠️ **QUELLON_013**: Sometimes missing hours (79-83% coverage)
- ⚠️ **QUELLON_110**: Sometimes missing hours (79-83% coverage)

**Programmed Data Availability**:
- ✅ **BA S/E CHILOE 110KV BP1**: Always 100% coverage
- ✅ **BA S/E CHONCHI 110KV BP1**: Always 100% coverage
- ❌ **BA S/E CHILOE 220KV BP1**: No programmed data
- ❌ **BA S/E DALCAHUE 23KV BP1**: No programmed data
- ❌ **BA S/E QUELLON 110KV BP1**: No programmed data
- ❌ **BA S/E QUELLON 13KV BP1**: No programmed data

## Implementation Status

### Backend (simple_sequential_update.py)
- ✅ Fetches with 4000 records/page for speed
- ✅ Handles API errors with exponential backoff
- ✅ Fetches ALL pages until complete
- ✅ Saves all available data to cache
- ⚠️ Need to verify hour extraction is working

### Frontend (Next.js API)
- 🔄 TODO: Implement 24-hour rolling window filter
- 🔄 TODO: Show only nodes with complete data
- 🔄 TODO: Merge historical + programmed seamlessly

## Recommended Node Selection

For best data integrity, use only these nodes:
1. **CHILOE_110** (Historical + Programmed)
2. **CHILOE_220** (Historical only)
3. **CHONCHI_110** (Historical + Programmed)
4. **DALCAHUE_023** (Historical only)

Avoid QUELLON nodes due to occasional missing hours.