-- ========================================
-- SUPABASE SCHEMA - SIMPLIFIED VERSION
-- CMG Prediction System
-- ========================================
-- Run this if the full schema.sql gives errors
-- ========================================

-- ========================================
-- TABLE 1: CMG ONLINE (HISTORICAL)
-- ========================================
CREATE TABLE IF NOT EXISTS cmg_online (
  id BIGSERIAL PRIMARY KEY,
  datetime TIMESTAMPTZ NOT NULL,
  date DATE NOT NULL,
  hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
  node TEXT NOT NULL,
  cmg_usd NUMERIC(10, 2) NOT NULL,
  source TEXT DEFAULT 'sip_api',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(datetime, node)
);

CREATE INDEX idx_cmg_online_datetime ON cmg_online(datetime DESC);
CREATE INDEX idx_cmg_online_date_node ON cmg_online(date, node);
CREATE INDEX idx_cmg_online_node ON cmg_online(node);

-- ========================================
-- TABLE 2: CMG PROGRAMADO (FORECAST)
-- ========================================
CREATE TABLE IF NOT EXISTS cmg_programado (
  id BIGSERIAL PRIMARY KEY,
  datetime TIMESTAMPTZ NOT NULL,
  date DATE NOT NULL,
  hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
  node TEXT NOT NULL DEFAULT 'PMontt220',
  cmg_programmed NUMERIC(10, 2) NOT NULL,
  fetched_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(datetime, node)
);

CREATE INDEX idx_cmg_programado_datetime ON cmg_programado(datetime DESC);
CREATE INDEX idx_cmg_programado_date ON cmg_programado(date);

-- ========================================
-- TABLE 3: ML PREDICTIONS
-- ========================================
CREATE TABLE IF NOT EXISTS ml_predictions (
  id BIGSERIAL PRIMARY KEY,
  forecast_datetime TIMESTAMPTZ NOT NULL,
  target_datetime TIMESTAMPTZ NOT NULL,
  horizon INTEGER NOT NULL CHECK (horizon >= 1 AND horizon <= 24),
  cmg_predicted NUMERIC(10, 2) NOT NULL,
  prob_zero NUMERIC(5, 4) DEFAULT 0,
  threshold NUMERIC(5, 4) DEFAULT 0.5,
  model_version TEXT DEFAULT 'v2.0',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(forecast_datetime, target_datetime)
);

CREATE INDEX idx_ml_predictions_forecast_datetime ON ml_predictions(forecast_datetime DESC);
CREATE INDEX idx_ml_predictions_target_datetime ON ml_predictions(target_datetime DESC);
CREATE INDEX idx_ml_predictions_horizon ON ml_predictions(horizon);

-- ========================================
-- ROW LEVEL SECURITY
-- ========================================
ALTER TABLE cmg_online ENABLE ROW LEVEL SECURITY;
ALTER TABLE cmg_programado ENABLE ROW LEVEL SECURITY;
ALTER TABLE ml_predictions ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read access (for public dashboard)
CREATE POLICY "Allow anonymous read access to cmg_online"
    ON cmg_online FOR SELECT
    USING (true);

CREATE POLICY "Allow anonymous read access to cmg_programado"
    ON cmg_programado FOR SELECT
    USING (true);

CREATE POLICY "Allow anonymous read access to ml_predictions"
    ON ml_predictions FOR SELECT
    USING (true);

-- Only service_role can write (use service_role key in backend)
CREATE POLICY "Allow service role write access to cmg_online"
    ON cmg_online FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Allow service role write access to cmg_programado"
    ON cmg_programado FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Allow service role write access to ml_predictions"
    ON ml_predictions FOR ALL
    USING (auth.role() = 'service_role');

-- ========================================
-- DONE! Tables ready to use
-- ========================================
