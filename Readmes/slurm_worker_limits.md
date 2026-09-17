# Weniger Slurm-Jobs

Die Startskripte fuer `add_new_ids` und `from_scratch` buendeln grosse Arrays:

| Bereich | Slurm-Teiljobs | Arbeit pro Job |
| --- | ---: | --- |
| Bioakustik | maximal 4 | Mehrere Modell-/Shard-Aufgaben nacheinander |
| HOSTRADA-Raster | maximal 2 | Mehrere Variablen-/Jahres-Aufgaben nacheinander |
| Wetter-Download | unveraendert maximal 8 laut aktueller Konfiguration | Aufgeteilte Aufnahme-IDs |

Die Bioakustik behaelt ihre 64 logischen Shards je Modell. Bei sechs Modellen
bearbeiten vier Worker weiterhin alle 384 Aufgaben. Die Workerzahl aendert weder
Shard-IDs noch vorhandene Checkpoints. Die anschliessenden Verifier pruefen
weiterhin alle erwarteten Produkte. Fehler einzelner Aufgaben werden gesammelt;
der Worker bearbeitet die uebrigen Aufgaben und endet mit Fehlerstatus.

Optional vor dem Start auf Horeka:

```bash
export BIOOTON_BIOACOUSTICS_WORKERS=4
export BIOOTON_STEP54_WORKERS=2
bash slurm_add_new_ids.sh
```

Die Einstellungen gelten auch fuer `slurm_from_scratch.sh`. Workerzahl und
Parallelitaet sind getrennt: `max_concurrent_tasks` begrenzt nur gleichzeitig
laufende Jobs, nicht die Zahl wartender Jobs.

Das Slurm-Zeitlimit gilt jetzt fuer einen ganzen Worker, nicht fuer jede seiner
Teilaufgaben. Bei langen Laeufen kann deshalb ein weiterer inkrementeller Start
noetig sein. Die Bioakustik erhaelt das Vorwarnsignal weiterhin, damit sie ihren
Fortschritt sichern kann. Nach einem Signal startet der Worker keine weitere
Aufgabe. Es gibt keine automatische Neueinreichung nach einem Zeitlimit.

Die Pipeline meldet weiterhin ihre einzelnen Vorbereitungs-, Pruef- und
Master-Schritte an. Auch mit kleineren Arrays kann ein gemeinsam ausgelastetes
Account-Limit die Einreichung verhindern.

Bereits eingereihte Jobs bleiben unveraendert. Nach einer zuvor abgebrochenen
Einreichung zuerst deren Jobs und Pipeline-Lock pruefen; nicht parallel einen
zweiten Lauf starten oder den Lock waehrend aktiver Jobs entfernen.

Lokale Pruefung: `python tests/test_array_worker.py` prueft Aufgabenabdeckung,
Fehlerweitergabe, Signalweitergabe sowie echte und simulierte sbatch-Argumente.
