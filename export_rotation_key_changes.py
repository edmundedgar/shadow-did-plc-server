#!/usr/bin/env python3
"""Export all records for DIDs that have a rotationKeys change."""

import json
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

cur = conn.cursor(name="export_cursor")
cur.itersize = 10000
cur.execute("""
    SELECT e.did, e.cid, e.operation, e.nullified, e.plc_timestamp
    FROM plc_log_entries e
    JOIN (
        SELECT DISTINCT cur.did
        FROM plc_log_entries cur
        JOIN plc_log_entries prev ON prev.cid = cur.operation->>'prev'
                                 AND prev.did = cur.did
        WHERE cur.nullified = false
          AND prev.nullified = false
          AND cur.operation->'rotationKeys' IS DISTINCT FROM prev.operation->'rotationKeys'
    ) changed ON changed.did = e.did
    ORDER BY e.did, e.plc_timestamp ASC
""")

outfile = "rotation_key_changes.json"
count = 0
with open(outfile, "w") as f:
    f.write("[\n")
    first = True
    for did, cid, operation, nullified, plc_timestamp in cur:
        if not first:
            f.write(",\n")
        json.dump({
            "did": did,
            "cid": cid,
            "operation": operation,
            "nullified": nullified,
            "createdAt": plc_timestamp,
        }, f)
        first = False
        count += 1
        if count % 100000 == 0:
            print(f"  exported {count} records...")
    f.write("\n]\n")

cur.close()
conn.close()

print(f"Exported {count} records to {outfile}")
