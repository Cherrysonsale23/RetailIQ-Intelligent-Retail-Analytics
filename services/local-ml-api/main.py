
from pathlib import Path
import importlib.util
import shutil
import tempfile

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ML_SCRIPT = PROJECT_ROOT / "ml" / "06_process_uploaded_csv.py"

spec = importlib.util.spec_from_file_location(
    "uploaded_ml_pipeline", ML_SCRIPT
)

if spec is None or spec.loader is None:
    raise RuntimeError("Could not load the uploaded CSV ML pipeline.")

upload_pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upload_pipeline)

app = FastAPI(title="Customer Segmentation Local API")

latest_dashboard_data = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def health_check():
    return {
        "status": "running",
        "message": "Local ML API is ready",
    }


@app.get("/latest-analysis")
def get_latest_analysis():
    if latest_dashboard_data is None:
        raise HTTPException(
            status_code=404,
            detail="No uploaded dataset has been analyzed yet.",
        )

    return latest_dashboard_data


@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    global latest_dashboard_data

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file.",
        )

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False
        ) as temp:
            shutil.copyfileobj(file.file, temp)
            temp_path = Path(temp.name)

        try:
            df = pd.read_csv(temp_path)

            results = upload_pipeline.process_uploaded_dataframe(df)

            latest_dashboard_data = {
                "project": "Customer Segmentation",
                "model": "K-Means Clustering",
                "dataset": file.filename,
                **results,
            }

            return {
                "message": "CSV uploaded and processed successfully.",
                "filename": file.filename,
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": df.columns.tolist(),
                "preview": df.head(5).fillna("").to_dict(
                    orient="records"
                ),
                "analysis": results,
            }

        finally:
            temp_path.unlink(missing_ok=True)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not process CSV: {str(exc)}",
        ) from exc

    finally:
        await file.close()
