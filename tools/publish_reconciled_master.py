"""Prepare/apply a backed-up two-root publication of the reconciled snapshot."""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from reconcile_master_snapshot import ROOT, OUT, PREP, LOCAL, REMOTE, sha
sys.path.insert(0,str(ROOT/'scripts'))
import Step_7_0_update_master_table as master


def prepare():
    validation=json.loads((OUT/'validation.json').read_text())
    result=pd.read_parquet(PREP/'Bio_O_Ton_Master.parquet')
    config=json.loads((ROOT/'config.horeka.json').read_text())
    # Reuse the complete index metadata, correcting the current primary variant.
    index=json.loads((REMOTE/'step_2_variants/variant_index.json').read_text())
    index['primary_suffix']=validation['primary']
    for item in index['variants']:
        item['is_primary']=item['suffix']==validation['primary']
    (PREP/'step_2_variants/variant_index.json').write_text(json.dumps(index,indent=2))
    var=pd.read_parquet(PREP/'Bio_O_Ton_Formation_Variants.parquet')
    if var.recording_year.isna().any() or var.recording_month.isna().any():
        wall_times=pd.to_datetime(var.datetime_local,errors='raise')
        var['recording_year']=wall_times.dt.year.astype('Int64')
        var['recording_month']=wall_times.dt.month.astype('Int64')
        var.to_parquet(PREP/'Bio_O_Ton_Formation_Variants.parquet',index=False,compression='zstd')
        var.to_csv(PREP/'Bio_O_Ton_Formation_Variants.csv',index=False)
    stats=var.groupby('lrt_variant').agg(
        source_gpkg=('source_gpkg','first'),
        is_primary=('lrt_variant_is_primary','first'),
        row_count=('dawn_chorus_id','count'),
        recording_count=('dawn_chorus_id','nunique'),
        complete_recording_count=('variant_complete_recording_count','first'),
        product_100m_exists=('variant_100m_product_exists','first'),
        product_10m_exists=('variant_10m_product_exists','first'),
        record_status=('variant_record_status','first'),
        majority_grid_100m_count=('variant_majority_grid_100m_count','first'),
        majority_grid_10m_count=('variant_majority_grid_10m_count','first'),
        lrt_polygon_count=('variant_lrt_polygon_count','first'),
        recordings_in_majority_grid_100m=('grid_100m_has_majority_formation','sum'),
        recordings_in_majority_grid_10m=('grid_10m_has_majority_formation','sum'),
        recordings_directly_in_lrt_polygon=('inside_lrt_polygon','sum'),
        recordings_100m_10m_agree=('formation_100m_10m_agree','sum'),
        recordings_general_ready=('ready_for_general_analysis','sum'),
        recordings_multimodal_ready=('ready_for_multimodal_analysis','sum'),
        recordings_bioacoustic_ready=('ready_for_bioacoustic_analysis','sum'),
    ).reset_index().rename(columns={'lrt_variant':'suffix'})
    stats.to_csv(PREP/'Bio_O_Ton_Variant_Summary.csv',index=False)
    var.groupby(['recording_year','lrt_variant']).agg(recording_count=('dawn_chorus_id','nunique'),
        recordings_in_majority_grid_100m=('grid_100m_has_majority_formation','sum'),
        recordings_in_majority_grid_10m=('grid_10m_has_majority_formation','sum'),
        recordings_directly_in_lrt_polygon=('inside_lrt_polygon','sum'),
        recordings_general_ready=('ready_for_general_analysis','sum')).reset_index().to_csv(
        PREP/'Bio_O_Ton_Variant_Temporal_Summary.csv',index=False)
    (PREP/'Bio_O_Ton_Formation_Variants_summary.json').write_text(json.dumps({
        'created_utc':datetime.now(timezone.utc).isoformat(),'primary_suffix':validation['primary'],
        'variant_count':12,'row_count':len(var),'recording_count':len(result),
        'complete_variant_products':int(var.groupby('lrt_variant').variant_10m_product_exists.all().sum()),
        'workflow_run_id':'master_reconciliation_20260924'},indent=2))
    events=PREP/'step_0_control/status_events.csv'
    events.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(REMOTE/'step_0_control/status_events.csv',events)
    event_config={'pipeline_control':{'status_event_csv':str(events)}}
    previous=pd.read_parquet(OUT/'sources/lsdf/Bio_O_Ton_Master.parquet')
    os.environ['BIOOTON_WORKFLOW_RUN_ID']='master_reconciliation_20260924'
    count=master.append_status_events(event_config,previous,result,datetime.now(timezone.utc).isoformat())
    summary=json.loads((PREP/'Bio_O_Ton_Master_summary.json').read_text())
    summary['status_events_written']=count
    (PREP/'Bio_O_Ton_Master_summary.json').write_text(json.dumps(summary,indent=2))
    files=[]
    def entry(source,destination):
        source=Path(source);destination=Path(destination)
        before=sha(destination) if destination.is_file() else None
        after=sha(source)
        if before==after:return
        files.append({'source':str(source),'destination':str(destination),
                      'before_sha256':before,'after_sha256':after})
        print('PREPARE',destination,flush=True)
    for source in sorted(PREP.rglob('*')):
        if not source.is_file():continue
        rel=source.relative_to(PREP)
        for root in [LOCAL,REMOTE]:entry(source,root/rel)
    # Keep local master inputs in step with the latest LSDF inventories.
    prefix='/lsdf/kit/ipf/projects/Bio-O-Ton/Data_automatisation_skripts/outputs/'
    inputs=set()
    for section in ['audio_inventory','photo_inventory','sentinel2_inventory','weather_inventory','sound_download','photo_download']:
        for key,value in config.get(section,{}).items():
            if key in {'compact_log','detailed_log','state_file','retry_log'} and isinstance(value,str) and value.startswith(prefix):
                inputs.add(value[len(prefix):])
    inputs.update('step_1_metadata/'+name for name in ['dawnchorus_metadata_clean.csv','dawnchorus_metadata_log.csv','metadata_source_fingerprints.csv'])
    for rel in sorted(inputs):
        source=REMOTE/rel
        if source.is_file():
            cached=OUT/'inventory_inputs'/rel
            cached.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,cached)
            entry(cached,LOCAL/rel)
    # Refuse replacing either baseline if it changed since reconciliation.
    for label,root in [('local',LOCAL),('lsdf',REMOTE)]:
        assert sha(root/'Bio_O_Ton_Master.csv')==sha(OUT/'sources'/label/'Bio_O_Ton_Master.csv')
    (OUT/'publish_plan.json').write_text(json.dumps({'files':files,'status_events_written':count},indent=2))
    print('Publication prepared:',len(files),'files',flush=True)


