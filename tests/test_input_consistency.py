"""Regression cases for interrupted metadata/assignment runs and truncated input."""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tools')]
from input_consistency import guard_source_population, point_output_gaps, require_point_coverage
import plan_pipeline_run as planner
import Step_7_0_update_master_table as master


def test_restart_and_coordinate_edits():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        points = pd.DataFrame({'id':[1,2,3], 'lat':[50,51,52], 'lon':[8,9,10]})
        out = root/'points.csv'
        pd.DataFrame({'id':[1,2], 'lat':[50,50], 'lon':[8,9],
                      'inside_lrt_polygon':[False,True]}).to_csv(out,index=False)
        assert point_output_gaps(points,out) == {'2','3'}
        cfg = {'point_lrt_assignment':{'output_csv':str(out)}}
        require_point_coverage(points.iloc[:1],cfg)  # legitimate negative result
        try:
            require_point_coverage(points,cfg)
        except ValueError as exc:
            assert 'POINT_ASSIGNMENT_INCOMPLETE' in str(exc)
        else:
            raise AssertionError('Incomplete assignment accepted')
        points.to_csv(out,index=False)
        assert not point_output_gaps(points,out)


def test_source_reduction_guard():
    guard_source_population(range(99),range(100))  # genuine individual deletion
    try:
        guard_source_population([1],range(111866))
    except ValueError as exc:
        assert 'SOURCE_POPULATION_REDUCED' in str(exc)
    else:
        raise AssertionError('Truncated source accepted')
    guard_source_population([1],range(100),{'allow_large_source_reduction':True})


def test_planner_retries_after_metadata_was_committed():
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw)
        source=pd.DataFrame({'id':[1,2], 'dawn_chorus_id':['1','2'],
                            'lat':[50,51], 'lng':[8,9]})
        for name in ['dawn.csv','previous.csv','dawnchorus_metadata_clean.csv','dawnchorus_metadata_log.csv']:
            source.to_csv(root/name,index=False)
        source.iloc[:1].rename(columns={'lng':'lon'}).to_csv(root/'points.csv',index=False)
        cfg={'dawn_chorus_csv':str(root/'dawn.csv'),'status_dir':str(root),
             'metadata_extraction':{'fingerprint_csv':str(root/'previous.csv')},
             'pipeline_control':{'run_plan_dir':str(root/'plans')},
             'point_lrt_assignment':{'output_csv':str(root/'points.csv')},
             'weather_inventory':{},'bioacoustics':{'enabled':False},'master_table':{}}
        fp=pd.DataFrame({'dawn_chorus_id':['1','2'], **{c:['a','b'] for c in ['source_fingerprint',*planner.FINGERPRINT_GROUPS]}})
        with (patch.object(planner,'parse_args',return_value=SimpleNamespace(config=root/'config.json',run_id='restart',mode='add_new_ids')),
              patch.object(planner,'load_config',return_value=cfg),
              patch.object(planner,'read_source',return_value=source),
              patch.object(planner,'build_fingerprints',return_value=fp),
              patch.object(planner,'read_previous_fingerprints',return_value=fp),
              patch.object(planner,'read_master',return_value=source[['dawn_chorus_id']]),
              patch.object(planner,'step20_needed',return_value=(False,[])),
              patch.object(planner,'step21_needed',return_value=(False,[])),
              patch.object(planner,'step23_needed',return_value=(False,[])),
              patch.object(planner,'step24_needed',return_value=(False,[]))):
            assert planner.main()==0
        plan=json.loads((root/'plans/restart/run_plan.json').read_text())
        assert plan['id_counts']['metadata']==0
        assert plan['id_counts']['point_assignment']==1
        assert plan['steps']['step_2_2_point_assignment']['run']
        ids=pd.read_csv(plan['id_files']['point_assignment'])
        assert ids.iloc[0,0]==2


def test_master_does_not_overwrite_when_spatial_input_missing():
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw)
        dest=root/'Bio_O_Ton_Master.csv'
        original=b'dawn_chorus_id,inside_lrt_polygon\n1,True\n'
        dest.write_bytes(original)
        cfg={'master_table':{'output_csv':str(dest),'output_parquet':str(root/'master.parquet'),
                            'summary_json':str(root/'summary.json')},
             'point_lrt_assignment':{'output_csv':str(root/'absent.csv')}}
        args=SimpleNamespace(config=root/'config.json',ids_file=None,preserve_existing_nonformation_domains=False)
        base=pd.DataFrame({'dawn_chorus_id':['1'],'lat':[50.0],'lon':[8.0]})
        with (patch.object(master,'parse_args',return_value=args),
              patch.object(master,'load_config',return_value=cfg),
              patch.object(master,'build_base_table',return_value=base)):
            assert master.main()==1
        assert dest.read_bytes()==original
        assert not (root/'master.parquet').exists()


if __name__=='__main__':
    for name,value in list(globals().items()):
        if name.startswith('test_'):
            value()
            print(name+': OK')
