# Audit: Grundprinzipien der Codebase

Stand: 2026-07-23

Gepruefter Bereich: `outputs/scripts_horeka`

## Kurzfazit

Die Codebase erfuellt die Prinzipien teilweise schon solide, vor allem fuer:

- zentrale Konfiguration ueber `config.horeka.json`,
- inkrementelle ID-Verarbeitung in Step 1, Step 2_2, Step 3 und Step 5_2,
- Checkpoints fuer Step 2_1 und Step 2_4,
- Batch-/Worker-Steuerung fuer HoreKa,
- kompakte und detaillierte Logs bei Medien-, Sentinel- und Wetterinventaren,
- `outputs/...` als Ziel fuer generierte Pipeline-Produkte.

Geschaetzter Gesamtstand: **ca. 55-60% erfuellt**.

Nachtraeglich umgesetzt am 2026-07-23, Git-Versionierung bewusst ausgenommen:

- gemeinsames Manifest-/Batch-Status-Grundgeruest in `scripts/common.py`,
- Run-Manifeste fuer `Step_2_4_generate_susi_10m_products.py`,
  `Step_5_2_download_weather_data.py` und
  `Step_5_4_prepare_hostrada_rasters.py`,
- Batch-Statusdateien fuer 10m-Chunks, Wetter-Recordings und HOSTRADA-Tiles,
- atomare Tile-Writes und Tile-Resume in Step 5_4,
- finaler Validierungsreport `tools/final_validation_report.py`,
- leichter Smoke-Test `tests/test_common_manifest.py`.

Damit steigt der praktische Erfuellungsgrad fuer die aktuell kritischen
Prinzipien auf etwa **70-75%**, solange Step 4_1 weiterhin als manueller
Sonderstep behandelt wird und noch keine vollstaendige Test-Suite fuer alle
Fachsteps existiert.

Der groesste Abstand zu den Prinzipien liegt nicht in einzelnen Bugfixes, sondern in fehlender Vereinheitlichung:

1. Es gibt kein zentrales Run-/Step-Manifest mit Statusmodell.
2. Checkpoints, Logs und Skip-Logik sind pro Step unterschiedlich geloest.
3. Automatisierte Tests fehlen praktisch komplett.
4. Einige spaetere Steps, besonders Step 4_1, Step 5_3, Step 5_4 und teilweise Step 5_5, sind noch deutlich weniger robust als Step 2/3.
5. Reproduzierbarkeit/Provenienz ist nur teilweise vorhanden: Datei-Fingerprints ja, aber Code-Version, Dependency-Versionen, Run-ID und Batch-ID fehlen meist.

## Bewertung nach Prinzip

| Nr. | Prinzip | Erfuellungsgrad | Bewertung | Hauptbefund |
|---:|---|---:|---|---|
| 1 | Effiziente und inkrementelle Verarbeitung | 65% | Gelb/gruen | Viele Steps skippen vorhandene IDs/Outputs, aber nicht alle Inputs/Konfigs werden gleich sauber versioniert. |
| 2 | Clusteroptimierung mit kontrollierter Batch-Verarbeitung | 70% | Gelb/gruen | Slurm-Orchestrierung, CPU-Caps und Batch-Parallelisierung sind vorhanden; Job-/Batch-Isolation ist aber nicht durchgaengig formalisiert. |
| 3 | Wiederaufnahme ueber Checkpoints | 60% | Gelb | Stark in Step 2_1 und 2_4, solide bei Downloads ueber Logs; schwach bei Raster-/Sentinel-Download-Teilen. |
| 4 | Ausfuehrliche Logs und nachvollziehbarer Status | 45% | Gelb/rot | Viele CSV-/stdout-Logs, aber kein einheitliches strukturiertes Logging mit Start/Ende, Parametern, Ressourcen, finalem Status je Step. |
| 5 | Sanity Checks und Qualitaetskontrollen | 55% | Gelb | Gute Checks fuer Medien, Sentinel-Inventory, Susi-Kompatibilitaet, HOSTRADA-Raster; kein globaler Gate/Fail-Policy-Mechanismus. |
| 6 | Einfache und ausfuehrliche Ergebnisdateien | 70% | Gelb/gruen | Besonders Step 3/4_0 und Susi-Sanity haben kompakt + detailliert. Nicht jeder Step trennt sauber Ergebnis und Diagnose. |
| 7 | Reproduzierbarkeit und Provenienz | 35% | Rot/gelb | Fingerprints/State teils vorhanden, aber kein Git-Commit, keine Dependency-Versionen, keine Run-ID/Batch-ID in allen Outputs. |
| 8 | Trennung von Code, Konfiguration und Daten | 75% | Gruen/gelb | Hauptpfade sind in Config; Rest-Hardcodings existieren als Defaults/Legacy-Pfade. Secrets sind nicht sichtbar hart codiert. |
| 9 | Idempotente Verarbeitungsschritte | 60% | Gelb | Viele Steps sind idempotent genug; einige Outputs werden ohne vollstaendige Konsistenzpruefung geloescht/ueberschrieben. |
| 10 | Validierung vor Veroeffentlichung/Uebergabe | 30% | Rot | Einzelne Sanity-Reports existieren, aber kein definierter Freigabe-/Publication-Status. |
| 11 | Saubere zweisprachige Dokumentation | 45% | Gelb/rot | Globale README und deutsche Schritt-Doku existieren; keine eigene DE/EN README pro Step. |
| 12 | Klare Schnittstellen und stabile Datenformate | 50% | Gelb | Viele Outputs sind dokumentiert; Spalten/Datentypen/Einheiten sind nicht fuer jeden Step formal versioniert. |
| 13 | Testbarkeit und automatisierte Tests | 10% | Rot | Keine echte Teststruktur gefunden. Nur lokale Compile-Checks/Manuelltools. |
| 14 | Sicherer Umgang mit Fehlern | 65% | Gelb/gruen | Viele Steps geben Fehler sichtbar weiter und stoppen sauber; einige Exceptions werden in Worker-/Batch-Kontexten nur begrenzt klassifiziert. |
| 15 | Wartbarkeit vor unnoetiger Komplexitaet | 70% | Gelb/gruen | Code ist pragmatisch modularisiert, aber es gibt Duplikate und mehrere eigene Mini-Frameworks fuer State/Logs. |

