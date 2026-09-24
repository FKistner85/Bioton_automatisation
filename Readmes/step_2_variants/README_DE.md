# Step 2 Varianten - LRT-Sensitivitaetsanalyse

## Zweck

Alle GeoPackages aus
`Biodiversity_data/Bundeslander/All_Bundeslander/All_Bundeslander_*.gpkg`
werden als getrennte fachliche Varianten verarbeitet. Kein Datensatz
ueberschreibt einen anderen. Der Dateisuffix nach `All_Bundeslander_` ist die
stabile Varianten-ID.

Die Primärvariante ist derzeit `no_K_post2017`. Nur ihre
Formation-Felder werden in der kompakten ID-Mastertabelle verwendet. Alle
Varianten stehen zusaetzlich in einer normalisierten Vergleichstabelle.

## Verarbeitung pro Variante

```text
Eingangs-GPKG
  -> Step 2_0 LRT-Bereinigung
  -> Step 2_1 100m-Formation und Statusmatrix
  -> Step 2_2 Recording-Zuordnung
  -> Step 2_3 groebere Rasterprodukte
  -> Step 2_4 10m-Formation und Statusmatrix
  -> Step 7_1 Varianten-Mastertabelle
  -> Step 7_0 kompakte Haupt-Mastertabelle
```

Step 2_2, 2_3 und 2_4 beginnen nach Abschluss der Step-2_1-Arraystufe. Ein
fehlender Vorgaengeroutput laesst nur den betroffenen Task mit einem klaren
Fehler enden. Die Abhaengigkeit `afterany` verhindert dauerhaft wartende
`DependencyNeverSatisfied`-Jobs. Auf Horeka laufen verschiedene Varianten als
Slurm-Array parallel. Lokal wird die Parallelitaet durch
`local_max_parallel_variants` begrenzt.

## Ausgaben

Alle variantenbezogenen Dateien liegen unter:

```text
outputs/step_2_variants/<suffix>/step_2_0/
outputs/step_2_variants/<suffix>/step_2_1/
outputs/step_2_variants/<suffix>/step_2_1_susi_compatible/
outputs/step_2_variants/<suffix>/step_2_2/
outputs/step_2_variants/<suffix>/step_2_3/
outputs/step_2_variants/<suffix>/step_2_4_susi_10m/
```

Zentrale Produkte:

```text
outputs/step_2_variants/variant_index.json
outputs/Bio_O_Ton_Formation_Variants.csv
outputs/Bio_O_Ton_Formation_Variants.parquet
outputs/Bio_O_Ton_Formation_Variants_summary.json
```

Die Varianten-Mastertabelle hat genau eine Zeile pro
`dawn_chorus_id` und `lrt_variant`. Sie enthaelt 100m-/10m-Majority,
Conservation Status, Majority-Werte, Disputed-Flags und Produktstatus.

## Inkrementelles Verhalten

Jede Variante besitzt eigene States und Checkpoints. Eine geaenderte
Eingangsdatei invalidiert nur ihren Zweig. Neue Recording-IDs erfordern nur
Step 2_2 und das anschliessende Mastertable-Update, solange die raeumlichen
Produkte unveraendert sind. `from_scratch` uebergibt `--force`; Step 2_1 und
Step 2_4 koennen nach einem Zeitlimit an ihren Chunk-Checkpoints fortsetzen.

## Start

Horeka:

```bash
bash submit_step2_variants_horeka.sh add_new_ids
bash submit_step2_variants_horeka.sh from_scratch
```

