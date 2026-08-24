# Earth-Engine-Schlüssel für unbeaufsichtigte Sentinel-Läufe

Der Service-Account `bio-o-ton@bio-o-ton-gee.iam.gserviceaccount.com` kann die Sentinel-Stufe ohne Browser-Login oder 2FA ausführen. Der private JSON-Schlüssel gehört **nicht** in Git – auch nicht vorübergehend –, weil Google öffentlich erkannte Schlüssel automatisch deaktivieren kann.

Auf HoreKa alle vier Dateien außerhalb des Checkout-Verzeichnisses ablegen. Der GEE-Schlüssel berechnet die Scores. Der Earth-Engine-Nutzer-Token startet die Legacy-Drive-Exporttasks mit dem Speicherkontingent von `biooton.kit@gmail.com`. Der separate Read-only-Drive-Token liest die fertigen TIFFs und spiegelt sie nach LSDF:

```bash
install -d -m 700 /lsdf/kit/ipf/projects/Bio-O-Ton/.secrets
install -m 600 bio-o-ton-gee-service-account.json \
  /lsdf/kit/ipf/projects/Bio-O-Ton/.secrets/bio-o-ton-gee-service-account.json
install -m 600 credentials_bio-o-ton.json \
  /lsdf/kit/ipf/projects/Bio-O-Ton/.secrets/credentials_bio-o-ton.json
install -m 600 token_bio-o-ton.json \
  /lsdf/kit/ipf/projects/Bio-O-Ton/.secrets/token_bio-o-ton.json
install -m 600 earthengine-export-token-bio-o-ton.json \
  /lsdf/kit/ipf/projects/Bio-O-Ton/.secrets/earthengine-export-token-bio-o-ton.json
```

`config.horeka.json` verweist bereits auf diese vier geschützten LSDF-Pfade. Optional lassen sie sich pro Job überschreiben:

```bash
export BIOOTON_GEE_SERVICE_ACCOUNT_KEY=/geschuetzter/pfad/service-account.json
export BIOOTON_DRIVE_CREDENTIALS=/geschuetzter/pfad/credentials.json
export BIOOTON_DRIVE_TOKEN=/geschuetzter/pfad/token.json
export BIOOTON_GEE_EXPORT_TOKEN=/geschuetzter/pfad/earthengine-export-token.json
```

Der Earth-Engine-Exporttoken wird einmalig lokal im angemeldeten Google-Konto erzeugt und danach wie oben nach LSDF kopiert:

```bash
python tools/create_gee_export_token.py \
  --output .secrets/earthengine-export-token-bio-o-ton.json
```

Der gespeicherte Refresh-Token erlaubt die späteren tmux-/Slurm-Läufe ohne Browser und ohne erneute 2FA, solange Google ihn nicht widerruft. Der Drive-Ordner `S2` muss für `bio-o-ton@bio-o-ton-gee.iam.gserviceaccount.com` mit Schreibrechten freigegeben sein, weil Earth Engine beim Legacy-Export nur den Ordnernamen, nicht die Ordner-ID, annimmt. Für lokale Tests liegen die Dateien in `.secrets/`; dieses Verzeichnis ist durch `.gitignore` ausgeschlossen. Nach der Übertragung sollte die heruntergeladene Schlüsselkopie im lokalen Downloads-Ordner gelöscht oder sicher verschlüsselt werden.

Schritt 4.1 verarbeitet alle neuen Sentinel-IDs in aufeinanderfolgenden 500-ID-Pipeline-Batches. Die Score-Abfrage bleibt intern bei den stabil getesteten 100 IDs pro GEE-Request. Pro Batch sind höchstens 20 Drive-Exporttasks gleichzeitig aktiv; erst nach deren Abschluss beginnt der nächste Batch. Bestehende Drive- oder LSDF-TIFFs werden auch mit `--force` nicht erneut exportiert oder überschrieben.

Der reproduzierbare Score-Regressionslauf zieht standardmäßig 100 deterministisch ausgewählte Referenzzeilen ab 2026 aus der bestehenden `S2_Scores.csv`, berechnet sie mit derselben `dc_best`-Expression neu und verlangt Score-Gleichheit mit absoluter Toleranz `1e-12` sowie einen exakt gleichen `best_index`:

```bash
bash run_sentinel_score_validation.sh
```

Der vollständige Einzelzeilenbericht wird nach `outputs/step_4_1_sentinel2_download/score_validation_100.csv` geschrieben. Schon eine Abweichung ergibt Exitcode 1; die Referenz-Score-Datei wird ausschließlich gelesen.
