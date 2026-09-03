from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.category import Category
from app.schemas.category import CategoryResponse
from app.dependencies import get_current_user


router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)



@router.get("/", response_model=list[CategoryResponse])
def get_categories(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)):
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