"""Run one spatial stage for every configured variant inside one existing job."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from step2_variants import prepare, run_stage_all, STAGE_SCRIPTS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--stage',choices=STAGE_SCRIPTS,required=True)
    parser.add_argument('--ids-file',type=Path)
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    config=json.loads(args.config.read_text(encoding='utf-8-sig'))
    if config.get('lrt_variants',{}).get('input_dir'):
        _,variants=prepare(args.config)
        return run_stage_all(root,Path(sys.executable),variants,args.stage,
                             force=args.force,ids_file=args.ids_file,max_workers=1)
    command=[sys.executable,str(root/STAGE_SCRIPTS[args.stage]),'--config',str(args.config)]
    if args.force: command.append('--force')
    if args.ids_file and args.stage=='2_2': command.extend(['--ids-file',str(args.ids_file)])
    return subprocess.call(command,cwd=root)


if __name__=='__main__':
    raise SystemExit(main())
