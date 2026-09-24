# Gemeinsame Master und sichere Wiederaufnahme

Die gemeinsame Datei heißt **Bio_O_Ton_Master.csv**. CSV, Parquet und Zusammenfassung
werden zusammen aktualisiert. Lokale und LSDF-Kopien eines veröffentlichten Stands
müssen dieselbe SHA-256 besitzen; Uploadkopien sind keine eigene fachliche Variante.

## Auswahl der Datenstände

Die Zusammenführung vom 24.09.2026 verwendet die vollständigen, aus Step-2-Produkten
geprüften räumlichen Zuordnungen und die zuletzt geprüften LSDF-Inventare für Wetter,
Audio, Fotos und Sentinel. IDs, Koordinaten und Aufnahmezeiten müssen zuvor exakt
übereinstimmen. Größere Trefferzahlen allein sind kein Auswahlkriterium. Die
zusätzlichen LRT-Varianten werden anhand ihrer Punktprodukte vervollständigt.
Die konkreten Quellen und Prüfsummen stehen im jeweiligen Veröffentlichungsbericht.

## `add_new_ids`

- Der Planer gleicht IDs **und Koordinaten** jeder konfigurierten LRT-Punktzuordnung
  unabhängig von den Step-1-Fingerprints ab. Unterbrochene Verarbeitung wird erneut
  eingeplant. Die Koordinaten älterer Produkte werden aus dem zugehörigen
  `point_processing_log` gelesen.
- Step 2.2 prüft dieselbe Abdeckung auch bei direktem Aufruf und entfernt nicht mehr
  im Metadatenbestand enthaltene IDs. Ein ausdrücklich berechnetes negatives
  räumliches Ergebnis bleibt gültig.
- Räumliche Stufen bearbeiten die konfigurierten Varianten innerhalb des jeweiligen
  bestehenden Jobs nacheinander; es entsteht kein Slurm-Array pro Variante.
- Zwischenstände dürfen Master-Updates bis zum Abschluss von Step 2.2 aufschieben.
  Der abschließende Master-Schritt verlangt vollständige Punktzuordnungen, aktualisiert
  die Variantentabelle und berechnet danach die Master-Zusammenfassung neu.
- `formation_variant_products_complete` wird pro Aufnahme geprüft. Die Existenz
  der globalen Variantendateien allein reicht nicht aus.
- Die separate Bioakustikphase bleibt separat und verändert keine räumlichen Felder.

## Neue Laufdiagnosen

| Meldung | Bedeutung / Handlung |
|---|---|
| `POINT_ASSIGNMENT_INCOMPLETE` | IDs fehlen, sind doppelt oder haben andere Koordinaten im Punktprodukt. Step 2.2 nachholen; Master nicht mit scheinbar negativen Treffern ersetzen. |
| `MASTER_UPDATE_DEFERRED` | Ein Zwischenupdate wartet auf vollständige räumliche Verarbeitung. Bestehende Master bleibt erhalten; der finale Schritt prüft streng. |
| `FORMATION_10M_MISSING` | Konfiguriertes 10-m-Produkt fehlt. Step 2.4 vervollständigen. |
| `FORMATION_10M_UNREADABLE` | Vorhandenes 10-m-Parquet konnte nicht gelesen werden. Datei prüfen/wiederherstellen; nicht als fehlende Formation interpretieren. |
| `SOURCE_POPULATION_REDUCED` | Mehr als 20 % und mehr als zehn bisherige IDs würden durch die Quelle verschwinden. Vollständige Originalquelle prüfen. Nur bei beabsichtigter großer Reduktion `metadata_extraction.allow_large_source_reduction=true` setzen. |

Diese Diagnosen sind Laufmeldungen, keine neu eingeführten Aufnahme-Issue-Codes.
Normale einzelne Löschungen bleiben möglich. Der Reduktionsschutz gilt auch beim
direkten Aufruf von Step 1 bzw. Step 7. Eine bereinigte Metadatendatei ersetzt niemals
die ursprüngliche Dawn-Chorus-Quelldatei.
