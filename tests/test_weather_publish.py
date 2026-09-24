"""Publication must back up old products and roll back a failed replacement."""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import publish_weather_status_refresh as publish


class PublishTests(unittest.TestCase):
    def run_case(self, fail_second):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            out=root/'local'
            remote=root/'remote'
            out.mkdir()
            (remote/'step_1_metadata').mkdir(parents=True)
            (remote/'step_1_metadata/dawnchorus_metadata_clean.csv').write_text('metadata')
            lock=remote/'step_0_control/pipeline.lock'
            lock.mkdir(parents=True)
            (lock/'owner.json').write_text(json.dumps({'workflow_run_id':publish.RETIRED}))
            files=[]
            for name in ['one.csv','two.csv']:
                (remote/name).write_text('old '+name)
                (out/name).write_text('new '+name)
                files.append({'local':str(out/name),'relative':name,'before_sha256':publish.digest(remote/name),'after_sha256':publish.digest(out/name)})
            plan={'files':files,'metadata_sha256':publish.digest(remote/'step_1_metadata/dawnchorus_metadata_clean.csv')}
            (out/'publish_plan.json').write_text(json.dumps(plan))
            pd.DataFrame(columns=['dawn_chorus_id','sha256']).to_csv(out/'current_weather_checks.csv',index=False)
            real_digest=publish.digest
            failed=False
            def checked_digest(path):
                nonlocal failed
                if fail_second and not failed and path==remote/'two.csv' and path.read_text()=='new two.csv':
                    failed=True
                    raise OSError('simulated readback failure')
                return real_digest(path)
            with patch.multiple(publish,OUT=out,REMOTE=remote), patch.object(publish,'digest',checked_digest), contextlib.redirect_stdout(io.StringIO()):
                if fail_second:
                    with self.assertRaises(OSError): publish.apply()
                else:
                    publish.apply()
            result=json.loads((out/'publish_result.json').read_text())
            self.assertTrue(result['lock_released'])
            self.assertFalse(lock.exists())
            backup=Path(result['backup_directory'])
            self.assertTrue((backup/'retired_pipeline.lock/owner.json').exists())
            for name in ['one.csv','two.csv']:
                self.assertEqual((backup/name).read_text(),'old '+name)
                self.assertEqual((remote/name).read_text(),('old ' if fail_second else 'new ')+name)
            self.assertEqual(result['status'],'failed' if fail_second else 'complete')
            if fail_second: self.assertTrue(result['rollback_complete'])

    def test_success_backs_up_and_releases_own_lock(self):
        self.run_case(False)

    def test_failed_readback_rolls_back_all_replacements(self):
        self.run_case(True)


if __name__=='__main__': unittest.main()
