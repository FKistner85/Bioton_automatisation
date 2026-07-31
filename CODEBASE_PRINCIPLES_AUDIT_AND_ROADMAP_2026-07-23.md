# Audit und Fahrplan zu den Grundprinzipien der Codebase

Stand: 2026-07-23

Gepruefter Bereich:

```text
outputs/scripts_horeka
```

## Umsetzungsstand nach dem Audit

Die priorisierten technischen Luecken dieses Dokuments wurden im lokalen
HoreKa-Paket inzwischen umgesetzt:

- zentraler Run-Plan mit Domaenenfingerprints und Changed-ID-Dateien
- atomarer Pipeline-Lock und gemeinsame `workflow_run_id`
- kanonisches Statusmodell, Run-Manifeste v2 und Statusereignisse
- inkrementelle Step-1- und Step-2_2-Upserts fuer bestehende IDs
- Wetterinventar als Mastertable-QC-Quelle mit sauberem Resume
- Remote-Metadatenabgleich fuer Sentinel-2
- Step 5.3 bis 5.5 im Haupt-DAG mit Raster-Checkpoints und inkrementeller QC
- Readiness-Gate und getrennte technische/manuelle Freigabe
- formale JSON Schemas Draft 2020-12
- synthetische Regressionstests fuer Plan, Lock, Changed IDs, Wetter-Resume,
  Formation-Schema und Mastertable-Statushistorie

Noch ausstehend ist die reale Cluster-Abnahme mit LSDF-Daten und Slurm:
Shell-Syntax/Submission auf HoreKa, ein 30-Minuten-Timeout-Resume-Test und ein
vollstaendiger Datenvergleich der 100m-/10m-Produkte mit den Referenzdateien.

## Aktuelle Bewertung nach Umsetzung

Ohne den bewusst zurueckgestellten Git-Punkt sind die Prinzipien nach der
lokalen Implementierung zu etwa **82-87 Prozent** umgesetzt. Die verbleibende
Unsicherheit liegt nicht mehr primaer in fehlender Pipeline-Logik, sondern in
der noch ausstehenden realen Cluster-Abnahme und in einzelnen
Dokumentations-/Betriebsdetails.

| Prinzip | Aktueller Stand | Verbleibende Luecke |
|---|---:|---|
| Inkrementelle Verarbeitung | 90% | Reale Laufzeitmessung bei sehr grossen LSDF-Bestaenden |
| Master-/Status-Orchestrierung | 85% | Master ist Planer-Input, aber keine live aktualisierte Jobdatenbank |
| Kontrollierte Cluster-Batches | 82% | Keine getrennte ID-Lease pro Slurm-Array; globaler Lock verhindert konkurrierende Gesamtlaeufe |
| Checkpoint/Resume | 88% | Timeout-Resume auf HoreKa fuer 2_1, 2_4, 5_2 und 5_4 praktisch abnehmen |
| Logs und Status | 88% | Ressourcenverbrauch nach Jobende noch nicht aus `sacct` ins Manifest zurueckgeschrieben |
| Sanity Checks | 86% | Schwellen und Verteilungen mit echten Referenzdaten fachlich freigeben |
| Kompakt-/Detailoutputs | 82% | Nicht jeder globale Grid-Step besitzt dieselbe kompakt/detail-Trennung |
| Provenienz | 82% | Git-Commit folgt nach der geplanten Repository-Migration |
| Code/Config/Daten-Trennung | 88% | Einige dokumentierte Legacy-Defaults bleiben aus Kompatibilitaetsgruenden |
| Idempotenz | 88% | Cluster-Abnahme fuer Abbruch exakt waehrend eines Atomic-Replaces |
| Validierung/Freigabe | 84% | Teamentscheidung fuer finale manuelle Freigaberegeln |
| DE/EN-Dokumentation | 78% | Step-READMEs sind vorhanden, koennen aber noch um reale Laufzeitbeispiele wachsen |
| Stabile Formate/Schemas | 85% | Schema-Validierung soll spaeter in CI verpflichtend werden |
| Automatisierte Tests | 78% | Kleine lokale Tests vorhanden; echter LSDF-End-to-End-Test fehlt |
| Fehlerbehandlung | 80% | Fehlerklassifikation ist bei einigen historischen Fachsteps noch grob |
| Wartbarkeit | 84% | Legacy-Wrapper erst nach erfolgreichem Referenzvergleich entfernen |

### Verbindlicher Restfahrplan

1. `bash slurm_functionality_test.sh` auf HoreKa ausfuehren.
2. Einen absichtlich auf 30 Minuten begrenzten `from_scratch`-Lauf starten,
   danach denselben Modus erneut submitten und Checkpoint-Resume pruefen.
3. `sacct` und `slurm_logs` fuer alle Jobs kontrollieren; insbesondere
   Step 2_1, 2_4, 5_2 und 5_4.
4. 100m-/10m-Formation-Produkte mit den Referenzdateien vergleichen und
   Skalierung, Spalten, Zeilenzahlen und Majority-Entscheidungen freigeben.
5. Mastertable-Readiness und `status_events.csv` mit problematischen,
   geaenderten und geloeschten Test-IDs pruefen.
6. Erst nach dieser Abnahme Git/CI aktivieren und JSON-Schema- sowie
   Regressionstests dort verpflichtend machen.

## Historischer Ausgangsbefund vor Umsetzung

Der folgende Teil dokumentiert den Zustand, aus dem die oben aufgefuehrten
Aenderungen abgeleitet wurden. Prozentwerte und Aussagen in diesem historischen
Abschnitt sind keine Bewertung des aktuellen Codes mehr.

### Frueheres Kurzfazit

Die Codebase ist bereits eine echte, auf HoreKa ausgerichtete Pipeline und keine
lose Notebook-Sammlung mehr. Besonders gut sind die zentrale Konfiguration,
die Slurm-Abhaengigkeitskette, mehrere inkrementelle Inventare, atomare
Download-Writes, Checkpoints fuer die grossen Formation-Schritte und die
kompakte finale Mastertabelle.

Gemessen an den vorliegenden 16 Grundprinzipien ist der aktuelle Stand dennoch
nur zu etwa **58-62 Prozent vollstaendig umgesetzt**. Der niedrigere Wert im
Vergleich zu frueheren Einschaetzungen entsteht vor allem dadurch, dass die
Grundprinzipien inzwischen eine echte statusbasierte Orchestrierung ueber die
Mastertabelle, kontrollierte Parallelitaet, formale Schemas, Release-Gates und
umfassende Tests verlangen.

Der wichtigste Unterschied zwischen Soll und Ist lautet:

> Die Mastertabelle ist aktuell ein am Laufende erzeugter Statusbericht. Sie ist
> noch nicht die operative Grundlage, aus der vor dem Lauf pro Step und ID ein
> Ausfuehrungsplan erzeugt wird.

Der normale Modus `add_new_ids` reicht weiterhin fast alle Hauptsteps als
Slurm-Jobs ein. Die einzelnen Skripte entscheiden anschliessend mit jeweils
eigener Logik, was sie ueberspringen. Das ist praktisch nutzbar, aber noch nicht
deckungsgleich mit der geforderten zentralen, status- und
abhaengigkeitsbasierten Orchestrierung.

## Pruefmethode

Geprueft wurden:

- `submit_bio_o_ton_horeka.sh` und die vier kanonischen Slurm-Entrypoints;
- alle produktiven `scripts/Step_*.py`;
- `scripts/common.py` und die Manifest-Hilfen;
- `config.horeka.json`;
- Mastertable-Builder und Mastertable-Schema;
- finaler Validierungsreport;
- vorhandene Tests und Funktionalitaetstest;
- DE/EN-Step-READMEs und globale Dokumentation;
- Schema-Dateien unter `schemas/`.

Zum damaligen Auditzeitpunkt wurden lokal ausgefuehrt:

```text
Python compileall: erfolgreich
JSON-Dateien parsebar: 7/7
test_common_manifest.py: erfolgreich
test_pipeline_regressions.py: erfolgreich
test_weather_inventory.py: erfolgreich
test_master_table.py: erfolgreich
```

Der lokale Test fuer die Mastertabelle konnte mangels `pyarrow` im gebuendelten
lokalen Python kein Parquet schreiben. Der Test behandelt dies als optionale
Ausgabe und war erfolgreich. Die vollstaendige HoreKa-/LSDF-Ausfuehrung und
reale Slurm-Ressourcenmessung waren nicht Teil dieses statischen Audits.

## Gesamtbewertung

| Nr. | Prinzip | Erfuellung | Status | Kernaussage |
|---:|---|---:|---|---|
| 1 | Effiziente und inkrementelle Verarbeitung | 65% | Gelb | Neue IDs werden oft erkannt; Aenderungen an bereits bekannten IDs noch nicht durchgaengig. |
| 2 | Orchestrierung ueber globale Mastertabelle | 30% | Rot | Mastertabelle existiert, steuert die Job-/ID-Auswahl aber noch nicht. |
| 3 | Clusteroptimierung und Batch-Verarbeitung | 65% | Gelb | Slurm, Worker-Limits und einige Batches vorhanden; keine zentrale Batch-Zuteilung oder Sperre. |
| 4 | Wiederaufnahme ueber Checkpoints | 65% | Gelb | Stark bei 2_1, 2_4, Medien, Wetter und teilweise 5_4; nicht durchgaengig transaktionssicher. |
| 5 | Ausfuehrliche Logs und Status | 60% | Gelb | Viele Logs und Run-Manifeste; kein gemeinsamer Workflow-Run und keine vollstaendige Statushistorie. |
| 6 | Sanity Checks und Qualitaetskontrollen | 70% | Gelb/Gruen | Gute fachliche Einzelchecks; zentrale Gate-Logik ist noch zu schwach. |
| 7 | Kompakte und ausfuehrliche Ergebnisse | 75% | Gruen/Gelb | Besonders bei Inventaren gut; Run-/Versionsbezug fehlt in vielen Ergebnisdateien. |
| 8 | Reproduzierbarkeit und Provenienz | 50% | Gelb/Rot | Fingerprints und Manifeste vorhanden; Code-/Dependency-Versionen und globaler Run-Bezug fehlen. |
| 9 | Trennung von Code, Konfiguration und Daten | 80% | Gruen | Hauptpfade zentral konfiguriert; einige Defaults und Legacy-Namen bleiben. |
| 10 | Idempotente Verarbeitungsschritte | 65% | Gelb | Viele Skip- und Atomic-Mechanismen; Append- und Parallel-Risiken bleiben. |
| 11 | Validierung vor Veroeffentlichung | 35% | Rot | Validierungsreport existiert, kann aber trotz fachlicher ID-Probleme `validated` melden. |
| 12 | Saubere zweisprachige Dokumentation | 60% | Gelb | DE/EN-Struktur vorhanden, aber teilweise zu knapp, unvollstaendig und an einer Stelle veraltet. |
| 13 | Klare Schnittstellen und stabile Formate | 50% | Gelb/Rot | Schema-Beschreibungen vorhanden, aber nicht maschinell erzwingbar. |
| 14 | Testbarkeit und automatisierte Tests | 35% | Rot | Vier kleine Tests sind vorhanden; Orchestrierung, Parallelitaet und echte Resume-Faelle fehlen. |
| 15 | Sicherer Umgang mit Fehlern | 60% | Gelb | Fehler werden meist sichtbar; Klassifikation, Retry-Policy und Statusuebersetzung sind uneinheitlich. |
| 16 | Wartbarkeit vor Komplexitaet | 70% | Gelb/Gruen | Gemeinsame Hilfen und ein Orchestrator sind da; mehrere parallele State-Systeme bleiben. |

## Detailbewertung

### 1. Effiziente und inkrementelle Verarbeitung

Bereits gut umgesetzt:

- Step 2_0 und 2_1 vergleichen globale Input-Fingerprints und
  Verarbeitungseinstellungen.
- Step 2_2 verarbeitet neue IDs inkrementell, solange sich die raeumlichen
  Inputs nicht geaendert haben.
- Audio-, Foto- und Sentinel-Inventare verwenden Dateigroesse und `mtime_ns`,
  um unveraenderte Dateien wiederzuverwenden.
- Medien-Downloads verwenden Inventare und persistente Retry-Logs.
- Step 5_2 nutzt das Step-5_1-Wetterinventar und ueberspringt nur als sauber
  bewertete Wetterdateien.
- Step 2_4 und Step 5_4 besitzen Batch-/Tile-Resume.

Noch nicht erfuellt:

- Step 1 betrachtet eine ID als dauerhaft erledigt, sobald sie in Clean- oder
  Log-CSV vorkommt. Aendert sich bei einer vorhandenen ID Zeit, GPS oder URL,
  wird sie im inkrementellen Modus nicht aktualisiert.
- Step 2_2 erkennt neue IDs, aber keine geaenderten Koordinaten bestehender IDs.
  Der Metadata-Fingerprint wird zwar gespeichert, entscheidet aber nicht ueber
  einen gezielten Rebuild bestehender IDs.
