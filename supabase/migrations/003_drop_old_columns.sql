-- ============================================================
-- MIGRATION 003: Drop Old Redundant Columns (CLEANUP)
-- ============================================================
-- Date: TBD (Run AFTER 7 days of verification)
-- Purpose: Remove duplicate date/hour/node columns
-- Risk Level: MEDIUM (destructive - ensure backups exist!)
-- ============================================================

-- ⚠️  PREREQUISITES:
-- 1. Migration 002 has been running for 7+ days
-- 2. All applications are using *_santiago views or node_id
-- 3. Backup database before running this script
-- 4. Verify no queries reference old columns

-- ============================================================
-- STEP 1: Verify Views are Working
-- ============================================================

DO $$
DECLARE
    view_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO view_count
    FROM information_schema.views
    WHERE table_schema = 'public'
    AND table_name IN ('cmg_online_santiago', 'cmg_programado_santiago', 'ml_predictions_santiago');

    IF view_count < 3 THEN
        RAISE EXCEPTION 'Migration views not found! Run 002_normalize_schema.sql first.';
    END IF;

    RAISE NOTICE 'All views exist - safe to proceed';
END$$;

-- ============================================================
-- STEP 2: Drop Redundant Columns from cmg_online
-- ============================================================

BEGIN;

-- Drop old columns
ALTER TABLE cmg_online
    DROP COLUMN IF EXISTS date CASCADE,
    DROP COLUMN IF EXISTS hour CASCADE,
    DROP COLUMN IF EXISTS node CASCADE;

-- Update indexes (old ones are cascade-dropped)
DROP INDEX IF EXISTS idx_cmg_online_date_node;

RAISE NOTICE 'Dropped redundant columns from cmg_online (date, hour, node)';

-- ============================================================
-- STEP 3: Drop Redundant Columns from cmg_programado
-- ============================================================

-- Drop old columns
ALTER TABLE cmg_programado
    DROP COLUMN IF EXISTS forecast_date CASCADE,
    DROP COLUMN IF EXISTS forecast_hour CASCADE,
    DROP COLUMN IF EXISTS target_date CASCADE,
    DROP COLUMN IF EXISTS target_hour CASCADE,
    DROP COLUMN IF EXISTS node CASCADE;

-- Drop old indexes
DROP INDEX IF EXISTS idx_cmg_prog_target_date;

RAISE NOTICE 'Dropped redundant columns from cmg_programado (forecast_date, forecast_hour, target_date, target_hour, node)';

-- ============================================================
-- STEP 4: Drop Redundant Columns from ml_predictions
-- ============================================================

-- NOTE: ml_predictions columns may not exist in actual DB yet
-- (they were in schema.sql but migration 001 showed they weren't created)
ALTER TABLE ml_predictions
    DROP COLUMN IF EXISTS forecast_date CASCADE,
    DROP COLUMN IF EXISTS forecast_hour CASCADE,
    DROP COLUMN IF EXISTS target_date CASCADE,
    DROP COLUMN IF EXISTS target_hour CASCADE;

-- Drop old indexes
DROP INDEX IF EXISTS idx_ml_pred_target_date;

RAISE NOTICE 'Dropped redundant columns from ml_predictions (forecast_date, forecast_hour, target_date, target_hour)';

-- ============================================================
-- STEP 5: Recreate Views (in case cascade broke them)
-- ============================================================

-- Recreate all views to ensure they still work
\i 002_normalize_schema.sql

-- ============================================================
-- STEP 6: Final Verification
-- ============================================================

DO $$
DECLARE
    online_cols TEXT[];
    prog_cols TEXT[];
    ml_cols TEXT[];
BEGIN
    -- Check remaining columns
    SELECT array_agg(column_name ORDER BY ordinal_position) INTO online_cols
    FROM information_schema.columns
    WHERE table_name = 'cmg_online' AND table_schema = 'public';

    SELECT array_agg(column_name ORDER BY ordinal_position) INTO prog_cols
    FROM information_schema.columns
    WHERE table_name = 'cmg_programado' AND table_schema = 'public';

    SELECT array_agg(column_name ORDER BY ordinal_position) INTO ml_cols
    FROM information_schema.columns
    WHERE table_name = 'ml_predictions' AND table_schema = 'public';

    RAISE NOTICE '========================================';
    RAISE NOTICE 'MIGRATION 003 COMPLETED';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'cmg_online columns: %', online_cols;
    RAISE NOTICE 'cmg_programado columns: %', prog_cols;
    RAISE NOTICE 'ml_predictions columns: %', ml_cols;
    RAISE NOTICE '';
    RAISE NOTICE 'Schema is now fully normalized!';
    RAISE NOTICE 'Use *_santiago views for Santiago timezone queries';
    RAISE NOTICE '========================================';
END$$;

COMMIT;

-- ============================================================
-- EXPECTED FINAL SCHEMA
-- ============================================================

-- cmg_online: id, datetime, node_id, cmg_usd, source, created_at, updated_at
-- cmg_programado: id, forecast_datetime, target_datetime, node_id, cmg_usd, source, created_at, updated_at
-- ml_predictions: id, forecast_datetime, target_datetime, horizon, cmg_predicted, prob_zero, threshold, model_version, created_at, updated_at
-- nodes: id, code, name, region, voltage_kv, latitude, longitude, is_active, created_at, updated_at
