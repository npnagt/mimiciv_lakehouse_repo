# Storage footprint of the multimodal lakehouse — analysis & method

Supporting analysis for dissertation propositions **P3** (physical data duplication /
redundancy ratio) and **P4** (ad-hoc queries combining structured data with AI inference
outputs). Written to be **auditable and reproducible**: every number here is produced by
[`measure_storage_footprint.py`](../measure_storage_footprint.py), and anyone with read
access to the buckets and the Athena workgroup can re-run it and compare.

## Reproduce

```bash
python measure_storage_footprint.py            # full run
python measure_storage_footprint.py --skip-athena   # S3 physical only (no Athena cost)
```

Outputs a timestamped `docs/storage_footprint/storage_footprint_<UTC>.{json,md}` plus
`latest.{json,md}`. The JSON is the machine-readable record of record; the Markdown is
the same data rendered with the methodology and framing text inline.

Defaults (bucket names, region) come from `.env` → `src/mimic_lakehouse/config.py` →
built-in fallbacks → CLI flags. The run is **read-only**: the only writes are Athena
query results into the workgroup's own output location.

## Structured vs unstructured / NLP — the comparison basis

The decoupled comparator, `mimic_datawarehouse_repo` (Aurora PostgreSQL), is a
**structured-only** port of the Gold layer — it has no clinical notes, no NLP-derived
tables, and no note text. So every object measured here is tagged into one of three
categories, and the P3 redundancy-ratio comparison uses the **structured** row only:

| Category | What is in it | Aurora warehouse equivalent |
|---|---|---|
| **structured** | raw `*_raw` CSV.gz (32 tables) · Gold `dim_` / `fact_` / `agg_` / `obt_` / `etl_control` | **yes** — `hosp` / `icu` / `staging` / `warehouse` schemas |
| **unstructured / NLP** | note `.csv.gz` (`discharge_raw`, `radiology_raw`) · `*_note_raw` Parquet · `fact_note_nlp*` / `fact_radiology_note_nlp*` Gold tables · per-note debug JSON | **no** — capability the lakehouse adds |
| infrastructure | Glue job scripts · stray Athena query results | n/a |

The **unstructured / NLP** total is *not duplication* and must not enter a P3 redundancy
ratio — it is coverage the Aurora warehouse does not provide at any byte count. Report it
separately as "what the multimodal lakehouse carries that the warehouse cannot."

## Data warehouse vs data lakehouse — the P3 comparison

