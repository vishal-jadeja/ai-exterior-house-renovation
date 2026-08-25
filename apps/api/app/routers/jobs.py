from fastapi import APIRouter, HTTPException, status

from app.core.deps import DB, CurrentUser
from app.models import Job
from app.schemas.region import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: DB, user: CurrentUser):
    job = await db.get(Job, job_id)
    if job is None or job.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job
