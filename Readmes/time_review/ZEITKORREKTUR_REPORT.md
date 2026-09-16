# Prüfung und Korrektur deutscher Aufnahmezeiten

Stand: 16.09.2026. Quelle: aktualisierte `L:/PointData/dawn-chorus-soundscape.csv` vom 15.09.2026. Die Datei auf LSDF wurde vollständig gelesen und geprüft; ihr SHA-256 stimmt mit der anschließend verwendeten lokalen Kopie überein.

**Die Metadatenkorrektur ist lokal abgeschlossen. Alle 111.866 Aufnahmen erfüllen die vereinbarte Zeitregel. 47 widersprüchliche Quellenangaben bleiben ausdrücklich dokumentiert.** Die wirkliche Geräteuhr dieser 47 Aufnahmen lässt sich aus den widersprüchlichen Angaben allein nicht zweifelsfrei bestätigen.

## Ergebnis

| Prüfung | Ergebnis |
|---|---:|
| Zeilen in Originaldatei, Metadaten und Master | 111.866 |
| Vorhandene `localtimes`: lokale Uhrzeit unverändert übernommen | 108.578 |
| Fehlende `localtimes`: `datetime` aus UTC nach Deutschland umgerechnet | 3.288 |
| Korrektur um +2 Stunden (Sommerzeit) | 3.264 |
| Korrektur um +1 Stunde (Winterzeit) | 24 |
| Abweichungen von der vereinbarten Auswahl-/Umrechnungsregel | 0 |
| Unaufgelöste Zeitwerte | 0 |
| Quellenkonflikte zwischen lokaler Uhrzeit und UTC | 47 |
| Davon unpassender Offset in `localtimes` | 46 |
| Geänderter deutscher Kalendertag | 4 |
| Geänderter UTC-Kalendertag | 1 |

Alle 111.866 Originalzeilen nennen `Germany`; es gibt keine fehlenden oder doppelten IDs. Sämtliche Originalwerte in `datetime` tragen ausdrücklich `+00:00`. Der Zeitraum reicht vom 26.03.2011 bis 15.09.2026.

## Verbindliche Regel und Fehlerbehebung

1. Ein **nicht leeres `localtimes`** ist maßgeblich. Datum und Uhrzeit bleiben erhalten; die gültige deutsche Zeitzone ist `Europe/Berlin`. Ein fremder oder falscher Offset überschreibt die lokale Uhrzeit nicht. Abweichungen zu `datetime` werden protokolliert.
2. **Nur wenn `localtimes` fehlt**, wird `datetime` als Zeitpunkt eingelesen und nach `Europe/Berlin` umgerechnet. Die Sommer-/Winterzeit wird datumsspezifisch bestimmt. Der frühere Code entfernte den UTC-Offset und interpretierte die UTC-Uhrzeit fälschlich als deutsche Uhrzeit; dieser Fehler ist behoben.
3. Nicht parsebare oder im Frühjahr nicht existierende lokale Zeiten werden nicht stillschweigend durch UTC ersetzt oder verschoben. Bei der doppelten Herbststunde entscheidet ein gültiger lokaler Offset; fehlt er, kann eine zur lokalen Uhrzeit passende UTC-Referenz die Stunde auflösen. Ohne eindeutige Evidenz bleibt der Wert als ungültig markiert. In der aktuellen Quelle gibt es keinen solchen unaufgelösten Fall.
4. Ein zukünftiges `datetime` ohne Offset wird als UTC behandelt und ausdrücklich mit `datetime_timezone_missing_assumed_utc` markiert. In der geprüften Datei kommt das **keinmal** vor.
5. Die Ausgabe hat Sekundengenauigkeit. Subsekunden werden nicht als volle Sekundenabweichung gewertet.

**`datetime_local`** enthält jetzt nur die deutsche Uhrzeit, beispielsweise `2025-03-01 16:03:00`, ohne `Z`, `+01:00` oder `+02:00`. Der interne Step-1-Zeitstempel behält den korrekten Offset. Die vollständige Mastertabelle enthält technische UTC-/Datumsfelder; die ci-tec-Kurzfassung enthält nur `datetime_local` als Aufnahmezeitspalte. Das Master-Schema ist auf `2026-09-16-mastertable-v5` aktualisiert.

