"""Minimal Databricks REST API helper for running jobs from the backend.
This is intentionally small: it reads `databricks_host` and `databricks_token` from settings and
provides a `run_job` helper that triggers a job run via the Jobs API.
"""
from typing import Any, Dict, Optional

import requests

from app.core.config import settings


class DatabricksClient:
    def __init__(self) -> None:
        self.host = settings.databricks_host
        self.token = settings.databricks_token
        if not self.host or not self.token:
            raise RuntimeError("Databricks host/token not configured in settings")
        self.base = self.host.rstrip("/")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def run_job(self, job_id: int, notebook_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base}/api/2.1/jobs/run-now"
        payload: Dict[str, Any] = {"job_id": int(job_id)}
        if notebook_params:
            payload["notebook_params"] = notebook_params

        resp = requests.post(url, json=payload, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

def trigger_default_job() -> Dict[str, Any]:
    if not settings.databricks_default_job_id:
        raise RuntimeError("No default Databricks job id configured")
    client = DatabricksClient()
    try:
        return client.run_job(int(settings.databricks_default_job_id))
    except requests.HTTPError as exc:
        response = exc.response
        return {
            "triggered": False,
            "job_id": settings.databricks_default_job_id,
            "status_code": getattr(response, "status_code", None),
            "error": str(exc),
        }
