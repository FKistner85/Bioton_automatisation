"""Small real run-plan migration tests for both local and HoreKa planners."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tools')]
import Step_1_metadata_extraction as step1
import plan_pipeline_run as planner


def _run_test_plan(tmp_path, policy_committed=False):
    src = pd.DataFrame({
        'id':[1,2,3], 'country':['Germany']*3, 'lat':[49.]*3,'lng':[8.]*3,
        'datetime':['2020-05-08T23:30:00Z','2020-05-08T20:21:00Z','2020-05-08T03:57:00Z'],
        'localtimes':['','','2020-05-08T05:57:00+02:00'],
    })
    source=tmp_path/'source.csv';src.to_csv(source,index=False)
    previous = step1.build_fingerprints(src, legacy_fallback=True)
    if policy_committed:
        previous = step1.build_fingerprints(src)
    fingerprints=tmp_path/'fingerprints.csv';previous.to_csv(fingerprints,index=False)
    pd.DataFrame({'id':[1,2,3], 'datetime':['2020-05-08T05:57:00+02:00']*3}).to_csv(tmp_path/'dawnchorus_metadata_clean.csv',index=False)
    pd.DataFrame({'id':[1,2,3], 'datetime_source':['datetime','datetime','localtimes']}).to_csv(tmp_path/'dawnchorus_metadata_log.csv',index=False)
    # Old-master sample: summertime old UTC -> local +2 hours; first crosses midnight,
    # while another stays on the same day, and the trusted third stays unchanged.
    m = pd.DataFrame({'dawn_chorus_id':['1','2','3'],
       'datetime_local':['2020-05-09 01:30:00','2020-05-08 22:21:00','2020-05-08 05:57:00'],
       'datetime_utc':['2020-05-08T23:30:00Z','2020-05-08T20:21:00Z','2020-05-08T03:57:00Z'],
       'date_local':['2020-05-09','2020-05-08','2020-05-08'],
       'lat':[49.]*3,'lon':[8.]*3})
    master=tmp_path/'master.csv';m.to_csv(master,index=False)
    point=tmp_path/'points.csv';pd.DataFrame({'id':[1,2,3], 'lat':[49.]*3,'lon':[8.]*3}).to_csv(point,index=False)
    cfg={
       'dawn_chorus_csv':str(source),'status_dir':str(tmp_path),
       'metadata_extraction':{'timezone':'Europe/Berlin','fingerprint_csv':str(fingerprints)},
       'master_table':{'output_csv':str(master)},
       'point_lrt_assignment':{'output_csv':str(point)},
       'pipeline_control':{'run_plan_dir':str(tmp_path/'plans')},
       'local_runtime':{'hostrada_execution':'horeka_only'},
    }
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg),encoding='utf-8')
    args=SimpleNamespace(config=config, mode='add_new_ids',run_id='migration')
    with patch.object(planner,'parse_args',return_value=args),\
         patch.object(planner,'step20_needed',return_value=(False,[])),\
         patch.object(planner,'step21_needed',return_value=(False,[])),\
         patch.object(planner,'step23_needed',return_value=(False,[])),\
         patch.object(planner,'step24_needed',return_value=(False,[])),\
         patch.object(planner,'inventory_baseline_ready',return_value=True),\
         patch.object(planner,'point_output_gaps',return_value=set()):
        assert planner.main()==0
    plan=json.loads((tmp_path/'plans'/'migration'/'run_plan.json').read_text())
    return plan, tmp_path/'plans'/'migration'


def test_timefix_scopes_point_weather_sentinel(tmp_path):
    plan,root=_run_test_plan(tmp_path)
    assert plan['id_counts']['metadata']==2
    assert plan['id_counts']['point_assignment']==0
    assert plan['id_counts']['weather_stale']==1
    assert plan['id_counts']['sentinel']==0  # UTC date did not change for the first case
    assert '1' in pd.read_csv(root/'weather_stale_ids.csv')['dawn_chorus_id'].astype(str).tolist()


def test_timefix_after_interrupted_step1_fingerprint_write(tmp_path):
    plan,root=_run_test_plan(tmp_path,policy_committed=True)
    assert plan['id_counts']['metadata']==0
    assert plan['id_counts']['weather_stale']==1
    assert plan['id_counts']['point_assignment']==0
