from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import DB, CurrentUser, OwnedProject
from app.models import Project
from app.schemas.project import ProjectIn, ProjectOut, ProjectPatch

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: DB, user: CurrentUser):
    rows = await db.execute(
        select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc())
    )
    return rows.scalars().all()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, db: DB, user: CurrentUser):
    project = Project(owner_id=user.id, name=body.name, currency=body.currency.upper())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project: OwnedProject):
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def patch_project(body: ProjectPatch, project: OwnedProject, db: DB):
    if body.name is not None:
        project.name = body.name
    if body.currency is not None:
        project.currency = body.currency.upper()
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project: OwnedProject, db: DB):
    await db.delete(project)
    await db.commit()
