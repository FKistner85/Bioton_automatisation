# Zwei getrennte Pipeline-Läufe

## 1. Daten aktualisieren

```bash
bash slurm_add_new_ids.sh
```

Metadaten, LRT-/Grid-Produkte, Audio, Fotos, Sentinel und Wetter laufen wie bisher.
Unabhängige Zweige bleiben parallel. Danach folgen Master, Abschlussprüfung und
Freigabe des Pipeline-Locks. Es werden **keine Schritte 6.x** eingeplant und keine
Bacpipe-Umgebung installiert. `from_scratch` baut ebenfalls nur diesen Kern neu auf.

## 2. Bioakustik bei Bedarf starten

Nach Abschluss des ersten Laufs separat ausführen:

```bash
bash slurm_bioacoustics.sh
```

Dieser Lauf umfasst Modellprüfung, Worklist, Inferenz, Vorhersagen,
Deutschland-Taxonomie, Aggregation, QC, Bioakustik-Master-Update und Abschlussprüfung.
Er verwendet die vorbereiteten Metadaten und das Audioinventar. Abweichende IDs
zwischen Metadaten und Master verhindern den Start; dann zuerst den Kernlauf abschließen.

Die Worklist wird für alle aktuellen Metadaten-IDs neu abgeglichen. Dadurch gehen
neue oder geänderte Audiodateien nicht verloren, wenn Step 1 seine Änderungsmarker
bereits aktualisiert hat. Gelöschte IDs werden aus der Worklist entfernt.
Unveränderte Audio-/Modell-Work-Keys verwenden weiterhin ihre Inferenz-Checkpoints.
Modelle, Parameter, logische Shards und Dateipfade bleiben unverändert.
Standardmäßig verteilen vier Slurm-Worker die bisherigen logischen Inferenzaufgaben.
Ein erneuter Start setzt die Arbeit anhand der Checkpoints fort.

Das Bioakustik-Master-Update ersetzt ausschließlich Bioakustikfelder und
`ready_for_bioacoustic_analysis`. Zeiten, Koordinaten, LRT-/Grid-Zuordnungen,
Medien-/Wetterstatus und zusätzliche vorhandene Spalten werden übernommen.
Die Kern-Abschlussprüfung fordert keine Bioakustikprodukte; der Bioakustiklauf
prüft seine eigenen Produkte und Voraussetzungen. Die gemeinsame Sperre verhindert
gleichzeitige Schreibzugriffe beider Phasen. Nicht parallel auf demselben Output starten.

Wer den bisherigen tmux-Controller verwendet, nutzt entsprechend zuerst:

```bash
bash run_horeka.sh add_new_ids
```

Und später:

```bash
bash run_horeka.sh bioacoustics
```

Beide Startwege verwenden denselben Planer. Unter Windows steht zusätzlich
`scripts_local_run/run_pipeline_local.ps1 -Mode bioacoustics` zur Verfügung.
Die Rechenarbeit der Modelle wird nicht schneller; der normale Datenlauf wartet
jetzt nicht mehr darauf.

## Vorbereitung für Horeka 2

Ohne Profil gelten die bisherigen Horeka-Einstellungen. Ein vertrauenswürdiges
lokales Shell-Profil kann über `BIOOTON_CLUSTER_PROFILE=/absoluter/pfad/profil.sh`
gewählt werden. Launcher und Environment-Bootstrap lesen es vor ihren Standardwerten;
der tmux-Start übernimmt die exportierten Einstellungen ebenfalls.

Das Profil bündelt `CONFIG`, Core-/Bacpipe-Python bzw. Environment-Präfixe,
Partitionen, Account und Ressourcen. `BIOOTON_CONSTRAINT` ersetzt das bisher fest
eingebaute `LSDF`; ein ausdrücklich leerer Wert lässt `--constraint` weg.
Zeit-, CPU-, Speicher-, GPU- und Worker-Overrides bleiben verfügbar.
Die Vorlage `cluster_profiles/horeka2.example.sh` bricht absichtlich ab, bis sie
kopiert und mit den auf Horeka 2 bestätigten Angaben konfiguriert wurde.
Partitionsnamen, Hardware und Mountpoints werden nicht vorweggenommen.

Bei der Migration die Konfiguration mit den dort gültigen absoluten Datenpfaden
bereitstellen, beide Python-Umgebungen neu aufbauen und Modell-/Runtime-Versionen
beibehalten. Keine bestehende virtuelle Umgebung zwischen Clustern kopieren.
Erst Funktionstest und Submission-Vorschau, danach ein kleiner Bioakustik-Testlauf
gegen bekannte Ergebnisse. LSDF-Produkte und Checkpoints nur übernehmen, wenn
Pfade und Zugriffsrechte bestätigt sind. Die Migration selbst ist noch nicht erfolgt.
