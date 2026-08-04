# Step 2 Variants - LRT Sensitivity Analysis

All `All_Bundeslander_*.gpkg` files are processed as isolated variants. The
suffix following `All_Bundeslander_` is the stable variant identifier, and no
variant overwrites another one.

Each branch executes Steps 2_0 through 2_4 and writes to
`outputs/step_2_variants/<suffix>/`. The configured primary variant is
`no_K_post2017_threshold_50`; its fields feed the compact ID-level master
table. Step 7_1 additionally writes
`outputs/Bio_O_Ton_Formation_Variants.parquet` and CSV with one row per
`dawn_chorus_id` and `lrt_variant` for sensitivity comparisons.

Horeka uses one Slurm array task per variant and stage. Stage barriers use
`afterany`, so a failed variant produces an explicit downstream error instead
of leaving `DependencyNeverSatisfied` jobs behind:

```bash
bash submit_step2_variants_horeka.sh add_new_ids
bash submit_step2_variants_horeka.sh from_scratch
```

Local execution uses the same Python steps and isolated configuration files:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts_local_run\run_step2_variants_local.ps1 -Mode add_new_ids -SkipEnvironmentSetup
```

States and checkpoints are variant-specific. A changed source only invalidates
its own branch. Do not run this workflow concurrently with another pipeline
writer.
