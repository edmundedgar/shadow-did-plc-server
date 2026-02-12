#!/usr/bin/env python3
"""Differential compression for DID:PLC operations - update operations.

Works on decoded DAG-CBOR structures. Per the did:plc spec, sig and prev
are plain strings in the CBOR (base64url and string-encoded CID respectively).

Compressed file format
======================
The compressed output is a single DAG-CBOR encoded array:

  [ full_op, diff_1, diff_2, ... ]

- full_op: The first operation, stored as a complete DAG-CBOR map (same
  structure as the original operation).

- diff_N: A map representing the changes from operation N-1 to operation N.
  Currently supports one key:

    "u" -> [[index, value], [index, value], ...]

  where each [index, value] pair is an update: replace the CBOR entity at
  the given flat index with the new value. The index is computed by walking
  the *previous* operation's decoded structure and incrementing a counter
  for every CBOR entity (maps, map entries, keys, values, arrays, array
  items).

  Future diff types will use additional keys:
    "d" -> deletes
    "i" -> inserts
    "p" -> prepends
"""

import sys
import copy
import dag_cbor


def build_index(obj):
    """
    Assign a flat incrementing index to every CBOR entity in the structure.
    Returns {index: value} for all entities except map entry groupings.
    """
    items = {}
    counter = [0]

    def _next():
        idx = counter[0]
        counter[0] += 1
        return idx

    def _walk(obj):
        items[_next()] = obj
        if isinstance(obj, dict):
            for key, value in obj.items():
                _next()            # map entry
                items[_next()] = key   # field name
                _walk(value)       # field value
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)        # array element

    _walk(obj)
    return items


def compute_updates(old, new):
    """Return {index: new_value} for every leaf that differs."""
    old_idx, new_idx = build_index(old), build_index(new)
    return {
        i: new_idx[i]
        for i in old_idx
        if i in new_idx
        and not isinstance(old_idx[i], (dict, list))
        and old_idx[i] != new_idx[i]
    }


def apply_updates(obj, updates):
    """Apply index-keyed value replacements to a deep copy of obj."""
    obj = copy.deepcopy(obj)
    counter = [0]

    def _next():
        idx = counter[0]
        counter[0] += 1
        return idx

    def _walk(obj, setter):
        idx = _next()
        if idx in updates:
            setter(updates[idx])
            if not isinstance(obj, (dict, list)):
                return
        if isinstance(obj, dict):
            for key in obj:
                _next()  # map entry
                _next()  # field name
                _walk(obj[key], lambda v, k=key, o=obj: o.__setitem__(k, v))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _walk(item, lambda v, j=i, o=obj: o.__setitem__(j, v))

    _walk(obj, lambda v: None)
    return obj


def compress(operations):
    """Compress a list of operations into a DAG-CBOR encoded blob."""
    entries = [operations[0]]
    for i in range(1, len(operations)):
        updates = compute_updates(operations[i - 1], operations[i])
        entries.append({"u": [[idx, val] for idx, val in sorted(updates.items())]})
    return dag_cbor.encode(entries)


def decompress(data):
    """Decompress a DAG-CBOR blob back to a list of operations."""
    entries = dag_cbor.decode(data)
    operations = [entries[0]]
    for diff in entries[1:]:
        updates = {idx: val for idx, val in diff["u"]}
        operations.append(apply_updates(operations[-1], updates))
    return operations


def format_val(val):
    """Format a value for display, truncating long items."""
    if isinstance(val, (dict, list)):
        return f"<{type(val).__name__}>"
    s = repr(val)
    return s[:70] + "..." if len(s) > 70 else s


if __name__ == "__main__":
    # Load operations from DAG-CBOR files
    with open("audit_log_example_update_0.dagcbor", "rb") as f:
        old_op = dag_cbor.decode(f.read())
    with open("audit_log_example_update_1.dagcbor", "rb") as f:
        new_op = dag_cbor.decode(f.read())
    operations = [old_op, new_op]

    # Show index of first operation
    print("=== Old operation index ===")
    for idx, val in sorted(build_index(old_op).items()):
        print(f"  {idx:3d}: {format_val(val)}")

    # Show diff
    updates = compute_updates(old_op, new_op)
    old_items = build_index(old_op)
    print(f"\n=== {len(updates)} update(s) ===")
    for idx, new_val in sorted(updates.items()):
        print(f"  [{idx}] {format_val(old_items[idx])}")
        print(f"    -> {format_val(new_val)}")

    # Compress
    compressed = compress(operations)
    outfile = "audit_log_example_update.compressed.dagcbor"
    with open(outfile, "wb") as f:
        f.write(compressed)

    raw_size = sum(len(dag_cbor.encode(op)) for op in operations)
    print(f"\n=== Compression ===")
    print(f"  Raw:        {raw_size} bytes ({len(operations)} operations)")
    print(f"  Compressed: {len(compressed)} bytes")
    print(f"  Saved:      {raw_size - len(compressed)} bytes ({100*(raw_size - len(compressed))/raw_size:.1f}%)")
    print(f"  Written to: {outfile}")

    # Round-trip: decompress and verify
    restored = decompress(compressed)
    for i, (orig, rest) in enumerate(zip(operations, restored)):
        assert orig == rest, f"Operation {i} mismatch after round-trip!"
        assert dag_cbor.encode(orig) == dag_cbor.encode(rest)
    print(f"\nVerified: round-trip decompression matches all {len(operations)} operations.")
