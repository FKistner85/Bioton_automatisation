#!/usr/bin/env python3
"""Generate concise DE/EN README files for the main pipeline steps."""

from __future__ import annotations

from pathlib import Path


STEP_REGISTRY_KEYS = {
    "step_1_metadata": ["step_1_metadata"],
    "step_2_0_lrt_cleaning": ["step_2_0_lrt_cleaning"],
    "step_2_1_100m_formation_status": ["step_2_1_100m_formation"],
    "step_2_2_point_assignment": ["step_2_2_point_assignment"],
    "step_2_3_grid_aggregation": ["step_2_3_grid_aggregation"],
    "step_2_4_10m_formation_status": ["step_2_4_10m_formation"],
    "step_3_media": [
        "step_3_0_audio_inventory",
        "step_3_0_photo_inventory",
        "step_3_1_audio_download",
        "step_3_1_photo_download",
    ],
    "step_4_sentinel2": [
        "step_4_1_sentinel2_mirror",
        "step_4_0_sentinel2_inventory",
    ],
    "step_5_2_weather": [
        "step_5_1_weather_inventory",
        "step_5_2_weather_download",
    ],
    "step_6_bioacoustics": [
        "step_6_0_bioacoustic_model_preflight",
        "step_6_1_bioacoustic_worklist",
        "step_6_2_bioacoustic_embeddings",
        "step_6_3_species_predictions",
        "step_6_4_germany_taxonomy_filter",
        "step_6_5_bioacoustic_aggregation",
        "step_6_6_bioacoustic_qc",
    ],
    "validation_and_comparison": ["step_7_0_master_table"],
}

CONFIG_SECTIONS = {
    "step_1_metadata": ["dawn_chorus_csv", "status_dir", "metadata_extraction"],
    "step_2_0_lrt_cleaning": ["lrt_cleaning"],
    "step_2_1_100m_formation_status": ["lrt_grid_merge"],
    "step_2_2_point_assignment": ["point_lrt_assignment"],
    "step_2_3_grid_aggregation": ["lrt_grid_aggregation"],
    "step_2_4_10m_formation_status": ["susi_10m_products"],
    "step_3_media": ["audio_inventory", "photo_inventory", "audio_download", "photo_download"],
    "step_4_sentinel2": ["sentinel2_download", "sentinel2_inventory"],
    "step_5_2_weather": ["weather_inventory", "weather_download"],
    "validation_and_comparison": ["master_table", "final_validation", "susi_sanity_check"],
}


