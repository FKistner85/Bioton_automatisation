# HoreKa Recovery-Runbook

Dieses Runbook beschreibt die sichere Reihenfolge nach Codeaenderungen. Es
veraendert oder loescht keine LSDF-Quelldaten.

## Vor dem Submit

1. Sicherstellen, dass keine alte Pipeline mehr laeuft.
2. Eine verwaiste Pipeline-Sperre erst nach der Jobkontrolle freigeben.
3. Den Git-Stand aktualisieren und den Commit-Hash notieren.
4. Hauptumgebung pruefen; Bacpipe nur fuer die separate Bioakustikphase benoetigt.
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

Im bestehenden Checkout arbeiten; Datenordner und Secrets nicht umbenennen.
Code nur aktualisieren, wenn keine alte Pipeline mehr auf diesen Checkout zugreift.
Die Bacpipe-Umgebung wird erst fuer die separate Bioakustikphase benoetigt.

```bash
bash update_horeka_from_git.sh main
```

```bash
bash bootstrap_env.sh
```

```bash
bash slurm_functionality_test.sh
```

Den Funktionstest mit `squeue`, `sacct` und dem neuen datierten Log pruefen.
Nur bei `COMPLETED 0:0` folgt der Recovery-Lauf:

```bash
bash slurm_add_new_ids.sh
```

Fuer diesen Lauf keinen globalen 10- oder 30-Minuten-Override setzen. Die
einzelnen Steps besitzen aufgabenspezifische Laufzeiten und Checkpoints.

Nach Abschluss des Kernlaufs bei Bedarf separat:

```bash
bash slurm_bioacoustics.sh
```

## Abnahmekriterien

- Funktionstest: `COMPLETED`, ExitCode `0:0`.
- Run-Plan enthaelt die erwarteten Wetter-Problem-IDs.
- Step 2_4 setzt vorhandene Chunk-Checkpoints fort und erzeugt das finale
  10-m-Parquet.
- Step 5_4 erkennt mindestens ein vollstaendiges Variable/Jahr-Paar; der
  Verify-Job meldet keine fehlenden erwarteten Tiles.
- Nur Bioakustikphase: Step 6_0 initialisiert alle durch die Konfiguration verlangten Modelle. Mit `require_all_models_complete=true` sind derzeit alle sechs Modelle auch fuer den Verify-Gate erforderlich.
- Die finale Validierung trennt `technical_status` und `release_status`.
  Eine fachliche Datenfreigabe bleibt ein manueller Teamentscheid.
