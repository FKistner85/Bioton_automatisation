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

<!-- BEGIN SOURCE DIAGNOSTICS -->
## Error Codes, Status And Exit Codes

Checked against local code: 2026-09-23. Tables separate data/QC codes, statuses, explicit exceptions and process exit codes. `{...}` denotes runtime values rather than fixed codes. Conditions identify the exact source trigger; multiple codes may occur together.

`0` only means process success, not necessarily clean data. Invalid argparse arguments can exit with `2`; uncaught Python exceptions typically exit with `1`. Slurm states such as `TIMEOUT`, `OUT_OF_MEMORY`, `CANCELLED` and `DependencyNeverSatisfied` are scheduler messages, not data-quality codes. Dynamic library/HTTP/filesystem errors retain their original messages in logs.

### Data And QC Codes

No fixed values in this category in the associated source.

### Status Values (Not All Are Errors)

No fixed values in this category in the associated source.

### Explicit Failure Messages

No fixed values in this category in the associated source.

### Explicit Process Returns

| Code / Message | Meaning / Trigger | Source |
|---|---|---|
| `0` | `Emitted by main` | [generate_pipeline_visual_reports.py:259](../../tools/generate_pipeline_visual_reports.py) |

**Recovery:** Read the step log and manifest for the affected run first, then the detail/retry/QC log for the ID or chunk. Correct the configuration or input and restart the same phase. File existence does not resolve `failed`/`partial` results. Release a pipeline lock only after inspecting its jobs.

<!-- END SOURCE DIAGNOSTICS -->
