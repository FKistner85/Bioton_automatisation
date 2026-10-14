# Bio-O-Ton – Zeitregel v4: Abnahme und produktiver Wiederanlauf
**Datum:** 13.10.2026 · **Status:** Code und lokaler Master-Snapshot geprüft; **nicht** auf LSDF oder HoreKa ausgerollt.

## Beschluss / Semantik

`timestamp_source` bleibt unverändert ein Herkunftsfeld (`localtimes`, `datetime`). Ein korrekt parsbarer, eindeutig in `Europe/Berlin` lokalisierter `datetime`-Fallback mit irreführendem `+00:00`-Suffix ist **kein Zeitfehler**; `time_has_issues=False`. Ein `localtimes`-Eintrag wird weiterhin bevorzugt. Echte Widersprüche, fehlende Zeitwerte, nicht vorhandene Frühlingsstunden, ungeklärte doppelte Herbststunden, fehlende Offsets und unvollständige Zeitprüfung werden weiter markiert. `datetime_local` hat ausnahmslos `YYYY-MM-DD HH:MM:SS` ohne Zeitzonensuffix, `datetime_utc` ein korrektes UTC-`Z`-Format. Niemals das irreführende Null-Offset der Quellspalte direkt als UTC-Instant konvertieren.

**Wichtige Safety-Regel:** Bei einem alten Master mit `timestamp_source=datetime`, aber noch altem `timestamp_change_reason=utc_instant_to_Europe/Berlin`, darf ein Master-Only-Refresh den Zeitfehler **nicht** aufheben. Erst ein Step-1-Lauf mit der v4-Auflösung stellt die geprüfte Zeit und den erfolgreichen Provenienzmarker her. Diese Schutzmaßnahme wurde in `refresh_time_quality()` eingefügt.

## Nachweisbarer lokaler Datenabgleich

| Merkmal | Ergebnis |
|---|---:|
| Dawn-Chorus-CSV Deutschland | 112.444 IDs |
| Vorliegender v5-Master-Snapshot | 111.866 IDs |
| Noch nicht im hochgeladenen Master | 578 IDs |
| Fallback `datetime`, vormals fälschlich als UTC behandelt | 3.288 |
| Korrekte lokale Uhrzeiten, vollständig gegen Quell-Digits abgeglichen | 3.288 |
| Quelle `datetime`, im korrigierten Snapshot `time_has_issues=False` | 3.288 |
| Quelle `localtimes`, weiterhin `time_has_issues=True` wegen Quellkonflikten | 47 |
| Änderung lokaler Kalendertag | 4 |
| Änderung UTC-Kalendertag | 1 |
| Ungültige Datums-/Uhrzeitformate im korrigierten Snapshot | 0 |
| Auf der Dawn-Chorus-Website unabhängige Nutzer-Stichproben | 14 |
| Neuberechnung von Wetterfenstern nötig | 4 |
| Sentinel-2 Szenenauswahl prüfen/neu erzeugen | 1 |

Die 3.288 Werte wurden rechnerisch auf dieselbe Zeitpolicy geprüft; dabei ergaben sich keine DST-Lücken oder ungeklärten Folds. Dieser **vollständige strukturelle Abgleich** und 14 unabhängige Website-Kontrollen liefern eine klare Evidenz für die Regel. **Nicht behauptet wird, alle 111.866/112.444 Aufnahmen individuell an der Website geprüft zu haben.** Die 47 eigenen `localtimes`-Konflikte bleiben ausdrücklich als offene Qualitätsprobleme sichtbar.

## Codeänderungen und Qualitätsvertrag

- `scripts/recording_time.py`: fehlerhafte UTC-Zuweisung repariert; v4-Policy entfernt reine Provenienzwarnungen nur für valide Fälle; echte DST-/Parsing-/Quellfehler bleiben bestehen. Echte Nichtnull-Offsets erhalten eine unterscheidbare Konvertierungsbegründung.
- `scripts/Step_7_0_update_master_table.py`: QC richtet sich nach gültigem Zeitwert, geloggter Prüfung und reparierter Konvertierungsregel **nicht** nach `timestamp_source != localtimes`; alte Master ohne aktuelle Zeitauflösung bleiben vorsichtshalber gesperrt; `time_source_not_localtimes` als veralteter Sperrcode wird aufgeräumt.
- `scripts/Step_1_metadata_extraction.py`: nimmt v4-Policy in die betroffenen Quellen-Fingerprints auf; beschränkte Metadatenmigration wird neu erkannt.
- Bestehende Fixes aus v3 bleiben: scoped Planner, 4 Wetter-Neuberechnungen lokal und HoreKa, Sentinel-Date-Drift-Sperre, persistente QC-Warnungen, DST-Handling, 7.1-Refresh.
- `schemas/master_table.schema.json`, `README.md`, `README_CI_TEC.md/.tex/.pdf`, `MASTER_TABLE_README.md`, normative revidierte **2-seitige** PDF, Step-README und generierte Fehlercodes aktualisiert. **Alte historische Audits bleiben als historische Nachweise erkennbar**.

