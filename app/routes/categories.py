from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.category import Category
from app.schemas.category import CategoryResponse


router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=list[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    result = db.execute(
        select(Category).order_by(Category.id)
    )

    return result.scalars().all()


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(Category).where(Category.id == category_id)
    )

    category = result.scalar_one_or_none()

    if category is None:
        raise HTTPException(
            status_code=404,
            detail="Categoria não encontrada.",
        )

    return category