# Susi vs. HoreKa: Aenderungsuebersicht LRT/Grid/10m

Stand: 2026-07-23

Verglichene Susi-Dateien:

- `C:/Users/Frede/OneDrive/Documents/1_cleanLRTs.py`
- `C:/Users/Frede/OneDrive/Documents/1_cleanLRTs_public.py`
- `C:/Users/Frede/OneDrive/Documents/2_mergeLRTand100mgrid.py`
- `C:/Users/Frede/OneDrive/Documents/3_10mgrid_prep3.py`
- `C:/Users/Frede/OneDrive/Documents/Step_2_0_clean_lrts.py`

Verglichene HoreKa-Gegenstuecke:

- `outputs/scripts_horeka/scripts/Step_2_0_clean_lrts.py`
- `outputs/scripts_horeka/scripts/Step_2_1_merge_lrts_and_grid.py`
- `outputs/scripts_horeka/scripts/Step_2_4_generate_susi_10m_products.py`
- `outputs/scripts_horeka/scripts/Step_2_5_clean_public_lrts.py`
- `outputs/scripts_horeka/scripts/Step_2_6_merge_public_lrts_and_grid.py`

## Kurzfazit

Die Formation-Definition ist im aktuellen HoreKa-`Step_2_0_clean_lrts.py` fachlich synchron mit Susis neuer Definition. Die Susi-kompatiblen 100m- und 10m-Matrixwriter in HoreKa wurden danach auf die README-Spalten `majority_value`, `second_value`, `majority_delta`, `majority_disputed`, `n_formations` und `n_lrts` vereinheitlicht.

Der urspruenglich kritischste Unterschied lag im 10m-Schritt: Susis neuer `3_10mgrid_prep3.py` nutzt fuer `majority_disputed` die korrekt skalierte Schwelle `<= 200`, waehrend HoreKa-`Step_2_4_generate_susi_10m_products.py` vorher noch `<= 2.0` nutzte. Das ist umgesetzt: HoreKa nutzt jetzt ebenfalls `majority_delta <= 200`.

Zusaetzlich erzeugt HoreKa die neuen README-Spalten jetzt direkt in jedem 10m-Chunk. Der finale 10m-Merge richtet weiter am 100m-Referenzschema aus, behaelt aber Extra-Spalten aus den 10m-Parts bei, falls ein altes Referenzschema noch nicht alle neuen Spalten enthaelt.

## Schrittvergleich

| Thema | Susi-Skript | HoreKa-Skript | Status | Unterschied / Kommentar |
|---|---|---|---|---|
| LRT reinigen privat | `1_cleanLRTs.py` und `Step_2_0_clean_lrts.py` | `Step_2_0_clean_lrts.py` | Gleich/aehnlich | Formation-Definition stimmt ueberein. HoreKa ist robuster: Config, mehrere Inputs, Fingerprints, State-Datei, Force-Modus, kontrollierte Parallelisierung. |
| LRT reinigen public | `1_cleanLRTs_public.py` | `Step_2_5_clean_public_lrts.py` | Gleich/aehnlich | Public-Logik nutzt dieselbe Formation-Funktion via Import aus Step 2_0. HoreKa schreibt in `outputs/step_2_5_public_lrt`, nicht direkt in `InspireGrid/Vector_Data`. |
| 100m Grid x LRT | `2_mergeLRTand100mgrid.py` | `Step_2_1_merge_lrts_and_grid.py` | Gleich/aehnlich, HoreKa erweitert | Beide berechnen Schnittflaechen und Susi-kompatible Matrix. HoreKa nutzt Checkpoints, Config, processed-Ordner, Zusatzdiagnostik und schreibt zusaetzlich Notebook-/Majority-Produkte. |
| 100m Susi-Matrix | `2_mergeLRTand100mgrid.py` | `write_susi_compatible_100m_products()` in Step 2_1 | Synchronisiert nach README | Beide speichern Werte skaliert: 10000 = 100.00 Prozent. Beide entfernen Formation-Status `_K`, behalten LRT `_K`, setzen `Permanent Glaciers_C = 0`, berechnen `majority_disputed` mit `<= 200` und schreiben die neuen README-Spalten direkt. |
| 10m Grid/Matrices | `3_10mgrid_prep3.py` | `Step_2_4_generate_susi_10m_products.py` | Synchronisiert nach README | Susi verarbeitet vorhandene `Data/ix_chunks/ix_part_*.csv`; HoreKa baut 10m-Zellen aus 100m-IDs, overlayt gegen `lrt.gpkg`, checkpointet Parts und merged final. Die Matrixspaltenlogik ist jetzt dieselbe wie bei 100m. |
| Public 100m Susi-Produkte | kein direktes neues Susi-Gegenstueck ausser public LRT | `Step_2_6_merge_public_lrts_and_grid.py` | Nur HoreKa | HoreKa erzeugt public Susi-kompatible 100m-Produkte als eigene QA-/Vergleichsschicht. |

## Neue Susi-Spalten und aktueller HoreKa-Stand