## Verfügbare Artefakte

- Separater **korrigierter v5-Snapshot**: `Bio_O_Ton_Master_Zeitfix_QC_korrigiert_v5_snapshot.csv` (111.866 Zeilen, 102 Spalten). Das ist bewusst **keine produktive v7-Master-Rekonstruktion**; dazu fehlen in der Upload-Sitzung die aktuellen LSDF-Produktinventare. Er enthält die geprüften korrigierten Aufnahmezeiten, zwei getrennte Quelllabels, korrekte Zeitflags, aktualisierte davon abhängige Ready-Flags sowie vorsichtshalber gesperrte 4 Wetter-/1 Sentinel-Produkte.
- Die 47 offenen Quellkonflikte: `BioOTon_Zeitfix_Verbleibende_Zeitkonflikte_47.csv`.
- Revidierte offizielle zweitseitige PDF: `Bio_O_Ton_Mastertable_README_Zeitregel_v4_2026-10-13.pdf`.

## Lokale Pipeline (Windows)

1. Backup von `Bio_O_Ton_Master.csv`, Metadatenlogs/Fingerprints, Wetter, Sentinel, Status und Config erstellen. Alte und neue Codeversionen nicht mischen.
2. `powershell -File .\scripts_local_run\run_pipeline_local.ps1 -Mode functionality_test`.
3. `powershell -File .\scripts_local_run\run_pipeline_local.ps1 -Mode add_new_ids -SkipLsdfPublish`.
4. Prüfen, ob die 3.288 Fallback-IDs tatsächlich in Step 1 verarbeitet wurden; Log `timestamp_status=validated`, `timestamp_issue_codes=''`, `timestamp_source=datetime`, `timestamp_change_reason=datetime_zero_utc_label_interpreted_as_German_walltime` und 3.288x `time_has_issues=False` im neuen Master.
5. Die vier veralteten Wetterdatumsfenster `9814310`, `9814106`, `9811988`, `9812288` mittels nicht-`missing-only` Lauf aktualisieren (nur wenn lokale Wetterpipeline aktiv; andernfalls auf HoreKa). Anschließend Step 5.1 QC und Step 7.0; ggf. Step 7.1.
6. Sentinel-ID `9891840` neu auf korrekte UTC-Szenenauswahl prüfen und ggf. exportieren; QC erst nach tatsächlicher Bestätigung per `master_table.sentinel_time_rechecked_ids_csv` freigeben.

## HoreKa-Pipeline

1. Identischen Code und Git-Stand wie lokal deployen. `config.horeka.json`, Mounts und Secrets prüfen.
2. Zuerst Plan kontrollieren: `python tools/plan_pipeline_run.py --config config.horeka.json --run-id zeitfix_v4_review --mode add_new_ids`. Prüfen, dass v4-Metadaten auf betroffene IDs beschränkt sind, Wetter-Neuberechnung ausschließlich die vier relevanten IDs umfasst und räumliche Vollläufe nicht ungewollt getriggert werden.
3. Controller-Simulation: `bash run_horeka.sh add_new_ids --local-test --foreground`.
4. Erst nach Planabnahme: `bash run_horeka.sh add_new_ids` (oder vorhandenen, gleichwertigen Slurm-Einstieg). HoreKa erzwingt für die vier Wetterfälle eigene Verarbeitung auch bei schon vorhandener Wetterdatei; Produkt-QC und Master folgen.
5. Sentinel-Ausnahme manuell prüfen, 7.0 und 7.1 ggf. fertigstellen; CSV/Parquet-Spalten und Zeit/QA-Invarianten mit dem korrigierten Snapshot vergleichen, *zusätzliche 578 Quell-IDs* separat kontrollieren.

**Kein vollständiger** `from_scratch`-Lauf erforderlich. Audio-, Foto-, LRT-Geometrie-, 100-/10-m-Raster- und Bioakustik-Inferenz werden allein wegen dieses Fehlers nicht neu berechnet.

## Testgrenze / Freigabegate

- 32 fokussierte Tests bestanden; 1 Parquet-Test nicht ausgeführt (kein `pyarrow` / `fastparquet`). Umfangreichere lokale Windows-/LSDF-Tests benötigen dortige Mounts. Python-`compileall`, Bash-`-n`, Diagnosereferenz-`--check` bestanden.
- **Keine** produktiven LSDF-, Windows-, Sentinel/GEE-, Wetter- oder HoreKa-Jobs wurden hier durchgeführt. Produktive Daten dürfen erst nach Wiederanlauf, Wetter-/Sentinel-QC, Statusvergleich und Backup ersetzt werden.
- Die README behauptet ausdrücklich keine individuelle Website-Verifikation aller Aufnahmen und unterscheidet strukturelle Regelvalidierung von tatsächlichem Daten-QC.