- Wetterdateien koennen bei geaenderten Koordinaten veraltet bleiben. Step 5_1
  prueft das Zeitfenster, aber die erzeugte CSV enthaelt keine Provenienz der
  verwendeten Koordinaten.
- Sentinel-2 verwendet bei bereits erfolgreichem Dateinamen den lokalen
  Download-Log. Die Google-Drive-Abfrage liest derzeit keine `modifiedTime`-
  oder Checksum-Information. Eine remote geaenderte Datei gleichen Namens wird
  deshalb nicht sicher erkannt.
- Step 5_1 liest und prueft aktuell bei jedem Lauf alle Wetter-CSV-Dateien
  erneut. Alte, unveraenderte und zuvor saubere IDs werden nicht aus einem
  Fingerprint-Cache uebernommen.
- Der Orchestrator reicht auch globale, wahrscheinlich unveraenderte
  Formation-Schritte als Jobs ein. Diese skippen intern, werden aber nicht
  bereits bei der Run-Planung ausgelassen.

Zielzustand:

- Pro ID wird ein Quellzeilen-Fingerprint fuer die jeweils relevanten Felder
  gespeichert.
- Pro Step ist zentral definiert, welche Felder und globalen Dateien seinen
  Output beeinflussen.
- Neue und geaenderte IDs werden getrennt protokolliert.
- Globale Steps werden nur eingereiht, wenn ihre fachlichen Inputs oder ihre
  Konfiguration geaendert wurden.

### 2. Orchestrierung ueber eine globale Mastertabelle

Bereits gut umgesetzt:

- `Step_7_0_update_master_table.py` erzeugt eine kompakte ID-Level-Tabelle.
- Medien, Sentinel, Punktwetter, 100m-/10m-Formation und globale
  HOSTRADA-Raster werden zusammengefuehrt.
- `ready_for_general_analysis`,
  `ready_for_formation_analysis_100m`,
  `ready_for_formation_analysis_10m` und
  `ready_for_multimodal_analysis` sind klar definiert.
- Issue-Codes bleiben kompakt, Details verbleiben in Step-Logs.

Kritische Restluecken:

- Die Mastertabelle wird erst nach den Hauptsteps gebaut.
- Kein Step liest die Mastertabelle zur Auswahl seiner IDs.
- Es gibt keine zentralen Step-Statusspalten wie `queued`, `running`,
  `validated`, `failed`, `outdated` oder `manual_review_required`.
- Es gibt keine getrennten automatischen und manuellen Statusfelder.
- Pro Produkt fehlen `last_run_id`, `last_validated_utc` und eine eindeutige
  Referenz auf das Detail-Log.
- Statusaenderungen werden nicht als Historie/Event-Log gespeichert.
- Es gibt keine zentrale Abhaengigkeitsauswertung, die z.B. aus
  `weather_point_has_issues=True` genau Step 5_2 fuer genau diese IDs plant.
- Es gibt keine Markierung oder Sperre fuer IDs, die bereits von einem aktiven
  Job verarbeitet werden.

Bewertung:

Die Mastertabelle erfuellt die Rolle einer kompakten fachlichen Uebersicht,
aber noch nicht die im Prinzip geforderte Rolle als operative
Orchestrierungsgrundlage.

### 3. Clusteroptimierung mit kontrollierter Batch-Verarbeitung

Bereits gut umgesetzt:

- Ein zentraler Slurm-Orchestrator definiert Abhaengigkeiten.
- CPU-Zahlen und Walltimes sind pro Step konfigurierbar.
- Worker-Zahlen werden in vielen Steps auf `SLURM_CPUS_PER_TASK` begrenzt.
- Step 2_1 und 2_4 verarbeiten Grid-Chunks.
- Medien-, Wetter-, Sentinel- und Raster-Schritte besitzen teilweise
  persistente Batch-/Datei-Statusdateien.
- Downloads verwenden Threads, CPU-intensive Geoverarbeitung teilweise
  Prozesse.

Restluecken:

- Batches werden nicht aus einem zentralen Run-Plan erzeugt.
- Es existiert keine Pipeline- oder Step-Sperre gegen zwei gleichzeitig
  eingereichte `add_new_ids`-Laeufe.
- Zwei konkurrierende Runs koennen dieselben CSV-Logs oder Outputs schreiben.
- Step 4_1 arbeitet seriell, obwohl mehrere Downloads moeglich waeren.
- Step 5_3 begrenzt `workers` nicht anhand der Slurm-Zuweisung.
- Step 5_5 schreibt waehrend des Laufs nach jeder fertigen Datei den gesamten
  bisherigen Report neu.
- Slurm Arrays werden fuer klar separierbare Jahre, Variablen oder
  ID-Batches noch nicht genutzt.

### 4. Wiederaufnahme ueber Checkpoints

Bereits gut umgesetzt:

- Step 2_1 schreibt atomare Chunk-Pickles.
- Step 2_4 schreibt Parquet-Parts und Batch-Status.
- Medien-Downloads schreiben Retry-Zustand batchweise.
- Step 5_2 schreibt per-ID-Status und atomare Wetterdateien.
- Step 5_4 schreibt pro Tile Status und `.part.tif`.
- Step 5_3 verwendet `.part` fuer NetCDF-Downloads.

Restluecken:

- Step 1 und Step 2_2 haengen direkt an CSVs an; ein Abbruch kann Clean-, Log-
  und Detailtabellen auseinanderlaufen lassen.
- Step 2_0 und grosse Teile von Step 2_1 schreiben finale Produkte direkt und
  ersetzen vorhandene GPKGs/Parquets nicht durch eine vollstaendig validierte
  Staging-Version.
- Step 5_4 muss bei einem unvollstaendigen Jahr die teure
  Monatsquantil-/Reprojektionsphase erneut ausfuehren, auch wenn bereits einige
  Tiles fertig sind.
- Step 5_5 besitzt keinen per-TIFF-Checkpoint.
- Checkpoints werden nicht gemeinsam mit Masterstatus und aktuellem Run-Plan
  auf Konsistenz geprueft.
- Es gibt keinen standardisierten Zustand `partial` auf ID-Ebene.

### 5. Ausfuehrliche Logs und nachvollziehbarer Status

Bereits gut umgesetzt:

- Slurm stdout/stderr wird pro Job gespeichert.
- `run_with_manifest.py` erzeugt fuer jeden ueber den Orchestrator gestarteten
  Job mindestens ein zentrales Manifest.
- Step 2_4, 4_1, 5_2 und 5_4 erzeugen reichere interne Manifeste oder
  Batch-Statusdateien.
- Mehrere Inventare liefern kompakte und detaillierte CSVs.
- ETA-Ausgaben sind in mehreren langen Steps vorhanden.

