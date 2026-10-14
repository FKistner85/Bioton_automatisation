# Bio-O-Ton Zeitfix – Code-Release / Prüfprotokoll (13.10.2026)

## Normative Grundlage und unveränderte Referenz

Verbindliche Benutzervorgabe ist `Bio_O_Ton_Mastertable_read_me_ci_tec (3).pdf` (13.10.2026, 2 Seiten). Die angehängte PDF wurde **nicht verändert**. Unveränderter SHA256: `fad063415ba4a05e59f0196dd39bc512b6365af513fee0a4e6d3efb7c885a310`.

Die PDF fordert für `datetime_local` eine deutsche Uhrzeit in `Europe/Berlin` **ohne** Zonen-/Offset-Suffix im Format `%Y-%m-%d %H:%M:%S`; Datenqualitätsflags für Zeit, Ton, Wetter und Sentinel sind getrennt zu behandeln; `time_has_issues=False` ist eine erforderliche Clean-Data-Bedingung.

**Quellwiderspruch ausdrücklich offen:** S. 2 nennt den `timestamp_source=datetime`-Fallback „UTC-based“ und warnt vor bis zu 2 h Abweichung. Die 14 nutzerseitig an der Website überprüften Aufnahmen zeigen dagegen für die betroffenen `+00:00`-Werte, dass ihre Uhrzeit bereits die deutsche Ortszeit ist. Der Code berücksichtigt die empirisch geprüfte Quellkorrektur, ohne die Norm-PDF umzuschreiben. Aus einem systematisch korrigierten Wert folgt jedoch **keine individuelle, unabhängige Validierung aller 3.288 Aufnahmen**: sie behalten `time_has_issues=True` und einen expliziten, dokumentierten QC-Code.

## Implementierte Änderungen

- `scripts/recording_time.py`: Vorrang von `localtimes`; wenn leer, werden `datetime`-Quellwerte mit `Z/+00:00` ohne Stundenversatz als **deutsche Wall Clock** interpretiert und **danach** nach UTC umgerechnet. DST-Lücken/-Folds werden ohne klare Evidenz nicht geraten. Nicht-null Offsets bleiben echte Instants. Neue Regel `german-local-priority-mislabeled-utc-wall-v3`.
- `scripts/Step_1_metadata_extraction.py`: zeitregelbezogene Fingerprints nur für betroffene Quellen und konsistente Metadaten/QC-Provenienz; unveränderte Zeitquellen lösen keinen globalen Wiederanlauf aus.
- `scripts/Step_7_0_update_master_table.py`: Ausgabe `datetime_local` als `YYYY-MM-DD HH:MM:SS` ohne Offset; passende `datetime_utc`, `date_local` und `time_local`; `time_has_issues` anhand Quelle **und** QC; Zeit-Konflikte bleiben nach inkrementellen Updates bestehen. `time_source_not_localtimes` und `time_validation_failed` sind korrekt getrennt; Readiness für Audio bleibt unabhängig. Wiederverwendung einer Sentinel-Szene nach UTC-Datumswechsel ist bis zur ausdrücklichen Bestätigung blockiert.
- `tools/plan_pipeline_run.py`: differenziert zeitbedingte Aktualisierung von Änderungen der WGS84-Koordinaten. Vier veraltete Wetterfenster und ein Sentinel-UTC-Tagswechsel werden nach Vergleich mit bestehendem Master erkannt, auch wenn Step 1 die neuen Fingerprints bereits geschrieben hatte. Zusätzliche Datei `weather_stale_ids.csv` im Runplan.
- `scripts_local_run/local_orchestrator.py`: bestehende Wetterdateien für `weather_stale_ids.csv` werden separat **ohne** `--missing-only` neu berechnet und anschließend inventarisiert; allgemeine schnelle Synchronisierung bleibt inkrementell.
- `submit_bio_o_ton_horeka.sh`: derselbe gezielte Wetter-Neulauf für HoreKa mit `--force`, **nach** der regulären Step-5.2-Verarbeitung, mit Shard-Verify, Step-5.1-QC und serialisiertem Master-Update. Es erfolgt keine globale Force-Neuberechnung aller Wetterdateien.
- `tools/audit_recording_times.py`, `tools/reconcile_master_snapshot.py`, `scripts_local_run/refresh_recording_times.py`: Audit, Vorsicht bei lokaler Migration und semantische Prüfung; geänderte vs. neue Aufnahmen werden getrennt behandelt.
- `tools/documentation_error_meanings.py`, `tools/documentation_reference.py`, `Readmes/*`: Diagnosecodes sind vollständig erklärt und die automatisch erzeugten DE/EN-Referenzen passen zum Code (`--check` erfolgreich). `schemas/master_table.schema.json` dokumentiert die korrekte Definition für Zeitissues.
- Tests für website-basierte 14 Beispiele, DST 2011–2026, echte Ausgabeformate, Masterflags, Fingerprints, Wiederanlauf, lokale/HoreKa-Pipelineplanung und Syntaxprüfung.

## Vollständiger Quell-Audit erneut durchgeführt

Quellfile: `dawn-chorus-soundscape(2).csv`; Referenz: `Bio_O_Ton_Master(2).csv`.

| Prüfgröße | Ergebnis |
|---|---:|
| Aufnahmen in aktueller Quelle | 112.444 |
| Bereits in Referenz-Master | 111.866 |
| Zusätzlich gegenüber altem Master | 578 |
| Aufnahmen mit bereitgestelltem `localtimes` | 109.156 |
| Problematische `datetime`-Fallbacks | 3.288 |
| Korrigierte Uhrzeiten -2 h / -1 h | 3.264 / 24 |
| Veränderter **lokaler** Aufnahmetag | 4 |
| Veränderter **UTC**-Aufnahmetag | 1 |
| Unauflösbare / widersprüchliche Ausgabestempel im Audit | 0 |
| QC weiterhin als `warning` markiert | 3.335 (3.288 Fallbacks + 47 lokale UTC-Konflikte; 46 Offset-Mismatches überschneiden sich mit diesen Konflikten) |

