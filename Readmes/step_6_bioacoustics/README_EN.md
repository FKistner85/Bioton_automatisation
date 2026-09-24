# Step 6 - Bioacoustic Embeddings and Species Inference

## Current Operation (2026-09-23)

Start separately after the core: `bash slurm_bioacoustics.sh` or `bash run_horeka.sh bioacoustics`. Step 6.1 reconciles all current metadata IDs using `--reconcile-all`, removing deleted IDs from the worklist. Unchanged work keys reuse checkpoints. Defaults: 64 logical shards per model, at most four workers with 4 CPUs, 24 GB and 12 hours each. `require_all_models_complete=true` makes the preceding verification gate require all six models, while per-ID QC still distinguishes required and optional models. The final master update changes bioacoustic fields only.


Step 6 processes technically valid Dawn Chorus audio with Bacpipe. It creates
model-specific embeddings, segment-level species predictions,
Germany/season plausibility flags, recording summaries and compact QC per
`dawn_chorus_id`.

The implementation follows the
[official Bacpipe API](https://github.com/bioacoustic-ai/bacpipe).
`run_pretrained_classifier`, device and classifier threshold are set
explicitly and are included in the model fingerprint.

The substeps are:

- `6_0`: provision checkpoint files, then validate Bacpipe, CUDA and the model registry.
- `6_1`: select valid audio and create audio/model fingerprints.
- `6_2`: run checkpointed CPU arrays over model x deterministic ID shard,
  followed by a verification gate over every required-model shard and work key;
  optional-model gaps remain warnings only when require_all_models_complete is false.
- `6_3`: normalise classifier outputs and retain thresholded segment top-k.
- `6_4`: harmonise taxonomy and add Germany/season plausibility.
- `6_5`: aggregate segments and model support per recording and species.
- `6_6`: reconcile expected/completed models and write per-ID QC.

Outputs use matching `outputs/step_6_<n>_*` directories. Exact paths and
thresholds are defined in the `bioacoustics` section of
`config.horeka.json`.

Required models are `birdnet`, `perch_v2`, `audioprotopnet` and
`convnext_birdset`. `insect66` and `naturebeats` are optional embedding
models. The Germany allowlist is shipped as a header-only template under
`reference_data/germany_species_allowlist.csv`; predictions remain
`not_evaluated` until a scientifically reviewed reference is supplied.

Native classifier output is thresholded and limited to top-k per segment
before it is written. The preflight explicitly calls Bacpipe's
`ensure_models_exist` for every configured model and persists checkpoints
under the configured `bacpipe/model_checkpoints/` directory relative to the active checkout. It then instantiates the
models before the inference array can start. A failed required-model registry
is automatically retried by the next `bioacoustics` run.

An existing directory is not assumed to be a valid checkpoint. On common
missing-file, truncated PyTorch archive, or invalid ZIP errors, the preflight
moves the affected model tree to
`bacpipe/model_checkpoints/_quarantine/<time>_<model>/`, downloads it once
again, and retries model initialisation. The repair is recorded in the model
registry while the damaged files remain available for diagnosis.

Resume is keyed by audio fingerprint, model fingerprint and preprocessing
version. Every model/shard state records completed and failed IDs. A timeout
continues at the last checkpoint, while failed IDs are retried in later runs.
Only the verification gate writes the completed Step 6_2 marker, so one
successful array task cannot prematurely complete a full rebuild.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `bacpipe_import_failed:{type(exc).__name__}:{exc}` | Bacpipe could not be imported. | [Step_6_0_bioacoustic_model_preflight.py:117](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `bacpipe_version_mismatch:expected={expected_version}:actual={bacpipe_version}` | Installed and configured Bacpipe versions differ. | [Step_6_0_bioacoustic_model_preflight.py:121](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `torch_import_failed:{type(exc).__name__}:{exc}` | PyTorch could not be imported. | [Step_6_0_bioacoustic_model_preflight.py:137](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `model_checkpoint_dir_not_accessible:{checkpoint_dir}` | Checkpoint directory lacks required access permissions. | [Step_6_0_bioacoustic_model_preflight.py:144](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `bacpipe_ensure_models_exist_unavailable` | Expected Bacpipe checkpoint provisioning API is unavailable. | [Step_6_0_bioacoustic_model_preflight.py:165](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `{type(repair_exc).__name__}:{repair_exc}` | Original exception type and message; not a separate fixed code. | [Step_6_0_bioacoustic_model_preflight.py:223](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `required_model_initialisation_failed:{name}` | Required model, or any model under require_all_models, cannot initialise. | [Step_6_0_bioacoustic_model_preflight.py:232](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `inventory_issue` | Worklist rejects audio without more specific inventory details. | [Step_6_1_prepare_bioacoustic_worklist.py:86](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `duplicate_valid_audio_for_id` | Extra valid audio for an ID; only the selected file enters the worklist. | [Step_6_1_prepare_bioacoustic_worklist.py:103](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `missing_state` | Expected shard state file is missing or unusable. | [Step_6_2_generate_bioacoustic_embeddings.py:116](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `state={state.get('status', 'unknown')}` | Shard state is not the expected complete status. | [Step_6_2_generate_bioacoustic_embeddings.py:121](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `failed_ids={len(state_failed)}` | Shard state contains failed IDs. | [Step_6_2_generate_bioacoustic_embeddings.py:125](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `task_error` | Shard state contains a task-level error. | [Step_6_2_generate_bioacoustic_embeddings.py:127](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `shard_count_mismatch` | Stored and configured shard counts differ. | [Step_6_2_generate_bioacoustic_embeddings.py:129](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `missing_rows={shard_missing}` | Expected work keys are not completed in the shard. | [Step_6_2_generate_bioacoustic_embeddings.py:146](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `required_models_incomplete` | At least one required model is incomplete for the recording. | [Step_6_6_bioacoustic_quality_control.py:91](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `model_inference_failed` | At least one model reports an inference failure for the ID. | [Step_6_6_bioacoustic_quality_control.py:93](../../scripts/Step_6_6_bioacoustic_quality_control.py) |

### Status Values (Not All Are Errors)

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `started` | `checkpoint_error_is_repairable(exc)` | [Step_6_0_bioacoustic_model_preflight.py:195](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `repaired` | `checkpoint_error_is_repairable(exc)` | [Step_6_0_bioacoustic_model_preflight.py:213](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `failed` | `except Exception` | [Step_6_0_bioacoustic_model_preflight.py:222](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `failed` | `Emitted by main` | [Step_6_0_bioacoustic_model_preflight.py:243](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `has_warnings` | `Emitted by main` | [Step_6_0_bioacoustic_model_preflight.py:243](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `validated` | `Emitted by main` | [Step_6_0_bioacoustic_model_preflight.py:243](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `rejected` | `Emitted by build_worklist` | [Step_6_1_prepare_bioacoustic_worklist.py:85](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `rejected` | `not duplicate_audio.empty` | [Step_6_1_prepare_bioacoustic_worklist.py:102](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `complete` | `Emitted by main` | [Step_6_1_prepare_bioacoustic_worklist.py:222](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `complete` | `Emitted by verify_shards` | [Step_6_2_generate_bioacoustic_embeddings.py:150](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `incomplete` | `Emitted by verify_shards` | [Step_6_2_generate_bioacoustic_embeddings.py:150](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `failed` | `Emitted by verify_shards` | [Step_6_2_generate_bioacoustic_embeddings.py:184](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `raw_model_prediction` | `Emitted by normalise_model` | [Step_6_3_normalise_species_predictions.py:68](../../scripts/Step_6_3_normalise_species_predictions.py) |
| `complete` | `Emitted by main` | [Step_6_3_normalise_species_predictions.py:105](../../scripts/Step_6_3_normalise_species_predictions.py) |
| `not_evaluated` | `allowlist.empty` | [Step_6_4_filter_germany_taxonomy.py:120](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `accepted` | `Emitted by apply_filter` | [Step_6_4_filter_germany_taxonomy.py:147](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `flagged` | `Emitted by apply_filter` | [Step_6_4_filter_germany_taxonomy.py:148](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `not_evaluated` | `Emitted by apply_filter` | [Step_6_4_filter_germany_taxonomy.py:153](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `complete` | `Emitted by main` | [Step_6_4_filter_germany_taxonomy.py:197](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `complete` | `Emitted by main` | [Step_6_5_aggregate_bioacoustic_results.py:121](../../scripts/Step_6_5_aggregate_bioacoustic_results.py) |
| `validated` | `Emitted by build_qc` | [Step_6_6_bioacoustic_quality_control.py:94](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `partial` | `Emitted by build_qc` | [Step_6_6_bioacoustic_quality_control.py:94](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `failed` | `Emitted by build_qc` | [Step_6_6_bioacoustic_quality_control.py:94](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `complete` | `Emitted by main` | [Step_6_6_bioacoustic_quality_control.py:149](../../scripts/Step_6_6_bioacoustic_quality_control.py) |

### Explicit Failure Messages

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `AttributeError: bacpipe.ensure_models_exist is unavailable` | `not callable(ensure_models)` | [Step_6_0_bioacoustic_model_preflight.py:177](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `FileNotFoundError: Audio inventory not found: {inventory_path}` | `not inventory_path.is_file()` | [Step_6_1_prepare_bioacoustic_worklist.py:151](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `FileNotFoundError: Bioacoustic model registry not found: {registry_path}` | `not registry_path.is_file()` | [Step_6_1_prepare_bioacoustic_worklist.py:162](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `RuntimeError: Bioacoustic model preflight registry has failed status.` | `registry.get('status') == 'failed'` | [Step_6_1_prepare_bioacoustic_worklist.py:167](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `ValueError: Unexpected empty embedding shape: {array.shape}` | `array.ndim != 2 or not array.size` | [Step_6_2_generate_bioacoustic_embeddings.py:245](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `ValueError: Classifier model returned no interpretable class-score output.` | `bool(work.get('classifier_available')) and (not native_rows)` | [Step_6_2_generate_bioacoustic_embeddings.py:624](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `KeyError: Taxonomy allowlist missing columns: {sorted(missing)}` | `missing` | [Step_6_4_filter_germany_taxonomy.py:77](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `KeyError: Missing required 'bioacoustics' configuration section.` | `not isinstance(section, dict)` | [bioacoustics_common.py:63](../../scripts/bioacoustics_common.py) |
| `ValueError: Each bioacoustic model needs a non-empty name.` | `not name` | [bioacoustics_common.py:75](../../scripts/bioacoustics_common.py) |
| `ValueError: Bioacoustic model names must be unique.` | `len(names) != len(set(names))` | [bioacoustics_common.py:85](../../scripts/bioacoustics_common.py) |
| `KeyError: Missing bioacoustics.{key} in configuration.` | `not value` | [bioacoustics_common.py:93](../../scripts/bioacoustics_common.py) |
| `ValueError: bioacoustics.model_checkpoint_dir must not be empty.` | `not raw` | [bioacoustics_common.py:104](../../scripts/bioacoustics_common.py) |
| `ValueError: Bacpipe 1.3.1 requires model_checkpoint_dir to end in 'bacpipe/model_checkpoints'; got: {checkpoint_dir}` | `checkpoint_dir.name.lower() != 'model_checkpoints' or checkpoint_dir.parent.name.lower() != 'bacpipe'` | [bioacoustics_common.py:118](../../scripts/bioacoustics_common.py) |
| `RuntimeError: Could not set bacpipe {attribute}={value}: {exc}` | `except Exception` | [bioacoustics_common.py:180](../../scripts/bioacoustics_common.py) |

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `1 if issues else 0` | `Emitted by main` | [Step_6_0_bioacoustic_model_preflight.py:276](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `0` | `Emitted by main` | [Step_6_1_prepare_bioacoustic_worklist.py:237](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `1` | `except Exception` | [Step_6_1_prepare_bioacoustic_worklist.py:240](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `2` | `not worklist_path.is_file()` | [Step_6_2_generate_bioacoustic_embeddings.py:83](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `2` | `blocking_models` | [Step_6_2_generate_bioacoustic_embeddings.py:205](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0` | `Emitted by verify_shards` | [Step_6_2_generate_bioacoustic_embeddings.py:207](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0` | `model_index >= len(models)` | [Step_6_2_generate_bioacoustic_embeddings.py:433](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0` | `pending.empty` | [Step_6_2_generate_bioacoustic_embeddings.py:501](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `1` | `except Exception` | [Step_6_2_generate_bioacoustic_embeddings.py:507](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `2` | `except Exception` | [Step_6_2_generate_bioacoustic_embeddings.py:528](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `3` | `stop_requested` | [Step_6_2_generate_bioacoustic_embeddings.py:661](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0 if not failed_by_id else 2` | `Emitted by main` | [Step_6_2_generate_bioacoustic_embeddings.py:676](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0` | `Emitted by main` | [Step_6_3_normalise_species_predictions.py:115](../../scripts/Step_6_3_normalise_species_predictions.py) |
| `1` | `except Exception` | [Step_6_3_normalise_species_predictions.py:118](../../scripts/Step_6_3_normalise_species_predictions.py) |
| `0` | `Emitted by main` | [Step_6_4_filter_germany_taxonomy.py:214](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `1` | `except Exception` | [Step_6_4_filter_germany_taxonomy.py:217](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `0` | `Emitted by main` | [Step_6_5_aggregate_bioacoustic_results.py:132](../../scripts/Step_6_5_aggregate_bioacoustic_results.py) |
| `1` | `except Exception` | [Step_6_5_aggregate_bioacoustic_results.py:135](../../scripts/Step_6_5_aggregate_bioacoustic_results.py) |
| `0` | `Emitted by main` | [Step_6_6_bioacoustic_quality_control.py:161](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `1` | `except Exception` | [Step_6_6_bioacoustic_quality_control.py:164](../../scripts/Step_6_6_bioacoustic_quality_control.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->
