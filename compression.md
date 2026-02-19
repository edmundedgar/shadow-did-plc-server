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

- full_op: The first operation with semantic tag compression applied (see
  below). Both values and map keys are compressed using tags.

- diff_N: A map representing the changes from operation N-1 to operation N.
  Supported keys:

    "u" -> [[index, value], ...]   updates: replace leaf at index
    "d" -> [index, ...]            deletes: remove map entry or array element
    "i" -> [[index, value], ...]   inserts: append to container at index
    "p" -> [[index, value], ...]   prepends: insert before element at index

  For map inserts, value is [key, value_structure] where key is tag(N, null)
  (if a known field name) or a string. For array inserts/prepends, value is
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

Semantic tag compression
========================

DAG-CBOR only permits tag 42 (IPLD CID link). Any other tag number is
therefore unambiguous as a custom compression marker. Tags 0–5 are avoided
because common CBOR libraries interpret them semantically (datetime,
timestamp, bignum, etc.). All tags used here fit in a single byte (0xc6–0xd3).

Value tags (6–9) replace verbose string values wherever they appear —
in full operations and in diff update/insert/prepend values:

| Tag | Replaces                               | Compressed form                         | Savings       |
|-----|----------------------------------------|-----------------------------------------|---------------|
|   6 | base64url sig string (86 chars)        | tag(6, bytes(64)) — raw signature       | ~24 bytes     |
|   7 | base32lower CID string (59 chars)      | tag(7, bytes(36)) — binary CID          | ~23 bytes     |
|   8 | "did:key:zQ3sh..." string (56 chars)   | tag(8, bytes(35)) — multicodec + pubkey | ~21 bytes/key |
|   9 | "at://example.com" string              | tag(9, "example.com") — strip prefix   | 5 bytes       |

Field name tags (10–19) replace string map keys with tag(N, null) (2 bytes),
applied in full operations and in nested structures within diff values.
Unknown field names are left as strings.

| Tag | Field name            | Net savings |
|-----|-----------------------|-------------|
|  10 | sig                   | 2 bytes     |
|  11 | prev                  | 3 bytes     |
|  12 | type                  | 3 bytes     |
|  13 | services              | 7 bytes     |
|  14 | alsoKnownAs           | 10 bytes    |
|  15 | rotationKeys          | 11 bytes    |
|  16 | verificationMethods   | 18 bytes    |
|  17 | atproto_pds           | 10 bytes    |
|  18 | endpoint              | 7 bytes     |
|  19 | atproto               | 6 bytes     |