## Die 47 Quellenkonflikte

Bei 46 Aufnahmen passt der Offset in `localtimes` nicht zu Deutschland am betreffenden Datum; bei einer weiteren Aufnahme passt der Offset, aber die UTC-Referenz widerspricht der lokalen Zeit. Zusammen sind es 47 Aufnahmen. Es werden **keine** dieser vorhandenen lokalen Uhrzeiten automatisch überschrieben.

| ID | Quelldaten und Behandlung |
|---|---|
| 9815166 | `localtimes` fehlt; `datetime=2020-05-04T05:57:00+00:00`. Korrektes Ergebnis: `2020-05-04 07:57:00`. |
| 21741556 | `localtimes=2023-09-07T18:26:00+01:00`, UTC-Referenz `17:26`. Ergebnis bleibt `18:26` deutsche Uhrzeit, nun intern mit `+02:00`; UTC würde `19:26` ergeben. Warnung. |
| 16169704 | `localtimes=2022-05-28T09:12:27+02:00`, UTC-Referenz ebenfalls `09:12:27`. Ergebnis bleibt `09:12:27` lokal; UTC würde `11:12:27` ergeben. Warnung. |

Alle 47 Fälle stehen in [recording_time_conflicts.csv](recording_time_conflicts.csv). Enthalten sind Originalwerte, Koordinaten, gewählte Zeit, UTC-Referenz, Differenz in Sekunden und Fehlercodes. Die Differenz ist **gewählter UTC-Zeitpunkt minus UTC-Referenz**; ein negativer Wert bedeutet, dass die gewählte lokale Zeit früher liegt als die Referenz.

`timestamp_status` und `timestamp_issue_codes` im Step-1-Log dokumentieren diese Quellenwarnungen. `metadata_status` in der Mastertabelle prüft weiterhin technische Gültigkeit und Koordinaten; `validated` bedeutet dort nicht automatisch, dass beide Quellenzeitfelder übereinstimmen.

## Vollständige Verifikation

- Die Implementierung verwendet `zoneinfo`; ein separates Audit rechnet alle Zeilen mit pandas nach. Beide verwenden Zeitzonenregeln, daher ergänzen explizite Regressionstests den Vergleich.
- Alle 108.578 vorhandenen lokalen Uhrzeiten sind komponentengleich erhalten, auf Sekundengenauigkeit.
- Alle 3.288 Fallbacks stimmen als UTC-Zeitpunkt exakt mit dem Original überein.
- Jeder interne Offset wurde gegen `Europe/Berlin` geprüft.
- Geschriebene Metadaten, Step-1-Log und Master stimmen bei allen Zeitwerten überein.
- CSV und Parquet stimmen bei allen Zeitfeldern überein.
- Jede enthaltene Zelle der 14-spaltigen Kurz-CSV stimmt mit der 99-spaltigen Mastertabelle überein.
- Alle IDs und Koordinaten wurden zwischen Quelle und Master abgeglichen.
- 12 Testmodule bestehen. Geprüft sind unter anderem beide Zeitumstellungen jedes Jahres 2011-2026, beide Herbst-Folds, Monats-/Tagesgrenzen, Quellenkonflikte, ungültige lokale Werte ohne Fallback, Cache-Migration, gelöschte IDs, Wetterfenster, Master, Artenfilter und Formation-Varianten.

**Koordinatenprüfung:** Alle Koordinaten sind gültige WGS84-Werte und liegen im breiten Deutschlandrechteck von 47 bis 55,2° Nord und 5,5 bis 15,6° Ost. Dies ist eine ergänzende Plausibilitätsprüfung. Es wurde kein exakter Abgleich gegen Landesgrenzen oder Zeitzonenpolygone durchgeführt. Die Quellenangabe `Germany` ist damit plausibel, aber nicht unabhängig als exakte Landeszuordnung bewiesen.

