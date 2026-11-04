
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import get_current_user
from app.models import Board, BoardItem, Category, Pictogram, Profile, User
from app.schemas.board_item import (
    BoardItemCreate,
    BoardItemResponse,
)
from app.schemas.pictogram import PictogramResponse


router = APIRouter(
    prefix="/boards",
    tags=["Board Items"],
)


def get_accessible_board(
    db: Session,
    board_id: int,
    user_id: int,
):
    """Retorna uma prancha padrao ou personalizada acessivel ao usuario."""

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


def get_editable_board(
    db: Session,
    board_id: int,
    user_id: int,
):
    """Retorna somente uma prancha personalizada do usuario."""

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


def build_board_item_response(
    board_item: BoardItem,
    pictogram: Pictogram,
    category_name: str,
):
    """Monta a resposta com os dados do item e do pictograma."""

    return BoardItemResponse(
        id=board_item.id,
        board_id=board_item.board_id,
        pictogram_id=board_item.pictogram_id,
        position=board_item.position,
        pictogram=PictogramResponse(
            id=pictogram.id,
            name=pictogram.name,
            image_url=pictogram.image_url,
            category_id=pictogram.category_id,
            category_name=category_name,
            created_at=pictogram.created_at,
        ),
    )


@router.post(
    "/{board_id}/items",
    response_model=BoardItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_board_item(
    board_id: int,
    item_data: BoardItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verifica se a prancha pertence ao usuario e pode ser editada.
    board = get_editable_board(
        db,
        board_id,
        current_user.id,
    )

    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prancha personalizada nao encontrada.",
        )

    # Busca o pictograma e o nome da sua categoria.
    pictogram_result = db.execute(
        select(
            Pictogram,
            Category.name.label("category_name"),
        )
        .join(Category, Pictogram.category_id == Category.id)
        .where(Pictogram.id == item_data.pictogram_id)
    )

    pictogram_row = pictogram_result.one_or_none()

    if pictogram_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pictograma nao encontrado.",
        )

    pictogram, category_name = pictogram_row

    # Impede adicionar o mesmo pictograma duas vezes na prancha.
    existing_item = db.execute(
        select(BoardItem.id).where(
            BoardItem.board_id == board_id,
            BoardItem.pictogram_id == item_data.pictogram_id,
        )
    ).scalar_one_or_none()

    if existing_item is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pictograma ja esta na prancha.",
        )

    # Calcula a proxima posicao disponivel.
    max_position = db.execute(
        select(func.max(BoardItem.position)).where(
            BoardItem.board_id == board_id,
        )
    ).scalar_one()

    next_position = (max_position or 0) + 1

    board_item = BoardItem(
        board_id=board_id,
        pictogram_id=pictogram.id,
        position=next_position,
    )

    db.add(board_item)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito ao adicionar pictograma. Atualize a prancha e tente novamente.",
        )

    db.refresh(board_item)

    return build_board_item_response(
        board_item,
        pictogram,
        category_name,
    )


@router.get(
    "/{board_id}/items",
    response_model=list[BoardItemResponse],
)
def get_board_items(
    board_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verifica se o usuario pode consultar a prancha.
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

    # Busca os itens e seus respectivos pictogramas.
    result = db.execute(
        select(
            BoardItem,
            Pictogram,
            Category.name.label("category_name"),
        )
        .join(
            Pictogram,
            BoardItem.pictogram_id == Pictogram.id,
        )
        .join(
            Category,
            Pictogram.category_id == Category.id,
        )
        .where(BoardItem.board_id == board_id)
        .order_by(BoardItem.position)
    )

    rows = result.all()

    return [
        build_board_item_response(
            board_item,
            pictogram,
            category_name,
        )
        for board_item, pictogram, category_name in rows
    ]

@router.delete(
    "/{board_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_board_item(
    board_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    board = get_editable_board(db, board_id, current_user.id)

    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prancha personalizada nao encontrada.",
        )

    board_item = db.execute(
        select(BoardItem).where(
            BoardItem.id == item_id,
            BoardItem.board_id == board_id,
        )
    ).scalar_one_or_none()

    if board_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item nao encontrado nesta prancha.",
        )

    try:
        # Remove somente a associacao entre a prancha e o pictograma.
        # O pictograma continua existindo no catalogo.
        db.delete(board_item)
        db.flush()

        # Busca os itens restantes na ordem atual.
        remaining_items = db.execute(
            select(BoardItem)
            .where(BoardItem.board_id == board_id)
            .order_by(BoardItem.position)
        ).scalars().all()

        if remaining_items:
            # Etapa 1: move as posicoes para uma faixa temporaria,
            # evitando conflitos com a restricao de unicidade.
            max_position = max(
                item.position for item in remaining_items
            )
            offset = max_position + len(remaining_items) + 1

            for item in remaining_items:
                item.position += offset

            db.flush()

            # Etapa 2: atribui novamente as posicoes sequenciais.
            for new_position, item in enumerate(
                remaining_items,
                start=1,
            ):
                item.position = new_position

        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito ao remover o item. Atualize a prancha e tente novamente.",
        )

    return None
