-- ============================================================
-- MIGRATION 004: Fix forecast_comparison View
-- ============================================================
-- Date: 2025-11-19
-- Purpose: Fix ML predictions matching with CMG Programado
-- Issue: forecast_datetime values were not matching because:
--   - ML predictions: hour-aligned (11:00:00)
--   - CMG Programado: exact scrape time (11:31:03.359887)
-- Solution: Join on hour-truncated timestamps
-- ============================================================

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
    -- Join on HOUR-TRUNCATED timestamps (matches forecasts made in same hour)
    ON date_trunc('hour', ml.forecast_datetime) = date_trunc('hour', prog.forecast_datetime)
    AND ml.target_datetime = prog.target_datetime
LEFT JOIN nodes n ON prog.node_id = n.id
LEFT JOIN cmg_online actual
    ON ml.target_datetime = actual.datetime
    AND prog.node_id = actual.node_id
WHERE actual.cmg_usd IS NOT NULL;

COMMENT ON VIEW forecast_comparison IS 'Compare ML predictions, CMG Programado, and actual values. Joins on hour-truncated forecast_datetime to match predictions made in the same hour.';

-- Verification
DO $$
DECLARE
    match_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO match_count FROM forecast_comparison;

    IF match_count = 0 THEN
        RAISE WARNING 'forecast_comparison view has no matches!';
    ELSE
        RAISE NOTICE 'forecast_comparison view has % matches', match_count;
    END IF;
END$$;