## Was schon gut erfuellt ist

### Inkrementelle Verarbeitung

Beispiele:

- `Step_1_metadata_extraction.py`: liest vorhandene IDs aus Clean-/Log-CSV und verarbeitet nur neue IDs.
- `Step_2_2_assign_points_to_lrt_grid.py`: verarbeitet bei unveraenderten Spatial Inputs nur neue Dawn-Chorus-IDs.
- `Step_3_0_a_audio_inventory.py`, `Step_3_0_b_photo_inventory.py`, `Step_4_0_Sentinel2_inventory.py`: vergleichen Dateigroesse und `mtime_ns`, behalten valide bestehende Logzeilen.
- `Step_3_1_a_audio_download.py`, `Step_3_1_b_photo_download.py`: nutzen Retry-Logs, erfolgreiche IDs und terminal failures.
- `Step_5_2_download_weather_data.py`: skippt vorhandene `weather_<id>.csv`, sofern nicht `--force`.

### Checkpoints und Resume

Gute Beispiele:

- `Step_2_1_merge_lrts_and_grid.py`: Chunk-Checkpoints `chunk_<start>_<end>.pkl`, atomarer Write ueber `.tmp` und `replace`.
- `Step_2_4_generate_susi_10m_products.py`: Chunk-Parquets `X_part_*.parquet` werden wiederverwendet; State vergleicht 100m-Quelle, LRT-GPKG und Schema-Version.
- Step 3 Downloads: Retry-Logs werden batchweise geschrieben; bei Timeout laeuft der naechste Run ab dem letzten Logzustand weiter.

### Cluster-/Batch-Optimierung

Gute Beispiele:

- `submit_pipeline_horeka.sh`: Slurm Dependencies, CPU-Parameter pro Step, 30-Minuten-Modus ueber Override.
- Step 2_1/2_4: Batch-Grenzen ueber Grid-Chunks.
- Step 3 Downloads und Weather: Worker werden durch `SLURM_CPUS_PER_TASK` und `max_workers` begrenzt.

### Output-Struktur

Die meisten generierten Analyseprodukte landen korrekt unter:

```text
/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/...
```

Downloads bleiben bewusst in den Originalbereichen:

```text
PointData/SoundRecordings
PointData/Images_SoundRecordings
PointData/S2
PointData/Weather/Hostrada
```

## Groesste Luecken

### 1. Kein zentrales Run-/Step-Manifest

Aktuell hat fast jeder Step eigene State-Logik:

- Step 2_0: `state.json` mit Fingerprints.
- Step 2_1: eigener `should_skip`, Checkpoint-PKLs, eigener State.
- Step 2_4: eigener State und eigene Part-Logik.
- Step 3: detaillierte CSVs + kompakte CSVs + State.
- Step 5_2: Python-Logger + per-recording CSVs, aber kein konsistentes State-Objekt wie Step 2.

