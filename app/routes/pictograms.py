from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models import User
from app.models.category import Category
from app.models.pictogram import Pictogram
from app.schemas.pictogram import PictogramResponse
from app.dependencies import get_current_user


router = APIRouter(
    prefix="/pictograms",
    tags=["Pictograms"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=list[PictogramResponse])
def get_pictograms(
    category_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = (
        select(
            Pictogram,
            Category.name.label("category_name"),
        )
        .join(Category, Pictogram.category_id == Category.id)
        .order_by(Pictogram.id)
    )

    if category_id is not None:
        statement = statement.where(
            Pictogram.category_id == category_id
        )

    if search is not None:
        statement = statement.where(
            Pictogram.name.ilike(f"%{search}%")
    )

    result = db.execute(statement)

    pictograms = []

    for pictogram, category_name in result.all():
        pictograms.append(
            PictogramResponse(
                id=pictogram.id,
                name=pictogram.name,
                image_url=pictogram.image_url,
                category_id=pictogram.category_id,
                category_name=category_name,
                created_at=pictogram.created_at,
            )
        )

    return pictograms


@router.get("/{pictogram_id}", response_model=PictogramResponse)
def get_pictogram(
    pictogram_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = (
        select(
            Pictogram,
            Category.name.label("category_name"),
        )
        .join(Category, Pictogram.category_id == Category.id)
        .where(Pictogram.id == pictogram_id)
    )

    result = db.execute(statement)
    row = result.one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Pictograma não encontrado.",
        )

    pictogram, category_name = row

    return PictogramResponse(
        id=pictogram.id,
        name=pictogram.name,
        image_url=pictogram.image_url,
        category_id=pictogram.category_id,
        category_name=category_name,
        created_at=pictogram.created_at,
    )