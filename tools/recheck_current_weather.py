"""Complete today's read-only weather review using already checked fresh copies."""
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
    original=ROOT/'output/weather_review'
    master=pd.read_csv(out/'current/Bio_O_Ton_Master.csv',dtype=str,keep_default_na=False).set_index('dawn_chorus_id')
    selected=pd.read_csv(original/'weather_checks.csv',dtype=str,keep_default_na=False)
    preflight=pd.read_csv(out/'preflight.csv',dtype=str,keep_default_na=False).set_index('dawn_chorus_id')
    config=json.loads((ROOT/'config.horeka.json').read_text())
    directory=Path('L:/PointData/Weather/Hostrada')
    cache=out/'current_weather'
    cache.mkdir(exist_ok=True)
    def check(ident):
        path=directory/f'weather_{ident}.csv'
        local=cache/path.name
        try:
            if ident in preflight.index and local.is_file():
                content=local.read_bytes()
                digest=hashlib.sha256(content).hexdigest()
                assert digest==preflight.loc[ident,'current_sha256']
                mtime=int(preflight.loc[ident,'current_mtime_ns'])
            else:
                before=path.stat()
                content=path.read_bytes()
                after=path.stat()
                assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
                local.write_bytes(content)
                digest=hashlib.sha256(content).hexdigest()
                mtime=after.st_mtime_ns
            result=inventory.inspect_weather_csv(local,master.loc[ident,'datetime_local'],config['weather_inventory'],config['weather_download'])
            result.update(path='/lsdf/kit/ipf/projects/Bio-O-Ton/PointData/Weather/Hostrada/'+path.name,mtime_ns=mtime,sha256=digest)
        except FileNotFoundError:
            if not directory.is_dir(): raise RuntimeError('LSDF directory unavailable')
            result=inventory.missing_row(ident,config['weather_inventory'])
        result['dawn_chorus_id']=ident
        result['old_master_codes']=master.loc[ident,'weather_point_issue_codes']
        return result
    rows=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(check,ident) for ident in selected.dawn_chorus_id]
        for n,future in enumerate(as_completed(futures),1):
            rows.append(future.result())
            if n%1000==0: print(f'Checked {n}/{len(selected)}',flush=True)
    frame=pd.DataFrame(rows)
    frame.to_csv(out/'current_weather_checks.csv',index=False)
    summary={'reviewed':len(frame),'issue_combinations':frame.issues.value_counts().to_dict(),
             'current_issue_rows':int(frame.has_issues.astype(str).str.lower().eq('true').sum()),
             'old_master_issue_rows':int(frame.old_master_codes.ne('').sum()),'lsdf_modified':False}
    (out/'current_review_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
