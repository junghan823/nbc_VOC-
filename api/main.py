"""FastAPI backend exposing VOC report data."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_PATH = DEFAULT_PROJECT_ROOT / "python" / "voc-report" / "voc_report.json"
ANALYZER_SCRIPT = DEFAULT_PROJECT_ROOT / "python" / "voc-report" / "voc_analyzer.py"


class Settings(BaseSettings):
    report_path: Path = DEFAULT_REPORT_PATH
    analyzer_path: Path = ANALYZER_SCRIPT

    class Config:
        env_prefix = "VOC_"
        env_file = DEFAULT_PROJECT_ROOT / ".env"
        env_file_encoding = "utf-8"


class RebuildResponse(BaseModel):
    message: str
    report_path: Path


settings = Settings()
app = FastAPI(title="VOC Report API", version="0.1.0")


def read_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report file not found: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON report: {exc}") from exc


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/report")
def get_report() -> JSONResponse:
    payload = read_report(settings.report_path)
    return JSONResponse(content=payload)


@app.post("/report/rebuild", response_model=RebuildResponse)
def rebuild_report() -> RebuildResponse:
    analyzer = settings.analyzer_path
    if not analyzer.exists():
        raise HTTPException(status_code=500, detail=f"Analyzer script not found: {analyzer}")

    try:
        subprocess.run(
            ["python3", str(analyzer), "--export-report"],
            cwd=analyzer.parent,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to rebuild report (exit code {exc.returncode})"
        ) from exc

    return RebuildResponse(message="Report rebuilt successfully", report_path=settings.report_path)
