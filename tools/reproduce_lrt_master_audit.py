"""Reproduce spatial master fields without modifying source products."""
import json
import hashlib
import types
from unittest.mock import patch
import sys
from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import Step_7_0_update_master_table as master
import Step_2_2_assign_points_to_lrt_grid as assignment

OUT = ROOT / 'output/lrt_audit_20260922'
cfg = json.loads((ROOT / 'scripts_local_run/config.local.generated.json').read_text())
old = pd.read_csv('C:/Users/Frede/OneDrive/Documents/Bio_O_Ton_Master.csv', low_memory=False)
new = pd.read_csv('C:/Users/Frede/OneDrive/Documents/Bio_O_Ton_Master_neu.csv', low_memory=False)
base = new[['dawn_chorus_id', 'lat', 'lon']].copy()
base['dawn_chorus_id'] = base.dawn_chorus_id.astype('string')
report = {}
for label in ['local', 'lsdf']:
    test_cfg = json.loads(json.dumps(cfg))
    if label == 'lsdf':
        rel = Path('step_2_variants/no_K_post2017/step_2_2/DawnChorus_LRT_Grid_Assignment_no_K_post2017.csv')
        test_cfg['point_lrt_assignment']['output_csv'] = str(Path('L:/Data_automatisation_skripts/outputs') / rel)
    result = master.add_100m_formation(base.copy(), test_cfg)
    report[label] = {c:int(result[c].sum()) for c in ['grid_100m_has_majority_formation', 'inside_lrt_polygon']}
    for c in ['grid_100m_has_majority_formation', 'inside_lrt_polygon']:
        report[label][c+'_mismatches_new'] = int((result[c].fillna(False).astype(bool).to_numpy() != new[c].to_numpy()).sum())
    result.to_csv(OUT / f'reproduced_100m_{label}.csv', index=False)
    print(label, report[label], flush=True)

lost = pd.read_csv(OUT / 'inside_lrt_polygon_lost.csv')
points = pd.DataFrame({'id':lost.dawn_chorus_id, 'lat':lost.lat_old, 'lon':lost.lon_old})
geo = assignment.build_point_geodataframe(points, 'EPSG:3035')
lrt = assignment.load_lrt(Path(cfg['point_lrt_assignment']['lrt_gpkg']), 'lrt', geo.crs)
matches = gpd.sjoin(geo, lrt, how='inner', predicate='within')
report['independent_local_polygon_check'] = {'lost_ids':len(lost), 'matched_ids':int(matches.id.nunique()),'matched_rows':len(matches)}
matches.drop(columns='geometry').to_csv(OUT/'independent_polygon_matches.csv',index=False)
print(report['independent_local_polygon_check'], flush=True)
(OUT/'reproduction.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

# Execute the exact Step-7 source recorded in the Horeka manifest, with writes disabled.
remote_path = Path('L:/Data_automatisation_skripts/bio_o_ton_pipeline_git/scripts/Step_7_0_update_master_table.py')
source = remote_path.read_bytes()
recorded = json.loads(Path('L:/Data_automatisation_skripts/outputs/step_0_manifests/step_7_0_master_metadata/20260917T142802Z_5149869_f8402b47.json').read_text())
recorded_fp = next(f for f in recorded['input_fingerprints'] if f['path'].endswith('Step_7_0_update_master_table.py'))
assert hashlib.sha256(source).hexdigest() == recorded_fp['edge_sha256']
remote = types.ModuleType('horeka_master_audit')
remote.__file__ = str(ROOT/'scripts/Step_7_0_update_master_table.py')
exec(compile(source, str(remote_path), 'exec'), remote.__dict__)
result = remote.add_100m_formation(base.copy(), test_cfg)
lost10 = pd.read_csv(OUT/'grid_10m_has_majority_formation_lost.csv')
selected = result[result.dawn_chorus_id.isin(lost10.dawn_chorus_id.astype(str))].copy().reset_index(drop=True)
ids = remote.compute_10m_grid_ids(selected)
report['actual_horeka_code'] = {'sha256':hashlib.sha256(source).hexdigest(), 'matches_run_manifest':True, 'lost_10m_recordings':len(selected), 'cannot_compute_10m_id':int(ids.isna().sum()), 'missing_100m_ids_all':int(result.grid_100m_id.isna().sum())}
result.to_csv(OUT/'reproduced_100m_actual_horeka_code.csv',index=False)
local100 = pd.read_csv(OUT/'reproduced_100m_local.csv',dtype={'dawn_chorus_id':'string'})
local10 = master.add_10m_formation(local100, cfg)
report['local_full_spatial'] = {c:int(local10[c].sum()) for c in ['grid_100m_has_majority_formation','inside_lrt_polygon','grid_10m_has_majority_formation']}
indexed = local10.set_index('dawn_chorus_id')
for field in ['grid_100m_has_majority_formation','inside_lrt_polygon','grid_10m_has_majority_formation']:
    positives = old.loc[old[field], 'dawn_chorus_id'].astype(str)
    report['local_full_spatial'][field+'_old_positives_not_recovered'] = int((~indexed.loc[positives,field]).sum())
local10.to_csv(OUT/'reproduced_full_spatial_local.csv',index=False)
(OUT/'reproduction.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
