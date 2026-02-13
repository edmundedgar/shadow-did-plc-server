#!/usr/bin/env python3
"""Differential compression for DID:PLC operations - update operations.

Works on decoded DAG-CBOR structures. Per the did:plc spec, sig and prev
are plain strings in the CBOR (base64url and string-encoded CID respectively).

Compressed file format
======================
The compressed output is a CBOR encoded array (not valid DAG-CBOR, since it
uses custom semantic tags):

  [ full_op, diff_1, diff_2, ... ]

- full_op: The first operation, with semantic tag compression applied.

- diff_N: A map representing the changes from operation N-1 to operation N.
  Currently supports one key:

    "u" -> [[index, value], [index, value], ...]

  where each [index, value] pair is an update: replace the CBOR entity at
  the given flat index with the new value. Indices are computed against the
  *previous* operation's uncompressed structure. Values have semantic tag
  compression applied.

  Future diff types will use additional keys:
    "d" -> deletes
    "i" -> inserts
    "p" -> prepends

Semantic tag compression
========================
Custom CBOR tags (illegal in DAG-CBOR, so unambiguous) replace verbose
string encodings with compact binary forms:

  Tag 6 (sig):     base64url string -> raw 64 bytes
  Tag 7 (CID):     base32lower CID string -> raw 36 bytes
  Tag 8 (did:key): "did:key:z..." string -> raw 35 bytes (multicodec + key)
  Tag 9 (at://):   "at://..." string -> suffix string (strip "at://")
"""

import base64
import copy
import cbor2
import dag_cbor
from multiformats import multibase

# Semantic tag numbers: 6-9 are single-byte CBOR tags (0xc6-0xc9) that cbor2
# passes through without semantic interpretation. DAG-CBOR only allows tag 42,
# so any other tag is unambiguously a compression marker.
TAG_SIG = 6
TAG_CID = 7
TAG_DID_KEY = 8
TAG_AT_URI = 9

# --- Semantic tag compression ---

def sem_compress_value(val):
    """Compress a single string value using semantic tags if applicable."""
    if not isinstance(val, str):
        return val
    # did:key — "did:key:zQ3sh..." -> 35 bytes (multicodec + compressed pubkey)
    if val.startswith("did:key:"):
        return cbor2.CBORTag(TAG_DID_KEY, bytes(multibase.decode(val[8:])))
    # at:// URI — strip prefix
    if val.startswith("at://"):
        return cbor2.CBORTag(TAG_AT_URI, val[5:])
    # CID — base32lower dag-cbor sha256 CID (59 chars, "bafyrei" prefix)
    if val.startswith("bafyrei") and len(val) == 59:
        return cbor2.CBORTag(TAG_CID, bytes(multibase.decode(val)))
    # sig — 86-char base64url (no padding) -> 64 raw bytes
    if len(val) == 86:
        try:
            raw = base64.urlsafe_b64decode(val + "==")
            if len(raw) == 64:
                return cbor2.CBORTag(TAG_SIG, raw)
        except Exception:
            pass
    return val


def sem_decompress_value(val):
    """Expand a single tagged value back to its original string form."""
    if not isinstance(val, cbor2.CBORTag):
        return val
    if val.tag == TAG_SIG:
        return base64.urlsafe_b64encode(val.value).rstrip(b"=").decode()
    if val.tag == TAG_CID:
        return multibase.encode(val.value, "base32")
    if val.tag == TAG_DID_KEY:
        return "did:key:" + multibase.encode(val.value, "base58btc")
    if val.tag == TAG_AT_URI:
        return "at://" + val.value
    return val


def sem_compress(obj):
    """Recursively apply semantic tag compression to a structure."""
    if isinstance(obj, dict):
        return {k: sem_compress(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sem_compress(item) for item in obj]
    return sem_compress_value(obj)


def sem_decompress(obj):
    """Recursively expand semantic tags in a structure."""
    if isinstance(obj, cbor2.CBORTag):
        return sem_decompress_value(obj)
    if isinstance(obj, dict):
        return {k: sem_decompress(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sem_decompress(item) for item in obj]
    return obj


# --- Differential compression (unchanged) ---

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


# --- Compress / decompress pipeline ---

def compress(operations):
    """Compress a list of operations into a CBOR blob with semantic tags."""
    # Diff against uncompressed structures (indices are defined on original form)
    entries = [sem_compress(operations[0])]
    for i in range(1, len(operations)):
        updates = compute_updates(operations[i - 1], operations[i])
        # Apply semantic compression to each diff value
        compressed_updates = [[idx, sem_compress_value(val)]
                              for idx, val in sorted(updates.items())]
        entries.append({"u": compressed_updates})
    return cbor2.dumps(entries)


def decompress(data):
    """Decompress a CBOR blob back to a list of original operations."""
    entries = cbor2.loads(data)
    operations = [sem_decompress(entries[0])]
    for diff in entries[1:]:
        updates = {idx: sem_decompress_value(val) for idx, val in diff["u"]}
        operations.append(apply_updates(operations[-1], updates))
    return operations


# --- Display ---

def format_val(val):
    """Format a value for display, truncating long items."""
    if isinstance(val, cbor2.CBORTag):
        inner = val.value
        if isinstance(inner, bytes):
            return f"tag({val.tag}, <{len(inner)} bytes>)"
        return f"tag({val.tag}, {repr(inner)[:50]})"
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

    # Show diff
    updates = compute_updates(old_op, new_op)
    old_items = build_index(old_op)
    print(f"=== {len(updates)} update(s) ===")
    for idx, new_val in sorted(updates.items()):
        print(f"  [{idx}] {format_val(old_items[idx])}")
        print(f"    -> {format_val(new_val)}")

    # Show semantic compression of first operation
    print("\n=== Semantic compression (first op) ===")
    compressed_op = sem_compress(old_op)
    for idx, val in sorted(build_index(compressed_op).items()):
        print(f"  {idx:3d}: {format_val(val)}")

    # Compress
    compressed = compress(operations)
    outfile = "audit_log_example_update.compressed.cbor"
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