Restluecken:

- Jeder Step erzeugt eine eigene `run_id`; ein gemeinsamer Workflow-Run fehlt.
- Der Wrapper kennt standardmaessig nur die Config als Input und keine
  tatsaechlichen Step-Inputs oder Outputs.
- Im `from_scratch`-Modus wird `--force` an das Fachskript, aber nicht an
  `run_with_manifest.py` uebergeben. Das Wrapper-Manifest kann daher
  `force=false` dokumentieren, obwohl der Step forciert lief.
- Software-/Dependency-Versionen fehlen.
- Peak-RAM, CPU-Zeit und Slurm-Endstatus aus `sacct` fehlen.
- Mastertable-Zeilen verweisen nicht auf Run-Manifest oder Detail-Log.
- Es gibt kein zentrales Status-Event-Log mit vorherigem und neuem Zustand.

### 6. Sanity Checks und Qualitaetskontrollen

Bereits gut umgesetzt:

- Step 1 prueft Pflichtspalten, Zeit und GPS.
- Step 2 prueft LRT-/Formation-Spalten, Grid-Zuordnungen und
  Formation-Status-Skalierung.
- Step 3 dekodiert Audio vollstaendig und verifiziert Bilder.
- Step 4 prueft Rasterstruktur, Pixel und Score-Zuordnung.
- Step 5_1 prueft Spalten, Zeilenzahl, Zeitintervall, Zeitfenster, NaNs und
  Wertebereiche.
- Step 5_5 prueft Rasterbaender, NoData und konstante Zeilen/Spalten.
- Der Formation-Vergleich prueft Schema, Skalierung und fachliche Differenzen.

Restluecken:

- Es gibt keine zentrale Einteilung in blockierende Fehler, Warnungen,
  automatisch wiederholbare Fehler und manuelle Prueffaelle.
- Ein Inventory-Step kann erfolgreich enden, obwohl viele IDs Issues haben.
  Das ist fachlich zulaessig, muss aber in einem standardisierten
  `partial/needs_attention`-Status ankommen.
- Der finale Validierungsreport liest die fachlichen Issue-Anzahlen nicht
  ausreichend aus Mastertabelle und Detailreports.
- Nicht alle Checks sind durch Tests gegen bekannte Fehlerbilder abgesichert.
- Vergleich mit vorherigen Verteilungen und unerwartete starke Aenderungen
  fehlen weitgehend.

### 7. Einfache und ausfuehrliche Ergebnisdateien

Bereits gut umgesetzt:

- Audio, Foto, Sentinel und Wetter besitzen kompakte und detaillierte Logs.
- Die Mastertabelle bleibt bewusst kompakt.
- Formation-Vergleiche und Raster-QC erzeugen JSON/CSV/Markdown.
- Generierte Analyseprodukte liegen ueberwiegend unter `outputs/<step>`.

Restluecken:

- Nicht jeder kompakte Output enthaelt eine `run_id` oder Schema-Version.
- Nicht jede Diagnosezeile ist eindeutig einem Batch und Run zugeordnet.
- Einige State-Dateien sind reine Zusammenfassungen ohne stabiles Schema.
- Step 5_3 und 5_5 besitzen keine getrennte stabile Ergebnis- und
  Diagnoseebene mit versionierter Schnittstelle.

### 8. Reproduzierbarkeit und Provenienz

Bereits gut umgesetzt:

- Mehrere Steps speichern Input-Fingerprints.
- Konfigurationspfad und Slurm-Kontext erscheinen in zentralen Manifesten.
- Die Formation-Produkte besitzen explizite Schema-Versionen.
- Abhaengigkeiten sind in `environment.hpc.yml` und
  `requirements.hpc.txt` aufgelistet.

Restluecken:

- Dependency-Versionen sind nicht gepinnt.
- Kein Environment-Lockfile wird archiviert.
- Kein gemeinsamer Workflow-Run verknuepft alle Step-Manifeste.
- Code-Version fehlt derzeit planmaessig; Git soll spaeter folgen.
- Datei-Fingerprints fuer Verzeichnisse sind nicht rekursiv.
- Der Edge-Hash liest nur Anfang und Ende einer Datei, nicht den kompletten
  Inhalt.
- Viele Outputs enthalten keinen direkten Provenienzverweis.
- Der finale Report ist nicht auf genau einen Workflow-Run begrenzt, sondern
  betrachtet die jeweils neuesten Manifeste aller gefundenen Steps.

### 9. Trennung von Code, Konfiguration und Daten

Bereits gut umgesetzt:

- Die produktiven LSDF-Pfade sind weitgehend in `config.horeka.json`.
- Zugangsdaten liegen nicht im Config-JSON.
- Google OAuth verwendet separate Credential-/Token-Dateien.
- Lokale/HoreKa-Pfadvarianten werden in `common.py` aufgeloest.
- Ressourcen und Walltimes sind ueber Umgebungsvariablen anpassbar.

Restluecken:

- Einige Tools und Defaults enthalten weiterhin projektspezifische
  `/lsdf/...`-Pfade.
- Abhaengigkeiten und Triggerregeln leben hauptsaechlich im Bash-Orchestrator,
  nicht in einer zentralen maschinenlesbaren Step-Registry.
- Legacy-Begriffe wie `susi_10m_products` bleiben in Config und Outputpfaden.
- `Step_4_1_Sentinel2_download.py` und `Step_5_1_Weather_inventory.py`
  verwenden noch uneinheitliche Schreibweise/Namenskonvention.

### 10. Idempotente Verarbeitungsschritte

Bereits gut umgesetzt:

- Viele Steps skippen gueltige vorhandene Ergebnisse.
- Downloads schreiben in `.part` und benennen atomar um.
- JSON-/CSV-Helfer in `common.py` schreiben atomar.
- Retry-Zustand verhindert unbegrenzte Medienwiederholungen.
- Formation- und Raster-Checkpoints verhindern viele Doppelberechnungen.

Restluecken:

- Step 1 und Step 2_2 verwenden Append-Dateien ohne globale Sperre.
- Derselbe Lauf kann bei doppelter Slurm-Einreichung dieselben IDs verarbeiten.
- `from_scratch` loescht Step-1-bis-Step-3-Produkte vor dem Neuaufbau. Bei
  fruehem Fehler ist der vorherige gueltige Stand nicht mehr verfuegbar.
- Step 2_0 loescht das bestehende GPKG vor dem Schreiben des neuen Outputs.
- Step 2_1 schreibt mehrere finale Produkte nacheinander; ein Abbruch kann
  Versionen mischen.
