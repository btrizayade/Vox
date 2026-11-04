
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import get_current_user
from app.models import Board, Profile, User
from app.schemas.board import (
    BoardCreate,
    BoardUpdate,
    BoardResponse,
)


router = APIRouter(
    prefix="/boards",
    tags=["Boards"],
)


def get_accessible_board(
    db: Session,
    board_id: int,
    user_id: int,
):
    """
    Retorna uma prancha padrao ou uma prancha personalizada
    pertencente ao usuario autenticado.
    """
    result = db.execute(
        select(Board)
        .outerjoin(Profile, Board.profile_id == Profile.id)
        .where(
            Board.id == board_id,
            or_(
                Board.board_type == "system",
                and_(
                    Board.board_type == "custom",
                    Profile.user_id == user_id,
                ),
            ),
        )
    )

    return result.scalar_one_or_none()


def get_user_custom_board(
    db: Session,
    board_id: int,
    user_id: int,
):
    """
    Retorna somente pranchas personalizadas pertencentes
    ao usuario autenticado.
    """
    result = db.execute(
        select(Board)
        .join(Profile, Board.profile_id == Profile.id)
        .where(
            Board.id == board_id,
            Board.board_type == "custom",
            Profile.user_id == user_id,
        )
    )

    return result.scalar_one_or_none()


@router.post(
    "/",
    response_model=BoardResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_board(
    board_data: BoardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile_result = db.execute(
        select(Profile).where(
            Profile.id == board_data.profile_id,
            Profile.user_id == current_user.id,
        )
    )

    profile = profile_result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado.",
        )

    board = Board(
        profile_id=profile.id,
        name=board_data.name,
        board_type="custom",
    )

    db.add(board)
    db.commit()
    db.refresh(board)

    return board


@router.get(
    "/",
    response_model=list[BoardResponse],
)
def get_boards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        select(Board)
        .join(Profile, Board.profile_id == Profile.id)
        .where(
            Board.board_type == "custom",
            Profile.user_id == current_user.id,
        )
        .order_by(Board.id)
    )

    return result.scalars().all()


# Esta rota deve ficar antes de /{board_id}.
@router.get(
    "/system",
    response_model=list[BoardResponse],
)
def get_system_boards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = db.execute(
        select(Board)
        .where(Board.board_type == "system")
        .order_by(Board.id)
    )

    return result.scalars().all()


@router.get(
    "/{board_id}",
    response_model=BoardResponse,
)
def get_board(
    board_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    board = get_accessible_board(
        db,
        board_id,
        current_user.id,
    )

    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prancha nao encontrada.",
        )

    return board


@router.put(
    "/{board_id}",
    response_model=BoardResponse,
)
def update_board(
    board_id: int,
    board_data: BoardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    board = get_user_custom_board(
        db,
        board_id,
        current_user.id,
    )

    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prancha personalizada nao encontrada.",
        )

    board.name = board_data.name

    db.commit()
    db.refresh(board)

    return board


@router.delete(
    "/{board_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_board(
    board_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    board = get_user_custom_board(
        db,
        board_id,
        current_user.id,
    )

    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prancha personalizada nao encontrada.",
        )

    db.delete(board)
    db.commit()
