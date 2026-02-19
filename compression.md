This is a compression scheme designed for representing DID:PLC operations in a compact way for storage in Ethereum blobs.

The scheme has two parts, differential compression and semantic-tag-based custom compression.

Differential compression
========================

- All records are CBOR-encoded.
- The first record is represented in full.
- The "prev" record in the second record tells us the previous version of the record. This is a "CID" which can be calculated by hashing the operation.
- Any entry in the original record can be identified by an index. This index is created by parsing the record, and incrementing the count every time we come to any CBOR entity, for example a number, a mapping, an entry in a mapping, a field name in a mapping, a field value in a mapping, an array or an entry in an array.
- All indices in a diff reference the *previous* operation's uncompressed structure.
- The diff consists of changes to the previous record:
  - update: "the value at index 123 should be replaced with 'newpds.example.com'"
  - delete: "the entry at index 123 should be removed" (map entry marker or array element)
  - insert: "the specified item should be added to the end of the container at index 123"
  - prepend: "the specified item should be added before the element at index 123"

Compressed file format
======================

The compressed output is a CBOR-encoded array (not valid DAG-CBOR, since it uses custom semantic tags):

    [ full_op, diff_1, diff_2, ... ]

- full_op: The first operation, with semantic tag and field name compression
  applied. Map keys use integer IDs for known field names (see below).

- diff_N: A map representing the changes from operation N-1 to operation N.
  Supported keys:

    "u" -> [[index, value], ...]   updates: replace leaf at index
    "d" -> [index, ...]            deletes: remove map entry or array element
    "i" -> [[index, value], ...]   inserts: append to container at index
    "p" -> [[index, value], ...]   prepends: insert before element at index

  For map inserts, value is [key, value_structure] where key is an integer
  field name ID (if known) or a string. For array inserts/prepends, value is
  the element itself. Empty keys are omitted.

Index semantics
===============

For delete operations on maps, the index refers to the *entry marker* index
(the implicit index between the dict itself and the key string). For arrays,
it refers to the element's index directly.

For insert operations on maps, the index refers to the dict container itself
and the value is [key_string, value_structure]. For arrays, the index refers
to the array container and the value is the element to append.

For prepend operations (arrays only), the index refers to the existing element
before which the new element should be inserted.

Field name integer keys
=======================

Known PLC field names are replaced with single-byte integer keys in all CBOR
maps (both in full_op and in nested structures within diff values). CBOR
integers 0–23 encode as a single byte, replacing string keys of 3–19 bytes.
Unknown field names are left as strings; the decompressor distinguishes by
key type (int vs str).

| ID | Field name            | Saves  |
|----|-----------------------|--------|
|  0 | sig                   | 3 bytes |
|  1 | prev                  | 4 bytes |
|  2 | type                  | 4 bytes |
|  3 | services              | 8 bytes |
|  4 | alsoKnownAs           | 11 bytes |
|  5 | rotationKeys          | 12 bytes |
|  6 | verificationMethods   | 19 bytes |
|  7 | atproto_pds           | 11 bytes |
|  8 | endpoint              | 8 bytes |
|  9 | atproto               | 7 bytes |

Semantic-tag-based custom compression
======================================

Certain items in a DID:PLC operation are not optimally encoded for size. For example, signatures are stored as base64_url-encoded strings, when they could be binary data.
For each piece of data that could be more efficiently encoded, we assign a dedicated semantic tag using a value that would not normally be allowed by DAG-CBOR (but would be allowed, and might have another assigned value, in regular CBOR).

DAG-CBOR only permits tag 42 (IPLD CID link). Any other tag number is therefore unambiguous as a custom compression marker. We use tag numbers 6-9 so each tag encodes as a single byte (0xc6-0xc9). Tags 0-5 are avoided because common CBOR libraries interpret them semantically (datetime, timestamp, bignum, etc.).

These tags are applied to values anywhere in the structure (both in full operations and in diff update values).

| Tag | Name       | Original form                          | Compressed form                                             | Savings     |
|-----|------------|----------------------------------------|-------------------------------------------------------------|-------------|
| 6   | sig        | base64url string (86 chars)            | tag(6, bytes(64)) — base64url-decode to raw signature bytes | ~24 bytes   |
| 7   | prev (CID) | base32lower CID string (59 chars)      | tag(7, bytes(36)) — binary CID (version + codec + multihash)| ~23 bytes   |
| 8   | did:key    | "did:key:zQ3sh..." string (56 chars)   | tag(8, bytes(35)) — base58btc-decode the key after "did:key:z", yielding 2-byte multicodec varint (0xe7 0x01 for secp256k1) + 33-byte compressed public key | ~21 bytes/key |
| 9   | at://      | "at://example.com" string              | tag(9, "example.com") — strip the "at://" prefix            | 5 bytes     |
