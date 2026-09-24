# Pipeline-Steuerung (DE)

## Aktueller Betrieb (2026-09-23)

`add_new_ids` und `from_scratch` planen nur den Kern. `bioacoustics` plant ausschliesslich Step 6 und sein Master-/Validierungsende. Der konkrete `run_plan.json` und der Launcher bestimmen die auszufuehrenden Jobs. Bioakustik verwendet vorbereitete Metadaten, Inventar und Master statt der Step-1-Aenderungsliste. Beide Phasen teilen den Pipeline-Lock. `afterany` erlaubt Diagnose nach Fehlschlaegen; harte `afterok`-Kanten (insbesondere Step 6) blockieren abhaengige Arbeit. Solche Jobs koennen `DependencyNeverSatisfied` melden; nicht blind erneut submitten.


### Slurm-Submitfehler

`AssocGrpSubmitJobsLimit` bedeutet, dass das gemeinsame Submit-Limit der Slurm-Association erreicht ist. Es koennen bereits Teiljobs eingereiht sein. Erst `squeue` und `sacct` pruefen; keine zweite Pipeline darueber starten und den Lock nicht bei aktiven Jobs entfernen. Die begrenzten Worker reduzieren die Zahl der gleichzeitig eingereihten Array-Elemente.

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
plant alle aktuellen IDs und alle globalen Kernschritte. Slurm-Abhaengigkeiten verwenden je nach Zweig `afterany` oder `afterok`; blockierte Jobs muessen geprueft werden.
Erfolgreiche Vollauf-Steps erhalten atomare Marker; ein neuer Submit reiht nur
Steps ohne Marker erneut ein.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `in_progress` | `not resume` | [plan_pipeline_run.py:469](../../tools/plan_pipeline_run.py) |
| `complete` | `Ausgabe in main` | [run_with_manifest.py:117](../../tools/run_with_manifest.py) |
| `failed` | `Ausgabe in main` | [run_with_manifest.py:117](../../tools/run_with_manifest.py) |
| `starting` | `Ausgabe in main` | [horeka_controller.py:180](../../tools/horeka_controller.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `ValueError: Bioacoustics is disabled in this configuration.` | `not config.get('bioacoustics', {}).get('enabled', True)` | [plan_pipeline_run.py:522](../../tools/plan_pipeline_run.py) |
| `FileNotFoundError: Run the core pipeline first; missing prerequisite: {path}` | `not path.is_file()` | [plan_pipeline_run.py:528](../../tools/plan_pipeline_run.py) |
| `ValueError: Prepared metadata and master IDs differ; finish the core pipeline first.` | `ids != master_ids` | [plan_pipeline_run.py:534](../../tools/plan_pipeline_run.py) |
| `ValueError: Require positive counts and 0 <= worker-index < worker-count` | `worker_count < 1 or task_count < 1 or (not 0 <= worker_index < worker_count)` | [run_array_worker.py:13](../../tools/run_array_worker.py) |
| `ValueError: A child command is required` | `not command` | [run_array_worker.py:20](../../tools/run_array_worker.py) |
| `ValueError: Unknown pipeline phase: {phase}` | `phase not in {'core', 'bioacoustics', 'all'}` | [pipeline_phase.py:16](../../scripts/pipeline_phase.py) |
| `ValueError: POINT_ASSIGNMENT_INCOMPLETE: {len(gaps)} recording IDs missing, duplicated or at different coordinates in {path}. Run Step 2.2 first; the existing master has not been replaced.` | `gaps` | [input_consistency.py:54](../../scripts/input_consistency.py) |
| `ValueError: SOURCE_POPULATION_REDUCED: source has {len(current)} IDs; {len(removed)} of {len(previous)} existing IDs would disappear. Restore the complete original source. For an intentional reduction set metadata_extraction.allow_large_source_reduction=true explicitly.` | `previous and len(removed) > max(10, len(previous) * 0.2) and (not settings.get('allow_large_source_reduction', False))` | [input_consistency.py:73](../../scripts/input_consistency.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `args.mode == 'bioacoustics'` | [plan_pipeline_run.py:564](../../tools/plan_pipeline_run.py) |
| `0` | `Ausgabe in main` | [plan_pipeline_run.py:884](../../tools/plan_pipeline_run.py) |
| `3` | `except FileExistsError` | [pipeline_lock.py:50](../../tools/pipeline_lock.py) |
| `0` | `Ausgabe in acquire` | [pipeline_lock.py:62](../../tools/pipeline_lock.py) |
| `0` | `not path.exists()` | [pipeline_lock.py:68](../../tools/pipeline_lock.py) |
| `4` | `not force and owner_run and (owner_run != run_id)` | [pipeline_lock.py:76](../../tools/pipeline_lock.py) |
| `0` | `Ausgabe in release` | [pipeline_lock.py:79](../../tools/pipeline_lock.py) |
| `0` | `args.command == 'status'` | [pipeline_lock.py:95](../../tools/pipeline_lock.py) |
| `2` | `not args.run_id and (not args.force)` | [pipeline_lock.py:98](../../tools/pipeline_lock.py) |
| `2` | `not command` | [run_with_manifest.py:76](../../tools/run_with_manifest.py) |
| `submitted.returncode or 1` | `submitted.returncode != 0 or not submission_path.is_file()` | [horeka_controller.py:233](../../tools/horeka_controller.py) |
| `0` | `args.local_test` | [horeka_controller.py:256](../../tools/horeka_controller.py) |
| `130` | `except KeyboardInterrupt` | [horeka_controller.py:313](../../tools/horeka_controller.py) |
| `128 + interrupted` | `interrupted` | [run_array_worker.py:54](../../tools/run_array_worker.py) |
| `1` | `failed` | [run_array_worker.py:57](../../tools/run_array_worker.py) |
| `0` | `Ausgabe in run_worker` | [run_array_worker.py:58](../../tools/run_array_worker.py) |
| `run_stage_all(root, Path(sys.executable), variants, args.stage, force=args.force, ids_file=args.ids_file, max_workers=1)` | `config.get('lrt_variants', {}).get('input_dir')` | [run_spatial_stage.py:22](../../tools/run_spatial_stage.py) |
| `0` | `Ausgabe in main` | [finalize_master.py:23](../../tools/finalize_master.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->
