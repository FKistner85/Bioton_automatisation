# Pipeline Control (EN)

## Purpose
Builds a deterministic run plan before submitting the Slurm DAG and prevents
concurrent workflows from writing the same products.

## Tools
`tools/plan_pipeline_run.py`, `tools/pipeline_lock.py`,
`tools/run_with_manifest.py`, `submit_bio_o_ton_horeka.sh`

## Inputs
- Dawn Chorus CSV and Step 1 domain fingerprints
- previous master table
- global step states and configured outputs

## Outputs
- `outputs/step_0_control/run_plans/<run_id>/run_plan.json`
- `outputs/step_0_control/run_plans/<run_id>/*_ids.csv`
- `outputs/step_0_control/full_rebuild/current.json`
- `outputs/step_0_control/full_rebuild/<generation_id>/completed_steps/*.json`
- `outputs/step_0_control/pipeline.lock/owner.json`
- `outputs/step_0_manifests/<step>/<step_run_id>.json`

## Behaviour
`add_new_ids` plans new, changed and previously problematic IDs.
`from_scratch` plans all current IDs and all global core steps. Slurm uses
`afterany` dependencies so failed jobs do not leave permanent dependency jobs.
Successful full-run steps receive atomic markers; a new submission only queues
steps whose markers are missing.
