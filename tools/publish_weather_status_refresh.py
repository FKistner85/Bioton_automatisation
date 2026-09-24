"""Publish only reviewed weather status products after the old Slurm run is retired.

Never writes a weather observation CSV. Refuses changed source files, owns the
pipeline lock, backs up all replaced products, stages and verifies replacements.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import shutil
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/weather_deployment'
REVIEW=ROOT/'output/weather_review/snapshot'
REMOTE=Path('L:/Data_automatisation_skripts/outputs')
RETIRED='20260917T144747Z_jk3038_4104599'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest():
    entries=[
        ('weather_inventory_detailed.csv','step_5_1_weather_inventory/weather_inventory_detailed.csv',REVIEW/'inventory_detailed.csv'),
        ('weather_inventory_compact.csv','step_5_1_weather_inventory/weather_inventory_compact.csv',REVIEW/'inventory_compact.csv'),
        ('state.json','step_5_1_weather_inventory/state.json',REVIEW/'inventory_state.json'),
        ('Bio_O_Ton_Master.parquet','Bio_O_Ton_Master.parquet',OUT/'current/Bio_O_Ton_Master.parquet'),
        ('Bio_O_Ton_Master.csv','Bio_O_Ton_Master.csv',OUT/'current/Bio_O_Ton_Master.csv'),
        ('Bio_O_Ton_Master_summary.json','Bio_O_Ton_Master_summary.json',OUT/'current/Bio_O_Ton_Master_summary.json'),
        ('status_events.csv','step_0_control/status_events.csv',OUT/'current/status_events.csv'),
    ]
    return [{'local':str(OUT/'prepared'/name),'relative':relative,'before_sha256':digest(before),
             'after_sha256':digest(OUT/'prepared'/name)} for name,relative,before in entries]


def prepare_events():
    prepared=OUT/'prepared'
    source=OUT/'current/status_events.csv'
    target=prepared/'status_events.csv'
    shutil.copyfile(source,target)
    events=pd.read_csv(OUT/'master_change_log.csv',dtype=str,keep_default_na=False)
    events=events.loc[events.field.ne('record_updated_in_mastertable_utc')]
    with target.open('a',encoding='utf-8',newline='') as handle:
        writer=csv.writer(handle)
        now=datetime.now(timezone.utc).isoformat(timespec='seconds')
        for row in events.itertuples(index=False):
            writer.writerow([now,'local_weather_refresh_20260924',row.dawn_chorus_id,row.field,row.previous_value,row.current_value])
    summary=json.loads((prepared/'Bio_O_Ton_Master_summary.json').read_text())
    summary['status_events_written']=len(events)
    (prepared/'Bio_O_Ton_Master_summary.json').write_text(json.dumps(summary,indent=2))
    plan={'files':manifest(),'retired_run_id':RETIRED,'weather_observation_files_written':0,
          'metadata_sha256':digest(REVIEW/'metadata.csv')}
    (OUT/'publish_plan.json').write_text(json.dumps(plan,indent=2))
    validation=json.loads((OUT/'prepared_validation.json').read_text())
    validation['prepared_sha256']={Path(item['local']).name:item['after_sha256'] for item in plan['files']}
    (OUT/'prepared_validation.json').write_text(json.dumps(validation,indent=2))
    print(f'Prepared {len(plan["files"])} replacements and {len(events)} status events',flush=True)


def apply():
    plan=json.loads((OUT/'publish_plan.json').read_text())
    for item in plan['files']:
        if digest(Path(item['local']))!=item['after_sha256']:
            raise RuntimeError('Prepared file changed: '+item['local'])
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id=f'weather_refresh_{stamp}_{os.getpid()}'
    backup=REMOTE/'step_0_control'/'weather_refresh_backups'/run_id
    lock=REMOTE/'step_0_control'/'pipeline.lock'
    # Verify exact resolved directory targets before retiring a directory.
    if not lock.resolve().is_relative_to(REMOTE.resolve()) or not backup.resolve().is_relative_to(REMOTE.resolve()):
        raise ValueError('Lock/backup outside intended output tree')
    backup.mkdir(parents=True,exist_ok=False)
    if lock.exists():
        owner=json.loads((lock/'owner.json').read_text())
        if owner.get('workflow_run_id')!=RETIRED or {p.name for p in lock.iterdir()}!={'owner.json'}:
            raise RuntimeError('Unexpected active lock; do not retire it')
        # User confirmed these exact Slurm jobs were cancelled and squeue empty.
        lock.replace(backup/'retired_pipeline.lock')
    lock.mkdir(exist_ok=False)
    (lock/'owner.json').write_text(json.dumps({'workflow_run_id':run_id,'created_utc':stamp,
        'host':socket.gethostname(),'pid':os.getpid(),'user':os.environ.get('USERNAME','')}))
    applied=[]
    staged=[]
    completed=False
    rollback_ok=True
    result={'run_id':run_id,'backup_directory':str(backup),'weather_files_written':0,'files':[]}
    try:
        if digest(REMOTE/'step_1_metadata/dawnchorus_metadata_clean.csv')!=plan['metadata_sha256']:
            raise RuntimeError('Metadata changed since the review')
        checks=pd.read_csv(OUT/'current_weather_checks.csv',dtype=str,keep_default_na=False)
        def verify(row):
            path=Path('L:/PointData/Weather/Hostrada')/f'weather_{row["dawn_chorus_id"]}.csv'
            if digest(path)!=row['sha256']:
                raise RuntimeError('Weather file changed since review: '+str(path))
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures=[pool.submit(verify,row) for row in checks.to_dict('records')]
            for n,future in enumerate(as_completed(futures),1):
                future.result()
                if n%1000==0: print(f'Live weather hashes verified: {n}/{len(checks)}',flush=True)
        for item in plan['files']:
            destination=REMOTE/item['relative']
            before=destination.stat()
            payload=destination.read_bytes()
            after=destination.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or hashlib.sha256(payload).hexdigest()!=item['before_sha256']:
                raise RuntimeError('Live output changed: '+str(destination))
            saved=backup/item['relative']
            saved.parent.mkdir(parents=True,exist_ok=True)
            saved.write_bytes(payload)
            if digest(saved)!=item['before_sha256']: raise RuntimeError('Backup verification failed')
            temporary=destination.with_name(destination.name+'.'+run_id+'.tmp')
            shutil.copyfile(item['local'],temporary)
            if digest(temporary)!=item['after_sha256']: raise RuntimeError('Upload verification failed')
            staged.append((item,destination,temporary,before.st_size,before.st_mtime_ns))
            print('Backed up and staged: '+item['relative'],flush=True)
        for item,destination,temporary,size,mtime in staged:
            stat=destination.stat()
            if (stat.st_size,stat.st_mtime_ns)!=(size,mtime): raise RuntimeError('Concurrent output change')
            temporary.replace(destination)
            applied.append(item)
            if digest(destination)!=item['after_sha256']: raise RuntimeError('Published verification failed')
            result['files'].append({'relative':item['relative'],'sha256':item['after_sha256']})
            print('Published and verified: '+item['relative'],flush=True)
        completed=True
        result.update(status='complete',reviewed_weather_files=len(checks))
    except BaseException as exc:
        result.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        for item in reversed(applied):
            try:
                destination=REMOTE/item['relative']
                restore=destination.with_name(destination.name+'.'+run_id+'.restore')
                shutil.copyfile(backup/item['relative'],restore)
                restore.replace(destination)
                if digest(destination)!=item['before_sha256']: raise RuntimeError('Rollback hash mismatch')
            except Exception as restore_error:
                rollback_ok=False
                result.setdefault('rollback_errors',[]).append(str(restore_error))
        result['rollback_complete']=rollback_ok
        raise
    finally:
        result['lock_released']=False
        if completed or rollback_ok:
            owner=json.loads((lock/'owner.json').read_text())
            if owner.get('workflow_run_id')==run_id:
                (lock/'owner.json').unlink()
                lock.rmdir()
                result['lock_released']=True
        (OUT/'publish_result.json').write_text(json.dumps(result,indent=2))
        (backup/'publish_result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    apply() if args.apply else prepare_events()
