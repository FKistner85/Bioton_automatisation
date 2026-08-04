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
| Python-Environments | `<environment_dir>/core` und `<environment_dir>/bacpipe` |
| Audio-Originale | LSDF `PointData/SoundRecordings` |
| Foto-Originale | LSDF `PointData/Images_SoundRecordings` |
| Sentinel-2-TIFs | LSDF `PointData/S2` |
| Punkt-Wetter-CSV | LSDF `PointData/Weather/Hostrada` |

Die vier Originalverzeichnisse werden ueber ein eingebundenes LSDF-Laufwerk
direkt gelesen und beschrieben. Vor dem ersten lokalen `add_new_ids` werden
die bereits auf Horeka erzeugten Produkte einmalig nach
`<workspace_dir>/outputs` uebernommen. Dadurch verwendet der lokale Planner
die vorhandenen Fingerprints, Inventare, Checkpoints und die Mastertabelle.
Remote-Locks, Run-Plaene und alte Slurm-Logs werden dabei ausgeschlossen.

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

Der Mount verwendet den offiziellen SSHFS-Win-Netzwerkprovider mit der
Root-UNC `\\sshfs.r\...`. Das Keyring-Passwort wird direkt ueber die
Windows-Netzwerk-API uebergeben und erscheint nicht in der Prozess-
Kommandozeile.

Ist ein altes Laufwerks-Mapping vorhanden, aber nicht mehr lesbar, wird es vor
dem Neuaufbau entfernt. Akzeptiert der Windows-Netzwerkprovider die Verbindung
nicht, versucht der Helper einmalig `sshfs.exe` direkt; auch dabei wird das
Passwort nur ueber die Standardeingabe uebergeben.

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

Es werden zwei kompatible Environments ausserhalb des tiefen OneDrive-Pfads
erzeugt. Standard ist `D:/BioOTon_envs`:

```text
core     Geodaten, Medien, Wetter, Reports und Orchestrierung
bacpipe  Bacpipe, TensorFlow und PyTorch fuer Step 6
```

Der kurze Pfad verhindert Windows-Installationsfehler durch sehr lange
TensorFlow-Dateinamen. Ein unvollstaendiges Environment kann explizit neu
erzeugt werden:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_local_env.ps1 -Recreate
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

Dieser Modus mountet LSDF nicht und kopiert keine grossen Eingabedateien.
Er installiert und benoetigt auch das Bacpipe-Environment nicht.

Nach dem ersten erfolgreichen Setup kann die Dependency-Pruefung uebersprungen
werden:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 -Mode add_new_ids -SkipEnvironmentSetup
```

CPU fuer Step 6 erzwingen:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 -Mode add_new_ids -SkipEnvironmentSetup -CpuOnly
```

## Vorhandene Horeka-Outputs

Der erste inkrementelle Lauf kopiert finale Horeka-Produkte, Statusdateien und
Manifeste fortsetzbar in den lokalen Workspace. Reine Zwischenchunk-Ordner wie
`grid10m_chunks`, `ix_chunks`, `parquet_10` und `_chunk_checkpoints` werden
nicht ueber SSHFS uebertragen. Dasselbe gilt fuer die grossen, unveraenderlichen
HOSTRADA-Downloadcaches aus Step 5.2 und 5.3. Diese werden von lokalen Steps
direkt unter `L:\Data_automatisation_skripts\outputs` wiederverwendet; neu
heruntergeladene Quelldateien ergaenzen dort den gemeinsamen Cache. Erzeugte
Raster, Tabellen, States und Reports bleiben dagegen bis zur erfolgreichen
Veroeffentlichung lokal. Bereits lokal neuere Dateien werden nicht
ueberschrieben. Einzelne temporaere Netzwerkfehler werden wiederholt und als
`partial` protokolliert; sie blockieren den lokalen Lauf nicht und werden beim
naechsten Bootstrap erneut versucht. Spaetere Horeka-Ergebnisse werden nur auf
ausdruecklichen Wunsch erneut abgeglichen:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 `
  -Mode add_new_ids -SkipEnvironmentSetup -RefreshHorekaOutputs
```

`from_scratch` importiert keine Horeka-Produkte. Der Bootstrap kann bei einem
inkrementellen Lauf mit `-SkipHorekaBootstrap` deaktiviert werden. Cluster und
lokaler Lauf duerfen waehrend des Abgleichs nicht gleichzeitig schreiben.

Die nur fuer den derzeit nicht orchestrierten Public-LRT-Zweig vorgesehene
Datei `InspireGrid/Vector_Data/grid_public.gpkg` ist lokal optional. Fehlt sie,
wird dies protokolliert, ohne die regulaere Pipeline zu blockieren. Alle
Kerndateien der ausgefuehrten Schritte bleiben Pflichtinputs.

## Erfolgreiche lokale Ergebnisse auf LSDF veroeffentlichen

Nach einem vollstaendig erfolgreichen `add_new_ids`- oder `from_scratch`-Lauf
werden kompatible lokale Outputs automatisch in den kanonischen LSDF-Ordner
`Data_automatisation_skripts/outputs` hochgeladen. Pfade in CSV-, JSON- und
pfadhaltigen Parquet-Dateien werden dabei von Windows auf LSDF uebersetzt.
Dadurch koennen die Horeka-Planung und ihre Checkpoints lokal abgeschlossene
Arbeit erkennen und ueberspringen.

Nicht veroeffentlicht werden lokale Logs, Slurm-Logs, Manifeste, Run-Plaene,
Locks, lokale Reports und die umgebungsspezifische Bacpipe-Model-Registry.
Der Upload loescht keine Remote-Dateien, ueberschreibt keine neueren
Remote-Dateien und bricht ab, wenn ein Remote-Pipeline-Lock existiert.

Fuer einen einzelnen Lauf kann die Veroeffentlichung abgeschaltet werden:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_pipeline_local.ps1 `
  -Mode add_new_ids -SkipEnvironmentSetup -SkipLsdfPublish
```

Dauerhaft steuerbar ist das Verhalten in `local.settings.json` mit
`publish_successful_outputs_to_lsdf`.

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
