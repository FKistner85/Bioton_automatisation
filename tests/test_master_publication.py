"""Publication must back up old bytes and roll back a partially committed run."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import publish_reconciled_master as publisher


class PublicationTest(unittest.TestCase):
    def run_publication(self, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local, remote, out = (root / name for name in ('local', 'remote', 'report'))
            for folder in (local, remote, out):
                folder.mkdir()
            source = out / 'new.csv'
            source.write_bytes(b'id,value\n1,new\n')
            entries = []
            for folder in (local, remote):
                destination = folder / 'Bio_O_Ton_Master.csv'
                destination.write_bytes(b'id,value\n1,old\n')
                entries.append(dict(source=str(source), destination=str(destination),
                                    before_sha256=publisher.sha(destination),
                                    after_sha256=publisher.sha(source)))
            (out / 'publish_plan.json').write_text(json.dumps({'files': entries}))
            original_replace = Path.replace

            def replace(path, target):
                if fail and path.parent == remote and path.suffix == '.tmp':
                    raise OSError('simulated commit failure')
                return original_replace(path, target)

            with patch.multiple(publisher, LOCAL=local, REMOTE=remote, OUT=out), patch.object(Path, 'replace', replace):
                if fail:
                    with self.assertRaisesRegex(OSError, 'simulated'):
                        publisher.apply()
                else:
                    publisher.apply()
            report = json.loads((out / 'publish_result.json').read_text())
            self.assertTrue(report['locks_released'])
            for folder in (local, remote):
                self.assertFalse((folder / 'step_0_control/pipeline.lock').exists())
                expected = b'id,value\n1,old\n' if fail else source.read_bytes()
                self.assertEqual((folder / 'Bio_O_Ton_Master.csv').read_bytes(), expected)
                if not fail:
                    backups = list((folder / 'backups').rglob('Bio_O_Ton_Master.csv'))
                    self.assertEqual(len(backups), 1)
                    self.assertEqual(backups[0].read_bytes(), b'id,value\n1,old\n')
            self.assertEqual(report['status'], 'failed' if fail else 'complete')
            if fail:
                self.assertTrue(report['rollback_complete'])

    def test_verified_publication_keeps_backup(self):
        self.run_publication()

    def test_commit_failure_restores_both_roots(self):
        self.run_publication(fail=True)


if __name__ == '__main__':
    unittest.main()