| Spalte / Muster | Bedeutung laut Susi | 100m HoreKa Step 2_1 | 10m HoreKa Step 2_4 | Kommentar |
|---|---|---:|---:|---|
| `grid_id` | 100m Zell-ID | Ja | Nein, dort `grid_id_10` | 10m nutzt absichtlich `grid_id_10`; beim Schema-Merge wird 100m-`grid_id` zu `grid_id_10` umbenannt. |
| `<Formation>` | Gesamtanteil Formation | Ja | Ja | Skaliert: 10000 = 100.00 Prozent. |
| `<Formation>_A/B/C` | Formation x Status | Ja | Ja | `_K` wird auf Formationsebene entfernt. |
| `Majority_formation` | Formation mit groesstem Anteil | Ja | Ja | Definition synchron. |
| `majority_formation_status` | haeufigster Status innerhalb Majority-Formation | Ja | Ja | HoreKa sortiert bei Tie zusaetzlich nach Status alphabetisch; Susi sortiert im neuen 10m-Code nur nach Wert. |
| `majority_value` | Anteil der Top-Formation | Ja | Ja | Skaliert: 10000 = 100.00 Prozent. |
| `second_value` | Anteil der zweitgroessten Formation | Ja | Ja | Skaliert: 10000 = 100.00 Prozent. |
| `majority_delta` | Differenz Top1 - Top2 | Ja | Ja | Skaliert: 100 = 1 Prozentpunkt. |
| `majority_disputed` | `majority_delta <= 200` | Ja | Ja | Entspricht maximal 2 Prozentpunkten Differenz. |
| `n_formations` | Anzahl Formationen > 0 | Ja | Ja | Wird aus den Formation-Totalspalten berechnet. |
| `<LRT code>_A/B/C/K` | LRT x Status | Ja | Ja | LRT `_K` bleibt erhalten. |
| `n_lrts` | Anzahl LRT-Codes > 0 | Ja | Ja | Wird aus den LRT-Code-Statusspalten berechnet. |

## Formation-Definition

Die aktuelle Definition in Susi und HoreKa ist fachlich gleich:

- `1340` und `7xxx` -> `Bogs`
- `8340` -> `Permanent Glaciers`
- `2180` und `9xxx` -> `Forests`
- `2310`, `2320`, `4xxx`, `5xxx` -> `Temperate heath`
- `2330` und `6xxx` -> `Grassland`
- `3xxx` -> `Freshwater`
- `8xxx` ausser `8340` -> `Rocky habitats`
- sonstige `1xxx`/`2xxx` -> `Costal`
- Rest -> `Other`

Hinweis: Der Label-String ist weiterhin `Costal`, nicht `Coastal`. Das ist in beiden Ansaetzen gleich und sollte nur geaendert werden, wenn downstream bewusst ein neues Label akzeptiert.

## Output-Orte

Susis Skripte schreiben teils direkt in:

- `/lsdf/kit/ipf/projects/Bio-O-Ton/InspireGrid/Vector_Data/lrt.gpkg`
- `/lsdf/kit/ipf/projects/Bio-O-Ton/InspireGrid/Vector_Data/lrt_public.gpkg`
- `/lsdf/kit/ipf/projects/Bio-O-Ton/InspireGrid/Vector_Data/Formation_Status_Grid_withLRTCode.parquet`
- lokale Arbeitsordner wie `Data/ix.csv`, `Data/ix_chunks`, `Data/parquet_10`, `Figures/`

HoreKa schreibt pipeline-konform in:

- `/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_2_0/lrt.gpkg`
- `/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_2_1_susi_compatible/Formation_Status_Grid_withLRTCode.parquet`
- `/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_2_4_susi_10m/Formation_Status_10m_Grid_withLRTCode.parquet`
- `/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_2_5_public_lrt/lrt_public.gpkg`
- `/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/step_2_6_public_susi_compatible/...`

Das ist gewollt und entspricht deiner Regel: generierte Pipeline-Dateien bleiben im `processed`-Baum.

## Umgesetzte Code-Anpassungen

1. `Step_2_4_generate_susi_10m_products.py`: `majority_disputed` nutzt jetzt `majority_delta <= 200`.
2. `Step_2_4_generate_susi_10m_products.py`: `majority_value`, `second_value`, `majority_delta`, `n_formations`, `n_lrts` werden direkt im 10m-Chunk erzeugt.
3. `Step_2_1_merge_lrts_and_grid.py`: Susi-kompatible 100m-Matrix erzeugt dieselben README-Spalten explizit.
4. `tools/sanity_check_susi_compatibility.py`: Spaltenexistenz, Datentypen und Skalierung werden fuer 100m und 10m geprueft:
   - `max(<Formation>) <= 10000`
   - `majority_delta <= 10000`
   - `majority_disputed == (majority_delta <= 200)`
   - `n_formations` entspricht Anzahl Formation-Totalspalten mit Wert > 0
   - `n_lrts` entspricht Anzahl LRT-Codes mit mindestens einem Statuswert > 0

## Fachlich kritisch

Der 10m-Schritt war der wichtigste Punkt, weil ein falscher disputed-Schwellenwert direkt die Interpretation der "knappen" Majority-Entscheidungen veraendert. Das ist jetzt korrigiert. Beim naechsten HoreKa-Lauf sorgt die neue Matrix-Schema-Version dafuer, dass alte Step-2_1-/Step-2_4-/Step-2_6-Outputs mit altem Schema nicht still wiederverwendet werden.
