from pathlib import Path

import pytest

from app.analytics.engine import analyze_cohorts, analyze_time
from app.datasets import kaggle
from app.datasets.profiling import inspect_csv
from app.workers import kaggle_pipeline

OWNER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
DATASET = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
JOB = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def test_parse_kaggle_dataset_url() -> None:
    assert kaggle.parse_dataset_ref("https://www.kaggle.com/datasets/owner/sample?select=data.csv") == "owner/sample"
    assert kaggle.parse_dataset_ref("owner/sample") == "owner/sample"
    with pytest.raises(kaggle.KaggleSourceError):
        kaggle.parse_dataset_ref("https://example.com/datasets/owner/sample")


def test_csv_profile_measures_rows_and_missing_without_distinct_scan(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    source.write_text("event_type,user_id,price\nview,u1,2.5\npurchase,,4.5\n")

    profile = kaggle.csv_profile(source)

    assert profile["row_count"] == 2
    assert profile["columns"][1]["missing_count"] == 1
    assert profile["columns"][1]["distinct_count"] is None


def test_utc_timestamp_csv_profiles_and_analyzes_without_losing_time(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    source.write_text(
        "event_time,event_type,product_id,category,brand,price,user_id,user_session\n"
        "2019-10-01 03:15:18 UTC,view,p1,cat-a,brand-a,10,u1,s1\n"
        "2019-10-01 03:20:18 UTC,purchase,p1,cat-a,brand-a,10,u1,s1\n"
    )

    profile = kaggle.csv_profile(source)
    assert profile["schema"]["event_time"] == kaggle.pl.String
    assert profile["row_count"] == 2
    assert inspect_csv(source)["row_count"] == 2

    parquet = tmp_path / "events.parquet"
    kaggle.csv_to_parquet(source, parquet, profile["schema"])
    series = analyze_time(parquet, "dataset-utc", 1)
    cohorts = analyze_cohorts(parquet, "dataset-utc", 1)
    assert sum(row["events"] for row in series["hourly"]) == 2
    assert series["hourly"][0]["hour"] == 3
    assert cohorts["supported"] is True
    assert cohorts["cohorts"][0]["cohort_month"] == "2019-10"


class MemoryAdmin:
    def __init__(self) -> None:
        self.calls = []
        self.snapshot = None
        self.dataset_updates = []

    async def request(self, method: str, table: str, **kwargs):
        self.calls.append((method, table, kwargs))
        if method == "POST" and table == "dataset_versions":
            return [{"id": "version-id"}]
        if method == "POST" and table == "dataset_analytics_snapshots":
            self.snapshot = kwargs["json"]["snapshot"]
        if method == "PATCH" and table == "datasets":
            self.dataset_updates.append(kwargs["json"])
        return None


@pytest.mark.asyncio
async def test_kaggle_job_builds_global_snapshot_and_removes_temporary_files(monkeypatch) -> None:
    content = {
        "2019-Oct.csv": "event_time,event_type,product_id,category,brand,price,user_id,user_session\n"
        "2019-10-01T00:00:00Z,view,p1,cat-a,brand-a,10.0,u1,s1\n"
        "2019-10-01T00:10:00Z,purchase,p1,cat-a,brand-a,10.0,u1,s1\n",
        "2019-Nov.csv": "event_time,event_type,product_id,category,brand,price,user_id,user_session\n"
        "2019-11-01T00:00:00Z,cart,p2,cat-b,brand-b,20.0,u1,s2\n"
        "2019-11-01T01:00:00Z,purchase,p2,cat-b,brand-b,20.0,u2,s3\n",
    }
    files = [{"name": name, "total_bytes": len(data.encode()), "created_at": None} for name, data in content.items()]
    temp_files: list[Path] = []

    async def list_files(_dataset_ref: str):
        return files

    async def download(_dataset_ref: str, file_name: str, directory: Path, _expected_size: int):
        path = directory / file_name
        path.write_text(content[file_name])
        temp_files.append(path)
        return path

    monkeypatch.setattr(kaggle_pipeline, "list_dataset_files", list_files)
    monkeypatch.setattr(kaggle_pipeline, "download_csv", download)
    admin = MemoryAdmin()
    source = {"dataset_ref": "owner/sample", "files": files, "raw_retained": False}

    await kaggle_pipeline.process_kaggle_job(
        {"id": JOB, "dataset_id": DATASET, "owner_id": OWNER, "source_config": source},
        {"id": DATASET, "owner_id": OWNER, "active_version": 0},
        admin,
    )

    assert admin.snapshot is not None
    assert admin.snapshot["overview"]["metrics"]["total_events"]["value"] == 4
    assert admin.snapshot["overview"]["metrics"]["unique_users"]["value"] == 2
    assert admin.snapshot["rankings"]["category"]["purchase"]["items"][0]["category"] == "cat-a" or admin.snapshot["rankings"]["category"]["purchase"]["items"][0]["category"] == "cat-b"
    assert admin.snapshot["customers"]["top_users"] == []
    assert admin.dataset_updates[-1]["status"] == "ready"
    assert admin.dataset_updates[-1]["source_metadata"]["raw_retained"] is False
    assert all(not path.exists() for path in temp_files)
    assert any(method == "POST" and table == "dataset_analytics_snapshots" for method, table, _ in admin.calls)
