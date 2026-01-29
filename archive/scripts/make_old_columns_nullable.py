#!/usr/bin/env python3
"""
Make Old CMG Programado Columns Nullable
==========================================

The SQL migration added new columns but the old columns still have
NOT NULL constraints. This prevents inserting records with only new
columns populated.

This script makes the old columns nullable so we can backfill data
using the new schema.
"""

import sys
from pathlib import Path
import psycopg2

def make_columns_nullable():
    """Make old columns nullable"""

    # Connection parameters
    conn_params = {
        'host': 'aws-1-sa-east-1.pooler.supabase.com',
        'port': 6543,
        'dbname': 'postgres',
        'user': 'postgres.btyfbrclgmphcjgrvcgd',
        'password': 'Tabancura_1997',
        'sslmode': 'require'
    }

    sql = """
    -- Make old columns nullable to allow backfill with new schema
    DO $$
    BEGIN
        RAISE NOTICE 'Making old columns nullable...';

        ALTER TABLE cmg_programado ALTER COLUMN datetime DROP NOT NULL;
        ALTER TABLE cmg_programado ALTER COLUMN date DROP NOT NULL;
        ALTER TABLE cmg_programado ALTER COLUMN hour DROP NOT NULL;
        ALTER TABLE cmg_programado ALTER COLUMN cmg_programmed DROP NOT NULL;
        ALTER TABLE cmg_programado ALTER COLUMN fetched_at DROP NOT NULL;

        RAISE NOTICE 'Old columns are now nullable';
    END $$;
    """

    print("="*80)
    print("MAKING OLD COLUMNS NULLABLE")
    print("="*80)

    try:
        print("Connecting to Supabase...")
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = True

        print("✅ Connected successfully!")
        print()

        cursor = conn.cursor()

        print("Executing SQL...")
        cursor.execute(sql)

        # Print notices
        print()
        print("Result:")
        print("-" * 80)
        for notice in conn.notices:
            print(notice.strip())
        print("-" * 80)

        cursor.close()
        conn.close()

        print()
        print("✅ Old columns are now nullable!")
        print("   You can now run the backfill script.")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = make_columns_nullable()
    sys.exit(0 if success else 1)