- Step 5_3 wertet eine nichtleere NetCDF-Datei bereits als vorhanden, ohne
  strukturelle Validierung.
- Ein standardisierter Complete-Marker fuer eine konsistente Outputgruppe
  fehlt.

### 11. Validierung vor Veroeffentlichung oder Uebergabe

Bereits umgesetzt:

- `final_validation_report.py` erzeugt JSON und Markdown.
- Fehlende Pflichtartefakte und neueste `failed/partial`-Manifeste werden
  beruecksichtigt.
- Ein separater Formation-Vergleich ist vorhanden.

Kritische Restluecken:

- `output_is_nonempty()` bewertet jedes existierende Verzeichnis als
  nichtleer, auch wenn es keine Dateien enthaelt.
- Der Report prueft viele Artefakte nur auf Existenz und Dateigroesse.
- Medien-, Wetter- und Sentinel-Issue-Anzahlen aus der Mastertabelle sind kein
  Release-Gate.
- Terminale Downloadfehler koennen in Mediensteps mit Returncode 0 enden.
  Das Wrapper-Manifest lautet dann `complete`.
- Step 5_5 meldet bei `ONLY_NODATA` nicht zwingend einen Fehlercode.
- Der Report ist nicht auf den aktuellen Workflow-Run begrenzt.
- Es fehlen manuelle Freigabe, Freigabeverantwortlicher und Freigabezeitpunkt.

Folge:

Der Statusname `validated` ist aktuell staerker als die tatsaechlich
durchgefuehrte Pruefung. Bis zur Nachbesserung sollte er fachlich als
`technical_inventory_complete` oder `needs_attention_checked` interpretiert
werden, nicht als Publikationsfreigabe.

### 12. Saubere und zweisprachige Dokumentation

Bereits gut umgesetzt:

- Globale `README.md` und deutsche Pipeline-Uebersicht existieren.
- Fuer die Hauptgruppen Step 1, Step 2_0 bis 2_4, Step 3, Step 4, Step 5_1/5_2,
  Step 6 und Validierung gibt es DE/EN-READMEs.
- Die Mastertable-Spalten sind ausfuehrlich dokumentiert.

Restluecken:

- Die meisten Step-READMEs sind nur etwa 23-45 Zeilen lang und decken nicht
  alle geforderten Punkte wie Statuswerte, typische Fehler, genaue
  Parallelisierung, Mastertable-Interaktion und Beispiele ab.
- Eigene DE/EN-Dokumentation fehlt fuer Step 2_5/2_6 und Step 5_3/5_4/5_5.
- `PIPELINE_SCHRITTE_DE.md` nennt Step 5_1 in der Liste der nicht automatisch
  aktiven Steps, obwohl der aktuelle Slurm-Orchestrator Step 5_1 vor und nach
  Step 5_2 ausfuehrt.
- Der alte Auditbericht referenziert teilweise alte Skriptnamen und bildet den
  aktuellen Mastertable-/Weather-Stand nicht mehr ab.

### 13. Klare Schnittstellen und stabile Datenformate

Bereits umgesetzt:

- Sechs Schema-Beschreibungsdateien existieren.
- Wichtige Spalten, Einheiten und Versionen sind dokumentiert.
- Formation 100m/10m verwendet dieselbe Centi-Prozent-Logik.
- Die Mastertabelle besitzt eine feste Spaltenreihenfolge und Schema-Version.

Restluecken:

- Die Dateien unter `schemas/*.json` sind Beschreibungsobjekte, keine
  standardkonformen JSON Schemas. Sie enthalten weder `$schema` noch
  `type/properties`.
- Der Funktionalitaetstest prueft nur, ob `schema_name` und
  `schema_version` vorhanden sind.
- CSV-/Parquet-Datentypen werden nicht automatisch gegen ein formales Schema
  validiert.
- Zulaessige Statusuebergaenge sind nicht formal definiert.
- Es gibt keine Migrationsfunktion fuer alte Mastertable- oder Log-Schemas.
- Ownership und Schreibberechtigung pro Mastertable-Feld sind nicht
  maschinenlesbar definiert.

### 14. Testbarkeit und automatisierte Tests

Bereits umgesetzt:

- Vier synthetische Testskripte existieren.
- Getestet werden Manifest-Lifecycle, atomare JSON-Writes, einfache
  New-ID-Erkennung, Formation-Skalierung, Medienauswahl, Wetterinventar und ein
  minimaler Mastertable-Build.
- Alle vorhandenen lokalen Tests liefen im Audit erfolgreich.

Restluecken:

- `functionality_test.py` startet nur `test_common_manifest.py`, nicht die
  gesamte vorhandene Test-Suite.
- Die Hilfsfunktion `new_ids()` im Regressionstest testet nicht die reale
  Step-1-Implementierung.
- Es gibt keinen Test fuer geaenderte bestehende IDs.
- Es gibt keinen Test fuer Step-2_1-/Step-2_4-Resume nach simuliertem Timeout.
- Es gibt keinen Test fuer doppelte oder konkurrierende Runs.
- Es gibt keinen Orchestrator-Test, der aus Statuskombinationen den erwarteten
  Job-/ID-Plan prueft.
- Es gibt keinen kleinen End-to-End-Test von Metadaten bis Mastertabelle.
- Sentinel-, Audio-, Foto-, HOSTRADA-Download und Raster-QC sind nicht mit
  realistischen synthetischen Fixtures abgedeckt.
- Shell-Syntax und erzeugte `sbatch`-Kommandos werden nicht automatisch
  getestet.

### 15. Sicherer Umgang mit Fehlern

Bereits gut umgesetzt:

- Die meisten Skripte geben Returncode 1 bei technischen Exceptions zurueck.
- Atomare Downloads entfernen `.part` bei Fehlern.
- Medien und Wetter besitzen begrenzte Retry-Mechanismen.
- Fehlermeldungen und Issue-Codes sind ueberwiegend sichtbar.
- Slurm-`afterok` verhindert viele fachlich unmoegliche Folgejobs.

Restluecken:

- Fehlerklassen sind nicht zentral definiert.
- Media-Terminalfehler koennen mit Returncode 0 enden.
- Fuer Sentinel und Step 5_3 gibt es keine vergleichbare persistente,
  begrenzte Retry-Policy.
- Es gibt keinen standardisierten manuellen Reset fuer terminale IDs.
- Mastertable und Run-Manifeste unterscheiden nicht sicher zwischen
  technischem Fehler, ungueltigen Daten, Timeout, Ressourcenproblem und
  manueller Pruefung.
