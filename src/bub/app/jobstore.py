import base64
import json
import pickle
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.job import Job
from apscheduler.jobstores.base import BaseJobStore, ConflictingIdError, JobLookupError
from loguru import logger


class JSONJobStore(BaseJobStore):
    """
    A simple JSON-based job store for APScheduler.

    Jobs are serialized using pickle and stored as base64-encoded strings in a JSON file.
    This provides persistence across restarts without requiring SQLAlchemy.
    """

    def __init__(self, file_path: str | Path):
        super().__init__()
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        """Load jobs from JSON file."""
        if self.file_path.exists():
            try:
                with open(self.file_path, encoding="utf-8") as f:
                    loaded_jobs = json.load(f)
                    return loaded_jobs  # type: ignore[no-any-return]
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Error loading job store: {e}")
        return {}

    def _save(self):
        """Save jobs to JSON file."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._jobs, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"Error saving job store: {e}")

    def _serialize_job(self, job: Job) -> dict[str, Any]:
        """Serialize a job to a storable format."""
        return {
            "id": job.id,
            "data": base64.b64encode(pickle.dumps(job)).decode("ascii"),
            "next_run_time": (job.next_run_time.isoformat() if job.next_run_time else None),
        }

    def _deserialize_job(self, job_data: dict[str, Any]) -> Job | None:
        """Deserialize a job from stored format."""
        try:
            job = pickle.loads(base64.b64decode(job_data["data"]))  # noqa: S301
            job._scheduler = self._scheduler
            job._jobstore_alias = self._alias
        except Exception as e:
            logger.error(f"Error deserializing job {job_data.get('id')}: {e}")
            return None
        else:
            return job

    def shutdown(self):
        """Called when the scheduler shuts down."""
        with self._lock:
            self._save()

    def lookup_job(self, job_id: str) -> Job | None:
        """Look up a job by its ID."""
        with self._lock:
            job_data = self._jobs.get(job_id)
            if job_data:
                return self._deserialize_job(job_data)
            return None

    def get_due_jobs(self, now: datetime) -> list[Job]:
        """Get jobs that are due to be run."""
        with self._lock:
            due_jobs = []
            for job_data in self._jobs.values():
                next_run_time_str = job_data.get("next_run_time")
                if next_run_time_str:
                    next_run_time = datetime.fromisoformat(next_run_time_str)
                    if next_run_time <= now:
                        job = self._deserialize_job(job_data)
                        if job:
                            due_jobs.append(job)
            return due_jobs

    def get_next_run_time(self) -> datetime | None:
        """Get the earliest next run time among all jobs."""
        with self._lock:
            next_times = []
            for job_data in self._jobs.values():
                next_run_time_str = job_data.get("next_run_time")
                if next_run_time_str:
                    next_times.append(datetime.fromisoformat(next_run_time_str))
            return min(next_times) if next_times else None

    def get_all_jobs(self) -> list[Job]:
        """Get all jobs in the store."""
        with self._lock:
            jobs = []
            for job_data in self._jobs.values():
                job = self._deserialize_job(job_data)
                if job:
                    jobs.append(job)
            return jobs

    def add_job(self, job: Job):
        """Add a job to the store."""
        with self._lock:
            if job.id in self._jobs:
                raise ConflictingIdError(job.id)
            self._jobs[job.id] = self._serialize_job(job)
            self._save()

    def update_job(self, job: Job):
        """Update a job in the store."""
        with self._lock:
            if job.id not in self._jobs:
                raise JobLookupError(job.id)
            self._jobs[job.id] = self._serialize_job(job)
            self._save()

    def remove_job(self, job_id: str):
        """Remove a job from the store."""
        with self._lock:
            if job_id not in self._jobs:
                raise JobLookupError(job_id)
            del self._jobs[job_id]
            self._save()

    def remove_all_jobs(self):
        """Remove all jobs from the store."""
        with self._lock:
            self._jobs.clear()
            self._save()
