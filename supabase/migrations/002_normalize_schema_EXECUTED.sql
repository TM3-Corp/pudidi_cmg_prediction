-- ============================================================
-- MIGRATION 002: Normalize Schema with Foreign Keys (v2 - No horizon constraint)
-- ============================================================
-- Date: 2025-11-18
-- Purpose: Eliminate data duplication, add proper relationships
-- Risk Level: LOW (additive migration, old columns kept for rollback)
-- ============================================================

BEGIN;

-- ============================================================
-- STEP 1: Create Nodes Dimension Table
-- ============================================================

CREATE TABLE IF NOT EXISTS nodes (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT,
    region TEXT,
    voltage_kv INTEGER,
    latitude DECIMAL(10, 7),
    longitude DECIMAL(10, 7),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE nodes IS 'Electrical grid nodes in Chilean power system';
COMMENT ON COLUMN nodes.code IS 'Unique node identifier (e.g., NVA_P.MONTT___220)';
COMMENT ON COLUMN nodes.name IS 'Human-readable node name';
COMMENT ON COLUMN nodes.region IS 'Geographic region (e.g., Los Lagos, Araucanía)';
COMMENT ON COLUMN nodes.voltage_kv IS 'Transmission line voltage in kilovolts';

-- Create index on code for fast lookups
CREATE INDEX IF NOT EXISTS idx_nodes_code ON nodes(code);

-- Populate with existing nodes from cmg_online
INSERT INTO nodes (code, name)
SELECT DISTINCT
    node,
    node  -- Use same value for name initially
FROM cmg_online
WHERE node IS NOT NULL
ON CONFLICT (code) DO NOTHING;

-- Populate with nodes from cmg_programado that don't exist yet
INSERT INTO nodes (code, name)
SELECT DISTINCT
    node,
    node
FROM cmg_programado
WHERE node IS NOT NULL
ON CONFLICT (code) DO NOTHING;

-- Add known node metadata (can be updated later)
UPDATE nodes SET
    name = 'Nueva Puerto Montt',
    region = 'Los Lagos',
    voltage_kv = 220
WHERE code = 'NVA_P.MONTT___220';

UPDATE nodes SET
    name = 'Dalcahue',
    region = 'Los Lagos',
    voltage_kv = 110
WHERE code = 'DALCAHUE______110';

-- ============================================================
-- STEP 2: Add node_id Foreign Key to cmg_online
-- ============================================================

-- Add column (nullable initially for migration)
ALTER TABLE cmg_online
ADD COLUMN IF NOT EXISTS node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE;

-- Populate node_id from node TEXT
UPDATE cmg_online co
SET node_id = n.id
FROM nodes n
WHERE co.node = n.code
AND co.node_id IS NULL;

-- Verify all rows have node_id
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count FROM cmg_online WHERE node_id IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION 'Migration failed: % cmg_online rows have NULL node_id', null_count;
    END IF;
    RAISE NOTICE 'All cmg_online rows have node_id';
END$$;

-- Make node_id NOT NULL and create index
ALTER TABLE cmg_online ALTER COLUMN node_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cmg_online_node_id ON cmg_online(node_id);
CREATE INDEX IF NOT EXISTS idx_cmg_online_node_datetime ON cmg_online(node_id, datetime DESC);

-- Update unique constraint to use node_id
ALTER TABLE cmg_online DROP CONSTRAINT IF EXISTS unique_cmg_online_datetime_node;
ALTER TABLE cmg_online ADD CONSTRAINT unique_cmg_online_datetime_node_id
    UNIQUE(datetime, node_id);

-- ============================================================
-- STEP 3: Add node_id Foreign Key to cmg_programado
-- ============================================================

-- Add column
ALTER TABLE cmg_programado
ADD COLUMN IF NOT EXISTS node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE;

-- Populate node_id from node TEXT
UPDATE cmg_programado cp
SET node_id = n.id
FROM nodes n
WHERE cp.node = n.code
AND cp.node_id IS NULL;

-- Verify
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count FROM cmg_programado WHERE node_id IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION 'Migration failed: % cmg_programado rows have NULL node_id', null_count;
    END IF;
    RAISE NOTICE 'All cmg_programado rows have node_id';
END$$;

-- Make NOT NULL and index
ALTER TABLE cmg_programado ALTER COLUMN node_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cmg_prog_node_id ON cmg_programado(node_id);
CREATE INDEX IF NOT EXISTS idx_cmg_prog_node_target ON cmg_programado(node_id, target_datetime);

-- Update unique constraint
ALTER TABLE cmg_programado DROP CONSTRAINT IF EXISTS unique_cmg_prog_forecast_target_node;
ALTER TABLE cmg_programado ADD CONSTRAINT unique_cmg_prog_forecast_target_node_id
    UNIQUE(forecast_datetime, target_datetime, node_id);

-- ============================================================
-- STEP 4: Create Convenience Views (Santiago Timezone)
-- ============================================================

-- CMG Online with Santiago timezone (backward compatible)
CREATE OR REPLACE VIEW cmg_online_santiago AS
SELECT
    co.id,
    co.datetime,
    co.datetime AT TIME ZONE 'America/Santiago' AS datetime_local,
    DATE(co.datetime AT TIME ZONE 'America/Santiago') AS date,
    EXTRACT(HOUR FROM co.datetime AT TIME ZONE 'America/Santiago')::INTEGER AS hour,
    n.code AS node,
    n.name AS node_name,
    n.region,
    co.cmg_usd,
    co.source,
    co.created_at,
    co.updated_at,
    -- Include node_id for joins
    co.node_id
FROM cmg_online co
JOIN nodes n ON co.node_id = n.id;

COMMENT ON VIEW cmg_online_santiago IS 'CMG Online with Santiago timezone columns - backward compatible';

-- ML Predictions with Santiago timezone
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

COMMENT ON VIEW ml_predictions_santiago IS 'ML Predictions with Santiago timezone columns';

-- CMG Programado with Santiago timezone (backward compatible)
CREATE OR REPLACE VIEW cmg_programado_santiago AS
SELECT
    cp.id,
    cp.forecast_datetime,
    cp.forecast_datetime AT TIME ZONE 'America/Santiago' AS forecast_local,
    DATE(cp.forecast_datetime AT TIME ZONE 'America/Santiago') AS forecast_date,
    EXTRACT(HOUR FROM cp.forecast_datetime AT TIME ZONE 'America/Santiago')::INTEGER AS forecast_hour,
    cp.target_datetime,
    cp.target_datetime AT TIME ZONE 'America/Santiago' AS target_local,
    DATE(cp.target_datetime AT TIME ZONE 'America/Santiago') AS target_date,
    EXTRACT(HOUR FROM cp.target_datetime AT TIME ZONE 'America/Santiago')::INTEGER AS target_hour,
    n.code AS node,
    n.name AS node_name,
    n.region,
    cp.cmg_usd,
    cp.created_at,
    cp.updated_at,
    -- Include node_id for joins
    cp.node_id
FROM cmg_programado cp
JOIN nodes n ON cp.node_id = n.id;

COMMENT ON VIEW cmg_programado_santiago IS 'CMG Programado with Santiago timezone columns - backward compatible';

-- ============================================================
-- STEP 5: Create Analytics Views
-- ============================================================

-- Forecast Comparison: ML vs Programado vs Actual
CREATE OR REPLACE VIEW forecast_comparison AS
SELECT
    ml.forecast_datetime,
    ml.forecast_datetime AT TIME ZONE 'America/Santiago' AS forecast_local,
    ml.target_datetime,
    ml.target_datetime AT TIME ZONE 'America/Santiago' AS target_local,
    ml.horizon,
    ml.cmg_predicted AS ml_cmg,
    ml.prob_zero,
    prog.cmg_usd AS programado_cmg,
    n.code AS node,
    actual.cmg_usd AS actual_cmg,
    -- Calculate errors
    ABS(ml.cmg_predicted - actual.cmg_usd) AS ml_absolute_error,
    ABS(prog.cmg_usd - actual.cmg_usd) AS prog_absolute_error,
    (ml.cmg_predicted - actual.cmg_usd) AS ml_error,
    (prog.cmg_usd - actual.cmg_usd) AS prog_error,
    -- ML better than Programado?
    CASE
        WHEN ABS(ml.cmg_predicted - actual.cmg_usd) < ABS(prog.cmg_usd - actual.cmg_usd)
        THEN true ELSE false
    END AS ml_better
FROM ml_predictions ml
LEFT JOIN cmg_programado prog
    ON ml.forecast_datetime = prog.forecast_datetime
    AND ml.target_datetime = prog.target_datetime
LEFT JOIN nodes n ON prog.node_id = n.id
LEFT JOIN cmg_online actual
    ON ml.target_datetime = actual.datetime
    AND prog.node_id = actual.node_id
WHERE actual.cmg_usd IS NOT NULL;

COMMENT ON VIEW forecast_comparison IS 'Compare ML predictions, CMG Programado, and actual values with error metrics';

-- Latest ML forecast
CREATE OR REPLACE VIEW latest_ml_forecast AS
SELECT
    forecast_datetime,
    forecast_datetime AT TIME ZONE 'America/Santiago' AS forecast_local,
    horizon,
    target_datetime,
    target_datetime AT TIME ZONE 'America/Santiago' AS target_local,
    cmg_predicted,
    prob_zero,
    threshold,
    model_version
FROM ml_predictions
WHERE forecast_datetime = (SELECT MAX(forecast_datetime) FROM ml_predictions)
ORDER BY horizon;

COMMENT ON VIEW latest_ml_forecast IS 'Most recent ML forecast (24-hour horizon)';

-- ============================================================
-- STEP 6: Update Triggers for new tables
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_nodes_updated_at BEFORE UPDATE ON nodes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- STEP 7: Grant RLS Policies for new tables/views
-- ============================================================

-- Enable RLS on nodes
ALTER TABLE nodes ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read access
DROP POLICY IF EXISTS "Allow anonymous read access to nodes" ON nodes;
CREATE POLICY "Allow anonymous read access to nodes"
    ON nodes FOR SELECT
    USING (true);

-- Only service_role can write
DROP POLICY IF EXISTS "Allow service role write access to nodes" ON nodes;
CREATE POLICY "Allow service role write access to nodes"
    ON nodes FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================
-- STEP 8: Verification Queries
-- ============================================================

DO $$
DECLARE
    online_count INTEGER;
    prog_count INTEGER;
    ml_count INTEGER;
    nodes_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO online_count FROM cmg_online WHERE node_id IS NOT NULL;
    SELECT COUNT(*) INTO prog_count FROM cmg_programado WHERE node_id IS NOT NULL;
    SELECT COUNT(*) INTO ml_count FROM ml_predictions;
    SELECT COUNT(*) INTO nodes_count FROM nodes;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'MIGRATION 002 COMPLETED SUCCESSFULLY';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Nodes: % entries', nodes_count;
    RAISE NOTICE 'CMG Online: % rows migrated', online_count;
    RAISE NOTICE 'CMG Programado: % rows migrated', prog_count;
    RAISE NOTICE 'ML Predictions: % rows', ml_count;
    RAISE NOTICE '';
    RAISE NOTICE 'Old columns (node, date, hour) are KEPT for rollback safety';
    RAISE NOTICE 'Use views (*_santiago) for Santiago timezone queries';
    RAISE NOTICE 'After 7 days of verification, run 003_drop_old_columns.sql';
    RAISE NOTICE '========================================';
END$$;

COMMIT;