def apply():
    plan=json.loads((OUT/'publish_plan.json').read_text())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run='master_reconciliation_'+stamp
    locks=[]; staged=[]; applied=[]; complete=False; rollback_ok=True
    report={'run_id':run,'files':[],'weather_observations_written':0}
    try:
        for root in [LOCAL,REMOTE]:
            lock=root/'step_0_control/pipeline.lock'
            lock.mkdir(parents=True,exist_ok=False)
            (lock/'owner.json').write_text(json.dumps({'workflow_run_id':run,'pid':os.getpid(),'created_utc':stamp}))
            locks.append(lock)
        for item in plan['files']:
            source=Path(item['source']);dest=Path(item['destination'])
            root=next((r for r in [LOCAL,REMOTE] if dest.resolve().is_relative_to(r.resolve())),None)
            if root is None:raise ValueError('Destination outside authorized roots')
            if sha(source)!=item['after_sha256']:raise ValueError('Prepared source changed: '+str(source))
            old=sha(dest) if dest.is_file() else None
            if old!=item['before_sha256']:raise ValueError('Live file changed: '+str(dest))
            backup=root/'backups'/run/dest.relative_to(root)
            if old is not None:
                backup.parent.mkdir(parents=True,exist_ok=True)
            before_stat=dest.stat() if dest.exists() else None
            dest.parent.mkdir(parents=True,exist_ok=True)
            temp=dest.with_name(dest.name+'.'+run+'.tmp')
            shutil.copyfile(source,temp)
            if sha(temp)!=item['after_sha256']:raise ValueError('Staged upload failed')
            staged.append((item,dest,temp,backup,before_stat))
            print('STAGED',dest,flush=True)
        for item,dest,temp,backup,before_stat in staged:
            if before_stat is not None:
                current=dest.stat()
                if (current.st_size,current.st_mtime_ns)!=(before_stat.st_size,before_stat.st_mtime_ns):
                    raise ValueError('Concurrent output change: '+str(dest))
                # Same-filesystem rename retains the exact verified old bytes
                # without a round-trip of large LSDF files through the client.
                dest.replace(backup)
            elif dest.exists():
                raise ValueError('Concurrent new output: '+str(dest))
            applied.append((item,dest,backup))
            temp.replace(dest)
            if dest.name=='Bio_O_Ton_Master.csv' and sha(dest)!=item['after_sha256']:
                raise ValueError('Published master hash mismatch')
            report['files'].append({'path':str(dest),'sha256':item['after_sha256']})
            print('VERIFIED',dest,flush=True)
        complete=True
        report['status']='complete'
    except BaseException as exc:
        report.update(status='failed',error=str(exc))
        for item,dest,backup in reversed(applied):
            try:
                if item['before_sha256'] is None:dest.unlink()
                else:
                    backup.replace(dest)
                    assert sha(dest)==item['before_sha256']
            except Exception as error:
                rollback_ok=False;report.setdefault('rollback_errors',[]).append(str(error))
        report['rollback_complete']=rollback_ok
        raise
    finally:
        report['locks_released']=False
        if complete or rollback_ok:
            for lock in locks:
                if json.loads((lock/'owner.json').read_text())['workflow_run_id']==run:
                    (lock/'owner.json').unlink();lock.rmdir()
            report['locks_released']=True
        (OUT/'publish_result.json').write_text(json.dumps(report,indent=2))
    print('COMPLETE',run,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    apply() if parser.parse_args().apply else prepare()
