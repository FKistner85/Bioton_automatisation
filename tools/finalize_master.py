"""Publish final recording/variant status only after all domain jobs finished."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'scripts'))
    from pipeline_phase import execution_phase
    config=json.loads(args.config.read_text(encoding='utf-8-sig'))
    scripts=['Step_7_0_update_master_table.py']
    if execution_phase()!='bioacoustics' and config.get('lrt_variants',{}).get('input_dir'):
        scripts+=['Step_7_1_update_formation_variant_table.py','Step_7_0_update_master_table.py']
    for script in scripts:
        code=subprocess.call([sys.executable,str(root/'scripts'/script),'--config',str(args.config)],cwd=root)
        if code: return code
    return 0


if __name__=='__main__':
    raise SystemExit(main())
