
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import get_current_user
from app.models import Profile, User
from app.schemas.profile import (
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
)

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
def delete_profile(
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

    db.delete(profile)
    db.commit()