Aurora baseline (from `mimic_datawarehouse_repo`'s own storage report, 2026-09-07),
passed to the script via `--aurora-baseline docs/storage_footprint/aurora_baseline.json`.
**The raw structured CSVs are the same files for both architectures** — one shared line,
excluded from the head-to-head of the *processed* layers where the designs differ.
The lakehouse numbers below are **post-compaction**: `OPTIMIZE … REWRITE DATA USING
BIN_PACK` was run across all 42 Athena-manageable Gold tables on 2026-09-08
([`compact_gold_tables.py`](../compact_gold_tables.py)), so the live snapshot is the
bin-packed layout, not an estimate.

| Layer | Data warehouse (Aurora) | Data lakehouse |
|---|--:|--:|
| Raw structured CSV.gz in S3 *(shared)* | 15.44 MiB | 15.44 MiB |
| Staging / raw-mirror layer | **materialized** — `staging.stg_*`, full TRUNCATE+reload | **0 B** — `mimic4_db_raw` = external tables over the same S3 files |
| Modeled / queryable layer | `warehouse.dim_/fact_/agg_*` | Gold Iceberg |
| **Processed structured — physical** | **578.39 MiB** (66 tables) | **1.47 GiB** (39 tables) |
| **Processed structured — live / current** | 553.24 MiB | **81.5 MiB** |
| Processed structured — compacted-logical | ~553 MiB (Postgres, little bloat) | **81.5 MiB (measured, post-`OPTIMIZE`)** |
| `pg_database_size()` (incl. catalogs) | 588.45 MiB | n/a |
| **NLP-derived tables** | **0 B — cannot store** | 797 KiB physical / 60 KiB live |

**Head-to-head, processed structured:**

- **On the live snapshot** — the data a correctly-maintained Iceberg table actually
  serves — the lakehouse is **81.5 MiB vs the warehouse's 553 MiB: 0.15×**. It holds the
  same structured information in **less than one-sixth** the space. `OPTIMIZE` cut the
  Gold live snapshot from **693 MiB in 98,792 Parquet files to 81.5 MiB in 13,887**
  (~8.5× — tiny row groups compress terribly; bin-packing 100-row files into
  15k-row files restores dictionary/RLE compression). **P3 supported.**
- **On raw physical bytes** the lakehouse is still **2.59×** the warehouse (1.47 GiB vs
  578 MiB). The live snapshot is only **~5.4 %** of physical because Athena `VACUUM`
  **expired the superseded snapshots but did not delete their data files** (verified: after
  `VACUUM`, `"<table>$snapshots"` shows a single snapshot, yet the pre-compaction Parquet
  files from 2026-07-29 and 2026-09-05 are still in S3 — e.g.
  `fact_medication_administration` keeps 35,696 orphaned files next to 1,276 live ones).
  Reclaiming them needs a Spark `remove_orphan_files` pass; it is a **tooling gap in
  Athena, not a property of the architecture** — those files back no snapshot and no query.

Row counts are *not* inflated — `sum(record_count)` from `"<table>$files"` equals
`count(*)` for every table checked (`dim_diagnosis` genuinely has 109,775 ICD-9 + ICD-10
codes; `fact_medication_administration` 35,835). The physical bloat is orphaned *files*.

### Redundancy ratio (physical materialized ÷ one clean modeled copy), structured

| Architecture | Ratio | Why |
|---|--:|---|
| **Data warehouse** | **2.0×** | Aurora materializes the structured dataset twice inside Postgres — `staging.stg_*` (full TRUNCATE+reload of every source) + `warehouse.*` (modeled copy). The shared raw CSV in S3 is a third copy, excluded as common to both. |
| Data lakehouse — as deployed | 18.4× | orphaned pre-compaction data files that Athena `VACUUM` expired the snapshots for but did not delete — reclaimable by Spark `remove_orphan_files`. Not a copy of the data. |
| **Data lakehouse — compacted** | **1.0×** | the live snapshot (81.5 MiB) is the only clean modeled copy; `mimic4_db_raw` staging is external tables (0 bytes) |

**P3 holds.** The warehouse keeps two full physical materializations of the structured
data inside Postgres; the lakehouse keeps one (Gold), because its staging layer is
external tables over the raw CSVs — **0 bytes**. That is one entire physical copy the
lakehouse eliminates by design, and on information content (live snapshot) the lakehouse
is **0.15×** the warehouse. The one figure that still favours the warehouse — raw
physical bytes — is orphaned files awaiting `remove_orphan_files`, not a second copy.
**For the NLP layer the comparison is unambiguous**: Aurora holds 0 bytes (coverage
gap); the lakehouse holds one copy (797 KiB); a decoupled architecture that did NLP would
hold each output in ≥ 2 (model store + warehouse load).

### The compaction run (2026-09-08)

`compact_gold_tables.py --vacuum --vacuum-max-age 300 --measure` — `OPTIMIZE … REWRITE
DATA USING BIN_PACK` on all 42 Athena-manageable Iceberg tables (the 13 day/bucket-
partitioned event facts need up to 13 rounds each at ≤100 partitions/call), then
`VACUUM` per table.

- **Live snapshot: 693 MiB → 81.5 MiB** across the Gold layer. This is the real,
  measured P3 number — no longer the earlier ~231 MiB estimate.
- **Snapshots expired**: every table now carries a single `replace` snapshot.
- **Physical S3 bytes: essentially unchanged** (1.44 → 1.47 GiB). Athena `VACUUM` does
  not remove data files once their snapshot is already gone; those become true orphans
  that only Spark `remove_orphan_files` (or `CALL system.remove_orphan_files` from a Glue
  6.0 job) can delete. Follow-up task: run that pass and re-measure to confirm physical
  converges on ~85–150 MiB.
- `fact_radiology_note_nlp_v` (Iceberg format-v3) is skipped — compact it from a Glue
  6.0 Spark job with `CALL glue_catalog.mimic4_db_business.system.rewrite_data_files`.

## What is measured, and why three numbers

| Number | Source | Meaning |
|---|---|---|
| **Physical bytes** | `s3:ListObjectsV2` over each bucket | Everything currently in S3 — including Iceberg metadata and data files from expired snapshots that `expire_snapshots` has not yet deleted. This is what you are billed for. |
| **Live-snapshot bytes** | `SELECT sum(file_size_in_bytes) FROM "<table>$files"` (Athena) | The data files the *current* Iceberg snapshot references. Scans no data — reads the manifest. |
| **Logical / compacted bytes** | the live snapshot, *once `OPTIMIZE … REWRITE DATA` has run* | The information content. As of 2026-09-08 this equals the live snapshot (compaction has been run): **81.5 MiB** for the structured Gold layer. |

`physical ÷ live` isolates snapshot / orphan-file bloat; `live ÷ logical` was small-file
fragmentation and is now ≈ 1 (compaction done). Both are ETL-hygiene artifacts, not
architecture — see **Caveats**.

## Layer classification

- **Raw bucket** prefixes: `note_text_gz` (`discharge_raw`, `radiology_raw`), `note_parquet`
  (`*_note_raw`, the converted notes), `structured_csv` (every other `*_raw`), `other`.
- **Gold bucket** tables (2nd path segment under `mimic_bus/`): `dim` / `fact` / `agg` /
  `obt` by name prefix; **`ai_nlp`** = `fact_note_nlp`, `fact_note_nlp_medspacy`,
  `fact_radiology_note_nlp`, `fact_radiology_note_nlp_v`; `control` = `etl_control`.
- A Gold object is **Iceberg metadata** iff its key is `mimic_bus/<table>/metadata/…`,
  otherwise **data**.
- `fact_radiology_note_nlp_v` is Iceberg **format-version 3** (VARIANT projection) and
  Athena engine v3 cannot read it — it is reported with physical bytes only and
  `athena_readable: false`.

## Findings — measured run 2026-09-08 (post-compaction)

Numbers below are from that run; `docs/storage_footprint/latest.md` always holds the most
recent. AWS account `684389449130`, region `us-east-2`, repo `7e814e6`.

**Total lakehouse physical: 3.28 GiB** (raw 1.81 GiB + gold 1.47 GiB + debug/scripts < 3 MiB).
Gold **live snapshot 81.5 MiB** (post-`OPTIMIZE`); physical is 18.4× that, held up by
orphaned pre-compaction files pending `remove_orphan_files`.

### Structured vs unstructured / NLP

| Category | Physical | Live snapshot | % of lakehouse | Aurora equivalent |
|---|--:|--:|--:|:--:|
| **Structured** (raw CSV + 39 Gold `dim`/`fact`/`agg`/`obt`/`control` tables) | 1.48 GiB | **96.93 MiB** | 45.20 % | yes |
| **Unstructured / NLP** | 1.79 GiB | 1.79 GiB | 54.73 % | **no** |
| Infrastructure (Glue scripts, Athena results) | 2.25 MiB | — | 0.07 % | n/a |

Unstructured / NLP breaks down as: clinical note text `.csv.gz` **1.79 GiB** · converted
note Parquet 2.51 MiB · **NLP-derived Gold tables 797 KiB physical / 60 KiB live** ·
per-note debug JSON 401 KiB.

- **P3 comparison vs. Aurora** is on the structured row: **96.93 MiB live** (Gold live
  81.5 MiB + shared raw CSV 15.44 MiB), post-`OPTIMIZE`, against
  `mimic_datawarehouse_repo`'s **553.24 MiB live** — the lakehouse is **0.15×**.
- The **1.79 GiB unstructured / NLP** figure is **not duplication** — it is capability
  the Aurora warehouse does not provide at any byte count. Almost all of it (1.79 GiB) is
  raw note *text*; the NLP *derivations* that P4 joins against are **797 KiB**.

### Raw bucket — `mimic4-datalake-v3`  ·  1.81 GiB / 36 objects

| Class | Size | Share |
|---|--:|--:|
| Free-text clinical notes (`.csv.gz` — `discharge_raw`, `radiology_raw`) | 1.79 GiB | **99.03 %** |
| Structured MIMIC-IV CSV.gz (32 tables) | 15.44 MiB | 0.83 % |
| Converted note Parquet (`discharge_note_raw`, `radiology_note_raw`) | 2.51 MiB | 0.14 % |

The unstructured modality dominates raw storage by **~118×** over all structured tables combined.

### Gold Iceberg layer — `mimic4-lakehouse-v3/mimic_bus/`  ·  1.47 GiB physical / ~215,000 objects

- **Physical** 1.47 GiB = 1.46 GiB data + 8.01 MiB Iceberg metadata + 2.07 MiB stray Athena results.
- **Live snapshot** 81.54 MiB in 13,887 files — physical is **18.4×** the live snapshot.
  Post-`OPTIMIZE` this ratio is *not* one-old-generation retention (that was the
  pre-compaction 2.13×); it is orphaned pre-compaction data files that `VACUUM` de-linked
  from every snapshot but did not delete.
- **Small-file fragmentation — fixed by `OPTIMIZE`.** Before: 41 of 42 tables averaged
  < 1 MiB per live data file; `fact_medication_administration` 104.65 MiB in 17,846
  files. After: the live snapshot is 8.5× smaller (693 → 81.5 MiB) in 7× fewer files
  (98,792 → 13,887) — bin-packing tiny row groups restored compression.
- Row counts are correct — `Σ file record_count` from `"<table>$files"` equals `count(*)`
  for every table checked (`dim_diagnosis` genuinely has 109,775 ICD-9 + ICD-10 codes;
  `fact_medication_administration` 35,835). Any inflation is file *count*, not row count.
- **Compacted-logical size of the structured Gold layer: 81.5 MiB — measured, not
  estimated** (this run, post-`OPTIMIZE`). Physical will follow once
  `remove_orphan_files` runs.

### AI-inference layer (P4)  ·  796.76 KiB physical / 60.05 KiB live

| Table | Physical | Live snapshot | Files | Grain |
|---|--:|--:|--:|---|
| `fact_radiology_note_nlp_v` (VARIANT, format-v3) | 296.10 KiB | n/a — not Athena-readable | — | admission |
| `fact_note_nlp_medspacy` | 256.37 KiB | 37.65 KiB | 1 | admission |
| `fact_radiology_note_nlp` | 228.54 KiB | 22.39 KiB | 1 | admission |
| `fact_note_nlp` (Comprehend — blocked, empty) | 15.75 KiB (metadata only) | 0 | 0 | admission |

- **0.052 %** of the Gold layer  ·  **0.042 %** of the raw bucket  ·  **0.023 %** of the total lakehouse.
- A fully-populated `fact_ai_inference` for the demo cohort (~275 admissions × a few
  model scores + a JSON payload column) is **< 200 KB**; at full MIMIC-IV scale (~430 k
  admissions) **~50–100 MB** — smaller than any single event-grain fact table
  (`fact_chart_observation` alone is 189 MiB physical).

## Framing for P4

**Marginal storage cost of the P4 capability ≈ 0.** An AI-inference output is a new
small Iceberg table in the *existing* catalog (`mimic4_db_business`) and the *existing*
bucket — no new store, no new format, no partitioning — joined to `fact_admission` in
place.

**Redundancy ratio for the AI-inference layer = 1.0** (one physical copy). In a
decoupled architecture the same output is materialized in the model/NLP store *and*
copied into the warehouse to become joinable — redundancy ≥ 2.0 plus an ongoing sync
job. The bytes are trivial either way; the property is **structural** — 1 physical copy
vs ≥ 2 — and it is what makes P4's "no ETL detour" true. This is also the native side of
P3's redundancy-ratio metric.

## Caveats

1. **Do not compute a P3 redundancy ratio off the raw physical number.** As of
   2026-09-08 `OPTIMIZE … REWRITE DATA USING BIN_PACK` has run on the whole Gold layer,
   so the **live snapshot (81.5 MiB) is the correct P3 figure**. Physical is still
   1.47 GiB because Athena `VACUUM` expired the old snapshots but does not delete their
   now-orphaned data files — run Spark `remove_orphan_files` (or Glue 6.0
   `CALL system.remove_orphan_files`) to reclaim, then re-measure. Athena `VACUUM` alone
   is insufficient here.
2. **`list_objects_v2` counts current object versions only.** If bucket versioning is
   ever enabled, noncurrent versions are not included.
3. **`"<table>$files"` reflects the current snapshot only** — it does not see historical
   snapshots' files (which is the point of the physical-vs-live comparison).
4. **The decoupled-baseline side of P3** must be measured separately against
   `mimic_datawarehouse_repo` (Aurora Postgres): `pg_total_relation_size()` over its
   `staging` + `warehouse` schemas, plus its raw S3 landing copy. This script only
   measures the native lakehouse.

## Files

- [`measure_storage_footprint.py`](../measure_storage_footprint.py) — the measurement tool
- `docs/storage_footprint/storage_footprint_<UTC>.json` — machine-readable record per run
- `docs/storage_footprint/storage_footprint_<UTC>.md` — rendered report per run
- `docs/storage_footprint/latest.{json,md}` — the most recent run
