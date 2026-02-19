#!/usr/bin/env python3
"""Create representative samples of the rotation_key_changes datasets.

Uses deterministic hashing to select ~1% of DIDs, preserving the
ops-per-DID distribution.

Reads:
  rotation_key_changes.json
  rotation_key_changes_normal.json

Writes:
  rotation_key_changes_sample.json
  rotation_key_changes_normal_sample.json
"""

import hashlib
import json

SAMPLE_RATE = 100  # 1 in 100 DIDs


def should_sample(did):
    h = int(hashlib.sha256(did.encode()).hexdigest(), 16)
    return h % SAMPLE_RATE == 0


def make_sample(input_path, output_path):
    current_did = None
    current_ops = []
    sampled_dids = 0
    sampled_ops = 0
    total_dids = 0

    with open(input_path) as fin, open(output_path, "w") as fout:
        fout.write("[\n")
        first = True

        for line in fin:
            line = line.strip().rstrip(",")
            if line in ("", "[", "]"):
                continue
            rec = json.loads(line)
            did = rec["did"]

            if did != current_did:
                if current_ops:
                    total_dids += 1
                    if should_sample(current_did):
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

        if current_ops:
            total_dids += 1
            if should_sample(current_did):
                for op in current_ops:
                    if not first:
                        fout.write(",\n")
                    json.dump(op, fout)
                    first = False
                sampled_dids += 1
                sampled_ops += len(current_ops)

        fout.write("\n]\n")

    print(f"{output_path}: {sampled_dids} DIDs, {sampled_ops} ops "
          f"({sampled_dids/total_dids*100:.1f}% of {total_dids} DIDs)")


make_sample("rotation_key_changes.json", "rotation_key_changes_sample.json")

# Use a higher rate for the normal dataset since it's much smaller (9,855 DIDs)
SAMPLE_RATE = 10
make_sample("rotation_key_changes_normal.json", "rotation_key_changes_normal_sample.json")
