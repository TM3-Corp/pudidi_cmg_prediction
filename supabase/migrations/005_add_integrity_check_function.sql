-- ============================================================
-- MIGRATION 005: Add Data Integrity Check RPC Function
-- ============================================================
-- Date: 2025-11-24
-- Purpose: Provide efficient single-call data integrity validation
--
-- This function reduces 504 API calls to 1 call by performing
-- server-side aggregation across all three data sources.
--
-- Usage (via PostgREST):
--   POST /rest/v1/rpc/check_data_integrity
--   Body: {"p_start_date": "2025-11-18", "p_end_date": "2025-11-24"}
--
-- Returns: Array of daily summaries with completeness metrics
-- ============================================================

-- Drop existing function if it exists (for re-running migration)
DROP FUNCTION IF EXISTS check_data_integrity(DATE, DATE);

-- ============================================================
-- MAIN FUNCTION: check_data_integrity
-- ============================================================
CREATE OR REPLACE FUNCTION check_data_integrity(
    p_start_date DATE,
    p_end_date DATE
)
RETURNS TABLE(
    check_date DATE,
    -- ML Predictions metrics
    ml_total INTEGER,
    ml_expected INTEGER,
    ml_complete_hours INTEGER,
    ml_missing_hours INTEGER[],
    ml_incomplete_hours JSONB,  -- Array of {hour, count} for hours with <24 records
    -- CMG Programado metrics
    prog_forecast_hours INTEGER,
    prog_expected INTEGER,
    prog_missing_hours INTEGER[],
    -- CMG Online metrics
    online_total INTEGER,
    online_expected INTEGER,
    online_complete_hours INTEGER,
    online_missing_hours INTEGER[],
    online_incomplete_hours JSONB  -- Array of {hour, count, nodes} for hours with <3 nodes
)
LANGUAGE plpgsql
STABLE  -- Function doesn't modify data
AS $$
BEGIN
    RETURN QUERY
    WITH date_series AS (
        -- Generate all dates in the range
        SELECT generate_series(p_start_date, p_end_date, '1 day'::interval)::DATE as date
    ),
    hour_series AS (
        -- Generate all 24 hours (0-23)
        SELECT generate_series(0, 23) as hour
    ),
    all_date_hours AS (
        -- Cross join to get all date-hour combinations
        SELECT ds.date, hs.hour
        FROM date_series ds
        CROSS JOIN hour_series hs
    ),

    -- ============================================================
    -- ML Predictions Aggregation
    -- Expected: 24 predictions per forecast hour = 576 per day
    -- ============================================================
    ml_hourly AS (
        SELECT
            forecast_date,
            forecast_hour,
            COUNT(*) as record_count
        FROM ml_predictions_santiago
        WHERE forecast_date BETWEEN p_start_date AND p_end_date
        GROUP BY forecast_date, forecast_hour
    ),
    ml_daily AS (
        SELECT
            adh.date,
            COALESCE(SUM(mh.record_count), 0)::INTEGER as total_records,
            COUNT(CASE WHEN mh.record_count = 24 THEN 1 END)::INTEGER as complete_hours,
            ARRAY_AGG(adh.hour ORDER BY adh.hour)
                FILTER (WHERE mh.record_count IS NULL OR mh.record_count = 0) as missing_hours,
            JSONB_AGG(
                jsonb_build_object('hour', adh.hour, 'count', mh.record_count)
                ORDER BY adh.hour
            ) FILTER (WHERE mh.record_count > 0 AND mh.record_count < 24) as incomplete_hours
        FROM all_date_hours adh
        LEFT JOIN ml_hourly mh
            ON adh.date = mh.forecast_date AND adh.hour = mh.forecast_hour
        GROUP BY adh.date
    ),

    -- ============================================================
    -- CMG Programado Aggregation
    -- Expected: 24 forecast hours per day (each with ~72 predictions)
    -- ============================================================
    prog_hourly AS (
        SELECT
            forecast_date,
            forecast_hour,
            COUNT(*) as record_count
        FROM cmg_programado_santiago
        WHERE forecast_date BETWEEN p_start_date AND p_end_date
        GROUP BY forecast_date, forecast_hour
    ),
    prog_daily AS (
        SELECT
            adh.date,
            COUNT(CASE WHEN ph.record_count > 0 THEN 1 END)::INTEGER as forecast_hours,
            ARRAY_AGG(adh.hour ORDER BY adh.hour)
                FILTER (WHERE ph.record_count IS NULL OR ph.record_count = 0) as missing_hours
        FROM all_date_hours adh
        LEFT JOIN prog_hourly ph
            ON adh.date = ph.forecast_date AND adh.hour = ph.forecast_hour
        GROUP BY adh.date
    ),

    -- ============================================================
    -- CMG Online Aggregation
    -- Expected: 3 nodes per hour = 72 per day
    -- ============================================================
    online_hourly AS (
        SELECT
            date,
            hour,
            COUNT(*) as record_count,
            ARRAY_AGG(DISTINCT node) as nodes_present
        FROM cmg_online_santiago
        WHERE date BETWEEN p_start_date AND p_end_date
        GROUP BY date, hour
    ),
    online_daily AS (
        SELECT
            adh.date,
            COALESCE(SUM(oh.record_count), 0)::INTEGER as total_records,
            COUNT(CASE WHEN oh.record_count = 3 THEN 1 END)::INTEGER as complete_hours,
            ARRAY_AGG(adh.hour ORDER BY adh.hour)
                FILTER (WHERE oh.record_count IS NULL OR oh.record_count = 0) as missing_hours,
            JSONB_AGG(
                jsonb_build_object(
                    'hour', adh.hour,
                    'count', oh.record_count,
                    'nodes', oh.nodes_present
                )
                ORDER BY adh.hour
            ) FILTER (WHERE oh.record_count > 0 AND oh.record_count < 3) as incomplete_hours
        FROM all_date_hours adh
        LEFT JOIN online_hourly oh
            ON adh.date = oh.date AND adh.hour = oh.hour
        GROUP BY adh.date
    )

    -- ============================================================
    -- Final Result: Join all aggregations
    -- ============================================================
    SELECT
        ds.date as check_date,
        -- ML Predictions
        COALESCE(ml.total_records, 0) as ml_total,
        576 as ml_expected,
        COALESCE(ml.complete_hours, 0) as ml_complete_hours,
        COALESCE(ml.missing_hours, ARRAY[]::INTEGER[]) as ml_missing_hours,
        COALESCE(ml.incomplete_hours, '[]'::JSONB) as ml_incomplete_hours,
        -- CMG Programado
        COALESCE(prog.forecast_hours, 0) as prog_forecast_hours,
        24 as prog_expected,
        COALESCE(prog.missing_hours, ARRAY[]::INTEGER[]) as prog_missing_hours,
        -- CMG Online
        COALESCE(online.total_records, 0) as online_total,
        72 as online_expected,
        COALESCE(online.complete_hours, 0) as online_complete_hours,
        COALESCE(online.missing_hours, ARRAY[]::INTEGER[]) as online_missing_hours,
        COALESCE(online.incomplete_hours, '[]'::JSONB) as online_incomplete_hours
    FROM date_series ds
    LEFT JOIN ml_daily ml ON ds.date = ml.date
    LEFT JOIN prog_daily prog ON ds.date = prog.date
    LEFT JOIN online_daily online ON ds.date = online.date
    ORDER BY ds.date;