- `afterany` startet Mastertable und Validierung auch nach fehlgeschlagenen
  Vorgaengern. Das ist fuer Diagnose sinnvoll, muss aber im Ergebnis eindeutig
  als unvollstaendiger Run markiert werden.

### 16. Wartbarkeit vor unnoetiger Komplexitaet

Bereits gut umgesetzt:

- `common.py` buendelt Pfadaufloesung, atomare Writes, Fingerprints und
  Manifest-Grundfunktionen.
- Es gibt einen zentralen produktiven Slurm-Orchestrator.
- Vier klar benannte Slurm-Entrypoints reduzieren Bedienfehler.
- Fachlogik bleibt groesstenteils in Step-Skripten.

Restluecken:

- State-, Skip-, Manifest- und Batch-Logik ist weiterhin in mehreren Varianten
  dupliziert.
- Mehrere sehr grosse Step-Dateien kombinieren Fachlogik, IO, Status,
  Parallelisierung und CLI.
- Legacy-Wrapper und alte Namenskonventionen erhoehen die Such- und
  Dokumentationslast.
- Die Abhaengigkeitslogik ist Bash-Code statt einer testbaren Step-Registry.

## Die groessten Risiken in Prioritaetsreihenfolge

### P0. Geaenderte bestehende IDs werden nicht korrekt propagiert

Betroffen:

```text
Step_1_metadata_extraction.py
Step_2_2_assign_points_to_lrt_grid.py
Step_5_1_Weather_inventory.py
Step_5_2_download_weather_data.py
Step_4_1_Sentinel2_download.py
```

Risiko:

Eine ID kann fachlich geaenderte Zeit-/GPS-/URL-Daten besitzen, aber weiterhin
alte Downstream-Produkte und `ready=True` erhalten.

### P0. Keine Sperre gegen parallele Pipeline-Laeufe

Betroffen:

```text
submit_bio_o_ton_horeka.sh
Step 1 und Step 2_2 Append-Outputs
gemeinsame Inventory-/Retry-CSV-Dateien
Mastertabelle
```

Risiko:

Doppelverarbeitung, verlorene Logupdates oder gemischte Outputversionen.

### P0. Der finale Status `validated` ist noch kein verlaessliches Release-Gate

Betroffen:

```text
tools/final_validation_report.py
scripts/common.py::output_is_nonempty
Step_7_0_update_master_table.py
```

Risiko:

Ein Lauf kann formal `validated` sein, obwohl viele IDs fehlen, Issues haben
oder ein Outputverzeichnis leer ist.

### P0. `from_scratch` entfernt gueltige Outputs vor erfolgreichem Ersatz

Betroffen:

```text
tools/cleanup_processed_to_step3.py
submit_bio_o_ton_horeka.sh
Step_2_0_clean_lrts.py
Step_2_1_merge_lrts_and_grid.py
```

Risiko:

Bei Timeout oder Fehler gibt es keinen konsistenten letzten gueltigen Stand.

### P1. Mastertabelle steuert die Pipeline noch nicht

Risiko:

Unnoetige Jobs, verteilte Skip-Regeln und keine gezielte Auswahl
problematischer IDs/Substeps.

### P1. Rasterzweig ist nicht in den regulaeren Gesamtworkflow integriert

Nicht im zentralen `add_new_ids`-/`from_scratch`-DAG:

```text
Step 5_3
Step 5_4
Step 5_5
```

Die Mastertabelle liest Rasterstatus, obwohl diese Produkte vom Standardlauf
nicht aktualisiert werden. Step 4_2 sowie der Public-LRT-Zweig sind ebenfalls
separate optionale Zweige; das ist in Ordnung, muss aber formal als optional
modelliert sein.

### P1. Manifeste besitzen keinen gemeinsamen Workflow-Run

Risiko:

Der finale Report kann Ergebnisse verschiedener Laeufe zusammenfassen.

### P1. Tests und Schemas sichern die Architektur noch nicht ab

Risiko:

Gerade Aenderungen an Statuslogik, Checkpoints und Orchestrierung koennen ohne
automatische Regressionserkennung falsche Jobs oder veraltete Daten erzeugen.

## Zielarchitektur ohne unnoetige Komplexitaet

Die Mastertabelle sollte kompakt bleiben. Sie sollte nicht gleichzeitig als
konkurrierend beschriebene Live-Datenbank verwendet werden.

Empfohlen ist folgende Aufgabentrennung:

```text
Quellen + vorhandene Outputs + Step-Logs
                |
                v
      Step 0: Status-Snapshot/Mastertabelle
                |
                v
      Step 0_1: Run-Plan pro run_id
      - globale geaenderte Inputs
      - IDs pro Step
      - Begruendung/Trigger
      - Batch-Grenzen
                |
                v
      Slurm-Orchestrator + exklusive Run-Sperre
                |
                v
      Fachsteps mit --ids-file/--batch-file
                |
                v
      Step-Manifeste + Status-Events + QC
                |
                v
      neue Mastertabelle + run-spezifisches Validation-Gate
```

Die operative Wahrheit waehrend eines Laufs sollte in atomaren
Run-/Batch-Manifesten und einem append-only Status-Event-Log liegen. Die
Mastertabelle bleibt der regelmaessig daraus erzeugte ID-Level-Snapshot.

## Konkreter Fahrplan

### Phase 0: Begriffe und Abhaengigkeiten festziehen

Aufwand: klein

Neue zentrale Definitionen:

```text
schemas/status_model.json
config/pipeline_steps.json oder pipeline_steps.py
```

Pro Step definieren:

- stabile `step_id`;
- `scope = global | per_id | per_file | per_tile`;
- relevante Inputs und Config-Keys;
- erzeugte Outputs;
- Upstream-/Downstream-Abhaengigkeiten;
- erlaubte Statuswerte und Uebergaenge;
- Retry-Klasse;
- ob Issues blockierend sind;
- Standardressourcen und Batchtyp.

Abnahmekriterium:

- Fuer jeden produktiven Step ist eindeutig dokumentiert, was ihn invalidiert
  und welche Downstream-Produkte dadurch `outdated` werden.

### Phase 1: Gemeinsamen Workflow-Run und korrekte Manifeste einfuehren

Aufwand: mittel

Betroffene Kernstellen:

```text
scripts/common.py
tools/run_with_manifest.py
submit_bio_o_ton_horeka.sh
schemas/step_manifest.schema.json
```

Umsetzen:

- Eine `BIOOTON_RUN_ID` wird einmal beim Submit erzeugt und an alle Jobs
  weitergegeben.
- Jedes Step-Manifest enthaelt `workflow_run_id`, `step_run_id`, Job-ID,
  Logpfade, tatsaechliche Inputs/Outputs, Config-Fingerprint und Force-Modus.