STEPS = [
    {
        "slug": "step_1_metadata",
        "title": "Step 1 Metadata Extraction",
        "script": "scripts/Step_1_metadata_extraction.py",
        "purpose_de": "Normalisiert Dawn-Chorus-IDs, Koordinaten und Zeitfelder.",
        "purpose_en": "Normalises Dawn Chorus IDs, coordinates and time fields.",
        "inputs": ["PointData/dawn-chorus-soundscape.csv"],
        "outputs": ["outputs/step_1_metadata/dawnchorus_metadata_clean.csv", "outputs/step_1_metadata/dawnchorus_metadata_log.csv"],
        "resume": "Neue IDs werden inkrementell ergaenzt; from_scratch nutzt --force.",
    },
    {
        "slug": "step_2_0_lrt_cleaning",
        "title": "Step 2_0 LRT Cleaning",
        "script": "scripts/Step_2_0_clean_lrts.py",
        "purpose_de": "Bereinigt LRT-Polygone, normalisiert Codes, Status und Formation.",
        "purpose_en": "Cleans LRT polygons and normalises code, status and formation fields.",
        "inputs": ["Biodiversity_data/Bundeslander/*.gpkg"],
        "outputs": ["outputs/step_2_0/lrt.gpkg", "outputs/step_2_0/state.json"],
        "resume": "State/Fingerprints entscheiden, ob ein Rebuild noetig ist.",
    },
    {
        "slug": "step_2_1_100m_formation_status",
        "title": "Step 2_1 100m Formation Status",
        "script": "scripts/Step_2_1_merge_lrts_and_grid.py",
        "purpose_de": "Verschneidet LRTs mit dem 100m-Grid und erzeugt Majority- und Formation-Status-Produkte.",
        "purpose_en": "Overlays LRTs with the 100m grid and creates majority and formation-status products.",
        "inputs": ["InspireGrid/Vector_Data/grid.gpkg", "outputs/step_2_0/lrt.gpkg"],
        "outputs": ["outputs/step_2_1/*", "outputs/step_2_1_susi_compatible/*"],
        "resume": "Chunk-Checkpoints und State-Datei ermoeglichen Wiederaufnahme.",
    },
    {
        "slug": "step_2_2_point_assignment",
        "title": "Step 2_2 Point Assignment",
        "script": "scripts/Step_2_2_assign_points_to_lrt_grid.py",
        "purpose_de": "Ordnet Dawn-Chorus-Punkte Gridzellen und LRT-Polygonen zu.",
        "purpose_en": "Assigns Dawn Chorus points to grid cells and LRT polygons.",
        "inputs": ["outputs/step_1_metadata/dawnchorus_metadata_clean.csv", "outputs/step_2_1/LRT_Grid_Majority.csv"],
        "outputs": ["outputs/step_2_2/DawnChorus_LRT_Grid_Assignment.csv", "outputs/step_2_2/DawnChorus_LRT_Polygon_Matches.csv"],
        "resume": "Bei unveraenderten Spatial Inputs werden nur neue IDs verarbeitet.",
    },
    {
        "slug": "step_2_3_grid_aggregation",
        "title": "Step 2_3 Grid Aggregation",
        "script": "scripts/Step_2_3_generate_remaining_grid_products.py",
        "purpose_de": "Aggregiert 100m-Gridprodukte auf groessere Raster.",
        "purpose_en": "Aggregates 100m grid products to coarser grid resolutions.",
        "inputs": ["outputs/step_2_1/majority_formation_grid.parquet"],
        "outputs": ["outputs/step_2_3/*.csv", "outputs/step_2_3/state.json"],
        "resume": "State/Fingerprint-basierter Skip bei unveraenderten Inputs.",
    },
    {
        "slug": "step_2_4_10m_formation_status",
        "title": "Step 2_4 10m Formation Status",
        "script": "scripts/Step_2_4_generate_10m_formation_status_products.py",
        "purpose_de": "Erzeugt checkpointfaehige 10m-Formation-Status-Produkte.",
        "purpose_en": "Creates checkpointed 10m formation-status products.",
        "inputs": ["outputs/step_2_1_susi_compatible/Formation_Status_Grid_withLRTCode.parquet", "outputs/step_2_0/lrt.gpkg"],
        "outputs": ["outputs/step_2_4_susi_10m/*"],
        "resume": "Parquet-Parts und _batch_status erlauben Wiederaufnahme nach Timeout.",
    },
    {
        "slug": "step_3_media",
        "title": "Step 3 Media Inventory And Download",
        "script": "scripts/Step_3_0_a_audio_inventory.py, Step_3_0_b_photo_inventory.py, Step_3_1_a_audio_download.py, Step_3_1_b_photo_download.py",
        "purpose_de": "Prueft und ergaenzt Audio- und Bilddateien.",
        "purpose_en": "Validates and fills audio and photo files.",
        "inputs": ["PointData/SoundRecordings", "PointData/Images_SoundRecordings", "PointData/dawn-chorus-soundscape.csv"],
        "outputs": ["outputs/step_3_0_*/*", "outputs/step_3_1_*/*"],
        "resume": "Inventare und Retry-Logs verhindern doppelte Downloads.",
    },
    {
        "slug": "step_4_sentinel2",
        "title": "Step 4 Sentinel-2 Mirror And Inventory",
        "script": "scripts/Step_4_1_Sentinel2_download.py, scripts/Step_4_0_Sentinel2_inventory.py",
        "purpose_de": "Spiegelt externe Sentinel-2-Drive-Dateien und inventarisiert GeoTIFFs.",
        "purpose_en": "Mirrors external Sentinel-2 Drive files and inventories GeoTIFFs.",
        "inputs": ["Google Drive token.json", "PointData/S2", "PointData/S2_Scores.csv"],
        "outputs": ["PointData/S2/*.tif", "outputs/step_4_0_Sentinel2_inventory/*", "outputs/step_4_1_sentinel2_download/*"],
        "resume": "Drive-Log, Dateigroesse und mtime steuern inkrementelle Verarbeitung.",
    },
    {
        "slug": "step_5_2_weather",
        "title": "Step 5_2 HOSTRADA Weather Per Recording",
        "script": "scripts/Step_5_2_download_weather_data.py",
        "purpose_de": "Laedt/cached HOSTRADA und extrahiert Wetterzeitreihen pro Recording.",
        "purpose_en": "Downloads/caches HOSTRADA data and extracts weather time series per recording.",
        "inputs": ["outputs/step_1_metadata/dawnchorus_metadata_clean.csv", "DWD HOSTRADA"],
        "outputs": ["PointData/Weather/Hostrada/weather_<id>.csv", "outputs/step_5_2_weather_download/*"],
        "resume": "Nichtleere weather_<id>.csv und _recording_status werden wiederverwendet.",
    },
    {
        "slug": "validation_and_comparison",
        "title": "Validation And Formation-Status Comparison",
        "script": "tools/compare_formation_status_products.py, tools/final_validation_report.py",
        "purpose_de": "Vergleicht Formation-Status-Produkte und erzeugt finalen Validierungsreport.",
        "purpose_en": "Compares formation-status products and creates the final validation report.",
        "inputs": ["outputs/step_2_*", "optional legacy/reference formation-status files"],
        "outputs": ["outputs/step_8_susi_compatibility/*", "outputs/step_9_validation/*"],
        "resume": "Reports werden pro Lauf neu geschrieben; Inputs bleiben unveraendert.",
    },
]


