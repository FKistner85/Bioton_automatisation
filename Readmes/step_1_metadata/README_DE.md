# Step 1 Metadata Extraction (DE)

## Zweck
Normalisiert Dawn-Chorus-IDs, Koordinaten und Zeitfelder.

## Script
`scripts/Step_1_metadata_extraction.py`

## Eingaben
- `PointData/dawn-chorus-soundscape.csv`

## Outputs
- `outputs/step_1_metadata/dawnchorus_metadata_clean.csv`
- `outputs/step_1_metadata/dawnchorus_metadata_log.csv`

## Abhaengigkeiten und Invalidierung
Die logischen Schrittvertraege stehen in `pipeline_steps.json` unter `step_1_metadata`. Der zentrale Run-Planer gibt nur betroffene IDs weiter und plant globale Schritte nur bei geaenderten Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs.

## Konfiguration
Ergebnisrelevante Einstellungen stehen zentral in `config.horeka.json`: `dawn_chorus_csv`, `status_dir`, `metadata_extraction`. Datenpfade und fachliche Schwellen stammen aus der Konfiguration. Slurm-Ressourcen und BIOOTON_*-Overrides werden vom Launcher und optionalen Clusterprofil aufgeloest.

Step 1 verarbeitet ausschliesslich Zeilen, bei denen die konfigurierte
Länderspalte dem konfigurierten Zielland entspricht (standardmaessig
`country = Germany`). Fehlt die Länderspalte, bricht der Step ab. Wechselt ein
zuvor verarbeitetes ID in ein anderes Land, wird es aus den Step-1-Outputs
entfernt und kann bei der folgenden Mastertable-Aktualisierung nicht mehr
erscheinen.

## Ausfuehrung
`bash slurm_add_new_ids.sh` startet den inkrementellen Kernlauf; `bash slurm_from_scratch.sh` baut den Kern neu auf. Step 6 startet separat mit `bash slurm_bioacoustics.sh`. Ein isolierter technischer Direktlauf ist mit folgenden Befehlen moeglich:
- `python scripts/Step_1_metadata_extraction.py --config config.horeka.json`

