"""Regression diagnostic: incomplete point outputs must be retried after metadata succeeds."""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'scripts')]
import plan_pipeline_run as planner

results = {}
with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    status = root/'status'
    status.mkdir()
    for name in ['dawnchorus_metadata_clean.csv','dawnchorus_metadata_log.csv']:
        (status/name).write_text('id\n1\n2\n')
    source = root/'dawn.csv'
    source.write_text('id\n1\n2\n')
    previous = root/'previous.csv'
    previous.write_text('dawn_chorus_id\n1\n2\n')
    point = root/'points.csv'
    point.write_text('id,lat,lon\n1,50,8\n')
    config = {'dawn_chorus_csv':str(source), 'status_dir':str(status),
              'metadata_extraction':{'fingerprint_csv':str(previous)},
              'pipeline_control':{'run_plan_dir':str(root/'plans')},
              'point_lrt_assignment':{'output_csv':str(point)},
              'weather_inventory':{}, 'bioacoustics':{'enabled':False},'master_table':{}}
    fp = pd.DataFrame({'dawn_chorus_id':['1','2'], **{c:['same1','same2'] for c in ['source_fingerprint',*planner.FINGERPRINT_GROUPS]}})
    for case, prior in [('metadata_succeeded_point_incomplete',fp), ('genuinely_new_id',fp.iloc[:1])]:
        with (patch.object(planner,'parse_args',return_value=SimpleNamespace(config=root/'config.json',run_id=case,mode='add_new_ids')),
              patch.object(planner,'load_config',return_value=config),
              patch.object(planner,'read_source',return_value=pd.DataFrame({'dawn_chorus_id':['1','2']})),
              patch.object(planner,'build_fingerprints',return_value=fp),
              patch.object(planner,'read_previous_fingerprints',return_value=prior),
              patch.object(planner,'read_master',return_value=pd.DataFrame()),
              patch.object(planner,'step20_needed',return_value=(False,[])),
              patch.object(planner,'step21_needed',return_value=(False,[])),
              patch.object(planner,'step23_needed',return_value=(False,[])),
              patch.object(planner,'step24_needed',return_value=(False,[]))):
            assert planner.main() == 0
        plan = json.loads((root/'plans'/case/'run_plan.json').read_text())
        results[case] = {'missing_point_ids':['2'], 'planned_point_ids':plan['id_counts']['point_assignment'], 'step22':plan['steps']['step_2_2_point_assignment']}
        results[case]['step22'].pop('ids_file')
assert results['metadata_succeeded_point_incomplete']['step22']['run']
assert results['genuinely_new_id']['step22']['run']
out = ROOT/'output/lrt_audit_20260922/planner_reproduction.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