Was fehlt:

- ein einheitliches `run_id`,
- ein `step_id`,
- `status = pending/running/complete/failed/skipped/partial/stale`,
- Start-/Endzeit,
- Slurm Job-ID,
- Code-Version,
- Config-Fingerprint,
- Input-Fingerprints,
- Output-Liste,
- Row-/File-Counts,
- Fehler/Warnungen,
- Batch-Status.

Das waere die groesste architektonische Verbesserung.

### 2. Logging ist vorhanden, aber nicht standardisiert

Viele Steps schreiben stdout oder CSV-Logs. Das reicht fuer manuelles Debugging, aber nicht fuer maschinelle Auswertung ueber die ganze Pipeline.

Beispiele:

- Step 5_2 nutzt `logging` und `run_log.txt`: relativ gut.
- Step 3 nutzt CSV-Logs und stdout: gut fuer Inhalte, weniger gut fuer Run-Metadaten.
- Step 2 schreibt meist State + stdout, aber keine strukturierte Run-Logdatei.
- Step 5_4 schreibt nur stdout und erzeugt Tiles, aber kein strukturierter Batch-/Run-Status.

### 3. Automatisierte Tests fehlen fast komplett

Es wurde keine echte `tests/`-Struktur gefunden. Damit sind zentrale Risiken nicht automatisch abgesichert:

- Checkpoint-Resume nach Timeout,
- Schema-Versionierung,
- neue-ID-Erkennung,
- Race-freies paralleles Schreiben,
- Susi-Matrix-Skalierung,
- Medien-Download-/Retry-Logik,
- HOSTRADA-Raster-Tile-Erzeugung.

Das ist der groesste Qualitaets-/Regressions-Risikohebel.

### 4. Step 4_1 und Step 5_4 sind deutlich weniger reif

`Step_4_1_Sentinal_2_download.py`:

- manuell, nicht Teil der normalen Pipeline,
- keine Slurm-Batch-Aufteilung,
- keine `--force`,
- keine explizite Run-State-Datei,
- Download schreibt direkt in Zielpfad, nicht mit `.part` und atomarem Replace,
- Google-Token/credential handling ist funktional, aber nicht sauber in Pipeline-Provenienz eingebunden.

`Step_5_4_prepare_hostrada_rasters.py`:

- kein Resume je Tile/Jahr ueber State,
- kein Skip vorhandener validierter Tiles,
- kein atomarer Tile-Write,
- keine structured logs,
- keine Batch-ID pro Variable/Jahr/Tile,
- bricht bei fehlendem Monat komplett ab.

### 5. Validierung vor Uebergabe ist noch kein definierter Prozess

Es gibt gute Einzelchecks:

- Susi-Kompatibilitaetscheck,
- HOSTRADA-Raster-Quality-Check,
- Medien-Inventory,
- Sentinel-Inventory.

Aber es fehlt ein finales Release-/Handover-Gate, z.B.:

```text
outputs/step_9_validation/final_validation_<run_id>.json
outputs/step_9_validation/final_validation_<run_id>.md
status: draft | validated | rejected | released
```

## Wo die groessten Aenderungen erfolgen muessten

### A. Zentrales Pipeline-State-Modul

Betroffene Dateien:

- `scripts/common.py`
- alle `scripts/Step_*.py`
- `submit_pipeline_horeka.sh`

Ziel:

- Ein gemeinsames State-/Manifest-Format fuer jeden Step.
- Atomare Writes.
- Einheitliche Statuswerte.
- Einheitliche Input-/Output-Fingerprints.
- Einheitliche Run-ID und Batch-ID.

Prioritaet: **sehr hoch**.

### B. Einheitliches Batch-Framework

Betroffene Steps:

- `Step_2_1_merge_lrts_and_grid.py`
- `Step_2_4_generate_susi_10m_products.py`
- `Step_3_1_a_audio_download.py`
- `Step_3_1_b_photo_download.py`
- `Step_5_2_download_weather_data.py`
- `Step_5_4_prepare_hostrada_rasters.py`

Ziel:

- Batch-Tabelle/Manifest je Step.
- Jeder Batch hat ID, Input-Slice, Output-Slice, Status, Attempts, Laufzeit.
- Failed Batches koennen separat wiederholt werden.
- Keine parallelen Writer auf dieselbe Datei.

Prioritaet: **hoch**.

