from pathlib import Path

from app.datasets.profiling import CsvValidationError, inspect_csv


def test_profiles_actual_csv_rows(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    source.write_text("event_type,price,user_id\nview,12.5,41\npurchase,22.0,41\nview,,52\n", encoding="utf-8")
    profile = inspect_csv(source)
    assert profile["row_count"] == 3
    assert profile["column_count"] == 3
    assert profile["duplicate_rows"] == 0
    assert [column["name"] for column in profile["columns"]] == ["event_type", "price", "user_id"]
    assert next(column for column in profile["columns"] if column["name"] == "price")["missing_count"] == 1
    assert profile["preview"][1]["event_type"] == "purchase"


def test_rejects_unreadable_csv(tmp_path: Path) -> None:
    source = tmp_path / "broken.csv"
    source.write_bytes(b"\x00\x01\x02")
    try:
        inspect_csv(source)
    except CsvValidationError as exc:
        assert "not a valid UTF-8 CSV" in str(exc)
    else:
        raise AssertionError("Expected malformed data to be rejected")


def test_flags_duplicate_rows_and_iqr_outliers(tmp_path: Path) -> None:
    source = tmp_path / "measurements.csv"
    source.write_text(
        "event_type,price,product_id\nview,1,p1\nview,1,p1\nview,2,p1\npurchase,3,p2\npurchase,4,p3\npurchase,1000,p4\n",
        encoding="utf-8",
    )
    profile = inspect_csv(source)
    assert profile["duplicate_rows"] == 1
    price = next(column for column in profile["columns"] if column["name"] == "price")
    assert price["outlier_candidate_count"] == 1


def test_parquet_transform_preserves_source_bytes(tmp_path: Path) -> None:
    import polars as pl

    from app.workers.pipeline import _to_parquet

    source = tmp_path / "raw.csv"
    target = tmp_path / "typed.parquet"
    original = b"event_type,price\nview,12.5\npurchase,25.0\n"
    source.write_bytes(original)
    _to_parquet(source, target)
    assert source.read_bytes() == original
    assert pl.read_parquet(target).height == 2
    assert pl.read_parquet(target)["price"].sum() == 37.5
