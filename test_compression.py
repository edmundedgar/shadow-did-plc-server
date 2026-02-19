#!/usr/bin/env python3
"""Test compression against rotation-key-change records.

Streams through a JSON dataset, groups by DID, compresses each DID's
operation chain, verifies round-trip, and reports stats.

Usage:
    python test_compression.py                  # uses sample (fast, ~30s)
    python test_compression.py --full           # uses full dataset (~50min)
"""

import json
import sys
import dag_cbor
from compress import compress, decompress


def stream_records(path):
    """Yield records from the JSON array file, one at a time."""
    with open(path) as f:
        for line in f:
            line = line.strip().rstrip(",")
            if line in ("", "[", "]"):
                continue
            yield json.loads(line)


def main():
    total_raw = 0
    total_compressed = 0
    total_dids = 0
    total_ops = 0
    errors = 0

    current_did = None
    current_ops = []

    def process_group():
        nonlocal total_raw, total_compressed, total_dids, total_ops, errors

        operations = [r["operation"] for r in current_ops]
        raw_size = sum(len(dag_cbor.encode(op)) for op in operations)
        total_raw += raw_size
        total_ops += len(operations)
        total_dids += 1

        compressed = compress(operations)
        total_compressed += len(compressed)

        # Verify round-trip
        restored = decompress(compressed)
        for i, (orig, rest) in enumerate(zip(operations, restored)):
            if dag_cbor.encode(orig) != dag_cbor.encode(rest):
                errors += 1
                print(f"  MISMATCH: {current_ops[0]['did']} op {i}")
                break

    if "--full" in sys.argv:
        path = "rotation_key_changes.json"
    else:
        path = "rotation_key_changes_sample.json"
    print(f"Using {path}")

    for record in stream_records(path):
        did = record["did"]
        if did != current_did:
            if current_ops:
                process_group()
            current_did = did
            current_ops = []
            if total_dids % 10000 == 0 and total_dids > 0:
                ratio = (1 - total_compressed / total_raw) * 100 if total_raw else 0
                print(f"  {total_dids} DIDs, {total_ops} ops, "
                      f"{ratio:.1f}% savings, {errors} errors")
        current_ops.append(record)

    if current_ops:
        process_group()

    print(f"\n=== Results ===")
    print(f"  DIDs:        {total_dids}")
    print(f"  Operations:  {total_ops}")
    print(f"  Raw:         {total_raw / 1e6:.1f} MB")
    print(f"  Compressed:  {total_compressed / 1e6:.1f} MB")
    print(f"  Savings:     {(1 - total_compressed / total_raw) * 100:.1f}%")
    print(f"  Errors:      {errors}")


if __name__ == "__main__":
    main()
