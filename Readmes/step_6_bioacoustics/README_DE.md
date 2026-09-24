# Step 6 - Bioakustische Embeddings und Arteninferenz

## Aktueller Betrieb (2026-09-23)

Separater Start nach dem Kernlauf: `bash slurm_bioacoustics.sh` oder `bash run_horeka.sh bioacoustics`. Step 6.1 gleicht mit `--reconcile-all` alle aktuellen Metadaten-IDs ab; entfernte IDs bleiben nicht in der Worklist. Unveraenderte Work-Keys nutzen Checkpoints. Standard: 64 logische Shards je Modell, bis zu vier Worker mit je 4 CPUs, 24 GB und 12 Stunden. `require_all_models_complete=true` macht den vorgeschalteten Verify-Gate fuer alle sechs Modelle verbindlich; die anschliessende ID-QC unterscheidet weiterhin `required` und optionale Modelle. Das Master-Ende aendert nur Bioakustikfelder.


## Zweck

Step 6 verarbeitet technisch valide Dawn-Chorus-Audiodateien mit Bacpipe. Er
erzeugt modellbezogene Embeddings, segmentweise Artenvorhersagen,
Deutschland-/Saison-Plausibilitaetskennzeichen, Aufnahme-Aggregate und einen
kompakten QC-Status pro `dawn_chorus_id`.

