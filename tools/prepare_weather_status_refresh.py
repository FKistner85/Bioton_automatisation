"""Prepare a narrow inventory/master refresh locally; no LSDF writes."""
from pathlib import Path
import hashlib
import json
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import Step_5_1_Weather_inventory as inventory
import Step_7_0_update_master_table as master
from common import utc_now_iso

DERIVED=['weather_point_status','ready_for_general_analysis','ready_for_formation_analysis_100m',
         'ready_for_direct_lrt_analysis','ready_for_formation_weather_raster_analysis_100m',
         'ready_for_formation_analysis_10m','ready_for_multimodal_analysis',
         'record_blocking_issue_codes','record_status','release_status']
WEATHER=['weather_point_exists','weather_point_has_issues','weather_point_issue_codes']


def refresh(raw, checks):
    """Keep lexical source values outside weather and its derived fields."""
    if not raw.dawn_chorus_id.is_unique or not checks.dawn_chorus_id.is_unique:
        raise ValueError('Duplicate IDs')
    if not set(checks.dawn_chorus_id).issubset(set(raw.dawn_chorus_id)):
        raise ValueError('Unknown review IDs')
    result=raw.copy().set_index('dawn_chorus_id',drop=False)
    byid=checks.set_index('dawn_chorus_id')
    for source,target in [('weather_exists',WEATHER[0]),('has_issues',WEATHER[1]),('issues',WEATHER[2])]:
        result.loc[byid.index,target]=byid[source]
    changed=result[WEATHER].ne(raw.set_index('dawn_chorus_id')[WEATHER]).any(axis=1)
    ids=result.index[changed]
    calc=result.loc[ids].copy().replace('',pd.NA)
    for column in calc:
        values=set(raw[column].dropna().unique())
        if values.issubset({'True','False',''}) and values & {'True','False'}:
            calc[column]=calc[column].map({'True':True,'False':False}).astype('boolean')
    if len(calc):
        calc=master.add_agreement_and_ready_flags(calc)
        for column in DERIVED:
            result.loc[ids,column]=calc[column].map(lambda value: '' if pd.isna(value) else str(value))
        result.loc[ids,'record_updated_in_mastertable_utc']=utc_now_iso()
    result=result.reset_index(drop=True)
    untouched=[c for c in raw if c not in WEATHER+DERIVED+['record_updated_in_mastertable_utc']]
    pd.testing.assert_frame_equal(result[untouched],raw[untouched])
    pd.testing.assert_frame_equal(result.loc[~changed.to_numpy()],raw.loc[~changed.to_numpy()])
    return result,ids.tolist()


def main():
    out=ROOT/'output/weather_deployment'
    old=ROOT/'output/weather_review/snapshot'
    prepared=out/'prepared'
    prepared.mkdir(exist_ok=True)
    checks=pd.read_csv(out/'current_weather_checks.csv',dtype=str,keep_default_na=False)
    raw=pd.read_csv(out/'current/Bio_O_Ton_Master.csv',dtype=str,keep_default_na=False)
    result,changed=refresh(raw,checks)
    result.to_csv(prepared/'Bio_O_Ton_Master.csv',index=False)
    # Preserve the established Parquet schema and every unrelated column.
    typed=pd.read_parquet(out/'current/Bio_O_Ton_Master.parquet')
    assert typed.dawn_chorus_id.astype(str).tolist()==raw.dawn_chorus_id.tolist()
    for column in WEATHER+DERIVED+['record_updated_in_mastertable_utc']:
        if pd.api.types.is_bool_dtype(typed[column].dtype):
            typed[column]=result[column].map({'True':True,'False':False}).astype(typed[column].dtype)
        else:
            typed[column]=result[column].replace('',None)
    typed.to_parquet(prepared/'Bio_O_Ton_Master.parquet',index=False,compression='zstd')
    unchanged=[c for c in typed if c not in WEATHER+DERIVED+['record_updated_in_mastertable_utc']]
    pd.testing.assert_frame_equal(pd.read_parquet(prepared/'Bio_O_Ton_Master.parquet')[unchanged],
                                  pd.read_parquet(out/'current/Bio_O_Ton_Master.parquet')[unchanged])
    for name,key in [('inventory_detailed.csv','detailed'),('inventory_compact.csv','compact')]:
        frame=pd.read_csv(old/name,dtype=str,keep_default_na=False)
        replacements=checks[inventory.DETAIL_COLUMNS] if key=='detailed' else inventory.compact_from_detail(checks)
        merged=pd.concat([frame.loc[~frame.dawn_chorus_id.isin(checks.dawn_chorus_id)],replacements],ignore_index=True)
        assert merged.dawn_chorus_id.is_unique and set(merged.dawn_chorus_id)==set(frame.dawn_chorus_id)
        merged=merged.sort_values('dawn_chorus_id')
        merged.to_csv(prepared/f'weather_inventory_{key}.csv',index=False)
    compact=pd.read_csv(prepared/'weather_inventory_compact.csv',dtype=str,keep_default_na=False)
    state=json.loads((old/'inventory_state.json').read_text())
    state.update(finished_utc=utc_now_iso(),partial_revalidation=True,reviewed_ids=len(checks),
                 weather_files_found=int(compact.weather_exists.str.lower().eq('true').sum()),
                 weather_files_revalidated=int(checks.weather_exists.str.lower().eq('true').sum()),
                 weather_files_reused=int(compact.weather_exists.str.lower().eq('true').sum())-int(checks.weather_exists.str.lower().eq('true').sum()),
                 ids_with_issues=int(compact.weather_has_issues.str.lower().eq('true').sum()),
                 ids_missing_weather_file=int(compact.weather_exists.str.lower().ne('true').sum()))
    (prepared/'state.json').write_text(json.dumps(state,indent=2))
    summary=json.loads((out/'current/Bio_O_Ton_Master_summary.json').read_text())
    summary.update(created_utc=utc_now_iso(),workflow_run_id='local_weather_refresh_20260924',
                   rows_updated=len(changed),incremental_update=True,ids_file='',
                   record_status_counts=result.record_status.value_counts().to_dict(),
                   release_status_counts=result.release_status.value_counts().to_dict())
    for column in result:
        if column.startswith('ready_for_'):
            summary[column]=int(result[column].str.lower().eq('true').sum())
    (prepared/'Bio_O_Ton_Master_summary.json').write_text(json.dumps(summary,indent=2))
    cells=[]
    for column in WEATHER+DERIVED+['record_updated_in_mastertable_utc']:
        mask=result[column].ne(raw[column])
        cells.extend({'dawn_chorus_id':row,'field':column,'previous_value':before,'current_value':after}
                     for row,before,after in zip(raw.loc[mask,'dawn_chorus_id'],raw.loc[mask,column],result.loc[mask,column]))
    pd.DataFrame(cells).to_csv(out/'master_change_log.csv',index=False)
    validation={'rows':len(result),'columns':len(result.columns),'weather_flags_before':int(raw.weather_point_has_issues.eq('True').sum()),
                'weather_flags_after':int(result.weather_point_has_issues.eq('True').sum()),'changed_rows':len(changed),
                'unrelated_columns_identical':True,'unreviewed_rows_identical':True,'lsdf_modified':False,
                'prepared_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in prepared.iterdir()}}
    (out/'prepared_validation.json').write_text(json.dumps(validation,indent=2))
    print(json.dumps(validation,indent=2))


if __name__=='__main__':
    main()
