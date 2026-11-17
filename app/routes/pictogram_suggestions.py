from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import get_current_user
from app.models import Category, PictogramSuggestion, User
from app.schemas.pictogram_suggestion import (
    PictogramSuggestionCreate,
    PictogramSuggestionResponse,
)


router = APIRouter(
    prefix="/pictogram-suggestions",
    tags=["Pictogram Suggestions"],
)


@router.post(
    "/",
    response_model=PictogramSuggestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_pictogram_suggestion(
    suggestion_data: PictogramSuggestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia uma sugestao de pictograma para analise."""

    if suggestion_data.category_id is not None:
        category = db.get(Category, suggestion_data.category_id)

        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Categoria nao encontrada.",
            )

    suggestion = PictogramSuggestion(
        user_id=current_user.id,
        name=suggestion_data.name,
        category_id=suggestion_data.category_id,
        other_category=suggestion_data.other_category,
        description=suggestion_data.description,
        usage_context=suggestion_data.usage_context,
    )

    db.add(suggestion)

    try:
        db.commit()
        db.refresh(suggestion)

    except IntegrityError as error:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nao foi possivel registrar a sugestao.",
        ) from error

    return suggestion


@router.get(
    "/",
    response_model=list[PictogramSuggestionResponse],
)
def list_pictogram_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista somente as sugestoes do usuario autenticado."""

    statement = (
        select(PictogramSuggestion)
        .where(PictogramSuggestion.user_id == current_user.id)
        .order_by(
            PictogramSuggestion.created_at.desc(),
            PictogramSuggestion.id.desc(),
        )
    )

    return db.execute(statement).scalars().all()


@router.get(
    "/{suggestion_id}",
    response_model=PictogramSuggestionResponse,
)
def get_pictogram_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Consulta uma sugestao pertencente ao usuario autenticado."""

    statement = select(PictogramSuggestion).where(
        PictogramSuggestion.id == suggestion_id,
        PictogramSuggestion.user_id == current_user.id,
    )

    suggestion = db.execute(statement).scalar_one_or_none()

    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sugestao nao encontrada.",
        )

    return suggestion