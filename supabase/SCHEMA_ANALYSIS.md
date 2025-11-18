# Database Schema Analysis & Redesign

**Date:** 2025-11-18
**Current Status:** Production (Migration Required)

---

## 🔍 Current Schema Issues

### 1. **Data Duplication**

Each table stores the same datetime information in 3+ different formats:

```sql
-- cmg_online
datetime TIMESTAMPTZ      -- "2025-11-18 18:00:00+00"
date DATE                 -- "2025-11-18"
hour INTEGER             -- 15 (Santiago time!)

-- cmg_programado & ml_predictions
forecast_datetime TIMESTAMPTZ
forecast_date DATE
forecast_hour INTEGER    -- Santiago timezone
target_datetime TIMESTAMPTZ
target_date DATE
target_hour INTEGER      -- Santiago timezone
```

**Problem:** Date and hour can be CALCULATED from datetime. Storing them separately:
- Wastes storage space
- Creates sync issues (what if they don't match?)
- Causes timezone confusion (hour is in Santiago, datetime is UTC)

### 2. **Timezone Confusion**

```sql
-- cmg_online example row:
datetime = '2025-11-18 18:00:00+00'  -- UTC
hour = 15                             -- Santiago (UTC-3)

-- This is confusing! hour != EXTRACT(HOUR FROM datetime)
```

**Problem:** Mixing UTC timestamps with Santiago-timezone hour values in the same row creates confusion and bugs.

### 3. **No Normalization - Nodes**

Nodes are stored as TEXT strings repeated across thousands of rows:

```sql
node = 'NVA_P.MONTT___220'  -- Repeated in every row!
```

**Problems:**
- Wasted storage (string repeated thousands of times)
- Typo risks ("NVA_P.MONT__220" vs "NVA_P.MONTT___220")
- Can't store metadata about nodes (region, voltage, etc.)
- No referential integrity

### 4. **No Foreign Key Relationships**

Tables are completely independent:
- ML prediction for datetime X can exist without actual value
- CMG Programado can reference non-existent target times
- No referential integrity enforcement

### 5. **Missing Abstractions**

Conceptually, forecasts are made in "sessions":
- At 10:00, we make 24 predictions (t+1 to t+24)
- All those predictions share the same forecast_datetime
- Could be grouped for efficiency

---

## ✅ Proposed New Schema (State-of-the-Art)

### Design Principles

1. **Single Source of Truth:** Store datetime in UTC only (TIMESTAMPTZ)
2. **Normalize Dimensions:** Create lookup tables for nodes
3. **Foreign Key Relationships:** Enforce referential integrity
4. **Views for Convenience:** Calculate local times in views, not storage
5. **Indexing Strategy:** Optimize for common query patterns

### Core Tables

```sql
-- ============================================================
-- DIMENSION TABLES (Lookup Tables)
-- ============================================================

-- Nodes: Electrical grid nodes
CREATE TABLE nodes (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT,
    region TEXT,
    voltage_kv INTEGER,
    coordinates GEOGRAPHY(POINT),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE nodes IS 'Electrical grid nodes in Chilean system';

-- Insert common nodes
INSERT INTO nodes (code, name, region, voltage_kv) VALUES
    ('NVA_P.MONTT___220', 'Nueva Puerto Montt', 'Los Lagos', 220),
    ('PIDPID___110', 'Pidenco-Piduco', 'Araucanía', 110)
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- FACT TABLES (Time-Series Data)
-- ============================================================

-- CMG Online: Actual observed values
CREATE TABLE cmg_online (
    id BIGSERIAL PRIMARY KEY,
    datetime TIMESTAMPTZ NOT NULL,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    cmg_usd DECIMAL(10, 2),
    source TEXT DEFAULT 'SIP_API_v4',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- One value per datetime + node
    CONSTRAINT unique_cmg_online_datetime_node UNIQUE(datetime, node_id)
);

-- ML Predictions: Model forecasts
CREATE TABLE ml_predictions (
    id BIGSERIAL PRIMARY KEY,
    forecast_datetime TIMESTAMPTZ NOT NULL,
    target_datetime TIMESTAMPTZ NOT NULL,
    horizon INTEGER NOT NULL CHECK (horizon >= 1 AND horizon <= 48),
    cmg_predicted DECIMAL(10, 2),
    prob_zero DECIMAL(5, 4) CHECK (prob_zero >= 0 AND prob_zero <= 1),
    threshold DECIMAL(5, 4) CHECK (threshold >= 0 AND threshold <= 1),
    model_version TEXT DEFAULT 'gpu_enhanced_v1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- One prediction per forecast + target
    CONSTRAINT unique_ml_pred_forecast_target UNIQUE(forecast_datetime, target_datetime),

    -- Horizon must match time difference
    CONSTRAINT check_horizon_matches_time
        CHECK (EXTRACT(EPOCH FROM (target_datetime - forecast_datetime))/3600 = horizon)
);

-- CMG Programado: Official forecasts from Coordinador
CREATE TABLE cmg_programado (
    id BIGSERIAL PRIMARY KEY,
    forecast_datetime TIMESTAMPTZ NOT NULL,
    target_datetime TIMESTAMPTZ NOT NULL,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    cmg_usd DECIMAL(10, 2),
    source TEXT DEFAULT 'Coordinador',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- One forecast per (forecast time + target time + node)
    CONSTRAINT unique_cmg_prog_forecast_target_node
        UNIQUE(forecast_datetime, target_datetime, node_id)
);

-- ============================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================

-- CMG Online
CREATE INDEX idx_cmg_online_datetime ON cmg_online(datetime DESC);
CREATE INDEX idx_cmg_online_node_datetime ON cmg_online(node_id, datetime DESC);

-- ML Predictions
CREATE INDEX idx_ml_pred_forecast_dt ON ml_predictions(forecast_datetime DESC);
CREATE INDEX idx_ml_pred_target_dt ON ml_predictions(target_datetime DESC);
CREATE INDEX idx_ml_pred_horizon ON ml_predictions(horizon);

-- CMG Programado
CREATE INDEX idx_cmg_prog_forecast_dt ON cmg_programado(forecast_datetime DESC);
CREATE INDEX idx_cmg_prog_target_dt ON cmg_programado(target_datetime DESC);
CREATE INDEX idx_cmg_prog_node_target ON cmg_programado(node_id, target_datetime);

-- ============================================================
-- CONVENIENCE VIEWS (Santiago Timezone)
-- ============================================================

-- CMG Online with Santiago timezone columns
CREATE OR REPLACE VIEW cmg_online_santiago AS
SELECT
    id,
    datetime,
    datetime AT TIME ZONE 'America/Santiago' AS datetime_local,
    DATE(datetime AT TIME ZONE 'America/Santiago') AS date,
    EXTRACT(HOUR FROM datetime AT TIME ZONE 'America/Santiago')::INTEGER AS hour,
    n.code AS node,
    n.name AS node_name,
    cmg_usd,
    source,
    created_at
FROM cmg_online
JOIN nodes n ON cmg_online.node_id = n.id;

-- ML Predictions with Santiago timezone columns
CREATE OR REPLACE VIEW ml_predictions_santiago AS
SELECT
    id,
    forecast_datetime,
    forecast_datetime AT TIME ZONE 'America/Santiago' AS forecast_local,
    DATE(forecast_datetime AT TIME ZONE 'America/Santiago') AS forecast_date,
    EXTRACT(HOUR FROM forecast_datetime AT TIME ZONE 'America/Santiago')::INTEGER AS forecast_hour,
    target_datetime,
    target_datetime AT TIME ZONE 'America/Santiago' AS target_local,
    DATE(target_datetime AT TIME ZONE 'America/Santiago') AS target_date,
    EXTRACT(HOUR FROM target_datetime AT TIME ZONE 'America/Santiago')::INTEGER AS target_hour,
    horizon,
    cmg_predicted,
    prob_zero,
    threshold,
    model_version,
    created_at
FROM ml_predictions;

-- CMG Programado with Santiago timezone columns
CREATE OR REPLACE VIEW cmg_programado_santiago AS
SELECT
    id,
    forecast_datetime,
    forecast_datetime AT TIME ZONE 'America/Santiago' AS forecast_local,
    DATE(forecast_datetime AT TIME ZONE 'America/Santiago') AS forecast_date,
    EXTRACT(HOUR FROM forecast_datetime AT TIME ZONE 'America/Santiago')::INTEGER AS forecast_hour,
    target_datetime,
    target_datetime AT TIME ZONE 'America/Santiago' AS target_local,
    DATE(target_datetime AT TIME ZONE 'America/Santiago') AS target_date,
    EXTRACT(HOUR FROM target_datetime AT TIME ZONE 'America/Santiago')::INTEGER AS target_hour,
    n.code AS node,
    n.name AS node_name,
    cmg_usd,
    source,
    created_at
FROM cmg_programado
JOIN nodes n ON cmg_programado.node_id = n.id;

-- ============================================================
-- ANALYTICS VIEWS
-- ============================================================

-- Forecast Comparison: ML vs Programado vs Actual
CREATE OR REPLACE VIEW forecast_comparison AS
SELECT
    ml.forecast_datetime,
    ml.target_datetime,
    ml.horizon,
    ml.cmg_predicted AS ml_cmg,
    ml.prob_zero,
    prog.cmg_usd AS programado_cmg,
    prog.node_id,
    actual.cmg_usd AS actual_cmg,
    ABS(ml.cmg_predicted - actual.cmg_usd) AS ml_error,
    ABS(prog.cmg_usd - actual.cmg_usd) AS prog_error
FROM ml_predictions ml
LEFT JOIN cmg_programado prog
    ON ml.forecast_datetime = prog.forecast_datetime
    AND ml.target_datetime = prog.target_datetime
LEFT JOIN cmg_online actual
    ON ml.target_datetime = actual.datetime
    AND prog.node_id = actual.node_id
WHERE actual.cmg_usd IS NOT NULL;

COMMENT ON VIEW forecast_comparison IS 'Compare ML predictions, CMG Programado, and actual values';
```

---

## 📊 Benefits of New Schema

### 1. **Storage Efficiency**
- Remove duplicate date/hour columns: **-40% column count**
- Normalize nodes: **-90% storage for node data**

### 2. **Data Integrity**
- Foreign keys prevent orphaned records
- Check constraints ensure horizon matches time difference
- Unique constraints prevent duplicates

### 3. **Clarity**
- All datetimes are UTC (TIMESTAMPTZ)
- Santiago time calculated in views, not stored
- No more timezone confusion!

### 4. **Flexibility**
- Easy to add node metadata (region, voltage, coordinates)
- Can create custom views for different timezones
- Supports analytics queries efficiently

### 5. **Performance**
- Smaller tables = faster queries
- Better indexing on foreign keys
- Views are materialized on demand

---

## 🔄 Migration Strategy

See `002_normalize_schema.sql` for full migration script.

**Steps:**
1. Create nodes table and populate
2. Add node_id columns to existing tables
3. Migrate node TEXT → node_id INTEGER
4. Drop redundant date/hour columns
5. Create views for backward compatibility
6. Update application code to use views
7. Drop old columns after verification

**Rollback Plan:** Keep old columns until full verification (7 days).

---

## 📝 Application Code Changes Required

### Before (Old Schema):
```python
# Query with redundant columns
result = supabase.table('cmg_online').select('datetime, date, hour, node, cmg_usd')
```

### After (New Schema):
```python
# Query using view (no code change needed!)
result = supabase.table('cmg_online_santiago').select('datetime_local, date, hour, node, cmg_usd')

# Or query base table and calculate in app
result = supabase.table('cmg_online').select('datetime, node_id, cmg_usd')
```

**Impact:** Minimal! Views provide backward compatibility.

---

## ✅ Recommendation

**APPROVE THIS MIGRATION** for production.

**Timeline:**
- Day 1: Create new tables/views (additive, no breaking changes)
- Day 2-7: Run both old and new schema in parallel, verify correctness
- Day 8: Switch application to use new views
- Day 15: Drop old redundant columns

**Risk Level:** LOW (additive migration with rollback capability)
