"""Read-only comparison of staged weather repairs with today's LSDF files."""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import Step_5_1_Weather_inventory as inventory


def main():
    out=ROOT/'output/weather_deployment'
    out.mkdir(exist_ok=True)
    review=ROOT/'output/weather_review'
    manifest=pd.read_csv(review/'staged_repair_manifest.csv',dtype=str,keep_default_na=False)
    master=pd.read_csv(out/'current/Bio_O_Ton_Master.csv',dtype=str,keep_default_na=False).set_index('dawn_chorus_id')
    oldmaster=pd.read_csv(review/'snapshot/Bio_O_Ton_Master.csv',dtype=str,keep_default_na=False).set_index('dawn_chorus_id')
    assert master.index.is_unique
    assert master.loc[manifest.dawn_chorus_id,'datetime_local'].equals(oldmaster.loc[manifest.dawn_chorus_id,'datetime_local'])
    config=json.loads((ROOT/'config.horeka.json').read_text())
    cache=out/'current_weather'
    cache.mkdir(exist_ok=True)
    def check(row):
        ident=row['dawn_chorus_id']
        path=Path('L:/PointData/Weather/Hostrada')/f'weather_{ident}.csv'
        result={'dawn_chorus_id':ident,'original_sha256':row['source_sha256'],'staged_sha256':row['staged_sha256']}
        try:
            before=path.stat()
            content=path.read_bytes()
            after=path.stat()
            assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'File changed during read'
            digest=hashlib.sha256(content).hexdigest()
            result.update(current_sha256=digest,current_mtime_ns=after.st_mtime_ns)
            if digest==row['source_sha256']:
                result['comparison']='unchanged_original'
            elif digest==row['staged_sha256']:
                result['comparison']='already_staged_content'
            else:
                dest=cache/path.name
                dest.write_bytes(content)
                qc=inventory.inspect_weather_csv(dest,master.loc[ident,'datetime_local'],config['weather_inventory'],config['weather_download'])
                result.update(comparison='changed_since_audit',current_codes=qc['issues'],current_rows=qc['row_count'],current_time_ok=qc['datetime_interval_ok'])
        except Exception as exc:
            result.update(comparison='read_error',error=f'{type(exc).__name__}: {exc}')
        return result
    results=[]
    with (out/'preflight.jsonl').open('w',encoding='utf-8') as log, ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(check,row) for row in manifest.to_dict('records')]
        for n,future in enumerate(as_completed(futures),1):
            result=future.result()
            results.append(result)
            log.write(json.dumps(result)+'\n')
            log.flush()
            if n%500==0: print(f'Compared {n}/{len(manifest)}',flush=True)
    frame=pd.DataFrame(results)
    frame.to_csv(out/'preflight.csv',index=False)
    summary={'counts':frame.comparison.value_counts().to_dict(),'lsdf_modified':False,'lock_owner':json.loads((out/'current/pipeline_lock_owner.json').read_text())}
    (out/'preflight_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
