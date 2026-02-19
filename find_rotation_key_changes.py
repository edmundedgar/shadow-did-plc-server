#!/usr/bin/env python3
"""Count DIDs that have an operation changing their rotationKeys.

Uses the prev->cid link to join each operation with its predecessor,
comparing rotationKeys. Only scans the ~6M non-first operations.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.environ["PLC_DB_HOST"],
    port=os.environ["PLC_DB_PORT"],
    user=os.environ["PLC_DB_USER"],
    password=os.environ["PLC_DB_PASSWORD"],
    dbname=os.environ["PLC_DB_NAME"],
)

cur = conn.cursor()
cur.execute("""
    SELECT COUNT(DISTINCT cur.did)
    FROM plc_log_entries cur
    JOIN plc_log_entries prev ON prev.cid = cur.operation->>'prev'
                             AND prev.did = cur.did
    WHERE cur.nullified = false
      AND prev.nullified = false
      AND cur.operation->'rotationKeys' IS DISTINCT FROM prev.operation->'rotationKeys'
""")

count = cur.fetchone()[0]
print(f"DIDs with a rotationKeys change: {count}")

cur.close()
conn.close()
