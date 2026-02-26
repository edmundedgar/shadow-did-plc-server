#!/usr/bin/env python3
"""Find abnormal DID records in plc_log_entries and mark them in did_spam.

Detection: a DID is spam if any of its operations has a JSON text
representation longer than JSON_THRESHOLD bytes.

The observed size distribution has a clean bimodal gap: normal operations
are <~1500 bytes of JSON text, spam operations are >~4000 bytes (they use
255-char alsoKnownAs handles and 511-char service endpoints). A threshold
of 3000 bytes sits comfortably in the gap.

Using length(operation::text) avoids JSONB unnesting, keeping the scan fast
on a table with millions of rows.

The script scans ALL DIDs in plc_log_entries (not just those with rotation
key changes). It is idempotent: ON CONFLICT DO NOTHING skips already-marked
DIDs, so it is safe to re-run as new data arrives.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

JSON_THRESHOLD = 3000  # bytes of operation::text; gap is ~1500–4000


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
    INSERT INTO did_spam (did, reason)
    SELECT DISTINCT did, 'large_operation' AS reason
    FROM plc_log_entries
    WHERE length(operation::text) > %(threshold)s
    ON CONFLICT (did) DO NOTHING
""", {"threshold": JSON_THRESHOLD})

inserted = cur.rowcount
conn.commit()
cur.close()
conn.close()

print(f"Marked {inserted} new DIDs as spam.")
