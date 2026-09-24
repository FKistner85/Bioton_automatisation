# Step 2 Variants - LRT Sensitivity Analysis

All `All_Bundeslander_*.gpkg` files are processed as isolated variants. The
suffix following `All_Bundeslander_` is the stable variant identifier, and no
variant overwrites another one.

Each branch executes Steps 2_0 through 2_4 and writes to
`outputs/step_2_variants/<suffix>/`. The configured primary variant is
`no_K_post2017`; its fields feed the compact ID-level master
table. Step 7_1 additionally writes
`outputs/Bio_O_Ton_Formation_Variants.parquet` and CSV with one row per
`dawn_chorus_id` and `lrt_variant` for sensitivity comparisons.

Horeka uses one Slurm array task per variant and stage. Stage barriers use
`afterany`, so a failed variant produces an explicit downstream error instead
of leaving `DependencyNeverSatisfied` jobs behind:

```bash
bash submit_step2_variants_horeka.sh add_new_ids
bash submit_step2_variants_horeka.sh from_scratch
```

Local execution uses the same Python steps and isolated configuration files:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts_local_run\run_step2_variants_local.ps1 -Mode add_new_ids -SkipEnvironmentSetup
```

States and checkpoints are variant-specific. A changed source only invalidates
its own branch. Do not run this workflow concurrently with another pipeline
writer.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

No fixed values in this category in the associated source.

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `complete` | `Emitted by build_variant_rows` | [Step_7_1_update_formation_variant_table.py:294](../../scripts/Step_7_1_update_formation_variant_table.py) |
| `partial` | `Emitted by build_variant_rows` | [Step_7_1_update_formation_variant_table.py:294](../../scripts/Step_7_1_update_formation_variant_table.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
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

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `args.task_count` | [step2_variants.py:309](../../tools/step2_variants.py) |
| `0` | `args.prepare_only` | [step2_variants.py:311](../../tools/step2_variants.py) |
| `0` | `Emitted by main` | [step2_variants.py:343](../../tools/step2_variants.py) |
| `0` | `should_skip(output_gpkg, state_file, expected_state, args.force)` | [Step_2_5_clean_public_lrts.py:127](../../scripts/Step_2_5_clean_public_lrts.py) |
| `0` | `Emitted by main` | [Step_2_5_clean_public_lrts.py:188](../../scripts/Step_2_5_clean_public_lrts.py) |
| `1` | `except Exception` | [Step_2_5_clean_public_lrts.py:191](../../scripts/Step_2_5_clean_public_lrts.py) |
| `0` | `should_skip(output_paths, state_file, expected_state, args.force)` | [Step_2_6_merge_public_lrts_and_grid.py:120](../../scripts/Step_2_6_merge_public_lrts_and_grid.py) |
| `0` | `Emitted by main` | [Step_2_6_merge_public_lrts_and_grid.py:176](../../scripts/Step_2_6_merge_public_lrts_and_grid.py) |
| `1` | `except Exception` | [Step_2_6_merge_public_lrts_and_grid.py:179](../../scripts/Step_2_6_merge_public_lrts_and_grid.py) |
| `0` | `not rebuilt and output_csv.is_file() and output_parquet.is_file()` | [Step_7_1_update_formation_variant_table.py:373](../../scripts/Step_7_1_update_formation_variant_table.py) |
| `0` | `Emitted by main` | [Step_7_1_update_formation_variant_table.py:462](../../scripts/Step_7_1_update_formation_variant_table.py) |
| `1` | `except Exception` | [Step_7_1_update_formation_variant_table.py:465](../../scripts/Step_7_1_update_formation_variant_table.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->