- `--force` wird auch im Wrapper-Manifest korrekt gesetzt.
- Statuswerte werden zentral vereinheitlicht.
- Ein finaler Collector ergaenzt Slurm-State, Exitcode, Elapsed, MaxRSS und
  CPUTime aus `sacct`.

Abnahmekriterium:

- Alle Manifeste eines Gesamtlaaufs koennen eindeutig ueber dieselbe
  `workflow_run_id` gefunden werden.

### Phase 2: Exklusive Run-Sperre und zentralen Run-Plan bauen

Aufwand: mittel bis gross

Neue Komponenten:

```text
tools/plan_pipeline_run.py
scripts/pipeline_state.py
outputs/step_0_control/run_plans/<run_id>.json
outputs/step_0_control/run_plans/<run_id>_<step>.csv
outputs/step_0_control/locks/
```

Umsetzen:

- Vor dem Submit wird atomar eine Pipeline-Sperre erworben.
- Der Planer liest Mastertabelle, Step-Logs, Manifeste und aktuelle Quellen.
- Er erzeugt pro Step eine Liste betroffener IDs und den Triggergrund.
- Globale Steps werden nur bei relevanter Input-/Config-Aenderung geplant.
- Zweiter paralleler Gesamt-Run bricht kontrolliert ab oder wird bewusst
  gequeued.
- Fachsteps erhalten `--ids-file` oder `--batch-file`.

Abnahmekriterium:

- Zwei direkt nacheinander gestartete `add_new_ids`-Kommandos koennen nicht
  dieselben IDs gleichzeitig bearbeiten.
- Ein leerer Run-Plan reicht keine teuren Fachjobs ein.

### Phase 3: Geaenderte bestehende IDs korrekt erkennen

Aufwand: gross, fachlich wichtigste Phase

Umsetzen:

- Step 1 berechnet pro ID einen Fingerprint aus relevanten Quellfeldern.
- Step 1 ersetzt Append-only durch atomaren Keyed-Upsert.
- Schrittweise Fingerprints:
  - Metadaten: Zeit, `localtimes`, GPS;
  - Audio: URL und erwartete ID;
  - Foto: URL und erwartete ID;
  - Wetter: Zeit, GPS, Zeitfensterparameter;
  - Sentinel: Drive-Datei-ID, `modifiedTime`, Checksum und lokaler Hash.
- Step 2_2 berechnet nur neue/geaenderte Punkt-IDs neu.
- Step 5_1 cached unveraenderte saubere Wetterchecks, prueft aber alte
  Issue-IDs erneut.
- Step 5_2 ersetzt Wetterdateien, wenn Zeit-/GPS-Provenienz nicht mehr passt.
- Terminale Medienfehler erhalten eine dokumentierte manuelle
  Reset-Moeglichkeit.

Abnahmekriterium:

- Aenderung nur der Koordinate einer vorhandenen ID invalidiert genau
  Punktzuordnung und Wetter, nicht Audio oder globale LRT-Raster.
- Aenderung nur der Audio-URL invalidiert genau den Audiozweig.

### Phase 4: Transaktionssicheren `from_scratch`-Modus und Atomic Promotion bauen

Aufwand: gross

Umsetzen:

- Kein Vorab-Loeschen des letzten gueltigen Datenstands.
- Neue Outputs werden unter
  `outputs/_staging/<run_id>/<step>/` erzeugt.
- Nach erfolgreichem Step-QC wird eine zusammengehoerige Outputgruppe atomar
  oder ueber einen versionierten Pointer promoted.
- Alte gueltige Version bleibt bis zur Promotion erhalten.
- State-Datei/Complete-Marker wird immer zuletzt geschrieben.
- Step 2_0, 2_1, 2_3 und Step 5_5 auf gruppenkonsistente Writes umstellen.

Abnahmekriterium:

- Ein absichtlich abgebrochener `from_scratch`-Lauf veraendert den zuvor
  freigegebenen Datenstand nicht.

### Phase 5: Lange und optionale Zweige sauber integrieren

Aufwand: mittel

HOSTRADA-Raster:

- Step 5_3 mit Dateivalidierung, persistenten Retry-Zustaenden und
  Slurm-Worker-Cap versehen.
- Step 5_4 pro `variable + year` als Slurm-Array oder klarer Batch.
- Zwischenprodukt nach Monatsquantilen/Reprojektion checkpointen, damit ein
  Timeout nicht die komplette Jahresrechnung wiederholt.
- Step 5_5 per-TIFF-Checkpoint und atomare Ergebniszusammenfuehrung geben.
- Step 5_3 bis 5_5 nur triggern, wenn neue/veraenderte Remote-Monate oder
  Rasterparameter vorliegen.

Sentinel:

- Drive-Metadaten/Checksumme fuer echte Updates spiegeln.
- Parallelisierung mit kontrollierter Workerzahl und Retry-Limit ergaenzen.

Optionale Zweige:

- Step 2_5/2_6 als `optional_qa` kennzeichnen.
- Fachlich entscheiden, ob Step 4_2 ein produktiver Cleaner oder nur
  `dry_run`-Diagnose bleibt.

Abnahmekriterium:

- Standardlauf und optionale Zweige sind im Run-Plan eindeutig getrennt.
- Die Mastertabelle kennzeichnet Rasterdaten nicht als aktuell, wenn der
  Rasterzweig nicht zum gleichen Inputstand gehoert.

### Phase 6: Mastertabelle zur echten Orchestrierungsansicht erweitern

Aufwand: mittel

Die bestehende kompakte Tabelle nicht mit technischen Details ueberladen.
Sinnvolle minimale Ergaenzungen pro Produktgruppe:

```text
<product>_status
<product>_last_run_id
<product>_last_validated_utc
<product>_log_ref
<product>_source_fingerprint
```

Zentrale manuelle Felder:

```text
manual_review_status
manual_review_reason
manual_review_updated_utc
manual_review_updated_by
```

Regeln:

- Automatische Felder werden nur von der Pipeline geschrieben.
- Manuelle Felder werden beim automatischen Rebuild erhalten.
- `exists=True` reicht nie fuer `validated`.
- `outdated` wird aus Dependency-/Fingerprint-Aenderungen abgeleitet.

Abnahmekriterium:

- Aus einer problematischen Mastertable-Zeile sind Step, Log und sinnvoller
  naechster Retry eindeutig ableitbar.

### Phase 7: Finales Validation-/Release-Gate korrigieren

Aufwand: mittel

Umsetzen:

