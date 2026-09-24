# HoReKa-Neustart nach Review vom 17.09.2026

> Historischer Stand: Befunde und Zahlen gelten fuer den damaligen Audit/Lauf. Aktuelle Betriebsanweisungen stehen in der Haupt-README und Readmes/pipeline_phases.md.


## Voraussetzung
Die lokalen Änderungen sind noch nicht committet/gepusht und noch nicht auf HoReKa übertragen. Ein `git pull` allein liefert sie deshalb derzeit NICHT. Erst den geprüften Arbeitsstand einschließlich der neuen Dateien übertragen bzw. committen/pushen. Bestehende Geheimnisse und Umgebungen bleiben auf HoReKa.

Quelle: `/lsdf/kit/ipf/projects/Bio-O-Ton/PointData/dawn-chorus-soundscape.csv`. Der Nutzer bestätigt, dass neue IDs dort bereits enthalten sind. Die Referenz-Mastertabelle ersetzt diese Quelle nicht.

## Befehle auf HoReKa (nach Übertragung)
Aus dem vorhandenen Repository `bio_o_ton_pipeline_git`:

```bash
export PYTHON="$PWD/.venv/bin/python"
export CONFIG="$PWD/config.horeka.json"
git status --short
squeue -u "$USER"
bash run_horeka.sh functionality_test --foreground
bash run_horeka.sh add_new_ids --local-test --foreground
# Nur nach erfolgreichen Tests und geprüftem Run-Plan:
bash run_horeka.sh add_new_ids --session bioton_refresh_20260917

tmux attach -t bioton_refresh_20260917
# Mit Ctrl-b, dann d wieder lösen; der Controller läuft weiter.
squeue -u "$USER"
```

Der lokale Test erzeugt einen Plan und prüft Voraussetzungen, ohne Slurm-Jobs zu starten. Er ist kein vollständig schreibfreier Trockenlauf. Keine aktive Pipeline parallel starten und keinen Lock blind löschen. Der inkrementelle Plan berücksichtigt neue/geänderte IDs sowie bekannte Probleme bestehender IDs. Erfolgreiche Downloads und Checkpoints werden weiterverwendet; nicht jedes QC-Problem lässt sich durch einen Download beheben.

Für belastbare Ressourcenmessung nach dem Lauf:

```bash
sacct -u "$USER" -S 2026-08-19 --units=G --parsable2 \
  --format=JobID,JobName%40,State,Elapsed,Timelimit,AllocCPUS,TotalCPU,ReqMem,MaxRSS \
  > horeka_resource_usage.psv
scontrol show partition cpuonly
```

`MaxRSS` steht oft in `.batch`-/Job-Step-Zeilen: diese nicht herausfiltern. Kein `-X` verwenden. Laut KIT-Dokumentation belegt `cpuonly` ganze Nodes; weniger angeforderte Kerne allein sparen dort nicht automatisch Kontingent. Lange Downloads, Rasterjobs und Inferenz bleiben in Slurm; Controller, Plan und bisherige kurze Nachverarbeitung bleiben in tmux. Weitergehendes Zusammenlegen von Jobs benötigt Messdaten und wurde nicht implementiert.

## Änderungen
- Zusammengehörige indexierte Zeitkorrekturen in 18 Dateien wiederhergestellt. Vorheriger Arbeitsstand: `tmp/horeka_review_20260917/preexisting_unstaged.patch` und Dateisicherungen. Git-Index unverändert.
- Step 5.3 und 5.5 begrenzen Worker auf die Slurm-Zuweisung. Separate Standardzuweisungen von je 4 CPUs (`BIOOTON_STEP53_CPUS`, `BIOOTON_STEP55_CPUS`). Step 6.2-Verifikation: 1 CPU.
- Zeitlimits pro Job konfigurierbar, z.B. `export BIOOTON_TIME_BIO_STEP53=02:00:00`. Globale Zeitüberschreibung hat Vorrang. Wegen 145 August-Fehlerlogs mit Zeitlimit-Abbruch keine pauschale Laufzeitverkürzung.
- Nach Jobabschluss aktualisiert der Hybridcontroller `step_0_slurm_logs/current/<jobname>/` und `archive/<Zeitstempel>/<jobname>/`. Hardlinks benötigen keine zweite Kopie der Logdaten; Originalpfade bleiben erhalten. Dies ist eine Archivansicht, kein Verschieben oder Löschen der Originale. Array-Tasks werden gemeinsam angezeigt; aktuell bedeutet neueste Submission, nicht letzter erfolgreicher Lauf. Bei fehlender Hardlink-Unterstützung erfolgt eine Warnung.
- Master-Schema v6 ergänzt `proximity_check_status`, `duplicate_candidate`, `duplicate_neighbor_count`, `spatiotemporal_cluster_id`, `spatiotemporal_cluster_size`.
- Direkte Kandidaten: sphärische Entfernung <=10 m UND UTC-Zeitdifferenz <=300 s. Gruppen: <=50 m UND <=1800 s, transitive Zusammenhangskomponenten. Eine Gruppe ist keine Garantie, dass jedes Paar innerhalb der Grenzen liegt. Gruppen-IDs können sich bei neuen Mitgliedern ändern. Fehlende/ungültige Raum-Zeit-Werte ergeben unbekannte Flags. Keine Änderung von Readiness, Downloadauswahl oder Datenbestand durch Flags.
- `proximity_review` in der JSON-Konfiguration kann `duplicate_distance_m`, `duplicate_seconds`, `cluster_distance_m`, `cluster_seconds` überschreiben. Grenzen sind inklusive. Bei inkrementellen Masterupdates werden Nachbarschaften über alle verbleibenden IDs neu berechnet.

## Befunde aus der Referenz
111.866 IDs; fehlend: 716 Audios, 13.758 Sentinel-Produkte, 572 Wetterdateien. Weitere QC-Probleme: 7.661 Audio, 2.136 Sentinel, 8.600 Wetter. Fehlende Fotos sind häufig und nicht automatisch beschaffbar. Bioakustik: 103.489 failed, 7.805 not_started, 572 ohne Status; der nächste Lauf kann daher umfangreich werden.

Näheprüfung: 10.161 direkte Kandidaten, 7.711 direkte Paare; 62.346 IDs in 20.059 größeren Gruppen. Laufzeit lokal rund 4,3 Sekunden. Die Original-CSV wurde nicht verändert.

367 `.err`-Logs aus August untersucht: 145 mit Zeitlimit-Abbruch, 48 mit fehlendem Keras-Modell, 96 mit FileNotFoundError (u.a. BEATs). Kategorien können sich überschneiden. Diese Logs beweisen nicht das Verhalten des neuen September-Codes.

## Validierung und Grenzen
Gezielte Tests erfolgreich: recording_time, step1_incremental, weather_inventory, weather_download_selection, pipeline_control, master_table, common_manifest, bioacoustics_pipeline, formation_variant_table sowie proximity_and_log_views. Letzterer enthält UTC/DST-, Grenzwert-, Arraylog-, Brute-Force-Vergleich und inkrementellen Nachbar-Test. Bash-Syntax wurde geprüft. Vollständiger Testlauf zum Abschluss noch nicht bestätigt; ein ursprünglicher Regressionstest benötigte lokal PyAV, das temporär nachinstalliert wurde. Keine Live-Prüfung von Slurm, LSDF, Zugangsdaten oder Modellgewichten.

Quellen: https://www.nhr.kit.edu/userdocs/horeka/batch/ und https://www.nhr.kit.edu/userdocs/horeka/accounting/
