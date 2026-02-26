#!/usr/bin/env python3
"""Add the did_spam table to the PLC mirror database.

Schema:
  did          — primary key, joins directly to plc_log_entries.did
  detected_at  — when the row was inserted
  reason       — short code for why the DID was flagged (e.g. 'long_aka',
                 'long_endpoint')

Indexes:
  PRIMARY KEY on did  — the join index; used by any query that filters or
                        joins on did_spam.did
  idx_did_spam_detected_at — lets you pull "recently flagged" rows cheaply

Run this once against the live database; it is idempotent (CREATE IF NOT EXISTS).
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(
        host=os.environ["PLC_DB_HOST"],
        port=os.environ["PLC_DB_PORT"],
        user=os.environ["PLC_DB_USER"],
        password=os.environ["PLC_DB_PASSWORD"],
        dbname=os.environ["PLC_DB_NAME"],
    )


conn = get_connection()
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS did_spam (
        did          TEXT        PRIMARY KEY,
        detected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        reason       TEXT        NOT NULL
    )
""")

# The PRIMARY KEY already creates a B-tree index on did, which is the fast
# path for JOINs like:
#   SELECT ... FROM plc_log_entries
#   LEFT JOIN did_spam USING (did)
#   WHERE did_spam.did IS NULL   -- exclude spam
#
# Add a secondary index on detected_at for housekeeping queries.
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_did_spam_detected_at
        ON did_spam (detected_at)
""")

conn.commit()
cur.close()
conn.close()

print("did_spam table and indexes created (or already exist).")
