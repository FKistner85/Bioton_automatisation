# Bio-O-Ton: lokaler Windows-Lauf mit LSDF

Dieser Ordner startet dieselben fachlichen Python-Skripte wie die Cluster-
Pipeline. Slurm wird lokal nicht emuliert. `local_orchestrator.py` bildet den
Abhaengigkeitsgraphen, parallele unabhaengige Schritte, Arrays, Manifeste,
Checkpoints und Mastertable-Updates mit lokalen Prozessen nach.

## Speicherorte

| Inhalt | Speicherort |
|---|---|
| Pipeline-Code | uebergeordneter Git-Ordner |
| Generierte Outputs | `<workspace_dir>/outputs/step_*` |
| Finale Mastertabelle | `<workspace_dir>/outputs/Bio_O_Ton_Mastertable.*` |
| Lokale Logs | `<workspace_dir>/outputs/step_0_local_logs` |
| Grosse/statische LSDF-Eingaben | `<workspace_dir>/lsdf_cache` |
| Audio-Originale | LSDF `PointData/SoundRecordings` |
| Foto-Originale | LSDF `PointData/Images_SoundRecordings` |
| Sentinel-2-TIFs | LSDF `PointData/S2` |
| Punkt-Wetter-CSV | LSDF `PointData/Weather/Hostrada` |

Die vier Originalverzeichnisse werden ueber ein eingebundenes LSDF-Laufwerk
direkt gelesen und beschrieben. Generierte Analyseprodukte bleiben lokal.

## Voraussetzungen

1. Windows 10/11, Python 3.11 und PowerShell.
2. WinFsp und SSHFS-Win muessen installiert sein.
3. Das LSDF-Passwort liegt im Windows Credential Manager.
4. Fuer den Sentinel-Drive-Mirror liegt `credentials.json` im Git-Hauptordner.

Passwort einmalig in der `BioTon`-Python-Umgebung speichern:

```python
import keyring
keyring.set_password("lsdf_kit", "jk3038", "DEIN_PASSWORT")
```

Das Passwort wird von `mount_lsdf.py` nur an SSHFS uebergeben und weder in
Konfigurationen noch in Logs geschrieben.

## Lokale Einstellungen

Beim ersten Start wird `local.settings.json` aus
`local.settings.example.json` erzeugt. Die Datei ist nicht fuer Git bestimmt.
Standardprofil fuer den aktuellen Rechner:

```text
20 nutzbare logische CPUs von 24
maximal 2 unabhaengige Pipeline-Schritte gleichzeitig
maximal 2 lokale Array-Tasks gleichzeitig
1 paralleler Bioakustik-Task bei CUDA, sonst 2
128 GB RAM werden nicht fest reserviert; die Step-Checkpoints begrenzen Spitzen
```

`workspace_dir` steht standardmaessig auf `D:/BioOTon_local_workspace` und
kann in `local.settings.json` geaendert werden.

## Environment erzeugen

```powershell
cd "C:\Users\Frede\OneDrive\Projects and Disschaptors\Bioton_automatisation\scripts_local_run"
powershell -ExecutionPolicy Bypass -File .\setup_local_env.ps1
```

Es werden zwei kompatible Environments erzeugt:

```text
.venv_local          Geodaten, Medien, Wetter, Reports und Orchestrierung
.venv_local_bacpipe  Bacpipe und PyTorch fuer Step 6
```

## Start

Inkrementell fuer neue, geaenderte oder problematische IDs:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 -Mode add_new_ids
```

Kompletter Neuaufbau mit den gleichen `--force`-Regeln wie auf dem Cluster:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 -Mode from_scratch
```

Schneller Funktionstest:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 -Mode functionality_test
```

Dieser Modus mountet LSDF nicht und kopiert keine groÃŸen Eingabedateien.

Nach dem ersten erfolgreichen Setup kann die Dependency-Pruefung uebersprungen
werden:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 -Mode add_new_ids -SkipEnvironmentSetup
```

CPU fuer Step 6 erzwingen:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 -Mode add_new_ids -SkipEnvironmentSetup -CpuOnly
```

## Resume und Fehler

Ein Abbruch mit `Ctrl+C` behaelt alle fachlichen Checkpoints. Beim naechsten
Aufruf erkennt `plan_pipeline_run.py` neue und problematische IDs erneut und
die Steps verwenden vorhandene Chunk-, Datei- und Batch-States.

Lokale Logs tragen einen UTC-Zeitstempel. Ein Step-Fehler laesst unabhaengige
Zweige weiterlaufen. Abhaengige Bioakustik-Schritte werden nach einem Fehler in
Model-Preflight, Worklist oder Inferenz nicht gestartet.

Das lokale Lock liegt ausschliesslich im lokalen Workspace. Cluster- und
lokaler Lauf duerfen trotzdem nicht gleichzeitig Originaldateien herunterladen
oder auf dem LSDF pruefen, da beide dieselben Medienverzeichnisse verwenden.

## LSDF trennen

Nach Ende aller lokalen Pipeline-Prozesse:

```powershell
net use L: /delete /y
```

