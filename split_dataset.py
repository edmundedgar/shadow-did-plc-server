#!/usr/bin/env python3
"""Split rotation_key_changes.json into normal and abnormal datasets.

A DID is abnormal if any of its operations exceed THRESHOLD bytes when
dag_cbor encoded. All operations for that DID go to the abnormal file.

The size distribution has a clean bimodal split with zero DIDs between
1100 and 3400 bytes, so the threshold can go anywhere in that gap.

Outputs:
  rotation_key_changes_normal.json
  rotation_key_changes_abnormal.json
"""

import json
import dag_cbor

THRESHOLD = 1500  # bytes; natural gap is 1099-3400, so any value there works

current_did = None
current_ops = []
normal_count = 0
abnormal_count = 0

with open("rotation_key_changes.json") as fin, \
     open("rotation_key_changes_normal.json", "w") as fnorm, \
     open("rotation_key_changes_abnormal.json", "w") as fabnorm:

    fnorm.write("[\n")
    fabnorm.write("[\n")
    first_norm = True
    first_abnorm = True

    def flush(did, ops):
        global normal_count, abnormal_count, first_norm, first_abnorm
        is_abnormal = any(
            len(dag_cbor.encode(r["operation"])) > THRESHOLD for r in ops
        )
        f = fabnorm if is_abnormal else fnorm
        first_flag = "first_abnorm" if is_abnormal else "first_norm"

        for rec in ops:
            if is_abnormal:
                if not first_abnorm:
                    fabnorm.write(",\n")
                json.dump(rec, fabnorm)
                first_abnorm = False
            else:
                if not first_norm:
                    fnorm.write(",\n")
                json.dump(rec, fnorm)
                first_norm = False

        if is_abnormal:
            abnormal_count += 1
        else:
            normal_count += 1

    for line in fin:
        line = line.strip().rstrip(",")
        if line in ("", "[", "]"):
            continue
        rec = json.loads(line)
        did = rec["did"]
        if did != current_did:
            if current_ops:
                flush(current_did, current_ops)
            current_did = did
            current_ops = []
        current_ops.append(rec)

    if current_ops:
        flush(current_did, current_ops)

    fnorm.write("\n]\n")
    fabnorm.write("\n]\n")

total = normal_count + abnormal_count
print(f"Normal:   {normal_count:6d} DIDs ({normal_count/total*100:.1f}%)")
print(f"Abnormal: {abnormal_count:6d} DIDs ({abnormal_count/total*100:.1f}%)")
print(f"Total:    {total:6d} DIDs")
