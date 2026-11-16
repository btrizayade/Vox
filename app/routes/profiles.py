
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import get_current_user
from app.models import (
    Board,
    BoardItem,
    Pictogram,
    Profile,
    User,
)
from app.schemas.profile import (
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
)
from app.services.pictogram_storage import delete_pictogram_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["Profiles"])


@router.post(
    "/",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    profile_data: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = Profile(
        user_id=current_user.id,
        name=profile_data.name,
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile


@router.get("/", response_model=list[ProfileResponse])
def get_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        select(Profile)
        .where(Profile.user_id == current_user.id)
        .order_by(Profile.id)
    )

    return result.scalars().all()


@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        select(Profile).where(
            Profile.id == profile_id,
            Profile.user_id == current_user.id,
        )
    )

    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil não encontrado.",
        )

    return profile


@router.put("/{profile_id}", response_model=ProfileResponse)
def update_profile(
    profile_id: int,
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        select(Profile).where(
            Profile.id == profile_id,
            Profile.user_id == current_user.id,
        )
    )

    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil não encontrado.",
        )

    profile.name = profile_data.name

    db.commit()
    db.refresh(profile)

    return profile


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Verifica se o perfil pertence ao usuario.
    profile = db.execute(
        select(Profile)
        .where(
            Profile.id == profile_id,
            Profile.user_id == current_user.id,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado.",
        )

    # 2. Guarda os caminhos das imagens personalizadas.
    storage_paths = db.execute(
        select(Pictogram.storage_path).where(
            Pictogram.profile_id == profile_id,
            Pictogram.storage_path.is_not(None),
        )
    ).scalars().all()

    # 3. Busca as pranchas pertencentes ao perfil.
    board_ids = db.execute(
        select(Board.id).where(
            Board.profile_id == profile_id,
        )
    ).scalars().all()

    try:
        # 4. Remove os itens associados as pranchas.
        if board_ids:
            db.execute(
                delete(BoardItem).where(
                    BoardItem.board_id.in_(board_ids),
                )
            )

        # 5. Remove as pranchas do perfil.
        db.execute(
            delete(Board).where(
                Board.profile_id == profile_id,
            )
        )

        # 6. Remove somente os pictogramas personalizados.
        db.execute(
            delete(Pictogram).where(
                Pictogram.profile_id == profile_id,
            )
        )

        # 7. Remove o perfil.
        db.delete(profile)

        db.commit()

    except IntegrityError as error:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nao foi possivel excluir o perfil devido a registros relacionados.",
        ) from error

    except Exception:
        db.rollback()
        raise

    # 8. Remove as imagens do Supabase.
    for storage_path in storage_paths:
        try:
            delete_pictogram_image(storage_path)
        except Exception:
            logger.exception(
                "Failed to delete profile pictogram from storage: %s",
                storage_path,
            )

    return None
