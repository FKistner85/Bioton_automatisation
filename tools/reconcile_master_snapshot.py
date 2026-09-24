"""Prepare one auditable master from current inventories and complete spatial products.

Only writes inside output/master_reconciliation. Publication is a separate,
hash-checked transaction. No observed weather values are edited here.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import gc

import pandas as pd
import geopandas as gpd

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tools')]
import Step_7_0_update_master_table as master
import Step_7_1_update_formation_variant_table as variants
import Step_2_2_assign_points_to_lrt_grid as points
from common import attach_optional_grid_majority, utc_now_iso
from input_consistency import point_output_gaps, require_point_coverage
from step2_variants import discover_variants, configure_variant

LOCAL=Path('D:/BioOTon_local_workspace/outputs')
CACHE=Path('D:/BioOTon_local_workspace/lsdf_cache')
REMOTE=Path('L:/Data_automatisation_skripts/outputs')
OUT=ROOT/'output/master_reconciliation'
PREP=OUT/'prepared'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def snapshot(path, target, manifest):
    before=path.stat()
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,target)
    after=path.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),str(path)
    manifest[str(path)]={'sha256':sha(target),'size':after.st_size,'mtime_ns':after.st_mtime_ns}


def translate_config(value):
    if isinstance(value,dict): return {k:translate_config(v) for k,v in value.items()}
    if isinstance(value,list): return [translate_config(v) for v in value]
    if isinstance(value,str):
        prefix='/lsdf/kit/ipf/projects/Bio-O-Ton/'
        if value.startswith(prefix):
            relative=value[len(prefix):]
            outputs='Data_automatisation_skripts/outputs/'
            return str(LOCAL/relative[len(outputs):]) if relative.startswith(outputs) else str(CACHE/relative)
    return value


def main():
    PREP.mkdir(parents=True,exist_ok=True)
    manifest={}
    snapshots=OUT/'sources'
    for label,root in [('local',LOCAL),('lsdf',REMOTE)]:
        for name in ['Bio_O_Ton_Master.csv','Bio_O_Ton_Master.parquet','Bio_O_Ton_Master_summary.json']:
            snapshot(root/name,snapshots/label/name,manifest)
    local=pd.read_csv(snapshots/'local/Bio_O_Ton_Master.csv',dtype=str,keep_default_na=False)
    live=pd.read_csv(snapshots/'lsdf/Bio_O_Ton_Master.csv',dtype=str,keep_default_na=False)
    live=live.set_index('dawn_chorus_id').loc[local.dawn_chorus_id].reset_index()
    assert local.shape==live.shape and local.dawn_chorus_id.is_unique
    for c in ['dawn_chorus_id','lat','lon','datetime_local','datetime_utc','source_fingerprint']:
        pd.testing.assert_series_equal(local[c],live[c])
    cfg=translate_config(json.loads((ROOT/'config.horeka.json').read_text()))
    metadata_path=REMOTE/'step_1_metadata/dawnchorus_metadata_clean.csv'
    snapshot(metadata_path,snapshots/'metadata.csv',manifest)
    metadata=points.load_points(snapshots/'metadata.csv')
    assert set(metadata.id.astype(str))==set(live.dawn_chorus_id)
    meta_by=metadata.set_index(metadata.id.astype(str)).loc[live.dawn_chorus_id]
    for c in ['lat','lon']:
        assert pd.to_numeric(live[c]).reset_index(drop=True).eq(meta_by[c].reset_index(drop=True)).all()
    clocks=pd.to_datetime(metadata.datetime,format='mixed',utc=True).dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
    assert pd.Series(clocks.to_numpy(),index=metadata.id.astype(str)).loc[live.dawn_chorus_id].reset_index(drop=True).eq(pd.to_datetime(live.datetime_local)).all()
    cfg['point_lrt_assignment']['metadata_csv']=str(snapshots/'metadata.csv')
    discovered=discover_variants(cfg)
    assert len(discovered)==12
    primary=cfg['lrt_variants']['primary_suffix']
    point_report={}
    spatial_configs={}
    # Stage all Step-2.2 products. Existing checked rows are reused; only gaps
    # are spatially evaluated. Removed non-German/source IDs are not retained.
    current_ids=set(metadata.id.astype(int))
    for variant in discovered:
        c=configure_variant(cfg,variant)
        s=c['point_lrt_assignment']
        gaps=point_output_gaps(metadata,s['output_csv'],s['log_csv'])
        target=PREP/Path(s['output_csv']).relative_to(LOCAL).parent
        target.mkdir(parents=True,exist_ok=True)
        staged_output=target/Path(s['output_csv']).name
        staged_log=target/Path(s['log_csv']).name
        resume_valid=(staged_output.is_file() and staged_log.is_file()
                      and (target/Path(s['matches_csv']).name).is_file()
                      and not point_output_gaps(metadata,staged_output,staged_log))
        for key in ['output_csv','matches_csv','log_csv']:
            origin=Path(s[key]); destination=target/origin.name
            snapshot(origin,snapshots/'points'/variant.suffix/origin.name,manifest)
            if not resume_valid:
                frame=pd.read_csv(origin,low_memory=False)
                frame=frame.loc[pd.to_numeric(frame.id,errors='coerce').isin(current_ids)]
                frame=frame.loc[~frame.id.astype(str).isin(gaps)]
                frame.to_csv(destination,index=False)
            s[key]=str(destination)
        if gaps and not resume_valid:
            selected=metadata.loc[metadata.id.astype(str).isin(gaps)].copy()
            projected=points.build_point_geodataframe(selected,'EPSG:3035')
            grid=master.read_grid_at_points(s['grid_gpkg'],s['grid_layer'],s['grid_id_column'],projected)
            majority=pd.read_csv(s['grid_majority_csv'],low_memory=False)
            grid=attach_optional_grid_majority(grid,majority,s['grid_id_column'])
            assigned=points.assign_points_to_grid(projected,grid,s['grid_id_column'])
            lrt=points.load_lrt(Path(s['lrt_gpkg']),s['lrt_layer'],projected.crs)
            matches=points.assign_points_to_lrt(assigned.loc[assigned[s['grid_id_column']].notna()],lrt)
            fresh=points.build_outputs(selected,assigned,matches,s['grid_id_column'])
            for key,new in zip(['output_csv','matches_csv','log_csv'],fresh):
                old=pd.read_csv(s[key],low_memory=False)
                pd.concat([old,new],ignore_index=True).to_csv(s[key],index=False)
            del lrt,grid,majority,assigned,projected
            gc.collect()
        # Grid IDs are variant-independent and already independently checked
        # in the local baseline. Fill legacy formation-filtered products once.
        grid_ids=local.set_index('dawn_chorus_id').grid_100m_id.replace('',pd.NA)
        for key in ['output_csv','log_csv']:
            frame=pd.read_csv(s[key],low_memory=False)
            mapped=frame.id.astype(str).map(grid_ids)
            existing=frame[s['grid_id_column']].astype('string')
            assert (existing.isna() | existing.eq(mapped).fillna(False)).all()
            frame[s['grid_id_column']]=existing.fillna(mapped)
            frame.to_csv(s[key],index=False)
        require_point_coverage(metadata,c)
        point_report[variant.suffix]={'recalculated_ids':len(gaps),'rows':len(pd.read_csv(s['output_csv'],usecols=['id']))}
        spatial_configs[variant.suffix]=c
        print('POINTS',variant.suffix,point_report[variant.suffix],flush=True)
    base=live[['dawn_chorus_id','lat','lon']].copy()
    spatial=master.add_10m_formation(master.add_100m_formation(base,spatial_configs[primary]),spatial_configs[primary])
    fields=[c for c in spatial if c in live and c not in ['dawn_chorus_id','lat','lon']]
    result=live.copy()
    aligned=spatial.set_index('dawn_chorus_id').loc[live.dawn_chorus_id]
    for c in fields:
        result[c]=aligned[c].map(lambda v:'' if pd.isna(v) else str(v)).to_numpy()
        if c=='lrt_codes': result[c]=result[c].str.replace(r'(?<=\d)\.0(?=$|\|)','',regex=True)
        # Retain lexical values where numbers are equivalent.
        if c.endswith('_count') or c.startswith(('majority_value_','second_value_','majority_delta_')):
            same=pd.to_numeric(local[c],errors='coerce').eq(pd.to_numeric(result[c],errors='coerce'))
            result.loc[same,c]=local.loc[same,c]
    for c in ['grid_100m_id','grid_10m_id','grid_100m_has_majority_formation','inside_lrt_polygon','grid_10m_has_majority_formation','majority_formation_100m','majority_formation_10m']:
        assert result[c].eq(local[c]).all(),c
    # Read using the established master schema, including nullable booleans.
    typed=pd.read_parquet(snapshots/'lsdf/Bio_O_Ton_Master.parquet')
    typed=typed.set_index(typed.dawn_chorus_id.astype(str)).loc[result.dawn_chorus_id].reset_index(drop=True)
    for c in fields:
        if pd.api.types.is_bool_dtype(typed[c].dtype): typed[c]=result[c].map({'True':True,'False':False}).astype(typed[c].dtype)
        elif pd.api.types.is_numeric_dtype(typed[c].dtype): typed[c]=pd.to_numeric(result[c],errors='coerce').astype(typed[c].dtype)
        else: typed[c]=result[c].replace('',None)
    typed=master.add_agreement_and_ready_flags(typed)
    typed['dawn_chorus_id']=typed.dawn_chorus_id.astype('string')
    variant_parts=[]
    vmeta=variants.load_metadata(cfg)
    context=typed[[c for c in variants.RECORDING_CONTEXT_COLUMNS if c in typed]].copy()
    wall_times=pd.to_datetime(typed.datetime_local,errors='raise')
    context['recording_year']=wall_times.dt.year.astype('Int64')
    context['recording_month']=wall_times.dt.month.astype('Int64')
    for variant in discovered:
        part=OUT/'variant_parts'/f'{variant.suffix}.parquet'
        part.parent.mkdir(exist_ok=True)
        rows=variants.build_variant_rows(vmeta,context,spatial_configs[variant.suffix],variant.suffix,primary,
              Path('/lsdf/kit/ipf/projects/Bio-O-Ton/Biodiversity_data/Bundeslander/All_Bundeslander')/variant.source_gpkg.name)
        rows.to_parquet(part,index=False,compression='zstd')
        variant_parts.append(rows)
        print('VARIANT',variant.suffix,len(rows),flush=True)
    combined=pd.concat(variant_parts,ignore_index=True)
    assert len(combined)==len(live)*12
    combined.to_parquet(PREP/'Bio_O_Ton_Formation_Variants.parquet',index=False,compression='zstd')
    combined.to_csv(PREP/'Bio_O_Ton_Formation_Variants.csv',index=False)
    index={'variant_count':12,'primary_suffix':primary,'variants':[{'suffix':v.suffix} for v in discovered]}
    (PREP/'step_2_variants').mkdir(exist_ok=True)
    (PREP/'step_2_variants/variant_index.json').write_text(json.dumps(index,indent=2))
    cfg['lrt_variants'].update(master_parquet=str(PREP/'Bio_O_Ton_Formation_Variants.parquet'),index_json=str(PREP/'step_2_variants/variant_index.json'))
    typed=master.add_formation_variant_status(typed,cfg)
    typed=master.add_agreement_and_ready_flags(typed)
    now=utc_now_iso()
    typed['record_updated_in_mastertable_utc']=now
    typed['workflow_run_id']='master_reconciliation_20260924'
    # Preserve the local first-registration date for already known recordings.
    typed['record_added_to_mastertable_utc']=local.record_added_to_mastertable_utc.replace('',None)
    typed=typed[live.columns]
    typed.to_parquet(PREP/'Bio_O_Ton_Master.parquet',index=False,compression='zstd')
    typed.to_csv(PREP/'Bio_O_Ton_Master.csv',index=False)
    saved=pd.read_csv(PREP/'Bio_O_Ton_Master.csv',dtype=str,keep_default_na=False)
    preserved=[c for c in live if c.startswith(('sound_','photo_','sentinel_','weather_','bioacoustic_'))]
    for c in preserved:
        a=live[c]; b=saved[c]
        assert (a.eq(b)|(pd.to_numeric(a,errors='coerce').eq(pd.to_numeric(b,errors='coerce')))).all(),c
    for c in ['datetime_local','datetime_utc','lat','lon']:
        assert saved[c].eq(live[c]).all(),c
    summary=json.loads((snapshots/'lsdf/Bio_O_Ton_Master_summary.json').read_text())
    summary.update(created_utc=now,workflow_run_id='master_reconciliation_20260924',rows=len(saved),rows_updated=len(saved))
    summary.update({c:int(typed[c].fillna(False).sum()) for c in typed if c.startswith('ready_for_')})
    summary['record_status_counts']=typed.record_status.value_counts().to_dict()
    summary['release_status_counts']=typed.release_status.value_counts().to_dict()
    (PREP/'Bio_O_Ton_Master_summary.json').write_text(json.dumps(summary,indent=2))
    report={'rows':len(saved),'columns':len(saved.columns),'primary':primary,'points':point_report,
            'counts':{c:int(typed[c].fillna(False).sum()) for c in ['grid_100m_has_majority_formation','inside_lrt_polygon','grid_10m_has_majority_formation','weather_point_has_issues']},
            'weather_codes':saved.weather_point_issue_codes.value_counts().to_dict(),'variant_rows':len(combined),
            'preserved_live_domain_columns':preserved,'source_manifest':manifest,'master_sha256':sha(PREP/'Bio_O_Ton_Master.csv')}
    (OUT/'validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='source_manifest'},indent=2),flush=True)


if __name__=='__main__': main()
