# Validation And Formation-Status Comparison (DE)

## Aktueller Betrieb (2026-09-23)

Der Abschlussbericht nennt `phase`. `core` fordert keine Step-6-Produkte; `bioacoustics` prueft Step 6 und seine Voraussetzungen. Ohne `BIOOTON_RUN_PLAN` prueft ein Direktaufruf den gesamten bisherigen Scope. `readiness_policy` und einzelne require_*-Schalter bleiben wirksam innerhalb der Phase.


## Zweck
Vergleicht Formation-Status-Produkte und erzeugt finalen Validierungsreport.

## Script
`tools/compare_formation_status_products.py, tools/final_validation_report.py`

## Eingaben
- `outputs/step_2_*`
- `optional legacy/reference formation-status files`

## Outputs
- `outputs/step_8_susi_compatibility/*`
- `outputs/step_9_validation/*`

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_7_0_master_table`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `master_table`, `final_validation`, `susi_sanity_check`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python tools/compare_formation_status_products.py --config config.horeka.json`
- `python tools/final_validation_report.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Reports werden pro Lauf neu geschrieben; Inputs bleiben unveraendert.

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

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `master_table_missing_or_empty` | Masterdatei fehlt oder ist leer. | [final_validation_report.py:249](../../tools/final_validation_report.py) |
| `master_table_read_error:{type(exc).__name__}` | Masterdatei konnte nicht gelesen werden. | [final_validation_report.py:256](../../tools/final_validation_report.py) |
| `master_missing_column:{column}` | Aktivierte Readiness-Pruefung benoetigt eine fehlende Master-Spalte. | [final_validation_report.py:295](../../tools/final_validation_report.py) |
| `{column}_not_ready:{not_ready}` | Unter strikter Readiness-Policy sind Zeilen fuer diese Anforderung nicht bereit. | [final_validation_report.py:307](../../tools/final_validation_report.py) |

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `ok` | `Ausgabe in check_path` | [final_validation_report.py:35](../../tools/final_validation_report.py) |
| `missing` | `required and (not exists)` | [final_validation_report.py:37](../../tools/final_validation_report.py) |
| `empty` | `required and (not nonempty)` | [final_validation_report.py:39](../../tools/final_validation_report.py) |
| `optional_missing` | `not required and (not exists)` | [final_validation_report.py:41](../../tools/final_validation_report.py) |
| `missing_column` | `column not in table.columns` | [final_validation_report.py:289](../../tools/final_validation_report.py) |
| `ok` | `Ausgabe in master_readiness` | [final_validation_report.py:301](../../tools/final_validation_report.py) |
| `not_ready` | `Ausgabe in master_readiness` | [final_validation_report.py:301](../../tools/final_validation_report.py) |
| `validated` | `Ausgabe in main` | [final_validation_report.py:435](../../tools/final_validation_report.py) |
| `has_issues` | `critical or failed_manifest_steps or missing_planned_manifests or readiness['critical']` | [final_validation_report.py:442](../../tools/final_validation_report.py) |
| `ready` | `Ausgabe in main` | [final_validation_report.py:446](../../tools/final_validation_report.py) |
| `manual_review_required` | `Ausgabe in main` | [final_validation_report.py:446](../../tools/final_validation_report.py) |
| `approved` | `Ausgabe in main` | [final_validation_report.py:449](../../tools/final_validation_report.py) |
| `not_started` | `Ausgabe in main` | [final_validation_report.py:449](../../tools/final_validation_report.py) |

### Explizite Fehlermeldungen

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0 if technical_status == 'validated' else 2` | `Ausgabe in main` | [final_validation_report.py:495](../../tools/final_validation_report.py) |
| `0` | `Ausgabe in main` | [compare_formation_status_products.py:509](../../tools/compare_formation_status_products.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->
