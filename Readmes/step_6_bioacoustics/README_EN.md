# Step 6 - Bioacoustic Embeddings and Species Inference

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
- `6_2`: run checkpointed CPU arrays over model x deterministic ID shard.
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
under `scripts_horeka/bacpipe/model_checkpoints/`. It then instantiates the
models before the inference array can start. A failed required-model registry
is automatically retried by the next `add_new_ids` run.

An existing directory is not assumed to be a valid checkpoint. On common
missing-file, truncated PyTorch archive, or invalid ZIP errors, the preflight
moves the affected model tree to
`bacpipe/model_checkpoints/_quarantine/<time>_<model>/`, downloads it once
again, and retries model initialisation. The repair is recorded in the model
registry while the damaged files remain available for diagnosis.

Resume is keyed by audio fingerprint, model fingerprint and preprocessing
version. Every model/shard state records completed and failed IDs. A timeout
continues at the last checkpoint, while failed IDs are retried in later runs.
