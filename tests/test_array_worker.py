"""Bounded workers must retain every logical task and propagate failures/signals."""
import signal
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_array_worker as worker


class WorkerTests(unittest.TestCase):
    def test_submission_arrays_keep_logical_task_counts(self):
        bash = Path("C:/Program Files/Git/bin/bash.exe")
        executable = str(bash) if bash.exists() else shutil.which("bash")
        if not executable:
            self.skipTest("Bash unavailable")
        source = (ROOT / "submit_bio_o_ton_horeka.sh").read_text()
        names = ["submit_bacpipe_array", "submit_hostrada_raster_array", "apply_override", "dry_run_submit"]
        if "apply_job_time() {" in source:
            names.append("apply_job_time")
        functions = "\n".join(re.search(r"^" + name + r"\(\) \{.*?^\}", source, re.M | re.S).group() for name in names)
        setup = """
set -euo pipefail
PYTHON=python BACPIPE_PYTHON=bacpython PIPELINE_DIR=/repo CONFIG=/config
BIOACOUSTICS_WORKERS=4 HOSTRADA_WORKERS=2 HOSTRADA_RASTER_MAX_CONCURRENT=2
BIOACOUSTICS_PARTITION=cpuonly PARTITION=cpuonly BIOACOUSTICS_CPUS=4
HOSTRADA_RASTER_CPUS=8 HOSTRADA_RASTER_MEMORY=32G BIOACOUSTICS_MEMORY=24G
RUN_ID=test LOGDIR=/logs LOG_STAMP=now TIME_OVERRIDE=''
account_args=() bio_resource_args=()
sbatch() { printf '%s\\n' "$@"; }
"""
        calls = """
submit_bacpipe_array bio_step62 embeddings 12:00:00 afterok:123 scripts/Step_6_2_generate_bioacoustic_embeddings.py 384 4 --force
submit_hostrada_raster_array 12:00:00 afterany:456 73 --force
"""
        for dry_run in (0, 1):
            result = subprocess.run([executable, "-c", setup + functions + f"\nSLURM_DRY_RUN={dry_run}\n" + calls], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = result.stdout + result.stderr
            self.assertIn("0-3%4", output)
            self.assertIn("0-1%2", output)
            self.assertIn("run_array_worker.py", output)
            if not dry_run:
                self.assertIn("--task-count '384'", output)
                self.assertIn("--task-count '73'", output)
                self.assertIn("--dependency=afterok:123", output)
                self.assertIn("--dependency=afterany:456", output)
                self.assertIn("--force", output)
        # Even an overlarge worker setting must not submit empty workers.
        result = subprocess.run([executable, "-c", setup + functions + "\nSLURM_DRY_RUN=0\nsubmit_hostrada_raster_array 12:00:00 '' 1"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--array=0-0%2", result.stdout)

    def test_coverage(self):
        for tasks, workers in [(384, 4), (73, 2), (1, 4), (11, 3)]:
            assigned = [i for w in range(workers) for i in worker.task_indices(w, workers, tasks)]
            self.assertEqual(sorted(assigned), list(range(tasks)))
        for values in [(0, 0, 4), (-1, 4, 8), (4, 4, 8), (0, 4, 0)]:
            with self.assertRaises(ValueError):
                worker.task_indices(*values)

    def test_real_children_continue_after_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            log = Path(raw) / "tasks.txt"
            command = [sys.executable, "-c", (
                "import sys; from pathlib import Path; "
                f"p=Path({str(log)!r}); "
                "i=int(sys.argv[-1]); "
                "p.open('a').write(str(i)+'\\n'); sys.exit(1 if i==2 else 0)"
            )]
            self.assertEqual(worker.run_worker(0, 2, 7, command), 1)
            self.assertEqual(worker.run_worker(1, 2, 7, command), 0)
            self.assertEqual(sorted(map(int, log.read_text().split())), list(range(7)))

    def test_signal_forwarding_stops_dispatch_and_restores_handler(self):
        sig = getattr(signal, "SIGUSR1", signal.SIGTERM)
        original = signal.getsignal(sig)
        with patch.object(worker.subprocess, "Popen") as spawn:
            child = spawn.return_value
            child.poll.return_value = None
            def interrupted_wait():
                signal.getsignal(sig)(sig, None)
                return 0
            child.wait.side_effect = interrupted_wait
            self.assertEqual(worker.run_worker(0, 4, 384, ["fake"]), 128 + sig)
            self.assertEqual(spawn.call_count, 1)
            child.send_signal.assert_called_once_with(sig)
        self.assertEqual(signal.getsignal(sig), original)


if __name__ == "__main__":
    unittest.main()
