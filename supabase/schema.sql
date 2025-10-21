-- ============================================================
-- PUDIDI CMG PREDICTION SYSTEM - SUPABASE SCHEMA
-- ============================================================
-- This schema replaces the Gist-based storage with a proper
-- PostgreSQL database for scalable time-series data storage.
--
-- Tables:
-- 1. cmg_online: Actual CMG values from SIP API
-- 2. cmg_programado: Forecast values from Coordinador
-- 3. ml_predictions: ML model predictions
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- TABLE 1: CMG Online (Actual Values)
-- ============================================================
CREATE TABLE IF NOT EXISTS cmg_online (
    id BIGSERIAL PRIMARY KEY,
    datetime TIMESTAMPTZ NOT NULL,
    date DATE NOT NULL,
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    node TEXT NOT NULL,
    cmg_usd DECIMAL(10, 2),
    source TEXT DEFAULT 'SIP_API_v4',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate entries for same datetime + node
    CONSTRAINT unique_cmg_online_datetime_node UNIQUE(datetime, node)
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_cmg_online_datetime ON cmg_online(datetime DESC);
CREATE INDEX IF NOT EXISTS idx_cmg_online_date_node ON cmg_online(date, node);
CREATE INDEX IF NOT EXISTS idx_cmg_online_created ON cmg_online(created_at DESC);

-- Comment for documentation
COMMENT ON TABLE cmg_online IS 'Actual CMG values fetched from SIP API every hour';
COMMENT ON COLUMN cmg_online.datetime IS 'Timestamp of the CMG value (with timezone)';
COMMENT ON COLUMN cmg_online.node IS 'Electrical node name (e.g., NVA_P.MONTT___220)';
COMMENT ON COLUMN cmg_online.cmg_usd IS 'CMG value in USD/MWh';

-- ============================================================
-- TABLE 2: CMG Programado (Scheduled Forecasts)
-- ============================================================
CREATE TABLE IF NOT EXISTS cmg_programado (
    id BIGSERIAL PRIMARY KEY,
    forecast_datetime TIMESTAMPTZ NOT NULL,
    forecast_date DATE NOT NULL,
    forecast_hour INTEGER NOT NULL CHECK (forecast_hour >= 0 AND forecast_hour <= 23),
    target_datetime TIMESTAMPTZ NOT NULL,
    target_date DATE NOT NULL,
    target_hour INTEGER NOT NULL CHECK (target_hour >= 0 AND target_hour <= 23),
    node TEXT NOT NULL,
    cmg_usd DECIMAL(10, 2),
    source TEXT DEFAULT 'Coordinador',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate entries for same forecast + target + node
    CONSTRAINT unique_cmg_prog_forecast_target_node UNIQUE(forecast_datetime, target_datetime, node)
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_cmg_prog_forecast_dt ON cmg_programado(forecast_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_cmg_prog_target_dt ON cmg_programado(target_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_cmg_prog_node ON cmg_programado(node);
CREATE INDEX IF NOT EXISTS idx_cmg_prog_target_date ON cmg_programado(target_date);
CREATE INDEX IF NOT EXISTS idx_cmg_prog_created ON cmg_programado(created_at DESC);

-- Comment for documentation
COMMENT ON TABLE cmg_programado IS 'CMG forecasts from Coordinador (scraped from website)';
COMMENT ON COLUMN cmg_programado.forecast_datetime IS 'When the forecast was made';
COMMENT ON COLUMN cmg_programado.target_datetime IS 'What hour is being forecasted';
COMMENT ON COLUMN cmg_programado.node IS 'Electrical node name (e.g., PMontt220, Pidpid110)';

-- ============================================================
-- TABLE 3: ML Predictions
-- ============================================================
CREATE TABLE IF NOT EXISTS ml_predictions (
    id BIGSERIAL PRIMARY KEY,
    forecast_datetime TIMESTAMPTZ NOT NULL,
    forecast_date DATE NOT NULL,
    forecast_hour INTEGER NOT NULL CHECK (forecast_hour >= 0 AND forecast_hour <= 23),
    target_datetime TIMESTAMPTZ NOT NULL,
    target_date DATE NOT NULL,
    target_hour INTEGER NOT NULL CHECK (target_hour >= 0 AND target_hour <= 23),
    horizon INTEGER NOT NULL CHECK (horizon >= 1 AND horizon <= 48),
    cmg_predicted DECIMAL(10, 2),
    prob_zero DECIMAL(5, 4) CHECK (prob_zero >= 0 AND prob_zero <= 1),
    threshold DECIMAL(5, 4) CHECK (threshold >= 0 AND threshold <= 1),
    value_pred DECIMAL(10, 2),
    confidence_lower DECIMAL(10, 2),
    confidence_upper DECIMAL(10, 2),
    model_version TEXT DEFAULT 'gpu_enhanced_v1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate entries for same forecast + target
    CONSTRAINT unique_ml_pred_forecast_target UNIQUE(forecast_datetime, target_datetime)
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_ml_pred_forecast_dt ON ml_predictions(forecast_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_ml_pred_target_dt ON ml_predictions(target_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_ml_pred_horizon ON ml_predictions(horizon);
CREATE INDEX IF NOT EXISTS idx_ml_pred_target_date ON ml_predictions(target_date);
CREATE INDEX IF NOT EXISTS idx_ml_pred_created ON ml_predictions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ml_pred_prob_zero ON ml_predictions(prob_zero DESC) WHERE prob_zero > 0.7;

-- Comment for documentation
COMMENT ON TABLE ml_predictions IS 'ML model predictions for CMG values';
COMMENT ON COLUMN ml_predictions.forecast_datetime IS 'When the prediction was made';
COMMENT ON COLUMN ml_predictions.target_datetime IS 'What hour is being predicted';
COMMENT ON COLUMN ml_predictions.horizon IS 'Forecast horizon (t+1, t+2, ..., t+24)';
COMMENT ON COLUMN ml_predictions.prob_zero IS 'Probability of CMG being zero (0.0-1.0)';
COMMENT ON COLUMN ml_predictions.threshold IS 'Decision threshold used for zero classification';
COMMENT ON COLUMN ml_predictions.value_pred IS 'Regression value before thresholding';

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables
CREATE TRIGGER update_cmg_online_updated_at BEFORE UPDATE ON cmg_online
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cmg_programado_updated_at BEFORE UPDATE ON cmg_programado
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ml_predictions_updated_at BEFORE UPDATE ON ml_predictions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================
-- Enable RLS on all tables for security
ALTER TABLE cmg_online ENABLE ROW LEVEL SECURITY;
ALTER TABLE cmg_programado ENABLE ROW LEVEL SECURITY;
ALTER TABLE ml_predictions ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read access (for public frontend)
CREATE POLICY "Allow anonymous read access to cmg_online"
    ON cmg_online FOR SELECT
    USING (true);

CREATE POLICY "Allow anonymous read access to cmg_programado"
    ON cmg_programado FOR SELECT
    USING (true);

CREATE POLICY "Allow anonymous read access to ml_predictions"
    ON ml_predictions FOR SELECT
    USING (true);

-- Only service_role can write (enforced by using service_role key in backend)
CREATE POLICY "Allow service role write access to cmg_online"
    ON cmg_online FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Allow service role write access to cmg_programado"
    ON cmg_programado FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Allow service role write access to ml_predictions"
    ON ml_predictions FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================
-- USEFUL VIEWS FOR ANALYTICS
-- ============================================================

-- View: Latest CMG Online values per node
CREATE OR REPLACE VIEW latest_cmg_online AS
SELECT DISTINCT ON (node)
    datetime, date, hour, node, cmg_usd, source
FROM cmg_online
ORDER BY node, datetime DESC;

-- View: Latest ML predictions by horizon
CREATE OR REPLACE VIEW latest_ml_predictions AS
SELECT DISTINCT ON (horizon)
    forecast_datetime, target_datetime, horizon,
    cmg_predicted, prob_zero, threshold, model_version
FROM ml_predictions
ORDER BY horizon, forecast_datetime DESC;

-- View: Forecast accuracy (ML vs Actual)
CREATE OR REPLACE VIEW ml_forecast_accuracy AS
SELECT
    ml.forecast_datetime,
    ml.target_datetime,
    ml.horizon,
    ml.cmg_predicted,
    ml.prob_zero,
    actual.cmg_usd AS actual_cmg,
    ABS(ml.cmg_predicted - actual.cmg_usd) AS absolute_error,
    CASE
        WHEN actual.cmg_usd = 0 THEN (ml.prob_zero > ml.threshold)
        ELSE (ml.prob_zero <= ml.threshold)
    END AS zero_classification_correct
FROM ml_predictions ml
LEFT JOIN cmg_online actual
    ON ml.target_datetime = actual.datetime
    AND actual.node = 'NVA_P.MONTT___220'
WHERE actual.cmg_usd IS NOT NULL;

COMMENT ON VIEW ml_forecast_accuracy IS 'Compare ML predictions against actual values for performance analysis';

-- ============================================================
-- SAMPLE QUERIES FOR TESTING
-- ============================================================

-- Get latest CMG Online for PMontt220
-- SELECT * FROM cmg_online WHERE node = 'NVA_P.MONTT___220' ORDER BY datetime DESC LIMIT 24;

-- Get all ML predictions for a specific date
-- SELECT * FROM ml_predictions WHERE target_date = '2025-10-20' ORDER BY target_hour, horizon;

-- Get CMG Programado forecasts made on a specific date
-- SELECT * FROM cmg_programado WHERE forecast_date = '2025-10-20' ORDER BY target_datetime;

-- Calculate ML model accuracy over last 7 days
-- SELECT
--     AVG(absolute_error) AS mae,
--     AVG(zero_classification_correct::int) AS zero_accuracy
-- FROM ml_forecast_accuracy
-- WHERE target_datetime > NOW() - INTERVAL '7 days';
