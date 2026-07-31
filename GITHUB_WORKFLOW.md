# GitHub Workflow

## Zielstruktur

Die bestehende Horeka-Struktur bleibt unveraendert:

```text
Data_automatisation_skripts/
  bio_o_ton_pipeline/
    scripts_horeka/              <- Git-Arbeitskopie
  outputs/                       <- generierte Produkte, nicht versioniert
PointData/                       <- Originaldownloads und Quelldaten, nicht versioniert
```

Das Git-Repository hat sinnvollerweise `scripts_horeka` als Repository-Wurzel.
Damit liegen Code, Konfiguration, Schemas, Tests und Readmes zusammen; grosse
Outputs, Zugangsdaten und Modell-Checkpoints verbleiben ausserhalb von Git.

## Einmalig lokal

```powershell
cd C:\Users\Frede\OneDrive\Documents\piepe_new\scripts_horeka
git init
git add .
git commit -m "Initial Bio-O-Ton pipeline"
git branch -M main
git remote add origin <GITHUB-REPOSITORY-URL>
git push -u origin main
```

Vor `git add` pruefen, dass `credentials.json`, `token.json`, `.venv` und
`bacpipe/model_checkpoints` nicht erfasst werden. Die bereitgestellte
`.gitignore` deckt diese Faelle ab.

## Einmalig auf Horeka

Statt Dateien manuell hochzuladen, wird die Arbeitskopie einmal als Git-Clone
eingerichtet. Bereits vorhandene Umgebungen und die neue `outputs`-Struktur
bleiben erhalten.

```bash
cd /lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/bio_o_ton_pipeline
mv scripts_horeka scripts_horeka_backup_$(date +%Y%m%d)
git clone <GITHUB-REPOSITORY-URL> scripts_horeka
```

Danach muessen `credentials.json` und `token.json` bei Bedarf einmalig wieder
in `scripts_horeka/` bereitgestellt werden. Die virtuellen
Umgebungen werden mit `bash bootstrap_env.sh` bzw.
`bash bootstrap_bacpipe_env.sh` erstellt.

## Regelmaessiges Update auf Horeka

```bash
cd /lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/bio_o_ton_pipeline/scripts_horeka
bash update_horeka_from_git.sh main
```

Das Skript nutzt ausschliesslich `git fetch` und `git pull --ff-only`. Bei
lokalen, nicht commiteten Codeaenderungen stoppt es absichtlich, damit keine
unbeabsichtigten Ueberschreibungen passieren. Vor einem Pipeline-Run zuerst
den Commit-Hash mit `git log -1 --oneline` dokumentieren.

## Empfohlene Arbeitsregel

1. Lokal entwickeln und `bash run_tests.sh` ausfuehren.
2. Aenderungen als kleinen, beschreibenden Commit auf `main` oder einen
   Feature-Branch pushen.
3. Auf Horeka mit `update_horeka_from_git.sh` aktualisieren.
4. Erst danach Slurm-Jobs einreichen. Bereits eingereichte Jobs behalten ihre
   beim Submit gespeicherte Befehlszeile; bei strukturellen Orchestrator-
   Aenderungen daher abbrechen und neu einreichen.