def bullets(items: list[str]) -> str:
    return "\n".join(f"- `{item}`" for item in items)


def render(step: dict[str, object], language: str) -> str:
    purpose_key = "purpose_de" if language == "DE" else "purpose_en"
    heading = "Zweck" if language == "DE" else "Purpose"
    inputs = "Eingaben" if language == "DE" else "Inputs"
    outputs = "Outputs" if language == "DE" else "Outputs"
    run = "Ausfuehrung" if language == "DE" else "Execution"
    resume = "Checkpoint/Resume" if language == "DE" else "Checkpoint/Resume"
    qc = "Qualitaetskontrolle" if language == "DE" else "Quality Control"
    slug = str(step["slug"])
    registry_keys = STEP_REGISTRY_KEYS.get(slug, [])
    config_sections = CONFIG_SECTIONS.get(slug, [])
    registry_text = ", ".join(f"`{value}`" for value in registry_keys)
    config_text = ", ".join(f"`{value}`" for value in config_sections)
    scripts = [value.strip() for value in str(step["script"]).split(",")]
    direct_commands = "\n".join(
        f"- `python {script if '/' in script else 'scripts/' + script} "
        f"--config config.horeka.json`"
        for script in scripts
    )
    text = [
        f"# {step['title']} ({language})",
        "",
        f"## {heading}",
        str(step[purpose_key]),
        "",
        "## Script",
        f"`{step['script']}`",
        "",
        f"## {inputs}",
        bullets(step["inputs"]),  # type: ignore[arg-type]
        "",
        f"## {outputs}",
        bullets(step["outputs"]),  # type: ignore[arg-type]
        "",
        "## Abhaengigkeiten und Invalidierung" if language == "DE" else "## Dependencies And Invalidation",
        (
            f"Die verbindlichen Abhaengigkeiten, der Scope und die "
            f"Invalidierungsregeln stehen in `pipeline_steps.json` unter "
            f"{registry_text}. Der zentrale Run-Planer gibt nur betroffene "
            f"IDs weiter und plant globale Schritte nur bei geaenderten "
            f"Inputs, ergebnisrelevanter Konfiguration oder fehlenden Outputs."
            if language == "DE"
            else
            f"Authoritative dependencies, scope and invalidation rules are "
            f"defined in `pipeline_steps.json` under {registry_text}. The "
            f"central run planner passes only affected IDs and schedules "
            f"global work only for changed inputs, result-relevant config or "
            f"missing outputs."
        ),
        "",
        "## Konfiguration" if language == "DE" else "## Configuration",
        (
            f"Ergebnisrelevante Einstellungen stehen zentral in "
            f"`config.horeka.json`: {config_text}. Pfade, Workerzahlen und "
            f"fachliche Schwellen werden nicht im Slurm-Script dupliziert."
            if language == "DE"
            else
            f"Result-relevant settings are centralised in "
            f"`config.horeka.json`: {config_text}. Paths, worker counts and "
            f"domain thresholds are not duplicated in Slurm scripts."
        ),
        "",
        f"## {run}",
        (
            "`bash slurm_add_new_ids.sh` startet den regulaeren "
            "inkrementellen DAG; `bash slurm_from_scratch.sh` startet oder "
            "setzt eine Vollgeneration fort. Ein isolierter technischer "
            "Direktlauf ist mit folgenden Befehlen moeglich:"
            if language == "DE"
            else
            "`bash slurm_add_new_ids.sh` starts the regular incremental DAG; "
            "`bash slurm_from_scratch.sh` starts or resumes a full generation. "
            "An isolated technical direct run is available with:"
        ),
        direct_commands,
        "",
        "## Batch- und Parallelisierungslogik" if language == "DE" else "## Batch And Parallel Execution",
        (
            "`SLURM_CPUS_PER_TASK` begrenzt die tatsaechliche Parallelitaet. "
            "Der Step verwendet nur die in der Konfiguration erlaubte Zahl "
            "von Prozessen/Workern. IDs oder Chunks besitzen eindeutige "
            "Status- bzw. Checkpoint-Schluessel; der globale Pipeline-Lock "
            "verhindert konkurrierende schreibende Gesamtlaeufe."
            if language == "DE"
            else
            "`SLURM_CPUS_PER_TASK` limits effective parallelism. The step "
            "uses no more processes/workers than configured. IDs or chunks "
            "have unique status/checkpoint keys, while the global pipeline "
            "lock prevents concurrent writing workflows."
        ),
        "",
        f"## {resume}",
        str(step["resume"]),
        "",
        f"## {qc}",
        (
            "Outputs gelten nicht allein wegen ihrer Existenz als gueltig. "
            "Kompakte und detaillierte Logs, Batch-Statusdateien und das "
            "Run-Manifest dokumentieren Validierung und Fehler. Der finale "
            "Gate wird mit `bash run_final_validation_report.sh` erzeugt; "
            "Formation-Produkte koennen zusaetzlich mit "
            "`bash slurm_compare_formation_status.sh` verglichen werden."
            if language == "DE"
            else
            "Output existence alone is not treated as validity. Compact and "
            "detailed logs, batch status files and the run manifest record "
            "validation and failures. `bash run_final_validation_report.sh` "
            "creates the final gate; formation products can additionally be "
            "compared with `bash slurm_compare_formation_status.sh`."
        ),
        "",
        "## Status, Manifeste und Mastertabelle" if language == "DE" else "## Status, Manifests And Master Table",
        (
            "Der Slurm-Orchestrator schreibt fuer diesen Step ein Manifest "
            "unter `outputs/step_0_manifests/<step>/<step_run_id>.json` mit "
            "`workflow_run_id`, Inputs, Parametern, Laufzeit, Logs und "
            "Outputs. Step 7 fasst die ID-bezogenen Ergebnisse in der "
            "Mastertabelle zusammen; technische Details bleiben in den "
            "Step-Logs. Kanonische Statuswerte stehen in "
            "`schemas/status_model.json`."
            if language == "DE"
            else
            "The Slurm orchestrator writes a manifest under "
            "`outputs/step_0_manifests/<step>/<step_run_id>.json` containing the "
            "`workflow_run_id`, inputs, parameters, runtime, logs and outputs. "
            "Step 7 summarises ID-level results in the master table while "
            "technical detail remains in step logs. Canonical statuses are "
            "defined in `schemas/status_model.json`."
        ),
        "",
        "## Typische Fehler" if language == "DE" else "## Typical Failures",
        (
            "Fehlende Inputs oder Konfigurationsabschnitte beenden den Step "
            "mit Exit-Code ungleich null. Datenprobleme einzelner IDs werden "
            "nach Moeglichkeit im Detail-/Retry-Log als `missing`, "
            "`has_issues` oder `failed` festgehalten. Nach einem Timeout wird "
            "derselbe Betriebsmodus erneut submitted; gueltige Checkpoints "
            "werden wiederverwendet."
            if language == "DE"
            else
            "Missing inputs or configuration sections terminate the step with "
            "a non-zero exit code. Per-ID data problems are recorded where "
            "possible in detail/retry logs as `missing`, `has_issues` or "
            "`failed`. After a timeout, resubmit the same mode; valid "
            "checkpoints are reused."
        ),
        "",
    ]
    return "\n".join(text)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    readme_root = root / "Readmes"
    readme_root.mkdir(parents=True, exist_ok=True)
    index_lines = ["# Step README Index", ""]
    generated_slugs: set[str] = set()
    for step in STEPS:
        directory = readme_root / str(step["slug"])
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "README_DE.md").write_text(render(step, "DE"), encoding="utf-8")
        (directory / "README_EN.md").write_text(render(step, "EN"), encoding="utf-8")
        index_lines.append(f"- `{step['slug']}`: [{step['title']}]({step['slug']}/README_DE.md)")
        generated_slugs.add(str(step["slug"]))
    for directory in sorted(path for path in readme_root.iterdir() if path.is_dir()):
        if directory.name in generated_slugs:
            continue
        de_readme = directory / "README_DE.md"
        if not de_readme.is_file():
            continue
        first_line = de_readme.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        index_lines.append(
            f"- `{directory.name}`: [{first_line}]({directory.name}/README_DE.md)"
        )
    (readme_root / "README_INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(STEPS) * 2 + 1} README files under {readme_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
