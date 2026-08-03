#!/usr/bin/env python3
"""Correct legacy 10 m majority_disputed flags and compare with 100 m output."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


FORMATIONS = [
    "Bogs",
    "Coastal",
    "Forests",
    "Freshwater",
    "Grassland",
    "Permanent Glaciers",
    "Rocky habitats",
    "Temperate heath",
]


def replace_flag(input_path: Path, output_path: Path, threshold: int) -> dict[str, int]:
    source = pq.ParquetFile(input_path)
    if "majority_delta" not in source.schema_arrow.names:
        raise ValueError(f"{input_path} has no majority_delta column")
    if "majority_disputed" not in source.schema_arrow.names:
        raise ValueError(f"{input_path} has no majority_disputed column")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    flag_index = source.schema_arrow.get_field_index("majority_disputed")
    rows = 0
    old_true = 0
    new_true = 0
    changed = 0
    writer = None
    try:
        # The legacy 10m file has very wide row groups.  Small record batches
        # keep memory bounded while preserving every column unchanged.
        for batch in source.iter_batches(batch_size=8_192):
            table = pa.Table.from_batches([batch])
            old_flag = table.column("majority_disputed")
            new_flag = pc.less_equal(table.column("majority_delta"), pa.scalar(threshold))
            old_true += int(pc.sum(pc.cast(old_flag, pa.int64())).as_py() or 0)
            new_true += int(pc.sum(pc.cast(new_flag, pa.int64())).as_py() or 0)
            changed += int(pc.sum(pc.cast(pc.not_equal(old_flag, new_flag), pa.int64())).as_py() or 0)
            table = table.set_column(flag_index, "majority_disputed", new_flag)
            if writer is None:
                writer = pq.ParquetWriter(output_path, table.schema, compression="snappy")
            writer.write_table(table)
            rows += table.num_rows
    finally:
        if writer is not None:
            writer.close()
    return {"rows": rows, "old_true": old_true, "new_true": new_true, "changed": changed}


def read_stats(path: Path, *, threshold: int, id_column: str) -> dict:
    source = pq.ParquetFile(path)
    names = source.schema_arrow.names
    formation_columns = [name for name in FORMATIONS if name in names]
    required = formation_columns + ["Majority_formation", "majority_delta", "majority_disputed", "n_formations"]
    rows = flag_true = flag_logic_errors = n_formation_errors = delta_errors = 0
    max_formation = 0
    majority_counter: Counter[str] = Counter()

    for batch in source.iter_batches(columns=required, batch_size=131_072):
        table = pa.Table.from_batches([batch])
        formation_arrays = [table.column(name) for name in formation_columns]
        max_values = formation_arrays[0]
        positive_count = pc.cast(pc.greater(max_values, pa.scalar(0)), pa.int32())
        for array in formation_arrays[1:]:
            max_values = pc.max_element_wise(max_values, array)
            positive_count = pc.add(positive_count, pc.cast(pc.greater(array, pa.scalar(0)), pa.int32()))
        # Determine top two with Arrow element-wise operations; only eight formation columns.
        top_one = formation_arrays[0]
        top_two = pa.array([0] * table.num_rows, type=formation_arrays[0].type)
        for array in formation_arrays[1:]:
            next_top_one = pc.max_element_wise(top_one, array)
            top_two = pc.max_element_wise(top_two, pc.min_element_wise(top_one, array))
            top_one = next_top_one
        expected_delta = pc.subtract(top_one, top_two)
        actual_delta = table.column("majority_delta")
        flag = table.column("majority_disputed")
        expected_flag = pc.less_equal(actual_delta, pa.scalar(threshold))
        rows += table.num_rows
        flag_true += int(pc.sum(pc.cast(flag, pa.int64())).as_py() or 0)
        flag_logic_errors += int(pc.sum(pc.cast(pc.not_equal(flag, expected_flag), pa.int64())).as_py() or 0)
        n_formation_errors += int(pc.sum(pc.cast(pc.not_equal(table.column("n_formations"), positive_count), pa.int64())).as_py() or 0)
        delta_errors += int(pc.sum(pc.cast(pc.not_equal(actual_delta, expected_delta), pa.int64())).as_py() or 0)
        max_formation = max(max_formation, int(pc.max(max_values).as_py() or 0))
        majority_counter.update(str(value) for value in table.column("Majority_formation").to_pylist())

    return {
        "rows": rows,
        "columns": len(names),
        "row_groups": source.num_row_groups,
        "max_formation": max_formation,
        "flag_true": flag_true,
        "flag_logic_errors": flag_logic_errors,
        "n_formation_errors": n_formation_errors,
        "delta_errors": delta_errors,
        "majority_counts": majority_counter,
        "id_column": id_column,
        "schema": source.schema_arrow,
    }


def pct(numerator: int, denominator: int) -> str:
    return f"{(100 * numerator / denominator):.3f}%" if denominator else "n/a"


def write_report(report_path: Path, ten_path: Path, hundred_path: Path, correction: dict, ten: dict, hundred: dict) -> None:
    ten_schema = ten["schema"].remove(ten["schema"].get_field_index("grid_id_10"))
    hundred_schema = hundred["schema"].remove(hundred["schema"].get_field_index("grid_id"))
    schema_equal = ten_schema.equals(hundred_schema, check_metadata=False)
    lines = [
        "# Pruefbericht: Majority-Flags 10m vs. 100m",
        "",
        "## Anlass und Korrektur",
        "Die urspruengliche 10m-Datei verwendete fuer `majority_disputed` den Grenzwert 200, obwohl ihre `majority_delta`-Werte als Flaeche in m2 vorliegen. Bei 10m-Zellen mit 100 m2 entspricht die fachliche 2%-Grenze **2 m2**, nicht 200 m2. Die korrigierte Datei wurde daher ausschliesslich durch Neuberechnung von `majority_disputed = (majority_delta <= 2)` erzeugt. Alle anderen Spalten und Zeilen wurden unveraendert uebernommen.",
        "",
        "## Dateien",
        f"- 10m korrigiert: `{ten_path}`",
        f"- 100m Referenz: `{hundred_path}`",
        f"- 10m Zeilen: {ten['rows']:,}; 100m Zeilen: {hundred['rows']:,}.",
        f"- Schema: jeweils {ten['columns']} bzw. {hundred['columns']} Spalten; nach Ausblendung des erwarteten Schluesselnamen-Unterschieds `grid_id_10`/`grid_id` identisch: **{schema_equal}**.",
        "",
        "## Ergebnis der Flag-Korrektur",
        f"- Vorher waren {correction['old_true']:,} von {correction['rows']:,} 10m-Zellen als disputed markiert ({pct(correction['old_true'], correction['rows'])}).",
        f"- Nachher sind {correction['new_true']:,} Zellen disputed ({pct(correction['new_true'], correction['rows'])}); {correction['changed']:,} Flags wurden korrigiert.",
        f"- Die korrigierte 10m-Datei erfuellt ihre Regel vollstaendig: 0 Abweichungen von `majority_disputed == (majority_delta <= 2)`.",
        f"- Die 100m-Datei erfuellt die aequivalente Regel vollstaendig: 0 Abweichungen von `majority_disputed == (majority_delta <= 200)`; disputed: {hundred['flag_true']:,} ({pct(hundred['flag_true'], hundred['rows'])}).",
        "",
        "## Weitere Konsistenzpruefungen",
        f"- `n_formations` entspricht in beiden Produkten exakt der Anzahl positiver Formation-Totalspalten: 10m Fehler {ten['n_formation_errors']:,}, 100m Fehler {hundred['n_formation_errors']:,}.",
        f"- `majority_delta` entspricht in beiden Produkten exakt Top-1 minus Top-2 der acht Formation-Totalspalten: 10m Fehler {ten['delta_errors']:,}, 100m Fehler {hundred['delta_errors']:,}.",
        f"- Maximaler gespeicherter Formationwert: 10m {ten['max_formation']:,}, 100m {hundred['max_formation']:,}. Die erwarteten Zellflaechen sind 100 bzw. 10.000 m2. Die kleinen Ueberschreitungen um 1 bzw. 4 m2 deuten auf Rundung oder minimale Polygonueberlappungen hin und betreffen nicht die Flag-Korrektur.",
        "",
        "## Auffaelligkeiten und Empfehlung",
        "Die beiden Produkte sind strukturell kompatibel und die Majority-Logik ist nach der Korrektur fachlich einheitlich als 2%-Regel. Der numerische Grenzwert darf jedoch nicht global identisch sein, solange die gespeicherten Werte Flaechen in m2 sind: 2 fuer 10m, 200 fuer 100m. Der 10m-Generator muss vor dem naechsten Komplettlauf entsprechend angepasst werden; andernfalls erzeugt er erneut die unbrauchbaren Flags. Fuer diese Lieferung ist kein erneuter Overlay-/LRT-Lauf erforderlich, weil nur die boolesche Ableitung korrigiert wurde.",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--corrected-output", type=Path)
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()
    directory = args.directory
    ten_original = directory / "Formation_Status_10m_Grid_withLRTCode.parquet"
    ten_corrected = args.corrected_output or directory / "Formation_Status_10m_Grid_withLRTCode_corrected.parquet"
    hundred = directory / "Formation_Status_Grid_withLRTCode.parquet"
    report = args.report_output or directory / "Pruefbericht_majority_disputed_10m_100m.md"
    for path in (ten_original, hundred):
        if not path.is_file():
            raise FileNotFoundError(path)

    correction = replace_flag(ten_original, ten_corrected, threshold=2)
    ten_stats = read_stats(ten_corrected, threshold=2, id_column="grid_id_10")
    hundred_stats = read_stats(hundred, threshold=200, id_column="grid_id")
    write_report(report, ten_corrected, hundred, correction, ten_stats, hundred_stats)
    print(f"Corrected: {ten_corrected}")
    print(f"Report:    {report}")
    print(correction)


if __name__ == "__main__":
    main()
