import csv
import math
from pathlib import Path
from typing import Any

import polars as pl

from app.analytics.roles import map_roles


class CsvValidationError(ValueError):
    pass



def validate_csv_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            header = next(csv.reader(source), None)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise CsvValidationError("The uploaded file is not a readable UTF-8 CSV.") from exc
    if not header or not any(name.strip() for name in header):
        raise CsvValidationError("The CSV must contain a header row.")
    if any("\x00" in name for name in header):
        raise CsvValidationError("The uploaded file is not a valid UTF-8 CSV.")
    if len(set(header)) != len(header):
        raise CsvValidationError("Column names must be unique.")
    return header


def timestamp_column_overrides(columns: list[str]) -> dict[str, pl.DataType]:
    """Keep recognized timestamps as strings so Polars does not guess formats too early."""
    timestamp_column = map_roles(columns)["event_time"]
    return {timestamp_column: pl.String} if timestamp_column else {}


def preview_csv(path: Path, *, preview_rows: int = 20) -> dict[str, Any]:
    try:
        header = validate_csv_header(path)
        lazy = pl.scan_csv(path, infer_schema_length=10_000, try_parse_dates=True, schema_overrides=timestamp_column_overrides(header), raise_if_empty=True)
        schema = lazy.collect_schema()
        if len(schema) != len(header):
            raise CsvValidationError("The CSV header could not be interpreted consistently.")
        frame = lazy.limit(preview_rows).collect(engine="streaming")
        preview = [{key: _json_value(value) for key, value in row.items()} for row in frame.to_dicts()]
        return {"columns": [{"name": name, "inferred_type": str(dtype)} for name, dtype in schema.items()], "preview": preview}
    except CsvValidationError:
        raise
    except Exception as exc:
        raise CsvValidationError(f"Could not preview this CSV: {exc}") from exc


def inspect_csv(path: Path, *, preview_rows: int = 12) -> dict[str, Any]:
    try:
        header = validate_csv_header(path)

        lazy = pl.scan_csv(path, infer_schema_length=10_000, try_parse_dates=True, schema_overrides=timestamp_column_overrides(header), raise_if_empty=True)
        schema = lazy.collect_schema()
        names = schema.names()
        if len(names) != len(header):
            raise CsvValidationError("The CSV header could not be interpreted consistently.")

        metrics: list[pl.Expr] = [pl.len().alias("row_count"), (pl.len() - pl.struct(pl.all()).n_unique()).alias("duplicate_rows")]
        numeric_names = []
        for index, (name, dtype) in enumerate(schema.items()):
            safe = f"c_{index}"
            metrics.append(pl.col(name).null_count().alias(f"{safe}_nulls"))
            metrics.append(pl.col(name).n_unique().alias(f"{safe}_distinct"))
            if dtype.is_numeric():
                numeric_names.append(name)
                column_expr = pl.col(name)
                q1 = column_expr.quantile(0.25)
                q3 = column_expr.quantile(0.75)
                iqr = q3 - q1
                metrics.extend([
                    ((column_expr < q1 - 1.5 * iqr) | (column_expr > q3 + 1.5 * iqr)).fill_null(False).cast(pl.UInt64).sum().alias(f"{safe}_outliers"),
                    pl.col(name).min().alias(f"{safe}_min"),
                    pl.col(name).max().alias(f"{safe}_max"),
                    pl.col(name).mean().alias(f"{safe}_mean"),
                    pl.col(name).quantile(0.25).alias(f"{safe}_q1"),
                    pl.col(name).quantile(0.75).alias(f"{safe}_q3"),
                ])

        aggregates = lazy.select(metrics).collect(engine="streaming").row(0, named=True)
        preview_frame = lazy.limit(preview_rows).collect(engine="streaming")
        preview = [{key: _json_value(value) for key, value in row.items()} for row in preview_frame.to_dicts()]
        columns = []
        for index, (name, dtype) in enumerate(schema.items()):
            safe = f"c_{index}"
            column = {
                "name": name,
                "inferred_type": str(dtype),
                "nullable": aggregates.get(f"{safe}_nulls", 0) > 0,
                "missing_count": int(aggregates.get(f"{safe}_nulls", 0)),
                "distinct_count": int(aggregates.get(f"{safe}_distinct", 0)),
            }
            if name in numeric_names:
                column["numeric_summary"] = {
                    key: _json_value(aggregates.get(f"{safe}_{key}"))
                    for key in ("min", "max", "mean", "q1", "q3")
                }
                column["outlier_candidate_count"] = int(aggregates.get(f"{safe}_outliers", 0))
            columns.append(column)
        return {
            "row_count": int(aggregates["row_count"]),
            "column_count": len(names),
            "duplicate_rows": int(aggregates["duplicate_rows"]),
            "columns": columns,
            "preview": preview,
        }
    except CsvValidationError:
        raise
    except Exception as exc:
        raise CsvValidationError(f"Could not parse this CSV: {exc}") from exc


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
