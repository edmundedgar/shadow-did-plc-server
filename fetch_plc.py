#!/usr/bin/env python3
"""Fetch records from the plc_log_entries table."""

import json
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


def fetch_operations(did, limit=10):
    """Fetch PLC operations for a DID, ordered by timestamp."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT did, cid, operation, nullified, plc_timestamp "
        "FROM plc_log_entries WHERE did = %s ORDER BY plc_timestamp ASC LIMIT %s",
        (did, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"did": r[0], "cid": r[1], "operation": r[2],
         "nullified": r[3], "createdAt": r[4]}
        for r in rows
    ]


if __name__ == "__main__":
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT did, cid, operation, nullified, plc_timestamp "
        "FROM plc_log_entries LIMIT 1"
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    print(f"DID: {row[0]}")
    print(f"CID: {row[1]}")
    print(f"Nullified: {row[3]}")
    print(f"Timestamp: {row[4]}")
    print(f"Operation: {json.dumps(row[2], indent=2)}")
