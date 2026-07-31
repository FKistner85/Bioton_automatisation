# HoreKa Recovery-Runbook

Dieses Runbook beschreibt die sichere Reihenfolge nach Codeaenderungen. Es
veraendert oder loescht keine LSDF-Quelldaten.

## Vor dem Submit

1. Sicherstellen, dass keine alte Pipeline mehr laeuft.
2. Eine verwaiste Pipeline-Sperre erst nach der Jobkontrolle freigeben.
3. Den Git-Stand aktualisieren und den Commit-Hash notieren.
4. Hauptumgebung und Bacpipe-Umgebung pruefen beziehungsweise neu aufbauen.
5. Zuerst den zehnminuetigen Funktionstest starten.

## Technische Recovery-Regeln

- Der Wetterplan nimmt neue/geaenderte IDs, Mastertable-Probleme und Problem-IDs
  aus dem letzten kompakten Wetterinventar auf.
- Step 5_2 ist geshardet und setzt vorhandene gueltige CSVs fort. Noch nicht
  veroeffentlichte DWD-Monate werden als `upstream_unavailable` protokolliert,
  nicht als interner Python-Fehler.
- HOSTRADA-Jahresdateien werden anhand der zehnstelligen Zeitstempel erkannt.
  Der Step-5_4-Verifier darf bei null erkannten vollstaendigen Jahren nicht
  erfolgreich enden.
- Mastertable-Readiness wird standardmaessig im Modus `report_only` berichtet.
  Fehlende technische Pflichtartefakte und fehlgeschlagene Manifeste bleiben
  harte Fehler. Nicht freigabebereite Einzel-IDs bleiben sichtbar, blockieren
  aber nicht die Aussage, dass die Pipeline technisch durchgelaufen ist.
- Medien- und Wetter-Batchfortschritt wird laufend geschrieben. Die
  Mastertable wird bei Medien erst nach 5.000 abgeschlossenen IDs aktualisiert,
  damit Volltabellen-Updates nicht zum Download-Bottleneck werden.

## Empfohlene Ausfuehrungsreihenfolge

Beim ersten Git-basierten Deployment den bisherigen Ordner als Backup
umbenennen, das Repository neu nach `scripts_horeka` klonen und nur die nicht
versionierten OAuth-Dateien `credentials.json` und `token.json` aus dem Backup
uebernehmen. Alte virtuelle Umgebungen und alte Modell-Checkpoints werden nicht
kopiert. Bei spaeteren Deployments reicht das Update-Skript.

```bash
cd /lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/bio_o_ton_pipeline/scripts_horeka
bash update_horeka_from_git.sh main
bash bootstrap_env.sh
bash bootstrap_bacpipe_env.sh
bash slurm_functionality_test.sh
```

Den Funktionstest mit `squeue`, `sacct` und dem neuen datierten Log pruefen.
Nur bei `COMPLETED 0:0` folgt der Recovery-Lauf:

```bash
bash slurm_add_new_ids.sh
```

Fuer diesen Lauf keinen globalen 10- oder 30-Minuten-Override setzen. Die
einzelnen Steps besitzen aufgabenspezifische Laufzeiten und Checkpoints.

## Abnahmekriterien

- Funktionstest: `COMPLETED`, ExitCode `0:0`.
- Run-Plan enthaelt die erwarteten Wetter-Problem-IDs.
- Step 2_4 setzt vorhandene Chunk-Checkpoints fort und erzeugt das finale
  10-m-Parquet.
- Step 5_4 erkennt mindestens ein vollstaendiges Variable/Jahr-Paar; der
  Verify-Job meldet keine fehlenden erwarteten Tiles.
- Step 6_0 meldet alle als `required` konfigurierten Modelle mit
  `initialisation: ok`. Optionale Modelle duerfen als Warnung erscheinen.
- Die finale Validierung trennt `technical_status` und `release_status`.
  Eine fachliche Datenfreigabe bleibt ein manueller Teamentscheid.
