#!/usr/bin/env python3
"""
Execute SQL Migration via PostgreSQL Connection
================================================
Runs the SQL migration file using psycopg2 via Supabase Transaction Pooler.
"""

import sys
from pathlib import Path
import os

try:
    import psycopg2
except ImportError:
    print("❌ psycopg2 not installed")
    sys.exit(1)

def run_migration():
    """Execute the SQL migration file via PostgreSQL connection"""

    # Connection parameters - Using Transaction Pooler (IPv4 compatible)
    # IMPORTANT: Supabase free plan requires pooler for IPv4 networks
    # Region: aws-1-sa-east-1 (South America - Chile)
    # Format: postgresql://postgres.[project-ref]:[password]@aws-1-sa-east-1.pooler.supabase.com:6543/postgres
    conn_params = {
        'host': 'aws-1-sa-east-1.pooler.supabase.com',
        'port': 6543,  # Transaction pooler port
        'dbname': 'postgres',
        'user': 'postgres.btyfbrclgmphcjgrvcgd',
        'password': 'Tabancura_1997',
        'sslmode': 'require'
    }

    # Read SQL file
    sql_file = Path(__file__).parent.parent / 'supabase' / 'migrations' / '001_migrate_cmg_programado_schema.sql'

    with open(sql_file) as f:
        sql_content = f.read()

    print("=" * 80)
    print("EXECUTING SQL MIGRATION")
    print("=" * 80)
    print(f"SQL file: {sql_file}")
    print(f"Project: btyfbrclgmphcjgrvcgd")
    print(f"Database: {conn_params['host']} (Transaction Pooler)")
    print()

    try:
        # Connect to database
        print("Connecting to Supabase...")
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = True

        print("✅ Connected successfully!")
        print()

        cursor = conn.cursor()

        # Execute SQL migration
        print("Executing migration SQL...")
        cursor.execute(sql_content)

        # Fetch any notices (RAISE NOTICE messages from the SQL)
        print()
        print("Migration output:")
        print("-" * 80)
        for notice in conn.notices:
            print(notice.strip())
        print("-" * 80)

        print()
        print("=" * 80)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 80)

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        print()
        print("=" * 80)
        print("❌ MIGRATION FAILED!")
        print("=" * 80)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