END;
$$;

-- ============================================================
-- DOCUMENTATION
-- ============================================================
COMMENT ON FUNCTION check_data_integrity IS
'Efficient data integrity check that returns daily summaries for all data sources in a single query.

Parameters:
  p_start_date: First date to check (inclusive)
  p_end_date: Last date to check (inclusive)

Returns for each date:
  ML Predictions:
    - ml_total: Total records (expected: 576)
    - ml_expected: 576 (24 hours × 24 predictions)
    - ml_complete_hours: Hours with exactly 24 predictions
    - ml_missing_hours: Array of hours with 0 records
    - ml_incomplete_hours: JSONB array of {hour, count} for partial hours

  CMG Programado:
    - prog_forecast_hours: Count of hours with forecasts (expected: 24)
    - prog_expected: 24 hours
    - prog_missing_hours: Array of hours with 0 forecasts

  CMG Online:
    - online_total: Total records (expected: 72)
    - online_expected: 72 (24 hours × 3 nodes)
    - online_complete_hours: Hours with exactly 3 nodes
    - online_missing_hours: Array of hours with 0 records
    - online_incomplete_hours: JSONB array of {hour, count, nodes} for partial hours

Example:
  SELECT * FROM check_data_integrity(''2025-11-18''::DATE, ''2025-11-24''::DATE);

  POST /rest/v1/rpc/check_data_integrity
  {"p_start_date": "2025-11-18", "p_end_date": "2025-11-24"}
';

-- ============================================================
-- PERMISSIONS
-- ============================================================
-- Grant execute permission to all roles that need it
GRANT EXECUTE ON FUNCTION check_data_integrity TO anon;
GRANT EXECUTE ON FUNCTION check_data_integrity TO authenticated;
GRANT EXECUTE ON FUNCTION check_data_integrity TO service_role;

-- ============================================================
-- VERIFICATION
-- ============================================================
DO $$
BEGIN
    -- Verify function exists
    IF EXISTS (
        SELECT 1 FROM pg_proc
        WHERE proname = 'check_data_integrity'
    ) THEN
        RAISE NOTICE '✅ MIGRATION 005 COMPLETED: check_data_integrity function created';
        RAISE NOTICE '';
        RAISE NOTICE 'Test with: SELECT * FROM check_data_integrity(CURRENT_DATE - 7, CURRENT_DATE);';
        RAISE NOTICE '';
        RAISE NOTICE 'API Usage:';
        RAISE NOTICE '  POST /rest/v1/rpc/check_data_integrity';
        RAISE NOTICE '  Body: {"p_start_date": "2025-11-18", "p_end_date": "2025-11-24"}';
    ELSE
        RAISE EXCEPTION '❌ MIGRATION 005 FAILED: Function not created';
    END IF;
END$$;
