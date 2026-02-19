#!/usr/bin/env python3
"""Export example audit logs for each diff type."""

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

EXAMPLES = {
    "insert": "did:plc:go2bcmsadpur2xclphjbtspb",
    "prepend": "did:plc:gcienmzzp3sbfurcnkqtcx4m",
    "delete_map": "did:plc:cb63f75img3xmjko4y6vomek",
    "delete_array": "did:plc:sjapw75zw6cmo53qg4wyc525",
    "insert_map": "did:plc:4j6e6lhmrjsihjtshsuh3chk",
}

cur = conn.cursor()
for name, did in EXAMPLES.items():
    cur.execute(
        "SELECT did, cid, operation, nullified, plc_timestamp "
        "FROM plc_log_entries WHERE did = %s ORDER BY plc_timestamp ASC",
        (did,),
    )
    rows = cur.fetchall()
    records = [
        {"did": r[0], "cid": r[1], "operation": r[2],
         "nullified": r[3], "createdAt": r[4]}
        for r in rows
    ]
    filename = f"audit_log_example_{name}.json"
    with open(filename, "w") as f:
        json.dump(records, f)
    print(f"{filename}: {len(records)} records for {did}")

cur.close()
conn.close()
