"""HoreKa regressions: rerun stale weather windows, never all weather by force."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "submit_bio_o_ton_horeka.sh"


def test_horeka_scheduler_is_valid_shell():
    bash = shutil.which("bash")
    if bash:
        subprocess.run([bash, "-n", str(SCRIPT)], check=True)


def test_horeka_stale_weather_is_scoped_forced_and_serialized():
    body = SCRIPT.read_text(encoding="utf-8")
    assert 'weather_stale_ids="$(plan_ids weather_stale)"' in body
    assert 'if (( weather_stale_count > 0 )); then' in body
    assert '"${weather_stale_ids}" --force)' in body
    assert '"$(afterok_jobs "${j1}" "${j51post}")"' in body
    assert '"${j52staleverify}")" scripts/Step_5_1_Weather_inventory.py --ids-file "${weather_stale_ids}"' in body
    assert 'submit_master_update weather_timefix "${j51stalepost}" "${weather_stale_ids}"' in body
    # Never silently change the regular all-problem-weather job into --force.
    assert '"${weather_ids}" "${force_args[@]}")' in body
