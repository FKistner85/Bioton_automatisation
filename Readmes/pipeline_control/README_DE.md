# Pipeline-Steuerung (DE)

## Zweck
Erzeugt vor dem Slurm-DAG einen deterministischen Run-Plan und verhindert
parallele schreibende Gesamtlaeufe.

## Tools
`tools/plan_pipeline_run.py`, `tools/pipeline_lock.py`,
`tools/run_with_manifest.py`, `submit_bio_o_ton_horeka.sh`

## Inputs
- Dawn-Chorus-CSV und Step-1-Domaenenfingerprints
- letzte Mastertabelle
- globale Step-States und konfigurierte Outputs

## Outputs
- `outputs/step_0_control/run_plans/<run_id>/run_plan.json`
- `outputs/step_0_control/run_plans/<run_id>/*_ids.csv`
- `outputs/step_0_control/full_rebuild/current.json`
- `outputs/step_0_control/full_rebuild/<generation_id>/completed_steps/*.json`
- `outputs/step_0_control/pipeline.lock/owner.json`
- `outputs/step_0_manifests/<step>/<step_run_id>.json`

## Verhalten
`add_new_ids` plant neue, geaenderte und problematische IDs. `from_scratch`
plant alle aktuellen IDs und alle globalen Kernschritte. Slurm-Abhaengigkeiten
verwenden `afterany`, damit Fehler nicht zu dauerhaft wartenden Jobs fuehren.
Erfolgreiche Vollauf-Steps erhalten atomare Marker; ein neuer Submit reiht nur
Steps ohne Marker erneut ein.
