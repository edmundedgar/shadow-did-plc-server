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

