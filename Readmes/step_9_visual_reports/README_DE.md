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
