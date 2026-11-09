# Lossless database payload compression

## Intent and constraints
Reduce the active inspection database while preserving all data, correction history, original source evidence, identities, verification state, quality state, versions and interchange behavior. The owner authorized implementation and requires backup, recovery, import and export compatibility. Preserve existing uncommitted UI work. Development and tests use disposable databases; never run migrations against operational data as a test.

## Approaches and recommended scope
Use Python standard-library zlib compression for selected JSON payloads, with explicit application-level encoding and decoding. This fits SQLite and both supported operating systems without a new dependency. Whole-file compression is useful for backups but cannot provide a writable SQLite database. Deduplicating imports or replacing history with differences would require much more complex reconstruction and is outside this change. The recommended implementation choice is explicit payload compression, subject to owner design approval.

Initially compress only correction_events.before_json/after_json, import_batches.contents, source_baselines.contents and import_reference.contents. These account for most retained payload bytes. Leave assets.details, snapshots, bulk operations, verification evidence and settings unchanged. This avoids changing revision hashes over raw asset rows and SQLite JSON snapshot queries. Original workbooks and existing backups remain untouched.

## Storage codec
Introduce a dedicated payload module with encode_text/decode_text and dumps/loads helpers. Plain JSON text remains supported. Compressed values use a SQLite BLOB with an unambiguous versioned magic header, original UTF-8 byte length, SHA-256 digest and a zlib stream. Preserve original JSON bytes during migration without parsing/reserializing. Keep small or incompressible values as text; use compression only when the complete envelope saves space. The builder chooses and documents the threshold and header layout.

Reject unknown versions, malformed headers, invalid/truncated streams, trailing compressed bytes, length mismatches, checksum failures and invalid UTF-8 with ValueError. Bound decompression against a documented maximum aligned with the existing 1 GiB database backup limit, without allocating based only on an untrusted declared length. Do not silently replace damaged values. JSON helpers preserve existing serialization parameters and unknown fields.

## Application integration
Audit every read and write of the selected columns, including import staging/commit/history, matching and baselines, consolidation, reconciliation, cleanup, exports, backup validation, recovery packaging and correction journaling. Use explicit codec calls at storage boundaries. Hashing, external workbook annotations, HTTP JSON, recovery manifests and ordinary JSON documents continue using ordinary JSON. New writes to selected columns use the codec. Mixed text/BLOB rows remain readable.

## Migration and compatibility
Bump schema version from 10 to 11. Existing startup migration backup happens before changes; old versions reject newer databases through the existing schema guard. Convert selected existing columns transactionally and idempotently, including optional tables only when present. Complete older migrations before compression. Schema version advances only with a successful transaction. Startup on schema 11 does not rewrite payloads. Preserve row IDs, sqlite_sequence, all nonpayload values and version clocks. Old uncompressed backups remain restorable and are migrated in the existing restore staging transaction. Validate every selected payload with the codec before a backup becomes operational.

Compression frees SQLite pages but does not shrink the file immediately. Do not add VACUUM to every startup or restore. After code and tests pass, hold the app data-directory lock for a separate authorized maintenance operation: create an independent backup, migrate and compact a candidate copy, compare logical contents, then publish only after successful checks. Keep the original independent backup. If the app holds the lock, defer installation until it is closed; never force-stop it. The builder must ensure publication does not leave live WAL/journal sidecars or replace an in-use database; use SQLite's transactional backup mechanism under the lock, followed by controlled compaction if required.

## Verification and acceptance
- Codec round trips cover Unicode, embedded nulls, empty values, large history, unknown JSON fields, incompressible input, legacy text and all corruption cases above.
- Migration on disposable fixtures proves exact decoded UTF-8 bytes, unchanged row counts and scalar columns, preserved schema/versions except schema_info, idempotency, independent backup readability, and rollback on malformed payloads/failure midway.
- Exercise compressed new writes and reads for staged imports after restart, committed import history, matching/baselines, reference export, correction creation and cleanup/consolidation updates.
- Raw and gzip database backups validate and restore compressed history; old uncompressed backups also restore. Recovery ZIP export, validation and restore preserve sources and compressed payloads. Damaged compressed backups/packages fail before target replacement.
- Workbook export/import preserves existing interchange semantics, source annotations and long values; exports contain normal workbook values rather than storage envelopes. Compare export tables before/after migration.
- Run focused tests followed by python3 -m unittest discover -s tests and node --test tests/*.test.cjs. No UI changes are intended. Native Windows and owner acceptance remain unverified unless actually tested.
- Operational installation verifies integrity_check, exact decoded values in every selected column, exact unchanged values in every other table (except schema_info), original IDs/counts/history/version clocks, and export table equality. Record original/candidate/final sizes and independent backup path. Do not add migration events or change application settings during comparison.

## Non-goals and remaining implementation decisions
No data deletion, history pruning, evidence merging, changes to quality rules or UI redesign. No claim of native Windows acceptance. The builder chooses codec layout, threshold, bounded decompression implementation and test fixtures, and can narrow compression scope if a measured benefit is negligible, documenting that choice. Failure to establish preservation or compatibility blocks operational installation, with original data retained.
