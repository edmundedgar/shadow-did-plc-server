This is a compression scheme designed for representing DID:PLC operations in a compact way for storage in Ethereum blobs.

The scheme has two parts, differential compression and semantic-tag-based custom compression.

Differential compression

- All records are CBOR-encoded.
- The first record is represented in full.
- The "prev" record in the second record tells us the previous version of the record. This is a "CID" which can be calculated by hashing the operation.
- Any entry in the original record can be identified by an index. This index is created by parsing the record, and incrementing the count every time we come to any CBOR entity, for example a number, a mapping, an entry in a mapping, a field name in a mapping, a field value in a mapping, an array or an entry in an array.
- The diff consists of changes to the first record, 
  - update: "the value at index 123 should be "newpds.example.com".
  - delete: "the mapping at index 123 should be removed"
  - insert: "the specified item should be added to the end of the array at index 123"
  - prepend: "the specified item should be added before the item at index 123"

Semantic-tag-based custom compression

Certain items in a DID:PLC operation are not optimally encoded for size. For example, signatures are stored as base64_url-encoded strings, when they could be binary data.
For each piece of data that could be more efficiently encoded, we will assign a dedicated semantic tag using a value that would not normally be allowed by DAG-CBOR (but would be allowed, and might have another assigned value, in regular CBOR).

DAG-CBOR only permits tag 42 (IPLD CID link). Any other tag number is therefore unambiguous as a custom compression marker. We use tag numbers 6-9 so each tag encodes as a single byte (0xc6-0xc9). Tags 0-5 are avoided because common CBOR libraries interpret them semantically (datetime, timestamp, bignum, etc.).

These tags are applied to values anywhere in the structure (both in full operations and in diff update values).

| Tag | Name       | Original form                          | Compressed form                                             | Savings     |
|-----|------------|----------------------------------------|-------------------------------------------------------------|-------------|
| 6   | sig        | base64url string (86 chars)            | tag(6, bytes(64)) — base64url-decode to raw signature bytes | ~24 bytes   |
| 7   | prev (CID) | base32lower CID string (59 chars)      | tag(7, bytes(36)) — binary CID (version + codec + multihash)| ~23 bytes   |
| 8   | did:key    | "did:key:zQ3sh..." string (56 chars)   | tag(8, bytes(35)) — base58btc-decode the key after "did:key:z", yielding 2-byte multicodec varint (0xe7 0x01 for secp256k1) + 33-byte compressed public key | ~21 bytes/key |
| 9   | at://      | "at://example.com" string              | tag(9, "example.com") — strip the "at://" prefix            | 5 bytes     |
