"""Boundary trimming must preserve observations and reject missing/duplicate hours."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from stage_weather_window_repairs import trim_extra_boundary_rows


class WeatherRepairTests(unittest.TestCase):
    def test_extra_boundary_only_and_preserved_values(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source, target = root/'source.csv', root/'target.csv'
            times = pd.date_range('2025-03-19 23:00', '2025-03-30 23:00', tz='Europe/Berlin', freq='h').tz_localize(None)
            pd.DataFrame({'datetime': times, 'value': ['1.23000']*len(times)}).to_csv(source,index=False)
            self.assertEqual(trim_extra_boundary_rows(source,target,'2025-03-30 06:00'),1)
            with target.open(newline='') as f:
                rows=list(csv.reader(f))
            self.assertEqual(len(rows)-1,263)
            self.assertTrue(all(r[1]=='1.23000' for r in rows[1:]))

    def test_missing_or_duplicate_is_not_fixed(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            times=pd.date_range('2025-10-16','2025-10-27',tz='Europe/Berlin',freq='h',inclusive='left').tz_localize(None)
            for broken in (times.delete(5), times.insert(0,times[0])):
                pd.DataFrame({'datetime':broken,'value':1}).to_csv(root/'source.csv',index=False)
                with self.assertRaises(ValueError):
                    trim_extra_boundary_rows(root/'source.csv',root/'target.csv','2025-10-26 06:00')
                self.assertFalse((root/'target.csv').exists())


if __name__=='__main__':
    unittest.main()