## Wetter und weitere Horeka-Schritte

### Wetter

Bei folgenden IDs ändert sich das deutsche Datum:

| ID | Bisherige lokale Uhrzeit | Korrigierte lokale Uhrzeit |
|---|---|---|
| 9814310 | 2020-05-15 23:20:00 | 2020-05-16 01:20:00 |
| 9814106 | 2020-05-17 22:26:00 | 2020-05-18 00:26:00 |
| 9811988 | 2020-05-22 23:10:00 | 2020-05-23 01:10:00 |
| 9812288 | 2020-04-25 23:53:00 | 2020-04-26 01:53:00 |

Ihre übernommenen Wetterergebnisse sind im lokalen Master zur erneuten Prüfung markiert. Derselbe lokale Refresh markiert konservativ auch ihre übernommenen Sentinel-Ergebnisse bei einem lokalen Datumswechsel.

Bei zehn vorangehenden lokalen Tagen plus Aufnahmetag ergeben sich:

| Fensterlänge | Aufnahmen |
|---|---:|
| 263 Stunden, über Frühlingsumstellung | 6.267 |
| 265 Stunden, über Herbstumstellung | 242 |
| 264 Stunden | 105.357 |

Die 6.509 Fenster über Zeitumstellungen sind **Prüfkandidaten**, nicht pauschal 6.509 nachgewiesen defekte Wetterdateien. Die bestehenden Dateien wurden in diesem Lauf nicht einzeln auf LSDF nachgeprüft oder neu heruntergeladen.

Download und QC berechnen jetzt dieselben lokalen Kalendergrenzen. Natürliche Herbst-Duplikate und die Frühlingslücke werden zugelassen; echte zusätzliche Duplikate und fehlende Stunden werden weiterhin erkannt. Eine neue QC-Version verhindert die Wiederverwendung alter Prüfergebnisse. Der Planer hält diese QC-Migration unabhängig von schon aktualisierten Step-1-Fingerprints offen, falls ein Lauf zwischen Metadaten und Wetterprüfung abbricht.

### Sentinel, Artenfilter, Formation und andere Produkte

- **Sentinel:** ID **9891840** wechselt als UTC-Zeitpunkt vom 11. auf den 12.05.2021. Die GEE-Auswahl benutzt UTC-Kalendertage; dieser Fall ist gezielt zu prüfen. Zeitfelder und Regelversion gehen jetzt in die Sentinel-Fingerprints ein. Bestehende Drive-/LSDF-Dateien wurden hier nicht fachlich neu berechnet; bloßes Spiegeln garantiert keine angepasste Szenenauswahl. Die unveränderten alten Sentinel-Flags dieser ID sind kein neuer Zeitbezugstest.
- **Artenfilter:** Die Monatsbestimmung verarbeitet gemischte Sommer-/Winterzeit-Offsets sicher und verwendet den deutschen Kalendermonat.
- **Formation-Varianten:** Zeit, Monat und Jahr werden aus den aktuellen Metadaten bezogen, auch wenn der vorhandene Masterstand älter ist. Die Variante muss auf Horeka erneut zusammengeführt werden; diese lokale Korrektur erstellt keine neue vollständige Variantenanalyse.
- **Rastermonate und Audio:** Die vorgehaltenen HOSTRADA-Monatsraster und Audioinhalte hängen nicht von der korrigierten Aufnahmeuhrzeit ab. Die Auswahl des richtigen Wetterfensters muss neu geprüft werden. Die Geometrie und Koordinaten selbst sind unverändert; vorhandene lokale Formation-Produkte wurden verwendet.
- **Gelöschte IDs:** Der zuvor behobene Master-Upsert entfernt nicht mehr vorhandene IDs im aktualisierten Scope. In diesem Datenstand mussten keine IDs gelöscht werden.

## Dateien und Nachweise