- Nur Manifeste des aktuellen `workflow_run_id` bewerten.
- Leere Verzeichnisse korrekt erkennen.
- Erwartete ID-Abdeckung gegen Dawn-Chorus-Metadaten pruefen.
- Mastertable-Issuezahlen und Ready-Verteilungen aufnehmen.
- Pflicht-Schema- und QC-Checks tatsaechlich ausfuehren.
- `technical_status` und `release_status` trennen:

```text
technical_status = complete | needs_attention | failed
release_status = draft | approved | rejected
```

- Manuelle Freigabe getrennt und nachvollziehbar speichern.

Abnahmekriterium:

- Eine fehlende Audio-, Wetter- oder Sentinel-Datei kann nicht zu
  `release_status=approved` fuehren.

### Phase 8: Formale Schemas und Migration

Aufwand: mittel

Umsetzen:

- Manifeste als echtes JSON Schema mit `$schema`, `type`, `properties`,
  `required` und Enums.
- Fuer CSV/Parquet einen tatsaechlichen Validator verwenden, z.B. zentrale
  Pandas-/PyArrow-Prueffunktionen oder Pandera.
- Schema-Version pro Output speichern.
- Migrationsfunktionen fuer Mastertable und wichtige Logs anlegen.
- Der Funktionalitaetstest validiert kleine Beispieldateien gegen jedes
  Schema.

Abnahmekriterium:

- Fehlender Pflichtwert, falscher Datentyp oder ungueltiger Status fuehrt in
  Tests und Validation reproduzierbar zu einem Fehler.

### Phase 9: Testpyramide vervollstaendigen

Aufwand: gross, parallel zu Phase 1-8

Prioritaet der neuen Tests:

1. Reale Step-1-New-/Changed-/Deleted-ID-Erkennung.
2. Run-Plan aus definierten Masterstatus-Kombinationen.
3. Dependency-Invalidierung pro Feld.
4. Pipeline-Lock und konkurrierender zweiter Run.
5. Step-2_1-/Step-2_4-Resume nach simuliertem Timeout.
6. Wetter-Resume bei Zeit- und GPS-Aenderung.
7. Sentinel-Remote-Aenderung gleichen Dateinamens.
8. Terminaler Medienfehler und manueller Reset.
9. HOSTRADA-NetCDF-/Tile-Korruption.
10. Mini-End-to-End von Metadaten bis Mastertable/Validation.
11. Shell-Syntax und `sbatch`-DAG im Dry-Run.

Ausserdem:

- `functionality_test.py` muss alle schnellen Tests ausfuehren, nicht nur
  `test_common_manifest.py`.
- Teure Integrationstests werden separat markiert.

Abnahmekriterium:

- Die oben genannten Kernfaelle laufen ohne LSDF-Vollbestand auf kleinen
  synthetischen Fixtures.

### Phase 10: Dokumentation und kontrollierter Umstieg

Aufwand: mittel

Umsetzen:

- Standardtemplate fuer jede DE/EN-Step-README.
- Eigene Dokumentation fuer Step 2_5/2_6 und Step 5_3/5_4/5_5.
- Statusmodell, Run-Plan, Retry-Regeln und Mastertable-Trigger global
  dokumentieren.
- Veraltete Aussage zu Step 5_1 korrigieren.
- Alte Audits als historisch markieren.
- Neue Orchestrierung zuerst im `plan-only`-Modus laufen lassen.
- Run-Plan mit den bisherigen Skip-Entscheidungen vergleichen.
- Danach schrittweise produktiv schalten.

Abnahmekriterium:

- Jede Codeaenderung an Input, Output, Status oder Trigger hat einen
  entsprechenden Schema-, Test- und Dokumentationsnachweis.

## Empfohlene Umsetzungsreihenfolge

Die sinnvollste Reihenfolge ist:

1. Phase 0 und 1: Statusmodell, Step-Registry, gemeinsamer Run.
2. Phase 2: Planner und Sperre.
3. Phase 3: geaenderte bestehende IDs korrekt behandeln.
4. Phase 7: falsche `validated`-Freigaben verhindern.
5. Phase 4: sicherer `from_scratch` und Atomic Promotion.
6. Phase 5: Sentinel-/HOSTRADA-Zweige produktionsreif integrieren.
7. Phase 6: Mastertabelle um minimale Orchestrierungsfelder ergaenzen.
8. Phase 8 und 9: formale Schemas und vollstaendige Tests.
9. Phase 10: Dokumentation finalisieren und kontrolliert umstellen.

Tests muessen dabei nicht bis Phase 9 warten. Jede Phase sollte ihre eigenen
Regressionstests direkt mitbringen.

## Definition of Done fuer die gesamte Umstellung

Die Grundprinzipien sind praktisch erfuellt, wenn alle folgenden Szenarien
automatisch funktionieren:

1. Eine neue ID erzeugt nur die erforderlichen ID-bezogenen Produkte.
2. Eine geaenderte bestehende ID invalidiert nur fachlich betroffene Produkte.
3. Eine LRT-/Grid-Aenderung startet die globalen Formation-Schritte und
   markiert abhaengige Outputs veraltet.
4. Eine unveraenderte Pipeline reicht keine teuren Jobs ein.
5. Ein Issue startet nur den zustaendigen Retry-Step, begrenzt nach Fehlerart.
6. Ein Timeout setzt am letzten konsistenten Checkpoint fort.
7. Zwei konkurrierende Runs koennen keine ID oder Outputgruppe doppelt
   schreiben.
8. Ein fehlgeschlagener `from_scratch`-Lauf laesst den letzten gueltigen Stand
   unangetastet.
9. Jede Mastertable-Statusaussage verweist auf Run, Log und
   Input-/Schema-Version.
10. `validated/approved` ist nur moeglich, wenn alle definierten Pflichtchecks
    fuer genau diesen Workflow-Run bestanden wurden.
11. Alle zentralen Status-, Resume-, Schema- und Orchestrierungsfaelle sind
    automatisiert getestet.

## Schlussurteil

Die Pipeline besitzt bereits viele der notwendigen Bausteine. Der groesste
naechste Schritt ist kein weiterer isolierter Fachstep, sondern die
Vereinheitlichung des operativen Kerns:

```text
gemeinsamer Workflow-Run
+ zentrale Step-/Dependency-Registry
+ ID-/Batch-Run-Plan
+ Sperr- und Statusmodell
+ run-spezifisches Validation-Gate
```

Danach koennen die bereits vorhandenen Inventare, Checkpoints, Retry-Logs und
Mastertable-Felder weiterverwendet werden. Die fachlichen Berechnungen muessen
nicht neu erfunden werden; vor allem ihre Auswahl-, Status- und
Promotionslogik muss vereinheitlicht werden.