Lokal:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts_local_run\run_step2_variants_local.ps1 -Mode add_new_ids -SkipEnvironmentSetup
```

Der Variantenlauf darf nicht gleichzeitig mit einem anderen schreibenden
Pipeline-Lauf ausgefuehrt werden.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `complete` | `Ausgabe in build_variant_rows` | [Step_7_1_update_formation_variant_table.py:294](../../scripts/Step_7_1_update_formation_variant_table.py) |
| `partial` | `Ausgabe in build_variant_rows` | [Step_7_1_update_formation_variant_table.py:294](../../scripts/Step_7_1_update_formation_variant_table.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `ValueError: Cannot derive a variant suffix from {path.name}` | `not suffix` | [step2_variants.py:60](../../tools/step2_variants.py) |
| `TypeError: 'lrt_variants' must be a JSON object.` | `not isinstance(settings, dict)` | [step2_variants.py:67](../../tools/step2_variants.py) |
| `NotADirectoryError: LRT variant input directory not found: {input_dir}` | `not input_dir.is_dir()` | [step2_variants.py:73](../../tools/step2_variants.py) |
| `FileNotFoundError: No LRT variant GeoPackages match {input_dir / pattern}` | `not sources` | [step2_variants.py:79](../../tools/step2_variants.py) |
| `ValueError: Duplicate LRT variant suffix: {suffix}` | `key in seen` | [step2_variants.py:86](../../tools/step2_variants.py) |
| `ValueError: 'lrt_variants.primary_suffix' must not be empty.` | `not primary` | [step2_variants.py:169](../../tools/step2_variants.py) |
| `ValueError: Configured primary LRT variant is missing: {primary}. Available: {', '.join(sorted(available))}` | `primary not in available` | [step2_variants.py:171](../../tools/step2_variants.py) |
| `ValueError: --task-index must be between 0 and {len(variants) - 1}` | `not 0 <= args.task_index < len(variants)` | [step2_variants.py:316](../../tools/step2_variants.py) |
| `ValueError: --stage is required with --task-index` | `args.stage is None` | [step2_variants.py:318](../../tools/step2_variants.py) |
| `ValueError: Select --stage, --all-stages, --prepare-only or --task-count` | `not stages` | [step2_variants.py:330](../../tools/step2_variants.py) |
| `KeyError: Missing public_lrt_cleaning section in config.` | `'public_lrt_cleaning' not in config` | [Step_2_5_clean_public_lrts.py:34](../../scripts/Step_2_5_clean_public_lrts.py) |
| `RuntimeError: No public LRT polygons remained after cleaning.` | `not results` | [Step_2_5_clean_public_lrts.py:159](../../scripts/Step_2_5_clean_public_lrts.py) |
| `KeyError: Missing public_lrt_grid_merge section in config.` | `'public_lrt_grid_merge' not in config` | [Step_2_6_merge_public_lrts_and_grid.py:32](../../scripts/Step_2_6_merge_public_lrts_and_grid.py) |
| `KeyError: Metadata missing columns: {sorted(missing)}` | `missing` | [Step_7_1_update_formation_variant_table.py:170](../../scripts/Step_7_1_update_formation_variant_table.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `args.task_count` | [step2_variants.py:309](../../tools/step2_variants.py) |
| `0` | `args.prepare_only` | [step2_variants.py:311](../../tools/step2_variants.py) |
| `0` | `Ausgabe in main` | [step2_variants.py:343](../../tools/step2_variants.py) |
| `0` | `should_skip(output_gpkg, state_file, expected_state, args.force)` | [Step_2_5_clean_public_lrts.py:127](../../scripts/Step_2_5_clean_public_lrts.py) |
| `0` | `Ausgabe in main` | [Step_2_5_clean_public_lrts.py:188](../../scripts/Step_2_5_clean_public_lrts.py) |
| `1` | `except Exception` | [Step_2_5_clean_public_lrts.py:191](../../scripts/Step_2_5_clean_public_lrts.py) |
| `0` | `should_skip(output_paths, state_file, expected_state, args.force)` | [Step_2_6_merge_public_lrts_and_grid.py:120](../../scripts/Step_2_6_merge_public_lrts_and_grid.py) |
| `0` | `Ausgabe in main` | [Step_2_6_merge_public_lrts_and_grid.py:176](../../scripts/Step_2_6_merge_public_lrts_and_grid.py) |
| `1` | `except Exception` | [Step_2_6_merge_public_lrts_and_grid.py:179](../../scripts/Step_2_6_merge_public_lrts_and_grid.py) |
| `0` | `not rebuilt and output_csv.is_file() and output_parquet.is_file()` | [Step_7_1_update_formation_variant_table.py:373](../../scripts/Step_7_1_update_formation_variant_table.py) |
| `0` | `Ausgabe in main` | [Step_7_1_update_formation_variant_table.py:462](../../scripts/Step_7_1_update_formation_variant_table.py) |
| `1` | `except Exception` | [Step_7_1_update_formation_variant_table.py:465](../../scripts/Step_7_1_update_formation_variant_table.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->
