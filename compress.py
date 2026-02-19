#!/usr/bin/env python3
"""Differential compression for DID:PLC operations.

Works on decoded DAG-CBOR structures. Per the did:plc spec, sig and prev
are plain strings in the CBOR (base64url and string-encoded CID respectively).

Compressed file format
======================
The compressed output is a CBOR encoded array (not valid DAG-CBOR, since it
uses custom semantic tags):

  [ full_op, diff_1, diff_2, ... ]

- full_op: The first operation, with semantic tag compression applied.

- diff_N: A map representing the changes from operation N-1 to operation N.
  All indices reference the *previous* operation's uncompressed structure.
  Supported keys:

    "u" -> [[index, value], ...]   updates: replace leaf at index
    "d" -> [index, ...]            deletes: remove map entry or array element
    "i" -> [[index, value], ...]   inserts: append to container at index
    "p" -> [[index, value], ...]   prepends: insert before element at index

  For map inserts, value is [key_string, value_structure].
  For array inserts/prepends, value is the element itself.
  Empty keys are omitted.

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
    if val.startswith("did:key:"):
        return cbor2.CBORTag(TAG_DID_KEY, bytes(multibase.decode(val[8:])))
    if val.startswith("at://"):
        return cbor2.CBORTag(TAG_AT_URI, val[5:])
    if val.startswith("bafyrei") and len(val) == 59:
        return cbor2.CBORTag(TAG_CID, bytes(multibase.decode(val)))
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


# --- Indexing helpers ---

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


def count_indices(obj):
    """Count total flat indices consumed by an object and its subtree."""
    if isinstance(obj, dict):
        total = 1  # dict itself
        for k, v in obj.items():
            total += 2  # entry marker + key
            total += count_indices(v)
        return total
    elif isinstance(obj, list):
        total = 1  # list itself
        for item in obj:
            total += count_indices(item)
        return total
    else:
        return 1  # scalar


# --- Structural diff ---

def compute_lcs(old_list, new_list):
    """Compute LCS of two lists by value equality. Returns [(old_pos, new_pos), ...]."""
    n, m = len(old_list), len(new_list)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if old_list[i - 1] == new_list[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        if old_list[i - 1] == new_list[j - 1]:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def compute_diff(old, new):
    """Compute a full structural diff between old and new operations.

    Returns (updates, deletes, inserts, prepends) where:
      updates:  {flat_idx: new_value}
      deletes:  set of flat_idx
      inserts:  {container_idx: [value, ...]}
      prepends: {element_idx: [value, ...]}

    For map inserts, each value is [key_string, value_structure].
    For array inserts/prepends, each value is the element.
    All indices reference the OLD structure.
    """
    updates = {}
    deletes = set()
    inserts = {}
    prepends = {}
    counter = [0]

    def _next():
        idx = counter[0]
        counter[0] += 1
        return idx

    def _advance(obj):
        counter[0] += count_indices(obj)

    def _diff(old_obj, new_obj):
        idx = _next()

        if isinstance(old_obj, dict) and isinstance(new_obj, dict):
            old_keys = set(old_obj.keys())
            new_keys = set(new_obj.keys())

            # Keys only in new → insert on this dict
            added = new_keys - old_keys
            if added:
                for k in sorted(added, key=lambda k: (len(k), k)):
                    inserts.setdefault(idx, []).append([k, new_obj[k]])

            # Walk old keys in order (DAG-CBOR canonical)
            for key in old_obj:
                entry_idx = _next()  # entry marker
                _next()              # key name

                if key not in new_obj:
                    deletes.add(entry_idx)
                    _advance(old_obj[key])
                else:
                    _diff(old_obj[key], new_obj[key])

        elif isinstance(old_obj, list) and isinstance(new_obj, list):
            lcs_pairs = compute_lcs(old_obj, new_obj)
            old_matched = {op for op, np in lcs_pairs}
            new_matched = {np for op, np in lcs_pairs}
            new_to_old = {np: op for op, np in lcs_pairs}

            # Record flat indices for old elements
            old_elem_indices = {}
            for i, item in enumerate(old_obj):
                old_elem_indices[i] = counter[0]
                if i in old_matched:
                    matched_new_pos = next(np for op, np in lcs_pairs if op == i)
                    _diff(item, new_obj[matched_new_pos])
                else:
                    deletes.add(counter[0])
                    _advance(item)

            # Classify new-only elements as insert or prepend
            for j in range(len(new_obj)):
                if j in new_matched:
                    continue
                # Find next LCS element after position j in new array
                next_lcs_new = None
                for np in sorted(new_matched):
                    if np > j:
                        next_lcs_new = np
                        break

                if next_lcs_new is not None:
                    old_pos = new_to_old[next_lcs_new]
                    target_idx = old_elem_indices[old_pos]
                    prepends.setdefault(target_idx, []).append(new_obj[j])
                else:
                    inserts.setdefault(idx, []).append(new_obj[j])

        elif type(old_obj) != type(new_obj):
            updates[idx] = new_obj

        else:
            if old_obj != new_obj:
                updates[idx] = new_obj

    _diff(old, new)
    return updates, deletes, inserts, prepends


def apply_diff(obj, updates, deletes, inserts, prepends):
    """Apply a full structural diff to a deep copy of obj."""
    obj = copy.deepcopy(obj)
    counter = [0]

    def _next():
        idx = counter[0]
        counter[0] += 1
        return idx

    def _advance(obj):
        counter[0] += count_indices(obj)

    def _walk(obj, setter):
        idx = _next()

        if idx in updates:
            setter(updates[idx])
            if not isinstance(obj, (dict, list)):
                return

        if isinstance(obj, dict):
            keys_to_delete = []

            for key in list(obj.keys()):
                entry_idx = _next()  # entry marker
                _next()              # key name

                if entry_idx in deletes:
                    _advance(obj[key])
                    keys_to_delete.append(key)
                else:
                    _walk(obj[key], lambda v, k=key, o=obj: o.__setitem__(k, v))

            for key in keys_to_delete:
                del obj[key]

            if idx in inserts:
                for key, val in inserts[idx]:
                    obj[key] = val

            # Re-sort to DAG-CBOR canonical order (by key length, then lexicographic)
            if keys_to_delete or idx in inserts:
                sorted_items = sorted(obj.items(), key=lambda kv: (len(kv[0]), kv[0]))
                obj.clear()
                for k, v in sorted_items:
                    obj[k] = v

        elif isinstance(obj, list):
            delete_positions = set()
            prepend_map = {}

            for i, item in enumerate(obj):
                elem_idx = counter[0]

                if elem_idx in deletes:
                    _advance(item)
                    delete_positions.add(i)
                else:
                    if elem_idx in prepends:
                        prepend_map[i] = prepends[elem_idx]
                    _walk(item, lambda v, j=i, o=obj: o.__setitem__(j, v))

            new_items = []
            for i, item in enumerate(obj):
                if i in prepend_map:
                    new_items.extend(prepend_map[i])
                if i not in delete_positions:
                    new_items.append(item)

            if idx in inserts:
                new_items.extend(inserts[idx])

            obj[:] = new_items

    _walk(obj, lambda v: None)
    return obj


# --- Legacy update-only functions (kept for reference) ---

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
    return apply_diff(obj, updates, set(), {}, {})


# --- Compress / decompress pipeline ---

def compress(operations):
    """Compress a list of operations into a CBOR blob with semantic tags."""
    entries = [sem_compress(operations[0])]
    for i in range(1, len(operations)):
        updates, deletes, inserts, prepends = compute_diff(
            operations[i - 1], operations[i])

        diff = {}
        if updates:
            diff["u"] = [[idx, sem_compress_value(val)]
                         for idx, val in sorted(updates.items())]
        if deletes:
            diff["d"] = sorted(deletes)
        if inserts:
            diff["i"] = [[idx, sem_compress(val)]
                         for idx, vals in sorted(inserts.items())
                         for val in vals]
        if prepends:
            diff["p"] = [[idx, sem_compress(val)]
                         for idx, vals in sorted(prepends.items())
                         for val in vals]
        entries.append(diff)
    return cbor2.dumps(entries)


def decompress(data):
    """Decompress a CBOR blob back to a list of original operations."""
    entries = cbor2.loads(data)
    operations = [sem_decompress(entries[0])]
    for diff in entries[1:]:
        updates = {}
        deletes = set()
        inserts = {}
        prepends = {}

        if "u" in diff:
            updates = {idx: sem_decompress_value(val) for idx, val in diff["u"]}
        if "d" in diff:
            deletes = set(diff["d"])
        if "i" in diff:
            for idx, val in diff["i"]:
                inserts.setdefault(idx, []).append(sem_decompress(val))
        if "p" in diff:
            for idx, val in diff["p"]:
                prepends.setdefault(idx, []).append(sem_decompress(val))

        operations.append(apply_diff(operations[-1], updates, deletes, inserts, prepends))
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
    import json
    import sys

    # Test against all example files
    examples = [
        "audit_log_example_update.json",
        "audit_log_example_insert.json",
        "audit_log_example_prepend.json",
        "audit_log_example_delete_map.json",
        "audit_log_example_delete_array.json",
        "audit_log_example_insert_map.json",
    ]

    total_raw = 0
    total_compressed = 0

    for filename in examples:
        try:
            with open(filename) as f:
                records = json.load(f)
        except FileNotFoundError:
            continue

        operations = [r["operation"] for r in records]
        raw_size = sum(len(dag_cbor.encode(op)) for op in operations)

        compressed = compress(operations)
        restored = decompress(compressed)

        ok = all(
            dag_cbor.encode(orig) == dag_cbor.encode(rest)
            for orig, rest in zip(operations, restored)
        )
        status = "OK" if ok else "FAIL"

        total_raw += raw_size
        total_compressed += len(compressed)

        print(f"{filename}: {len(operations)} ops, "
              f"{raw_size} -> {len(compressed)} bytes "
              f"({100*(1-len(compressed)/raw_size):.1f}% saved) [{status}]")

    if total_raw:
        print(f"\nTotal: {total_raw} -> {total_compressed} bytes "
              f"({100*(1-total_compressed/total_raw):.1f}% saved)")