**Betroffene Wetter-IDs:** `9814310`, `9814106`, `9811988`, `9812288`.
**Sentinel-Datumswechsel:** `9891840`.
Die initialen 14 Website-Beispiele werden mit Uhrzeit und korrekt aus Europe/Berlin abgeleitetem UTC getestet.

## Code-Prüfungen

- 43 gezielte Pytest-Tests bestanden: Zeitregeln, Master-README-Vertrag, Planner, Windows/HoreKa-Pfade auf Codeebene, Wetterfenster, Inventar, Quellkonsistenz, automatische Diagnose-Referenzen.
- `python -m compileall -q scripts tools scripts_local_run tests`: bestanden.
- `bash -n submit_bio_o_ton_horeka.sh run_horeka.sh update_horeka_from_git.sh`: bestanden.
- `python tools/documentation_reference.py --check`: keine ausstehenden Änderungen.
- Nicht als E2E-verifiziert zu betrachten: komplette Windows-Laufumgebung, produktive LSDF-Mounts, Slurm-Submission, Earth-Engine-Export sowie Parquet-basierte Tests (in dieser Testumgebung fehlen insbesondere `pyarrow` und ggf. Google-OAuth-Module). Andere plattformbezogene Alt-Tests können unabhängig davon fehlschlagen.

## Empfohlener Wiederanlauf (nicht automatisch ausgeführt)

1. Backup von Quell-, Status-, Master-, Wetter- und Sentinel-Produkten erstellen. `config.horeka.json` und lokale Settings für die jeweilige Umgebung prüfen; aktuellen Code auf **beiden** Installationen installieren. Keine Mischung alter und neuer Skripte.
2. Lokale Funktionstests, bevor LSDF geschrieben wird:
   `powershell -File .\\scripts_local_run\\run_pipeline_local.ps1 -Mode functionality_test`.
3. Optional kontrollierten Prüfplan erzeugen (Pfad/Run-ID anpassen):
   `python tools/plan_pipeline_run.py --config config.horeka.json --run-id timefix_check_20261013 --mode add_new_ids`.
   Im generierten `run_plan.json` und `weather_stale_ids.csv` insbesondere die IDs/Schritte und ausgehende Produktliste kontrollieren.
4. Lokale inkrementelle Pipeline (noch ohne Publikation):
   `powershell -File .\\scripts_local_run\\run_pipeline_local.ps1 -Mode add_new_ids -SkipLsdfPublish`.
   Achtung: Lokaler Wetter-Neulauf setzt eine lokale Weather-Konfiguration (`hostrada_execution` nicht `horeka_only`) voraus. Wenn lokal ausschließlich HoreKa-Wetterdateien gespiegelt werden, ist **HoreKa** für deren Neuberechnung verantwortlich.
5. HoreKa zunächst als simulierten Controllerlauf testen: `bash run_horeka.sh add_new_ids --local-test --foreground`; auf dem Cluster danach: `bash run_horeka.sh add_new_ids`. In beiden Fällen neue Policy sicherstellen und keinen `from_scratch`-Lauf auslösen.
6. Nach vollständigem Wetter-Neulauf das **4er**-Subset im Step-5.1-QC kontrollieren. Für Sentinel-ID `9891840` die mit dem geänderten UTC-Kalendertag ausgewählte GEE-Szene **tatsächlich** neu prüfen/exportieren, dann erst via `master_table.sentinel_time_rechecked_ids_csv` (Spalten `dawn_chorus_id,reviewed`; `reviewed=True`) die Warnung bestätigen; ein vorhandenes altes TIF reicht nicht.
7. Den fertigen Master (v7) einschließlich CSV und Parquet erzeugen, CI-TEC-Ausschnitt/7.1-Formationsvariante bei Bedarf aktualisieren. Audio, Fotos, Rastergeometrien oder die vollständige Bioakustik-Inferenz werden allein wegen dieses Zeitproblems nicht erneut benötigt.
8. QA-Gate: `datetime_local` ohne Suffix, Ausgabezeiten aller 14 Stichproben, alle 3.288 neuen Quell-Uhrzeiten, 47 alten `localtimes`-Konflikte, verbleibende 4 Wetter- und 1 Sentinel-Neuprüfungen, alle Readiness-Flags, kein unberechtigtes Zurücksetzen von `time_has_issues`. Erst danach freigeben/publizieren.

## Wichtige Grenzen

Die 3.288 korrigierten Uhrzeiten sind mit den 14 Website-Stichproben und dem kompletten Datenmuster vereinbar, wurden aber **nicht alle einzeln auf der Website geprüft**. Deshalb bleiben sie als noch unbestätigte Zeitquellen markiert. Die README vom 13.10.2026 bleibt unverändert. Die Formulierung „UTC-based fallback“ darin und die empirische Quellkorrektur lassen sich nicht wortwörtlich zugleich erfüllen; eine textliche Klarstellung wäre eine **separate, durch den Owner zu autorisierende README-Änderung**, nicht Bestandteil dieses Releases.

Alle Arbeiten erfolgten an einer **Kopie des hochgeladenen Repositories**. Weder das aktuelle HoreKa/LSDF-System noch deine lokale produktive Pipeline wurde von hier aus aktualisiert oder gestartet.
