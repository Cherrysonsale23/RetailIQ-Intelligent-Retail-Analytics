from pydantic import BaseModel, Field


class DatasetSummary(BaseModel):
    id: str
    name: str
    original_filename: str
    byte_size: int
    status: str
    row_count: int | None = None
    column_count: int | None = None
    active_version: int = 0
    created_at: str
    detected_schema: list[dict] = Field(default_factory=list)


class UploadAccepted(BaseModel):
    dataset: DatasetSummary
    status: str


class UploadIntent(BaseModel):
    filename: str
    byte_size: int
    name: str | None = None


class KaggleImportRequest(BaseModel):
    dataset_url: str = Field(min_length=1, max_length=500)
    files: list[str] = Field(min_length=1, max_length=12)
    name: str | None = Field(default=None, max_length=120)


class UploadPreview(BaseModel):
    columns: list[str]
    rows: list[dict[str, str | None]]


class ProcessAccepted(BaseModel):
    job_id: str
    status: str
