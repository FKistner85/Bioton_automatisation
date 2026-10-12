# Master-Schema: Abgleich mit ci-tec-PDF vom 09.10.2026

Gepruefte Referenz: `C:/Users/Frede/Downloads/Bio_O_Ton_Mastertable_read_me_ci_tec (1).pdf`, beide Seiten ausgelesen und visuell geprueft. Das Dokument beschreibt den Datenvertrag; die Anweisungen zur spaeteren Analyse sind keine Aufforderung, Masterzeilen herauszufiltern. Massgeblich sind ausserdem die beiden ausdruecklichen Nutzerentscheidungen: reine Wetter-NaNs und reine Audio-Dauerabweichungen sind Hinweise; die Mastertabelle bleibt ungefiltert.

## Ergebnis und Datenvertrag

Schema `2026-10-09-mastertable-v7`, 106 geordnete Spalten in CSV und Parquet. Horeka und lokale Pipeline rufen denselben `scripts/Step_7_0_update_master_table.py` auf, einschliesslich Zwischenupdates, finaler Aktualisierung, fokussiertem Metadaten-Refresh und separater Bioakustikphase.

| PDF-Vorgabe | Umsetzung / Pruefergebnis |
|---|---|
| Eine Zeile pro Aufnahme-ID | Kein neuer Qualitaetsfilter und keine Dauergrenze in der Zeilenauswahl. Problematische Aufnahmen bleiben enthalten. Bestehende Regeln zur Metadatenpopulation, eindeutigen IDs und geloeschten Quell-IDs bleiben bestehen. |
| Deutsche Ortszeit ohne Suffix | `datetime_local` bleibt `%Y-%m-%d %H:%M:%S`; UTC wird vorher aus dem offsetbehafteten Step-1-Wert bestimmt. Winter, Sommer, Tageswechsel und beide DST-Wechsel getestet. |
| `time_has_issues` | False genau fuer `timestamp_source=localtimes`. Fallback `datetime`, unbekannte und fehlende Herkunft ergeben True. Eine ungueltige lokale Uhrzeit wird zusaetzlich durch Metadaten-/Readinesschecks erkannt. |
| Rohdaten statt Clean-Auswahl | Alle IDs bleiben in der Tabelle, auch mit Fallbackzeit, 39 s / 0 s Audio, fehlender Dauer oder problematischen Sentinel-Bildern. Die vorgeschlagenen Analysefilter werden erst vom Verbraucher angewendet. |
| `duration_seconds` | Gepruefte Dauer aus dem detaillierten Audioinventar. Null wenn unbekannt; bei mehreren Dateien Minimum der bekannten Dauern. Technische Dateiprobleme bleiben separat geflaggt. Metadaten-Refresh kann die bisherige Dauer erhalten. |
| Audio ausserhalb 59-61 s | `duration_not_60s` bleibt als Hinweis; allein setzt der Code weder im Inventar noch Download-QC noch Master eine Issue-Flag. Dekodierungsfehler und fehlende/ungueltige Eigenschaften bleiben problematisch. Die 40-s-Grenze wird nicht automatisch angewendet. |
| Wetter `missing_value` | Code bleibt sichtbar, setzt allein keine Issue-Flag. Zeit-, Struktur-, Plausibilitaets- und Lesefehler bleiben problematisch. Auch alte kompakte Inventare werden hinsichtlich dieses Hinweises korrekt interpretiert. |
| `_exists` | Inventarstatus der physischen Datei; keine Live-Dateipruefung und keine Qualitaetsfreigabe. |
| Fehlendes QC | Fehlende Issue-Checks gelten nicht als bestanden. Vorhandene Audiodatei mit unbekannter Dauer erhaelt `duration_unavailable`. |
| Sentinel | Score 0 bleibt 0 und setzt `too_cloudy_sentinel_not_available`. Physisch vorhandene Datei kann weiter exists=True sein. Fehlender Score setzt `quality_score_missing`. |
| Grid und direkte LRT-Lage | Grid-IDs implizieren keine Mehrheitsformation. `grid_*_has_majority_formation` und `inside_lrt_polygon` bleiben getrennte Kriterien. |
| Inkrementelle Laeufe | Zeitflag und abgeleitete Statuswerte werden auch auf behaltene Zeilen angewendet; keine leeren neuen Zeitflags. Statusereignisse erfassen auch diese Migration. |
| Bioakustik-Updates | Neue Zeitflag, nullable Dauer-Spalte und v7-Version werden ergaenzt. Auf vollstaendigen Masters werden die kombinierten Flags konsistent neu abgeleitet. Audio-only-Bioakustik bleibt unabhaengig von der Zeitquelle. |
| Optionaler kompakter Export | Enthaelt auch Zeitflag, Zeitquelle, Audiodauer und die drei LRT-/Mehrheitskriterien. Der vollstaendige Master bleibt das Standardprodukt. |

