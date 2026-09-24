# GitHub-Workflow

Die aktuelle Arbeitskopie liegt auf Horeka unter
`/home/hk-project-pai00063/jk3038/Bio-O-Ton/Data_automatisation_skripts/bio_o_ton_pipeline_git`.
Der Pfad kann je nach Mount auch unter LSDF erreichbar sein. Befehle im Root des
bestehenden Checkouts ausfuehren; keine vorhandenen Ordner umbenennen oder neu initialisieren.

## Aktualisieren

```bash
bash update_horeka_from_git.sh main
```

Das Skript aktualisiert per Fast-Forward und stoppt bei lokalen Aenderungen.
Ein normaler Submit fuehrt keinen automatischen Pull aus. `run_horeka.sh --update`
fordert das Update ausdruecklich an. Aktiven produktiven Code nicht waehrend eines
Laufs austauschen: die beim Submit gespeicherte Befehlszeile verweist weiterhin
auf Dateien im Checkout, deren Inhalt sich sonst aendern kann.

## Getrennte Laeufe

Nach Update und Tests zuerst den Kern starten:

```bash
bash slurm_add_new_ids.sh
```

Nach dessen Abschluss Bioakustik separat starten:

```bash
bash slurm_bioacoustics.sh
```

Alternativ dienen `bash run_horeka.sh add_new_ids` und
`bash run_horeka.sh bioacoustics` als tmux-/Hybrid-Startwege.

## Lokale Arbeit

Aenderungen und Tests zuerst lokal pruefen. Vor einem Commit `git diff` und die
Dateiliste kontrollieren. Secrets, Modellgewichte, Umgebungen und produktive
Outputs gehoeren nicht in Git; `.gitignore` schliesst sie aus.
Remote: `https://github.com/FKistner85/Bioton_automatisation.git`.
Ein bestehendes Repository benoetigt weder `git init` noch einen neuen Remote.

Die relativen `.secrets/`- und `bacpipe/model_checkpoints/`-Pfade beziehen sich auf
den aktiven Checkout. Auf einem anderen Cluster Umgebungen neu aufbauen und die
Datenpfade explizit pruefen; siehe [Horeka-2-Vorbereitung](Readmes/pipeline_phases.md).
