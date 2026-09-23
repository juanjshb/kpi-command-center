from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select, text

from app.api.deps import DB, CurrentUser, Paging, Writer
from app.models import JobRun
from app.models.enums import JobRunStatus
from app.schemas import JobRunOut, Page
from app.services.common import audit, get_or_404, paginate
from app.services.jobs import BHD_LOCATIONS_JOB, recover_stale_jobs, run_bhd_location_job

router = APIRouter(prefix="/jobs", tags=["Jobs de datos"])


@router.get("", response_model=Page[JobRunOut])
def list_jobs(
    db: DB,
    user: CurrentUser,
    paging: Paging,
    status: JobRunStatus | None = None,
    job_key: str | None = None,
):
    stmt = select(JobRun)
    if status is not None:
        stmt = stmt.where(JobRun.status == status)
    if job_key is not None:
        stmt = stmt.where(JobRun.job_key == job_key)
    return paginate(db, stmt.order_by(JobRun.created_at.desc()), paging)


@router.post("/bhd-locations", response_model=JobRunOut, status_code=202)
def start_bhd_locations_job(background: BackgroundTasks, db: DB, user: Writer):
    # Serializa la comprobación/creación incluso con varios workers de API.
    db.execute(text("SELECT pg_advisory_xact_lock(714003)"))
    recover_stale_jobs(db, older_than=timedelta(hours=1))
    active = db.scalar(
        select(JobRun).where(
            JobRun.job_key == BHD_LOCATIONS_JOB,
            JobRun.status.in_([JobRunStatus.PENDING, JobRunStatus.RUNNING]),
        )
    )
    if active:
        raise HTTPException(409, f"Ya existe una sincronización BHD activa: {active.id}")

    job = JobRun(
        job_key=BHD_LOCATIONS_JOB,
        status=JobRunStatus.PENDING,
        requested_by_id=user.id,
        message="Job registrado; esperando ejecución",
    )
    db.add(job)
    audit(db, user, job, "START_JOB")
    db.commit()
    db.refresh(job)
    background.add_task(run_bhd_location_job, job.id)
    return job


@router.get("/{id}", response_model=JobRunOut)
def detail(id: UUID, db: DB, user: CurrentUser):
    return get_or_404(db, JobRun, id)