### C. Step 5_4 refactoren

Betroffene Datei:

- `scripts/Step_5_4_prepare_hostrada_rasters.py`

Ziel:

- Ein Batch = `variable + year + tile`.
- Skip, wenn Tile existiert und Quality-Check OK war.
- Atomarer `.tmp.tif` Write.
- State/Log je Tile.
- Optional: fehlende Monate als kontrollierter Status statt sofortiger Komplettabbruch, je nach fachlicher Vorgabe.

Prioritaet: **hoch**, weil der Step teuer ist und aktuell schlecht resume-faehig.

### D. Step 4_1 produktionsreif machen

Betroffene Datei:

- `scripts/Step_4_1_Sentinal_2_download.py`

Ziel:

- `--force`,
- `.part` Downloads + atomarer Rename,
- Retry- und terminal-failure-Status,
- Batch-/Worker-Parallelisierung,
- klare Credential-Konfiguration ausserhalb des Codes,
- Integration in Pipeline nur, wenn Credentials vorhanden sind.

Prioritaet: **mittel/hoch**, falls Sentinel-Download aktiv genutzt wird.

### E. Test-Suite einfuehren

Betroffene neue Struktur:

```text
tests/
tests/fixtures/
tests/test_step1_incremental.py
tests/test_step2_checkpoints.py
tests/test_susi_matrix_schema.py
tests/test_step3_retry_logs.py
tests/test_weather_resume.py
```

Ziel:

- kleine synthetische Daten,
- kein LSDF-Zugriff noetig,
- prueft Resume/Checkpoint/Schema/Idempotenz.

Prioritaet: **sehr hoch**, wenn die Pipeline stabil weiterentwickelt werden soll.

### F. Dokumentation granularisieren

Aktuell:

- globale `README.md`,
- deutsche `PIPELINE_SCHRITTE_DE.md`,
- einige Sonderdokus.

Fehlt:

- eigene README pro Step,
- jeweils DE und EN,
- maschinenlesbare Schema-Doku je Output.

Empfohlene Struktur:

```text
Readmes/
  step_1_metadata/README_DE.md
  step_1_metadata/README_EN.md
  step_2_0_lrt_cleaning/README_DE.md
  ...
schemas/
  step_2_1_majority_formation_grid.schema.json
  step_2_1_susi_matrix.schema.json
```

Prioritaet: **mittel**.

## Konkrete Risiken, die zuerst adressiert werden sollten

1. **Alte Outputs koennen teilweise gueltig wirken, obwohl sie nur teilweise erzeugt wurden.**
   Besonders kritisch bei grossen Raster-/Tile-Produkten und Steps ohne atomaren finalen Complete-Marker.

2. **State-Formate sind uneinheitlich.**
   Das erschwert Pipeline-weite Entscheidungen wie "nur neue IDs" oder "alles vor Step 3 ist vollstaendig OK".

3. **Tests fehlen.**
   Neue Schema-Aenderungen, wie gerade bei Susi-Spalten, koennen ohne Test leicht in 100m/10m divergieren.

4. **Provenienz ist fuer wissenschaftliche Reproduzierbarkeit noch zu duenn.**
   Input-Fingerprints sind gut, aber Code-/Dependency-/Run-Umgebung fehlen meist.

5. **Step 5_4 ist nicht 30-Minuten-resume-optimiert.**
   Wenn der Step abbricht, gibt es keinen sauberen per-Tile Status.

## Empfohlene Reihenfolge

1. Zentrales `run_manifest` und `step_state` in `common.py` bauen.
2. Step 2_1, 2_4, 3_1, 5_2 darauf migrieren.
3. Step 5_4 als Tile-Batch-Step refactoren.
4. Susi-Matrix- und Checkpoint-Tests einfuehren.
5. Step 4_1 produktionsreif machen oder bewusst als manuellen Sonderstep dokumentieren.
6. Finalen Validation-/Release-Report einfuehren.
7. Pro-Step READMEs und Schema-Dateien nachziehen.

## Gesamturteil

Die Codebase ist nicht mehr "Notebook-Sammlung", sondern bereits eine brauchbare HoreKa-Pipeline mit echter Inkrementalitaet in wichtigen Teilen. Fuer den Anspruch der 15 Prinzipien fehlt aber noch ein einheitlicher operativer Kern: Run-Manifest, State-Modell, Batch-Manifest, Tests und finale Validierungsstufe.

Wenn diese Basis gebaut ist, lassen sich die meisten Einzelsteps relativ mechanisch angleichen.
