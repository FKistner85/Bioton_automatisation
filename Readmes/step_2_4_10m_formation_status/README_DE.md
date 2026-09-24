# Step 2_4 10m Formation Status (DE)

## Zweck
Erzeugt checkpointfaehige 10m-Formation-Status-Produkte.

## Script
`scripts/Step_2_4_generate_10m_formation_status_products.py`

## Eingaben
- `outputs/step_2_variants/<suffix>/step_2_1_susi_compatible/Formation_Status_Grid_withLRTCode.parquet`
- `outputs/step_2_variants/<suffix>/step_2_0/lrt_<suffix>.gpkg`

Es wird kein separates originales INSPIRE-10m-Grid eingelesen. Wie in Susis
`3_10mgrid_prep.py` werden die 100 10m-Zellen je 100m-INSPIRE-ID in EPSG:3035
deterministisch abgeleitet: `x0=E100*100`, `y0=N100*100`, anschliessend
`grid_id_10=10mN(N100*10+dy)E(E100*10+dx)` fuer `dx,dy=0..9`.

## Outputs
- `outputs/step_2_variants/<suffix>/step_2_4_susi_10m/*`

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_2_4_10m_formation`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `susi_10m_products`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_2_4_generate_10m_formation_status_products.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Parquet-Parts und _batch_status erlauben Wiederaufnahme nach Timeout.

## Qualitaetskontrolle
Outputs gelten nicht allein wegen ihrer Existenz als gueltig. Kompakte und detaillierte Logs, Batch-Statusdateien und das Run-Manifest dokumentieren Validierung und Fehler. Der finale Gate wird mit `bash run_final_validation_report.sh` erzeugt; Formation-Produkte koennen zusaetzlich mit `bash slurm_compare_formation_status.sh` verglichen werden.

## Status, Manifeste und Mastertabelle
Der Slurm-Orchestrator schreibt fuer diesen Step ein Manifest unter `outputs/step_0_manifests/<step>/<step_run_id>.json` mit `workflow_run_id`, Inputs, Parametern, Laufzeit, Logs und Outputs. Step 7 fasst die ID-bezogenen Ergebnisse in der Mastertabelle zusammen; technische Details bleiben in den Step-Logs. Kanonische Run-Statuswerte stehen in `scripts/common.py`; `schemas/status_model.json` definiert Status-Event-Felder.

## Typische Fehler
Fehlende Inputs oder Konfigurationsabschnitte beenden den Step mit Exit-Code ungleich null. Datenprobleme einzelner IDs werden nach Moeglichkeit im Detail-/Retry-Log als `missing`, `has_issues` oder `failed` festgehalten. Nach einem Timeout wird derselbe Betriebsmodus erneut submitted; gueltige Checkpoints werden wiederverwendet.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `in_progress` | `reset_required` | [Step_2_4_generate_10m_formation_status_products.py:614](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `complete` | `Ausgabe in main` | [Step_2_4_generate_10m_formation_status_products.py:707](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:43](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `KeyError: Missing 'susi_10m_products' section in config.` | `'susi_10m_products' not in config` | [Step_2_4_generate_10m_formation_status_products.py:47](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `FileNotFoundError: Input file not found: {path}` | `not path.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:53](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `ValueError: Invalid 100 m grid_id: {grid_id}` | `match is None` | [Step_2_4_generate_10m_formation_status_products.py:101](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `RuntimeError: Temporary final parquet is empty: {temporary}` | `not temporary.is_file() or temporary.stat().st_size == 0` | [Step_2_4_generate_10m_formation_status_products.py:307](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `RuntimeError: Step 2_4 worker was not initialised.` | `_WORKER_LRT is None or _WORKER_SETTINGS is None` | [Step_2_4_generate_10m_formation_status_products.py:467](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `FileNotFoundError: 10 m grid selection CSV not found: {path}` | `not path.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:503](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `KeyError: 10 m grid selection CSV needs a 'grid_100m_id' or 'grid_id' column.` | `column is None` | [Step_2_4_generate_10m_formation_status_products.py:510](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `ValueError: 10 m grid selection CSV contains no usable grid IDs.` | `not selected` | [Step_2_4_generate_10m_formation_status_products.py:516](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `FileNotFoundError: Missing source parquet: {source}` | `not source.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:545](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `FileNotFoundError: Missing LRT GPKG: {lrt_gpkg}` | `not lrt_gpkg.is_file()` | [Step_2_4_generate_10m_formation_status_products.py:547](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `ValueError: No selected 100 m grid IDs occur in the Step 2.1 product.` | `not grid_ids` | [Step_2_4_generate_10m_formation_status_products.py:636](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `same_inputs and previous_state.get('status') == 'complete' and final_parquet.is_file() and (final_parquet.stat().st_size > 0) and (not args.force)` | [Step_2_4_generate_10m_formation_status_products.py:593](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `0` | `Ausgabe in main` | [Step_2_4_generate_10m_formation_status_products.py:738](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |
| `1` | `except Exception` | [Step_2_4_generate_10m_formation_status_products.py:748](../../scripts/Step_2_4_generate_10m_formation_status_products.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->
