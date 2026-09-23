from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import utcnow
from app.db.session import get_session_factory
from app.models import JobRun
from app.models.enums import JobRunStatus
from app.services.location_import import import_bhd_rows
from app.services.main_bank_sync import fetch_bhd_rows

BHD_LOCATIONS_JOB = "bhd_locations_sync"
logger = logging.getLogger("kpi.jobs")


def recover_stale_jobs(db, *, older_than: timedelta = timedelta(hours=1)) -> int:
    jobs = list(
        db.scalars(
            select(JobRun).where(
                JobRun.status.in_([JobRunStatus.PENDING, JobRunStatus.RUNNING]),
                JobRun.created_at < utcnow() - older_than,
            )
        )
    )
    for job in jobs:
        job.status = JobRunStatus.FAILED
        job.finished_at = utcnow()
        job.message = "Ejecución interrumpida"
        job.error = "El proceso terminó antes de completar el job. Puede ejecutarlo nuevamente."
    return len(jobs)


def _update_progress(job_id: UUID, current: int, total: int | None, message: str) -> None:
    with get_session_factory()() as db:
        job = db.get(JobRun, job_id)
        if not job or job.status != JobRunStatus.RUNNING:
            return
        job.progress_current = current
        job.progress_total = total
        job.message = message[:255]
        db.commit()


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, SQLAlchemyError):
        return "La carga en PostgreSQL no pudo completarse. Revise los logs del servidor."
    message = str(exc).strip()
    return (message or type(exc).__name__)[:2000]


def run_bhd_location_job(job_id: UUID) -> None:
    try:
        with get_session_factory()() as db:
            job = db.get(JobRun, job_id)
            if not job or job.status != JobRunStatus.PENDING:
                return
            job.status = JobRunStatus.RUNNING
            job.started_at = utcnow()
            job.message = "Conectando con el API de BHD"
            db.commit()

        rows, extraction = fetch_bhd_rows(
            lambda current, total, message: _update_progress(job_id, current, total, message)
        )
        pages = int(extraction.get("pages") or 0)
        _update_progress(job_id, pages, pages + 1, "Validando y cargando ubicaciones")

        with get_session_factory()() as db:
            summary = import_bhd_rows(db, rows)
            job = db.get(JobRun, job_id)
            if not job:
                db.rollback()
                return
            job.status = JobRunStatus.SUCCEEDED
            job.finished_at = utcnow()
            job.progress_current = pages + 1
            job.progress_total = pages + 1
            job.message = "Sincronización BHD completada"
            job.result = {"extraction": extraction, "load": summary.to_dict()}
            job.error = None
            db.commit()
    except Exception as exc:
        logger.exception("BHD location job failed: job_id=%s", job_id)
        with get_session_factory()() as db:
            job = db.get(JobRun, job_id)
            if job:
                job.status = JobRunStatus.FAILED
                job.finished_at = utcnow()
                job.message = "La sincronización BHD falló"
                job.error = _safe_error(exc)
                db.commit()
