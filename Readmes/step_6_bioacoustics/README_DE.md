# Step 6 - Bioakustische Embeddings und Arteninferenz

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
`scripts_horeka/bacpipe/model_checkpoints/` geladen und bei Folgejobs
wiederverwendet. Pflichtmodelle muessen danach initialisierbar sein; optionale
Modelle werden ebenfalls bereitgestellt, blockieren die Pipeline bei einem
externen Downloadfehler jedoch nicht.

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
`Modell x Shard` ausgefuehrt. Jeder Task schreibt nach kleinen Batches atomare
Parquet-Checkpoints. Native Klassenscores werden bereits hier auf den
konfigurierten Mindestscore und Top-k pro Segment begrenzt, damit keine
unkontrolliert grossen Zwischenprodukte entstehen.

Nach dem Array prueft ein eigener Verify-Job jeden erwarteten Modell/Shard-
Status und jeden Worklist-Schluessel. Erst dieser Verify-Job markiert Step 6_2
als vollstaendig abgeschlossen. Einzelne erfolgreiche Array-Tasks koennen
daher einen unvollstaendigen Full-Rebuild nicht versehentlich als fertig
kennzeichnen. Bei einem Timeout bleiben deren Checkpoints erhalten; ein
Folgelauf berechnet nur fehlende oder fehlgeschlagene Worklist-Eintraege neu.

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
optionale Modelle blockieren sie nicht.

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
`add_new_ids`-Lauf automatisch erneut versucht.

## Resume

Der Verarbeitungsschluessel enthaelt Audiofingerprint, Modellfingerprint,
Bacpipe-/Preprocessing-Version und Modellparameter. Abgeschlossene IDs werden
pro Modell/Shard gespeichert. Nach einem Timeout laufen nur offene IDs weiter;
Inference-Fehler bleiben offen und werden beim naechsten Lauf erneut versucht.