`ready_for_*` bleibt ausschliesslich eine abgeleitete Spalte, keine Zeilenauswahl. Kombinierte Flags beruecksichtigen nun die Zeitquelle; `ready_for_bioacoustic_analysis` bleibt davon unabhaengig. Bestehende manuelle Freigaben bleiben erhalten und ersetzen keinen aktuellen Analysefilter.

## Dokumentation und weitere Korrektur

Masterreferenz, ci-tec-README, Haupt-README, lokales Handbuch, Phasenbeschreibung, deutsche/englische Step-7-Texte und generierte Diagnoseverweise wurden aktualisiert. Historische Auditberichte bleiben historische Nachweise. Die beiden gepflegten PDF-Handbuecher werden aus ihren Markdownquellen neu erstellt.

Die vorhandene editierbare LaTeX-Fassung wurde ebenfalls mit der Markdownquelle synchronisiert. Der eingebaute LaTeX-Compiler konnte wegen `windows sandbox: helper_unknown_error: setup refresh had errors` nicht starten; eine erfolgreiche LaTeX-Kompilation wird daher nicht behauptet. Die ausgelieferten PDFs werden unabhaengig davon mit ReportLab erzeugt und geprueft.

Bei der umfassenden Pruefung wurde ein separater Windows-Fehler gefunden: `os.kill(pid, 0)` erzeugt dort ein Konsolensignal statt einer POSIX-Prozessabfrage. Der lokale Orchestrator fragt jetzt ueber Windows-Prozesshandles ab, ob eine Sperre einem lebenden Prozess gehoert. Bei fehlenden Zugriffsrechten bleibt die Sperre vorsichtshalber erhalten. Ein echter gestarteter und anschliessend beendeter Testprozess prueft diese Unterscheidung.

## Validierung

Gezielte Regressionen pruefen den PDF-Datenvertrag, die unveraenderte Zeilenpopulation, identische CSV-/Parquet-Spalten, alte Inventare, fehlende Zeitquellen, inkrementelle Migration, Statusereignisse und technische Fehler. Der vollstaendige Lauf von `tools/functionality_test.py --config config.horeka.json` hat am 12.10.2026 bestanden: alle 25 Testmodule sowie Imports, Konfiguration, Schemas, Step-Registry, Dokumentationsreferenzen und Syntax. Darunter sind zwoelf neue PDF-Vertragsfaelle und sieben Phasentests mit direkten/hybriden Horeka-Startwegen und lokalem Bioakustiklauf. Das Protokoll liegt unter `output/schema_pdf_audit_20261009/functionality_test.log`.

Der Quelltexttest prueft gepflegte Projektdateien und ueberspringt virtuelle Python-Umgebungen, Daten-Snapshots, Logs und temporaere Exporte. Der zuvor gemeldete Latin-1-Fall war eine absichtlich anders kodierte Joblib-Testdatei im lokalen Bacpipe-Environment, kein Fehler im Pipelinecode. Gemeinsame historische `README.md`-Dateien werden vom Dokumentationscheck akzeptiert. Die beiden PDF-Handbuecher werden neu erstellt, gerendert und visuell kontrolliert.

## Anwendung auf vorhandene Daten

Diese Aenderung aktualisiert den lokalen Code und die Dokumentation. Ein Produktivlauf mit allen LSDF-Daten und eine Veroeffentlichung auf Horeka/LSDF sind damit nicht behauptet. Ein regulaerer Kernlauf erstellt v7 aus den Inventaren. Ein inkrementeller Lauf migriert die behaltenen Zeitflags ebenfalls. Ein reiner Bioakustiklauf kann fehlende historische Audiodauern nur als null kennzeichnen; zum Befuellen ist ein Kernlauf mit dem Audioinventar erforderlich. Es werden keine Audiodateien, Wetterbeobachtungen oder Sentinel-Bilder durch diese Anpassung veraendert.
