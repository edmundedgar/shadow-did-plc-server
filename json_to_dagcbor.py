#!/usr/bin/env python3
"""Convert the JSON audit log example to DAG-CBOR files.

Per the did:plc spec:
- 'sig' is a base64url *string* in the CBOR (not raw bytes)
- 'prev' is a string-encoded CID (not an IPLD Link/tag 42) or null
So the JSON values go into DAG-CBOR as-is.
"""

import json
import hashlib
import dag_cbor
from multiformats import CID, multihash


def op_to_cid(op):
    """Compute the CIDv1 (dag-cbor + sha-256) of an operation dict."""
    encoded = dag_cbor.encode(op)
    digest = hashlib.sha256(encoded).digest()
    mh = multihash.digest(encoded, "sha2-256")
    return CID("base32", 1, "dag-cbor", mh)


if __name__ == "__main__":
    with open("audit_log_example_update.json") as f:
        records = json.load(f)

    for i, record in enumerate(records):
        op = record["operation"]
        expected_cid = record["cid"]

        # Encode as DAG-CBOR (values are already the right types — all strings)
        encoded = dag_cbor.encode(op)
        filename = f"audit_log_example_update_{i}.dagcbor"
        with open(filename, "wb") as f:
            f.write(encoded)

        # Verify CID matches audit log
        computed_cid = str(op_to_cid(op))
        match = "OK" if computed_cid == expected_cid else "MISMATCH"
        print(f"{filename} ({len(encoded)} bytes) [{match}]")
        print(f"  expected: {expected_cid}")
        print(f"  computed: {computed_cid}")
