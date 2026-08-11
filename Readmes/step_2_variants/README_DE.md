# Step 2 Varianten - LRT-Sensitivitaetsanalyse

## Zweck

Alle GeoPackages aus
`Biodiversity_data/Bundeslander/All_Bundeslander/All_Bundeslander_*.gpkg`
werden als getrennte fachliche Varianten verarbeitet. Kein Datensatz
ueberschreibt einen anderen. Der Dateisuffix nach `All_Bundeslander_` ist die
stabile Varianten-ID.

Die Primärvariante ist derzeit `no_K_post2017_threshold_50`. Nur ihre
Formation-Felder werden in der kompakten ID-Mastertabelle verwendet. Alle
Varianten stehen zusaetzlich in einer normalisierten Vergleichstabelle.

## Verarbeitung pro Variante

```text
Eingangs-GPKG
  -> Step 2_0 LRT-Bereinigung
  -> Step 2_1 100m-Formation und Statusmatrix
  -> Step 2_2 Recording-Zuordnung
  -> Step 2_3 groebere Rasterprodukte
  -> Step 2_4 10m-Formation und Statusmatrix
  -> Step 7_1 Varianten-Mastertabelle
  -> Step 7_0 kompakte Haupt-Mastertabelle
```

Auf Horeka ist jede Array-Aufgabe eine vollstaendige, isolierte Variantenkette
von Step 2_0 bis Step 2_4. Eine fehlgeschlagene Stufe beendet nur diese Variante;
andere Varianten laufen weiter. Bei einem erneuten `add_new_ids`-Submit werden
aktuelle Stufen uebersprungen und vorhandene Chunk-Checkpoints aus Step 2_1 und
Step 2_4 fortgesetzt. Dadurch kann derselbe Submit nach einem Zeitlimit sicher
wiederholt werden. Lokal wird die Parallelitaet durch
`local_max_parallel_variants` begrenzt.

## Ausgaben

Alle variantenbezogenen Dateien liegen unter:

```text
outputs/step_2_variants/<suffix>/step_2_0/
outputs/step_2_variants/<suffix>/step_2_1/
outputs/step_2_variants/<suffix>/step_2_1_susi_compatible/
outputs/step_2_variants/<suffix>/step_2_2/
outputs/step_2_variants/<suffix>/step_2_3/
outputs/step_2_variants/<suffix>/step_2_4_susi_10m/
```

Zentrale Produkte:

```text
outputs/step_2_variants/variant_index.json
outputs/Bio_O_Ton_Formation_Variants.csv
outputs/Bio_O_Ton_Formation_Variants.parquet
outputs/Bio_O_Ton_Formation_Variants_summary.json
```

Die Varianten-Mastertabelle hat genau eine Zeile pro
`dawn_chorus_id` und `lrt_variant`. Sie enthaelt 100m-/10m-Majority,
Conservation Status, Majority-Werte, Disputed-Flags, die Statuswerte aller
Step-2-Stufen und maschinenlesbare Issue-Codes. Eine Variante gilt nur dann als
vollstaendig, wenn alle fuenf Stufen einen gueltigen State und ihre erwarteten
Ausgaben besitzen.

## Inkrementelles Verhalten

Jede Variante besitzt eigene States und Checkpoints. Eine geaenderte
Eingangsdatei invalidiert nur ihren Zweig. Neue Recording-IDs erfordern nur
Step 2_2 und das anschliessende Mastertable-Update, solange die raeumlichen
Produkte unveraendert sind. `from_scratch` uebergibt `--force`; Step 2_1 und
Step 2_4 koennen nach einem Zeitlimit an ihren Chunk-Checkpoints fortsetzen.

## Start

Horeka:

```bash
bash submit_step2_variants_horeka.sh add_new_ids
bash submit_step2_variants_horeka.sh from_scratch
```

Empfohlener inkrementeller Start auf Horeka:

```bash
BIOOTON_STEP2_VARIANT_CONCURRENCY=2 \
BIOOTON_STEP2_VARIANT_CPUS=16 \
BIOOTON_STEP2_VARIANT_MEMORY=64G \
BIOOTON_STEP2_VARIANT_TIME=24:00:00 \
bash submit_step2_variants_horeka.sh add_new_ids
```

Wenn Array-Aufgaben ihr Zeitlimit erreichen, nach Abschluss des nachgeschalteten
Master- und Unlock-Jobs denselben Befehl erneut ausfuehren. `from_scratch` ist
fuer diese iterative Fortsetzung nicht geeignet, weil es bewusst `--force`
uebergibt.

Lokal:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts_local_run\run_step2_variants_local.ps1 -Mode add_new_ids -SkipEnvironmentSetup
```

Der Variantenlauf darf nicht gleichzeitig mit einem anderen schreibenden
Pipeline-Lauf ausgefuehrt werden.
