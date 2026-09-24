"""Read-only comparison of user-provided master snapshots."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'lrt_audit_20260922'
OUT.mkdir(parents=True, exist_ok=True)
a, b = [pd.read_csv(Path('C:/Users/Frede/OneDrive/Documents') / n, low_memory=False).set_index('dawn_chorus_id', verify_integrity=True) for n in ['Bio_O_Ton_Master.csv', 'Bio_O_Ton_Master_neu.csv']]
common = a.index.intersection(b.index)
x, y = a.loc[common], b.loc[common]
summary = {'rows_old':len(a), 'rows_new':len(b), 'removed_ids':a.index.difference(b.index).tolist(), 'added_count':len(b.index.difference(a.index))}
summary['changed_columns'] = {c:int((x[c].fillna('<NA>').astype(str) != y[c].fillna('<NA>').astype(str)).sum()) for c in x}
summary['changed_columns'] = {k:v for k,v in summary['changed_columns'].items() if v}
flags=['grid_100m_has_majority_formation','inside_lrt_polygon','grid_10m_has_majority_formation']
for c in flags:
 lost=common[x[c].eq(True)&~y[c].eq(True)]
 gained=common[~x[c].eq(True)&y[c].eq(True)]
 summary[c]={'old':int(a[c].sum()),'new':int(b[c].sum()),'lost_existing':len(lost),'gained_existing':len(gained),'added_positive':int(b.loc[b.index.difference(a.index),c].sum())}
 cols=['lat','lon','grid_100m_id','grid_10m_id',*flags,'majority_formation_100m','majority_formation_10m','lrt_codes','lrt_mapping_years','datetime_local','metadata_status','sound_status','ready_for_formation_analysis_100m','workflow_run_id']
 d=x.loc[lost,cols].add_suffix('_old').join(y.loc[lost,cols].add_suffix('_new'))
 d.to_csv(OUT/f'{c}_lost.csv')
 summary[c]['lost_coordinate_changes']=int(((x.loc[lost,'lat']!=y.loc[lost,'lat']) | (x.loc[lost,'lon']!=y.loc[lost,'lon'])).sum())
 summary[c]['lost_grid_changes']=int((x.loc[lost,'grid_100m_id']!=y.loc[lost,'grid_100m_id']).sum())
 summary[c]['lost_unique_100m_cells']=int(x.loc[lost,'grid_100m_id'].nunique())
 summary[c]['lost_metadata_status']=y.loc[lost,'metadata_status'].value_counts(dropna=False).to_dict()
summary['new_workflows']=b.workflow_run_id.value_counts(dropna=False).to_dict()
(OUT/'summary.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')
print(json.dumps(summary,indent=2,default=str))