## Batch- und Parallelisierungslogik
`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. Der Step verwendet nur die in der Konfiguration erlaubte Zahl von Prozessen/Workern. IDs oder Chunks besitzen eindeutige Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock verhindert konkurrierende schreibende Gesamtlaeufe.

## Checkpoint/Resume
Neue IDs werden inkrementell ergaenzt; from_scratch nutzt --force.

## Qualitaetskontrolle
Outputs gelten nicht allein wegen ihrer Existenz als gueltig. Kompakte und detaillierte Logs, Batch-Statusdateien und das Run-Manifest dokumentieren Validierung und Fehler. Der finale Gate wird mit `bash run_final_validation_report.sh` erzeugt; Formation-Produkte koennen zusaetzlich mit `bash slurm_compare_formation_status.sh` verglichen werden.

## Status, Manifeste und Mastertabelle
Der Slurm-Orchestrator schreibt fuer diesen Step ein Manifest unter `outputs/step_0_manifests/<step>/<step_run_id>.json` mit `workflow_run_id`, Inputs, Parametern, Laufzeit, Logs und Outputs. Step 7 fasst die ID-bezogenen Ergebnisse in der Mastertabelle zusammen; technische Details bleiben in den Step-Logs. Kanonische Run-Statuswerte stehen in `scripts/common.py`; `schemas/status_model.json` definiert Status-Event-Felder.

## Typische Fehler
Fehlende Inputs oder Konfigurationsabschnitte beenden den Step mit Exit-Code ungleich null. Datenprobleme einzelner IDs werden nach Moeglichkeit im Detail-/Retry-Log als `missing`, `has_issues` oder `failed` festgehalten. Nach einem Timeout wird derselbe Betriebsmodus erneut submitted; gueltige Checkpoints werden wiederverwendet.

## German recording-time policy (2026-10-13, v4)

`localtimes` has first priority: keep its local clock and apply actual
Europe/Berlin DST. A nonempty but invalid or ambiguous local clock is flagged,
not silently replaced by `datetime`. When `localtimes` is missing, zero-offset
`datetime` values (Z/+00:00) from Dawn Chorus have been verified against the
website as mislabeled **German local wall clocks** for 14 examples. Preserve
the clock components, localize to Europe/Berlin (gap/fold detection), and only
then derive real UTC. The 3,288 affected recordings passed the structural source-wide
reconciliation and no longer carry a warning solely due to provenance. Nonzero-offset `datetime` values continue
to be interpreted as offset-aware instants. If no offset exists, the historical
UTC assumption remains visible in timestamp issues.

The normative 13.10.2026 ci-tec PDF requires `datetime_local` **without**
any timezone suffix (`%Y-%m-%d %H:%M:%S`) and `time_has_issues=False` for clean
time. Step-1 stores an internal ISO time **with** the correct German offset;
Step-7 exports the local clock without offset and a real UTC instant. Step-1
QC issue reasons persist in the master's additional `time_issue_codes` field.
The revised normative PDF now describes the checked local-clock interpretation
of the zero-offset datetime fallback. The 3,288 source rows were reconciled;
14 independent website spot-checks support the correction, not a per-row website audit.

The clean intermediate `datetime` retains the correct +01:00/+02:00 offset.
The master `datetime_local` stores only the German clock, without an offset.
Planner and extraction share fingerprints. A policy change invalidates metadata,
weather and Sentinel planning. The first migration therefore revisits existing IDs,
not only newly added IDs. A scoped extraction never acknowledges untouched IDs.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-10-13. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `datetime_timezone_missing_assumed_utc` | datetime hat keinen Offset und wird als UTC interpretiert; Warnung bleibt sichtbar. | [recording_time.py:63](../../scripts/recording_time.py) |
| `localtimes_unparseable` | Nichtleere localtimes ist unlesbar; kein stiller UTC-Fallback. | [recording_time.py:71](../../scripts/recording_time.py) |
| `nonexistent_localtime` | Lokale Uhrzeit faellt in die uebersprungene Fruehlingsstunde; bleibt ungueltig. | [recording_time.py:81](../../scripts/recording_time.py) |
| `ambiguous_localtime_unresolved` | Doppelte Herbststunde ohne eindeutigen Offset/UTC-Abgleich; Zeitpunkt bleibt ungueltig. | [recording_time.py:98](../../scripts/recording_time.py) |
| `localtimes_offset_mismatch` | Mitgelieferter lokaler Offset passt nicht zu Europe/Berlin; lokale Uhrzeit bleibt massgeblich. | [recording_time.py:100](../../scripts/recording_time.py) |
| `utc_reference_unavailable` | Keine nutzbare UTC-Referenz fuer den Gegencheck. | [recording_time.py:102](../../scripts/recording_time.py) |
| `datetime_missing_or_unparseable` | Ohne lokale Zeit ist auch datetime nicht nutzbar. | [recording_time.py:106](../../scripts/recording_time.py) |
| `ambiguous_localtime_unresolved` | Doppelte Herbststunde ohne eindeutigen Offset/UTC-Abgleich; Zeitpunkt bleibt ungueltig. | [recording_time.py:121](../../scripts/recording_time.py) |
| `utc_local_conflict` | UTC-Referenz widerspricht der lokalen Uhr; localtimes bleibt massgeblich. | [recording_time.py:144](../../scripts/recording_time.py) |

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `within_broad_germany_bounds` | `Ausgabe in build_outputs` | [Step_1_metadata_extraction.py:115](../../scripts/Step_1_metadata_extraction.py) |
| `outside_broad_germany_bounds` | `Ausgabe in build_outputs` | [Step_1_metadata_extraction.py:116](../../scripts/Step_1_metadata_extraction.py) |
| `invalid_wgs84_coordinates` | `Ausgabe in build_outputs` | [Step_1_metadata_extraction.py:117](../../scripts/Step_1_metadata_extraction.py) |
| `invalid` | `Ausgabe in resolve_recording_time` | [recording_time.py:145](../../scripts/recording_time.py) |
| `warning` | `Ausgabe in resolve_recording_time` | [recording_time.py:145](../../scripts/recording_time.py) |
| `validated` | `Ausgabe in resolve_recording_time` | [recording_time.py:145](../../scripts/recording_time.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `FileNotFoundError: Config file not found: {config_path}` | `not config_path.is_file()` | [Step_1_metadata_extraction.py:52](../../scripts/Step_1_metadata_extraction.py) |
| `ValueError: Missing required Dawn Chorus column: id` | `'id' not in source.columns` | [Step_1_metadata_extraction.py:155](../../scripts/Step_1_metadata_extraction.py) |
| `ValueError: Missing required Dawn Chorus country column: {country_column}` | `country_column not in source.columns` | [Step_1_metadata_extraction.py:157](../../scripts/Step_1_metadata_extraction.py) |
| `FileNotFoundError: IDs file not found: {path}` | `not path.is_file()` | [Step_1_metadata_extraction.py:271](../../scripts/Step_1_metadata_extraction.py) |
| `KeyError: No dawn_chorus_id/id column in {path}` | `Ausgabe in read_ids_file` | [Step_1_metadata_extraction.py:280](../../scripts/Step_1_metadata_extraction.py) |
| `ValueError: This pipeline requires country Germany and timezone Europe/Berlin` | `timezone != DEFAULT_TIMEZONE or country_value != 'Germany'` | [Step_1_metadata_extraction.py:347](../../scripts/Step_1_metadata_extraction.py) |
| `FileNotFoundError: Dawn Chorus CSV not found: {input_csv}` | `not input_csv.is_file()` | [Step_1_metadata_extraction.py:359](../../scripts/Step_1_metadata_extraction.py) |
| `ValueError: Germany recordings require timezone Europe/Berlin` | `timezone != GERMAN_TIMEZONE` | [recording_time.py:49](../../scripts/recording_time.py) |
| `ValueError: POINT_ASSIGNMENT_INCOMPLETE: {len(gaps)} recording IDs missing, duplicated or at different coordinates in {path}. Run Step 2.2 first; the existing master has not been replaced.` | `gaps` | [input_consistency.py:54](../../scripts/input_consistency.py) |
| `ValueError: SOURCE_POPULATION_REDUCED: source has {len(current)} IDs; {len(removed)} of {len(previous)} existing IDs would disappear. Restore the complete original source. For an intentional reduction set metadata_extraction.allow_large_source_reduction=true explicitly.` | `previous and len(removed) > max(10, len(previous) * 0.2) and (not settings.get('allow_large_source_reduction', False))` | [input_consistency.py:73](../../scripts/input_consistency.py) |

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `1` | `except Exception` | [Step_1_metadata_extraction.py:460](../../scripts/Step_1_metadata_extraction.py) |
| `0` | `Ausgabe in main` | [Step_1_metadata_extraction.py:498](../../scripts/Step_1_metadata_extraction.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->