- Vollständiger Master: `D:/BioOTon_local_workspace/outputs/Bio_O_Ton_Master.csv`
- Master-Parquet: `D:/BioOTon_local_workspace/outputs/Bio_O_Ton_Master.parquet`
- Kurzfassung: `D:/BioOTon_local_workspace/outputs/Bio_O_Ton_Master_CI_TEC.csv`
- Bereinigte Metadaten und Zeitprotokoll: `D:/BioOTon_local_workspace/outputs/step_1_metadata/`
- Vollständiger Zeilenaudit: `output/review/time_correction_2026-09-16/recording_time_audit_all.csv` (lokaler vollständiger Audit; große Laufzeitdatei, nicht im Git)
- Uhrzeitänderungen: [recording_time_changes.csv](recording_time_changes.csv)
- Quellenkonflikte: [recording_time_conflicts.csv](recording_time_conflicts.csv)
- Wetter-Datumswechsel: [weather_changed_date_ids.csv](weather_changed_date_ids.csv)
- Wetter-DST-Fenster: [weather_dst_window_ids.csv](weather_dst_window_ids.csv)
- Sentinel-UTC-Datumswechsel: [sentinel_changed_utc_date_ids.csv](sentinel_changed_utc_date_ids.csv)
- Prüfsummen, Ergebniszähler und Sicherungspfad: [recording_time_audit_summary.json](recording_time_audit_summary.json)
- Separater LSDF-Nachweis: [lsdf_source_audit_summary.json](lsdf_source_audit_summary.json)
- Geschriebene Produkte: [written_products_validation.json](written_products_validation.json)
- Originaldatei-Kontrollen: [source_crosschecks.json](source_crosschecks.json)
- Testergebnisse: [test_results.json](test_results.json)

Sicherung vor dem Schreiben: `D:/BioOTon_local_workspace/backups/local_time_correction_20260916T123531Z_32400/`.

## Übertragung nach Horeka: nur Befehle, nicht ausgeführt

Die folgenden Befehle dokumentieren die Übertragung des geprüften Codestands. Der Git-Verlauf zeigt den aktuellen Übertragungsstand. Kein Horeka-Job wurde gestartet; keine LSDF-Produktdatei wurde überschrieben. Die lokale Kurzfassung enthält bestehende Bestandsflags und 572 neue IDs mit noch nicht vorhandenen Prüfergebnissen. Diese Flags sind keine aktuelle Vollprüfung des LSDF.

Der erste Lauf mit dieser Regel ist eine **Migration bestehender Aufnahmen**, nicht nur ein Lauf für die 572 neuen IDs. Metadata-, Wetter- und Sentinel-Fingerprints invalidieren beim Wechsel zunächst den gesamten alten Bestand. Der aktuelle Wetter-Downloader verarbeitet ausdrücklich angeforderte IDs erneut; der erste reguläre Lauf kann deshalb **alle 111.866 Wetteraufnahmen** umfassen, statt nur die 6.509 DST-Kandidaten. Das ist vor einem großen Horeka-Lauf zu berücksichtigen. Die Metadaten sind lokal bereits vollständig korrigiert; dieser Wetterlauf ist kein Voraussetzungsschritt für die lokale Zeitkorrektur.

Zuerst lokal in PowerShell, wenn die Änderungen übertragen werden sollen:

```powershell
Set-Location 'C:\Users\Frede\OneDrive\Projects and Disschaptors\Bioton_automatisation'
git add -- MASTER_TABLE_README.md Readmes schemas scripts scripts_local_run tools tests
git diff --cached --stat
git commit -m "Correct German recording times and DST-dependent processing"
git push origin main
```

Danach im **bestehenden Repository-Verzeichnis auf Horeka**, sobald der reguläre Folgelauf gestartet werden soll:

```bash
git pull --ff-only origin main
bash slurm_add_new_ids.sh
```

Die lokal erzeugten Fingerprint- oder Masterdateien nicht vorab über den Horeka-Zustand kopieren: Der dortige Planer soll den Versionswechsel selbst erkennen. Für die vollständige Weiterverarbeitung ist der geplante DAG maßgeblich.
