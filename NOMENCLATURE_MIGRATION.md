# Nomenclature Migration

Stand: 2026-07-23

Ziel: Neue Skript- und Toolnamen beschreiben das fachliche Produkt
`formation_status` statt eine personenbezogene Herkunft wie `susi`.

## Neue Standardnamen

| Alter Name | Neuer Standardname | Status |
|---|---|---|
| `scripts/Step_2_4_generate_susi_10m_products.py` | `scripts/Step_2_4_generate_10m_formation_status_products.py` | Alter Name bleibt Wrapper |
| `tools/sanity_check_susi_compatibility.py` | `tools/compare_formation_status_products.py` | Alter Name bleibt Wrapper |
| `submit_bio_o_ton_horeka.sh susi_compare` | `submit_bio_o_ton_horeka.sh formation_compare` | Alter Mode bleibt Alias |

## Entfernte Shell-Aliase

Diese alten Shell-Dateien wurden entfernt, damit der HoreKa-Ordner nicht mehr
mehrere Einstiegspunkte fuer denselben Zweck enthaelt:

- `run_susi_sanity_check.sh`
- `slurm_compare_susi.sh`

Bitte stattdessen verwenden:

```bash
bash run_formation_status_comparison.sh
bash slurm_compare_formation_status.sh
```

## Noch bewusst vorhandene `susi`-Vorkommen

Diese Vorkommen bleiben vorerst, weil sie Output-Kompatibilitaet oder historische
Vergleichbarkeit sichern:

- Config-Keys wie `susi_10m_products` und `susi_compatible_outputs`
- Output-Ordner wie `outputs/step_2_1_susi_compatible`
- Output-Ordner wie `outputs/step_2_4_susi_10m`
- Doku/Audit-Dateien mit historischem Vergleichsbezug, z.B.
  `SUSI_HOREKA_AENDERUNGSUEBERSICHT_2026-07-23.md`

Empfehlung fuer eine spaetere Breaking-Change-Version:

- Config-Keys nach `formation_status_10m_products` und
  `formation_status_compatible_outputs` migrieren.
- Output-Ordner nur nach erfolgreichem Datensatzvergleich umbenennen.
- Alte Pfade fuer mindestens einen Release-Zyklus als Symlink oder
  Kompatibilitaetsalias erhalten.
