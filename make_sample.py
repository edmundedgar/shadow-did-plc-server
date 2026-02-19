#!/usr/bin/env python3
"""Create a representative sample of rotation_key_changes.json.

Uses deterministic hashing to select ~1% of DIDs, preserving the
ops-per-DID distribution. Writes to rotation_key_changes_sample.json.
"""

import hashlib
import json

SAMPLE_RATE = 100  # 1 in 100 DIDs

def should_sample(did):
    h = int(hashlib.sha256(did.encode()).hexdigest(), 16)
    return h % SAMPLE_RATE == 0

current_did = None
current_ops = []
sampled_dids = 0
sampled_ops = 0

with open("rotation_key_changes.json") as fin, \
     open("rotation_key_changes_sample.json", "w") as fout:
    fout.write("[\n")
    first = True

    for line in fin:
        line = line.strip().rstrip(",")
        if line in ("", "[", "]"):
            continue
        rec = json.loads(line)
        did = rec["did"]

        if did != current_did:
            if current_ops and should_sample(current_did):
                for op in current_ops:
                    if not first:
                        fout.write(",\n")
                    json.dump(op, fout)
                    first = False
                sampled_dids += 1
                sampled_ops += len(current_ops)
            current_did = did
            current_ops = []

        current_ops.append(rec)

    if current_ops and should_sample(current_did):
        for op in current_ops:
            if not first:
                fout.write(",\n")
            json.dump(op, fout)
            first = False
        sampled_dids += 1
        sampled_ops += len(current_ops)

    fout.write("\n]\n")

print(f"Sampled {sampled_dids} DIDs, {sampled_ops} ops")
print(f"({sampled_dids/132941*100:.1f}% of DIDs, {sampled_ops/1265327*100:.1f}% of ops)")
