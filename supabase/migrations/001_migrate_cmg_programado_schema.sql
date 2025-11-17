-- ============================================================
-- CMG PROGRAMADO SCHEMA MIGRATION
-- ============================================================
-- Migrates from old schema (datetime, fetched_at, cmg_programmed)
-- to new schema (forecast_datetime, target_datetime, cmg_usd)
--
-- Run this in Supabase SQL Editor:
-- https://btyfbrclgmphcjgrvcgd.supabase.co/project/_/sql
-- ============================================================

-- Step 1: Add new columns
DO $$
BEGIN
    RAISE NOTICE 'Adding new columns...';

    -- Add forecast columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='cmg_programado' AND column_name='forecast_datetime') THEN
        ALTER TABLE cmg_programado ADD COLUMN forecast_datetime TIMESTAMPTZ;
        RAISE NOTICE 'Added forecast_datetime column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='cmg_programado' AND column_name='forecast_date') THEN
        ALTER TABLE cmg_programado ADD COLUMN forecast_date DATE;
        RAISE NOTICE 'Added forecast_date column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='cmg_programado' AND column_name='forecast_hour') THEN
        ALTER TABLE cmg_programado ADD COLUMN forecast_hour INTEGER
            CHECK (forecast_hour >= 0 AND forecast_hour <= 23);
        RAISE NOTICE 'Added forecast_hour column';
    END IF;

    -- Add target columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='cmg_programado' AND column_name='target_datetime') THEN
        ALTER TABLE cmg_programado ADD COLUMN target_datetime TIMESTAMPTZ;
        RAISE NOTICE 'Added target_datetime column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='cmg_programado' AND column_name='target_date') THEN
        ALTER TABLE cmg_programado ADD COLUMN target_date DATE;
        RAISE NOTICE 'Added target_date column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='cmg_programado' AND column_name='target_hour') THEN
        ALTER TABLE cmg_programado ADD COLUMN target_hour INTEGER
            CHECK (target_hour >= 0 AND target_hour <= 23);
        RAISE NOTICE 'Added target_hour column';
    END IF;

    -- Add cmg_usd column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='cmg_programado' AND column_name='cmg_usd') THEN
        ALTER TABLE cmg_programado ADD COLUMN cmg_usd DECIMAL(10, 2);
        RAISE NOTICE 'Added cmg_usd column';
    END IF;

    RAISE NOTICE 'All new columns added successfully';
END $$;

-- Step 2: Populate new columns from old columns
DO $$
DECLARE
    row_count INTEGER;
BEGIN
    RAISE NOTICE 'Migrating data from old columns to new columns...';

    UPDATE cmg_programado
    SET
        target_datetime = datetime,
        target_date = date,
        target_hour = hour,
        forecast_datetime = fetched_at,
        forecast_date = DATE(fetched_at),
        forecast_hour = EXTRACT(HOUR FROM fetched_at)::INTEGER,
        cmg_usd = cmg_programmed
    WHERE target_datetime IS NULL;

    GET DIAGNOSTICS row_count = ROW_COUNT;
    RAISE NOTICE 'Migrated % rows', row_count;
END $$;

-- Step 3: Drop old constraints
DO $$
BEGIN
    RAISE NOTICE 'Dropping old constraints...';

    ALTER TABLE cmg_programado DROP CONSTRAINT IF EXISTS unique_cmg_programado_datetime_node;
    ALTER TABLE cmg_programado DROP CONSTRAINT IF EXISTS unique_cmg_prog_forecast_target_node;

    RAISE NOTICE 'Old constraints dropped';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Some constraints did not exist (OK)';
END $$;

-- Step 4: Add new unique constraint
DO $$
BEGIN
    RAISE NOTICE 'Adding new unique constraint...';

    ALTER TABLE cmg_programado
    ADD CONSTRAINT unique_cmg_prog_forecast_target_node
    UNIQUE(forecast_datetime, target_datetime, node);

    RAISE NOTICE 'New unique constraint added';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Constraint may already exist (OK)';
END $$;

-- Step 5: Create indexes
DO $$
BEGIN
    RAISE NOTICE 'Creating indexes...';

    CREATE INDEX IF NOT EXISTS idx_cmg_prog_forecast_dt
        ON cmg_programado(forecast_datetime DESC);

    CREATE INDEX IF NOT EXISTS idx_cmg_prog_target_dt
        ON cmg_programado(target_datetime DESC);

    CREATE INDEX IF NOT EXISTS idx_cmg_prog_node
        ON cmg_programado(node);

    CREATE INDEX IF NOT EXISTS idx_cmg_prog_target_date
        ON cmg_programado(target_date);

    RAISE NOTICE 'Indexes created successfully';
END $$;

-- Step 6: Verify migration
DO $$
DECLARE
    total_rows INTEGER;
    null_count INTEGER;
BEGIN
    RAISE NOTICE 'Verifying migration...';

    SELECT COUNT(*) INTO total_rows FROM cmg_programado;
    RAISE NOTICE 'Total rows: %', total_rows;

    SELECT COUNT(*) INTO null_count FROM cmg_programado
    WHERE forecast_datetime IS NULL OR target_datetime IS NULL OR cmg_usd IS NULL;

    IF null_count > 0 THEN
        RAISE WARNING 'Found % rows with NULL values in new columns!', null_count;
    ELSE
        RAISE NOTICE 'All rows migrated successfully - no NULL values';
    END IF;
END $$;

-- ============================================================
-- OPTIONAL: Drop old columns (RUN THIS LATER, AFTER VERIFICATION!)
-- ============================================================
-- Uncomment and run ONLY after you've verified the migration worked:

-- ALTER TABLE cmg_programado DROP COLUMN IF EXISTS datetime;
-- ALTER TABLE cmg_programado DROP COLUMN IF EXISTS date;
-- ALTER TABLE cmg_programado DROP COLUMN IF EXISTS hour;
-- ALTER TABLE cmg_programado DROP COLUMN IF EXISTS cmg_programmed;
-- ALTER TABLE cmg_programado DROP COLUMN IF EXISTS fetched_at;

-- RAISE NOTICE 'Old columns dropped - migration complete!';
