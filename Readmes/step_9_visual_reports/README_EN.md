# Step 9 Visual Reports (EN)

`tools/generate_pipeline_visual_reports.py` reads only compact outputs from
completed or partial steps. It creates no new analysis and does not modify
source or domain products.

Outputs:

- `outputs/step_9_visual_reports/index.html`: overview
- `outputs/step_9_visual_reports/01_step_1_metadata.html` through
  `07_step_7_mastertable.html`: per-step pages
- `outputs/step_9_visual_reports/report_manifest.json`: technical page list

The Slurm workflow runs the generator after `final_validation`. It remains
robust when some steps are incomplete; open `index.html` directly in a browser.