Grundlage ist die
[offizielle Bacpipe-API](https://github.com/bioacoustic-ai/bacpipe).
`run_pretrained_classifier`, Device und Klassifikatorschwelle werden explizit
gesetzt und sind Teil des Modellfingerprints.

Die threshold- und Top-k-begrenzten Modellvorhersagen vor der
Plausibilitaetspruefung bleiben erhalten. Plausibilitaetsfilter markieren
Vorhersagen; das kanonische Rohvorhersageprodukt aus Step 6_3 wird nicht
ueberschrieben.

## Abhaengigkeiten

- Step 1 liefert den korrigierten Aufnahmezeitpunkt.
- Step 3_0_a post liefert das Audio-Inventar nach dem Download.
- Step 3_1_a liefert vorhandene Original-Audiodateien.
- Bacpipe laeuft in `.venv_bacpipe` mit Python 3.11.
- CPU-Jobs verwenden standardmaessig HoreKa `cpuonly`; eine GPU ist nicht
  erforderlich.

## Teilschritte und Outputs

### Step 6_0: Modell-Preflight

`scripts/Step_6_0_bioacoustic_model_preflight.py` prueft Bacpipe-Version,
Torch/CUDA, Modelle und Taxonomiereferenz. Vor der Modellinitialisierung ruft
er explizit Bacpipes `ensure_models_exist` auf. Damit werden fehlende
Checkpoint-Dateien einmalig aus `vskode/bacpipe_models` nach
`bacpipe/model_checkpoints/` relativ zum aktiven Checkout geladen und bei Folgejobs
wiederverwendet. Pflichtmodelle muessen danach initialisierbar sein; optionale
Modelle werden ebenfalls bereitgestellt. In der HoreKa-Konfiguration muessen
alle sechs Modelle initialisierbar sein, bevor Step 6_1 oder Step 6_2 startet.
Der Preflight wird fuer jeden Lauf mit geplanter Bioakustik-Inferenz erneut
ausgefuehrt; ein veraltetes Registry-JSON kann ihn nicht mehr ueberspringen.

Ein vorhandener Ordner gilt nicht automatisch als gueltiger Checkpoint. Bei
typischen Fehlern wie fehlenden Keras-Dateien, abgeschnittenen PyTorch-Archiven
oder ungueltigen ZIP-Zentralverzeichnissen verschiebt der Preflight den
betroffenen Modellbaum nach
`bacpipe/model_checkpoints/_quarantine/<zeit>_<modell>/`, laedt ihn einmal neu
und initialisiert das Modell erneut. Die Reparatur wird im Modellregister
protokolliert; die defekten Dateien bleiben zur Diagnose erhalten.

```text
outputs/step_6_0_bioacoustic_model_preflight/model_registry.json
```

### Step 6_1: Worklist

`scripts/Step_6_1_prepare_bioacoustic_worklist.py` waehlt nur probe-, decode-
und dauer-validierte Audios. Pro ID wird genau eine valide Datei verwendet.

```text
outputs/step_6_1_bioacoustic_worklist/worklist.csv
outputs/step_6_1_bioacoustic_worklist/worklist.parquet
outputs/step_6_1_bioacoustic_worklist/rejected_audio.csv
outputs/step_6_1_bioacoustic_worklist/state.json
```

### Step 6_2: Embeddings und native Modelloutputs

`scripts/Step_6_2_generate_bioacoustic_embeddings.py` wird als Slurm-Array
mit bis zu vier Slurm-Workern ausgefuehrt. Die 64 logischen Shards je Modell
bleiben erhalten; jeder Worker bearbeitet mehrere Modell-/Shard-Aufgaben nacheinander. Jeder Task schreibt nach kleinen Batches atomare
Parquet-Checkpoints. Native Klassenscores werden bereits hier auf den
konfigurierten Mindestscore und Top-k pro Segment begrenzt, damit keine
unkontrolliert grossen Zwischenprodukte entstehen.

Nach dem Array prueft ein eigener Verify-Job jeden erwarteten Pflichtmodell-
Shard-Status und Worklist-Schluessel. Probleme optionaler Modelle blockieren nur dann nicht, wenn
`require_all_models_complete` ausgeschaltet ist. Die aktuelle Horeka-Konfiguration
setzt diesen Wert auf `true`: alle sechs Modelle muessen abschliessen. Erst dieser Verify-Job
markiert Step 6_2 als vollstaendig abgeschlossen. Einzelne Array-Tasks koennen
daher einen unvollstaendigen Full-Rebuild nicht versehentlich als fertig
kennzeichnen. Bei einem Timeout bleiben deren Checkpoints erhalten; ein
Folgelauf berechnet nur fehlende oder fehlgeschlagene Worklist-Eintraege neu.
Die Verifikation schreibt zusaetzlich eine kompakte Aufschluesselung je Modell
nach `step_6_2_bioacoustic_state/verification.json`. Step 6_3 bis Step 6_6
verwenden harte `afterok`-Abhaengigkeiten und starten nicht, wenn die
Verifikation fehlschlaegt.

Die HoreKa-Standardwerte sind 64 Shards pro Modell, vier CPUs und 24 GB RAM pro
Array-Task sowie 12 Stunden Walltime. Drei Minuten vor dem Walltime sendet Slurm
`SIGUSR1`; der Task speichert seinen letzten Batch und markiert den Shard als
`interrupted`.

```text
outputs/step_6_2_bioacoustic_embeddings/model=<modell>/*.parquet
outputs/step_6_2_bioacoustic_native_predictions/model=<modell>/*.parquet
outputs/step_6_2_bioacoustic_state/model=<modell>/shard=<n>.json
```

### Step 6_3: Vorhersagen normalisieren

`scripts/Step_6_3_normalise_species_predictions.py` vereinheitlicht
Klassifikatorausgaben, wendet den konfigurierten Mindestscore an und behaelt
Top-k Vorhersagen pro Segment.

```text
outputs/step_6_3_species_predictions_raw/model=<modell>/predictions.parquet
```

### Step 6_4: Deutschland und Saison

`scripts/Step_6_4_filter_germany_taxonomy.py` verwendet:

```text
reference_data/germany_species_allowlist.csv
```

Die ausgelieferte Datei ist bewusst nur ein Template. Bis eine fachlich
freigegebene Referenz eingetragen ist, lautet der Status `not_evaluated`.

```text
outputs/step_6_4_species_predictions_germany/model=<modell>/predictions.parquet
```

### Step 6_5: Aufnahme-Aggregation

`scripts/Step_6_5_aggregate_bioacoustic_results.py` aggregiert Segmente und
Modelle. Modellkonfidenzen werden nicht miteinander gemittelt.

```text
outputs/step_6_5_bioacoustic_recording_summary/recording_summary.csv
outputs/step_6_5_bioacoustic_recording_summary/recording_summary.parquet
outputs/step_6_5_bioacoustic_recording_summary/recording_species.parquet
```

### Step 6_6: Qualitaetskontrolle

`scripts/Step_6_6_bioacoustic_quality_control.py` vergleicht erwartete und
abgeschlossene Modelle. Pflichtmodelle bestimmen die Bioakustik-Readiness;
die QC in Step 6_6 orientiert sich an `required`. Der vorgeschaltete
Verify-Gate kann mit `require_all_models_complete=true` strenger sein.

```text
outputs/step_6_6_bioacoustic_quality_control/bioacoustic_qc_compact.csv
outputs/step_6_6_bioacoustic_quality_control/bioacoustic_qc_detailed.csv
outputs/step_6_6_bioacoustic_quality_control/state.json
```

## Modelle

Pflichtmodelle sind `birdnet`, `perch_v2`, `audioprotopnet` und
`convnext_birdset`. `insect66` und `naturebeats` sind optionale
Embedding-Modelle. Fledermausmodelle sind fuer normale Smartphone-Aufnahmen
nicht aktiviert, weil deren Samplingrate typische Ultraschallrufe nicht
zuverlaessig abbildet.

Die Modellgewichte werden im Preflight explizit bereitgestellt und danach
instanziiert. Schlaegt die Initialisierung eines Pflichtmodells fehl, startet
das Inferenzarray nicht. Ein fehlgeschlagener Registry-Status wird im naechsten
`bioacoustics`-Lauf erneut versucht.

## Resume

Der Verarbeitungsschluessel enthaelt Audiofingerprint, Modellfingerprint,
Bacpipe-/Preprocessing-Version und Modellparameter. Abgeschlossene IDs werden
pro Modell/Shard gespeichert. Nach einem Timeout laufen nur offene IDs weiter;
Inference-Fehler bleiben offen und werden beim naechsten Lauf erneut versucht.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `bacpipe_import_failed:{type(exc).__name__}:{exc}` | Bacpipe konnte nicht importiert werden. | [Step_6_0_bioacoustic_model_preflight.py:117](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `bacpipe_version_mismatch:expected={expected_version}:actual={bacpipe_version}` | Installierte und konfigurierte Bacpipe-Version unterscheiden sich. | [Step_6_0_bioacoustic_model_preflight.py:121](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `torch_import_failed:{type(exc).__name__}:{exc}` | PyTorch konnte nicht importiert werden. | [Step_6_0_bioacoustic_model_preflight.py:137](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `model_checkpoint_dir_not_accessible:{checkpoint_dir}` | Checkpoint-Verzeichnis hat nicht die benoetigten Zugriffsrechte. | [Step_6_0_bioacoustic_model_preflight.py:144](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `bacpipe_ensure_models_exist_unavailable` | Bacpipe bietet die erwartete Checkpoint-Bereitstellung nicht an. | [Step_6_0_bioacoustic_model_preflight.py:165](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `{type(repair_exc).__name__}:{repair_exc}` | Originaler Exception-Typ und Meldung; kein eigener statischer Fehlercode. | [Step_6_0_bioacoustic_model_preflight.py:223](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `required_model_initialisation_failed:{name}` | Pflichtmodell bzw. unter require_all_models jedes Modell kann nicht initialisiert werden. | [Step_6_0_bioacoustic_model_preflight.py:232](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `inventory_issue` | Worklist verwirft Audio; Detailgruende aus dem Inventar fehlen. | [Step_6_1_prepare_bioacoustic_worklist.py:86](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `duplicate_valid_audio_for_id` | Weitere valide Audiodatei fuer dieselbe ID; nur die ausgewaehlte Datei kommt in die Worklist. | [Step_6_1_prepare_bioacoustic_worklist.py:103](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `missing_state` | Erwartete Shard-State-Datei fehlt oder ist nicht nutzbar. | [Step_6_2_generate_bioacoustic_embeddings.py:116](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `state={state.get('status', 'unknown')}` | Shard-State hat nicht den erwarteten Status complete. | [Step_6_2_generate_bioacoustic_embeddings.py:121](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `failed_ids={len(state_failed)}` | Shard-State enthaelt fehlgeschlagene IDs. | [Step_6_2_generate_bioacoustic_embeddings.py:125](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `task_error` | Shard-State enthaelt einen Fehler des gesamten Tasks. | [Step_6_2_generate_bioacoustic_embeddings.py:127](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `shard_count_mismatch` | Gespeicherte und konfigurierte Shardzahl unterscheiden sich. | [Step_6_2_generate_bioacoustic_embeddings.py:129](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `missing_rows={shard_missing}` | Erwartete Work-Keys sind im Shard nicht abgeschlossen. | [Step_6_2_generate_bioacoustic_embeddings.py:146](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `required_models_incomplete` | Mindestens ein Pflichtmodell ist fuer die Aufnahme nicht abgeschlossen. | [Step_6_6_bioacoustic_quality_control.py:91](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `model_inference_failed` | Mindestens ein Modell meldet einen Inferenzfehler fuer die ID. | [Step_6_6_bioacoustic_quality_control.py:93](../../scripts/Step_6_6_bioacoustic_quality_control.py) |

### Statuswerte (nicht alle sind Fehler)

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `started` | `checkpoint_error_is_repairable(exc)` | [Step_6_0_bioacoustic_model_preflight.py:195](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `repaired` | `checkpoint_error_is_repairable(exc)` | [Step_6_0_bioacoustic_model_preflight.py:213](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `failed` | `except Exception` | [Step_6_0_bioacoustic_model_preflight.py:222](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `failed` | `Ausgabe in main` | [Step_6_0_bioacoustic_model_preflight.py:243](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `has_warnings` | `Ausgabe in main` | [Step_6_0_bioacoustic_model_preflight.py:243](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `validated` | `Ausgabe in main` | [Step_6_0_bioacoustic_model_preflight.py:243](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `rejected` | `Ausgabe in build_worklist` | [Step_6_1_prepare_bioacoustic_worklist.py:85](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `rejected` | `not duplicate_audio.empty` | [Step_6_1_prepare_bioacoustic_worklist.py:102](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `complete` | `Ausgabe in main` | [Step_6_1_prepare_bioacoustic_worklist.py:222](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `complete` | `Ausgabe in verify_shards` | [Step_6_2_generate_bioacoustic_embeddings.py:150](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `incomplete` | `Ausgabe in verify_shards` | [Step_6_2_generate_bioacoustic_embeddings.py:150](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `failed` | `Ausgabe in verify_shards` | [Step_6_2_generate_bioacoustic_embeddings.py:184](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `raw_model_prediction` | `Ausgabe in normalise_model` | [Step_6_3_normalise_species_predictions.py:68](../../scripts/Step_6_3_normalise_species_predictions.py) |
| `complete` | `Ausgabe in main` | [Step_6_3_normalise_species_predictions.py:105](../../scripts/Step_6_3_normalise_species_predictions.py) |
| `not_evaluated` | `allowlist.empty` | [Step_6_4_filter_germany_taxonomy.py:120](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `accepted` | `Ausgabe in apply_filter` | [Step_6_4_filter_germany_taxonomy.py:147](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `flagged` | `Ausgabe in apply_filter` | [Step_6_4_filter_germany_taxonomy.py:148](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `not_evaluated` | `Ausgabe in apply_filter` | [Step_6_4_filter_germany_taxonomy.py:153](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `complete` | `Ausgabe in main` | [Step_6_4_filter_germany_taxonomy.py:197](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `complete` | `Ausgabe in main` | [Step_6_5_aggregate_bioacoustic_results.py:121](../../scripts/Step_6_5_aggregate_bioacoustic_results.py) |
| `validated` | `Ausgabe in build_qc` | [Step_6_6_bioacoustic_quality_control.py:94](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `partial` | `Ausgabe in build_qc` | [Step_6_6_bioacoustic_quality_control.py:94](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `failed` | `Ausgabe in build_qc` | [Step_6_6_bioacoustic_quality_control.py:94](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `complete` | `Ausgabe in main` | [Step_6_6_bioacoustic_quality_control.py:149](../../scripts/Step_6_6_bioacoustic_quality_control.py) |

### Explizite Fehlermeldungen

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
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

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `1 if issues else 0` | `Ausgabe in main` | [Step_6_0_bioacoustic_model_preflight.py:276](../../scripts/Step_6_0_bioacoustic_model_preflight.py) |
| `0` | `Ausgabe in main` | [Step_6_1_prepare_bioacoustic_worklist.py:237](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `1` | `except Exception` | [Step_6_1_prepare_bioacoustic_worklist.py:240](../../scripts/Step_6_1_prepare_bioacoustic_worklist.py) |
| `2` | `not worklist_path.is_file()` | [Step_6_2_generate_bioacoustic_embeddings.py:83](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `2` | `blocking_models` | [Step_6_2_generate_bioacoustic_embeddings.py:205](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0` | `Ausgabe in verify_shards` | [Step_6_2_generate_bioacoustic_embeddings.py:207](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0` | `model_index >= len(models)` | [Step_6_2_generate_bioacoustic_embeddings.py:433](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0` | `pending.empty` | [Step_6_2_generate_bioacoustic_embeddings.py:501](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `1` | `except Exception` | [Step_6_2_generate_bioacoustic_embeddings.py:507](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `2` | `except Exception` | [Step_6_2_generate_bioacoustic_embeddings.py:528](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `3` | `stop_requested` | [Step_6_2_generate_bioacoustic_embeddings.py:661](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0 if not failed_by_id else 2` | `Ausgabe in main` | [Step_6_2_generate_bioacoustic_embeddings.py:676](../../scripts/Step_6_2_generate_bioacoustic_embeddings.py) |
| `0` | `Ausgabe in main` | [Step_6_3_normalise_species_predictions.py:115](../../scripts/Step_6_3_normalise_species_predictions.py) |
| `1` | `except Exception` | [Step_6_3_normalise_species_predictions.py:118](../../scripts/Step_6_3_normalise_species_predictions.py) |
| `0` | `Ausgabe in main` | [Step_6_4_filter_germany_taxonomy.py:214](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `1` | `except Exception` | [Step_6_4_filter_germany_taxonomy.py:217](../../scripts/Step_6_4_filter_germany_taxonomy.py) |
| `0` | `Ausgabe in main` | [Step_6_5_aggregate_bioacoustic_results.py:132](../../scripts/Step_6_5_aggregate_bioacoustic_results.py) |
| `1` | `except Exception` | [Step_6_5_aggregate_bioacoustic_results.py:135](../../scripts/Step_6_5_aggregate_bioacoustic_results.py) |
| `0` | `Ausgabe in main` | [Step_6_6_bioacoustic_quality_control.py:161](../../scripts/Step_6_6_bioacoustic_quality_control.py) |
| `1` | `except Exception` | [Step_6_6_bioacoustic_quality_control.py:164](../../scripts/Step_6_6_bioacoustic_quality_control.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->
