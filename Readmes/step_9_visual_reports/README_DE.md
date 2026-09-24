# Step 9 Visuelle Reports (DE)

Der Reportgenerator `tools/generate_pipeline_visual_reports.py` liest nur die
kompakten Ergebnisdateien der abgeschlossenen bzw. teilweise abgeschlossenen
Steps. Er erstellt keine neue Analyse und veraendert keine Quell- oder
Fachprodukte.

Output:

- `outputs/step_9_visual_reports/index.html`: Gesamtuebersicht
- `outputs/step_9_visual_reports/01_step_1_metadata.html` bis
  `07_step_7_mastertable.html`: einzelne Step-Seiten
- `outputs/step_9_visual_reports/report_manifest.json`: technische Liste der
  erzeugten Seiten

Der Slurm-Workflow startet den Generator nach `final_validation`; die Ausfuehrung
ist auch bei unvollstaendigen Steps robust. Zum lokalen Oeffnen kann die
`index.html` direkt im Browser geoeffnet werden.

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Fehlercodes, Status und Exit-Codes

Abgleich mit dem lokalen Code: 2026-09-23. Die Tabellen trennen Daten-/QC-Codes, Statuswerte, explizite Exceptions und Prozess-Exit-Codes. `{...}` sind variable Werte, keine festen Codes. Bedingungen nennen den konkreten Ausloeser im Quellcode; mehrere Codes koennen gleichzeitig auftreten.

`0` bedeutet nur einen erfolgreichen Prozessabschluss, nicht automatisch fehlerfreie Daten. `argparse` kann bei ungueltigen Argumenten mit `2` abbrechen; ungefangene Python-Exceptions typischerweise mit `1`. Slurm-Zustaende wie `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` und `DependencyNeverSatisfied` sind Scheduler-Meldungen, keine fachlichen Fehlercodes. Dynamische Bibliotheks-/HTTP-/Dateisystemfehler stehen mit ihrer Originalmeldung im Log.

### Daten- und QC-Codes

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Statuswerte (nicht alle sind Fehler)

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Explizite Fehlermeldungen

Keine festen Werte dieser Kategorie im zugeordneten Quellcode.

### Explizite Prozessrueckgaben

| Code / Meldung | Bedeutung / Ausloeser | Quelle |
|---|---|---|
| `0` | `Ausgabe in main` | [generate_pipeline_visual_reports.py:259](../../tools/generate_pipeline_visual_reports.py) |

**Vorgehen:** Zuerst das Step-Log und den Manifest-Eintrag des betreffenden Runs lesen, dann Detail-/Retry-/QC-Logs der betroffenen ID bzw. des Chunks. Konfiguration oder Quelldatei korrigieren und dieselbe Phase erneut starten. `failed`/`partial` nicht allein durch Existenz einer Datei als erledigt behandeln. Eine Pipeline-Sperre erst nach Pruefung der zugehoerigen Jobs freigeben.

<!-- END SOURCE DIAGNOSTICS -->
