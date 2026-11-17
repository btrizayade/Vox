import logging
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import get_current_user
from app.models import BoardItem, Category, Pictogram, Profile, User
from app.schemas.pictogram import PictogramResponse
from app.services.pictogram_storage import (
    BUCKET_NAME,
    MAX_UPLOAD_SIZE,
    create_pictogram_signed_url,
    delete_pictogram_image,
    process_pictogram_image,
    upload_pictogram_image,
)


logger = logging.getLogger(__name__)

MAX_CUSTOM_PICTOGRAMS_PER_PROFILE = 15

router = APIRouter(
    prefix="/profiles",
    tags=["Custom Pictograms"],
)


def get_owned_profile(
    db: Session,
    profile_id: int,
    user_id: int,
    lock: bool = False,
):
    """Busca um perfil pertencente ao usuario autenticado."""

    statement = select(Profile).where(
        Profile.id == profile_id,
        Profile.user_id == user_id,
    )

    if lock:
        statement = statement.with_for_update()

    return db.execute(statement).scalar_one_or_none()


def cleanup_storage_object(storage_path: str) -> None:
    """Tenta remover um arquivo enviado quando ocorre uma falha."""

    try:
        delete_pictogram_image(storage_path)
    except Exception:
        logger.exception(
            "Failed to clean up storage object: %s",
            storage_path,
        )


def build_pictogram_response(
    pictogram: Pictogram,
    category_name: str,
) -> PictogramResponse:
    """Monta a resposta com a URL apropriada para a imagem."""

    image_url = pictogram.image_url

    if pictogram.profile_id is not None:
        try:
            image_url = create_pictogram_signed_url(
                pictogram.storage_path
            )
        except Exception as error:
            logger.exception(
                "Failed to generate signed URL for pictogram %s",
                pictogram.id,
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Nao foi possivel acessar a imagem.",
            ) from error

    return PictogramResponse(
        id=pictogram.id,
        name=pictogram.name,
        image_url=image_url,
        category_id=pictogram.category_id,
        category_name=category_name,
        created_at=pictogram.created_at,
    )


@router.post(
    "/{profile_id}/pictograms",
    response_model=PictogramResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_pictogram(
    profile_id: int,
    name: str = Form(..., min_length=1, max_length=100),
    category_id: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria um pictograma personalizado para um perfil."""
    normalized_name = name.strip()

    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O nome do pictograma nao pode estar vazio.",
        )
    # 1. Bloqueia o perfil durante a operacao.
    # Isso protege o limite contra uploads simultaneos.
    profile = get_owned_profile(
        db,
        profile_id,
        current_user.id,
        lock=True,
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado.",
        )

    # 2. Confere se a categoria existe.
    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoria nao encontrada.",
        )

    # 3. Confere o limite de pictogramas personalizados.
    custom_count = db.execute(
        select(func.count(Pictogram.id)).where(
            Pictogram.profile_id == profile_id,
        )
    ).scalar_one()

    if custom_count >= MAX_CUSTOM_PICTOGRAMS_PER_PROFILE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O perfil atingiu o limite de 15 pictogramas personalizados.",
        )

    # 4. Le somente o limite permitido mais um byte.
    try:
        file_content = await image.read(MAX_UPLOAD_SIZE + 1)
    finally:
        await image.close()

    if len(file_content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="O arquivo deve ter no maximo 5 MB.",
        )

    # 5. Valida, otimiza e calcula o hash da imagem.
    try:
        processed_image = process_pictogram_image(file_content)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    # 6. Verifica se o mesmo arquivo ja existe no perfil.
    duplicate = db.execute(
        select(Pictogram.id).where(
            Pictogram.profile_id == profile_id,
            Pictogram.content_hash == processed_image.content_hash,
        )
    ).scalar_one_or_none()

    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este arquivo ja foi enviado para este perfil.",
        )

    # 7. Gera um nome de arquivo que nao depende do nome original.
    storage_path = f"{profile_id}/{uuid4().hex}.webp"

    try:
        upload_pictogram_image(
            storage_path,
            processed_image.content,
        )
    except Exception as error:
        cleanup_storage_object(storage_path)

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nao foi possivel armazenar a imagem.",
        ) from error

    # 8. Salva os metadados no banco.
    pictogram = Pictogram(
        name=normalized_name,
        image_url=None,
        storage_path=storage_path,
        content_hash=processed_image.content_hash,
        profile_id=profile_id,
        category_id=category_id,
    )

    db.add(pictogram)

    try:
        db.commit()
        db.refresh(pictogram)

    except IntegrityError as error:
        db.rollback()
        cleanup_storage_object(storage_path)

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nao foi possivel cadastrar o pictograma. Verifique se o arquivo ja existe.",
        ) from error

    except Exception:
        db.rollback()
        cleanup_storage_object(storage_path)
        raise

    return build_pictogram_response(
        pictogram,
        category.name,
    )


@router.get(
    "/{profile_id}/pictograms",
    response_model=list[PictogramResponse],
)
def list_profile_pictograms(
    profile_id: int,
    category_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista pictogramas institucionais e do perfil."""

    # 1. Verifica se o perfil pertence ao usuario.
    profile = get_owned_profile(
        db,
        profile_id,
        current_user.id,
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado.",
        )

    # 2. Busca os pictogramas institucionais e personalizados
    # pertencentes exclusivamente ao perfil solicitado.
    statement = (
        select(
            Pictogram,
            Category.name.label("category_name"),
        )
        .join(Category, Pictogram.category_id == Category.id)
        .where(
            or_(
                Pictogram.profile_id.is_(None),
                Pictogram.profile_id == profile_id,
            )
        )
        .order_by(Pictogram.id)
    )

    if category_id is not None:
        statement = statement.where(
            Pictogram.category_id == category_id,
        )

    if search is not None:
        statement = statement.where(
            Pictogram.name.ilike(f"%{search}%"),
        )

    rows = db.execute(statement).all()

    return [
        build_pictogram_response(
            pictogram,
            category_name,
        )
        for pictogram, category_name in rows
    ]


@router.delete(
    "/{profile_id}/pictograms/{pictogram_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_custom_pictogram(
    profile_id: int,
    pictogram_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui um pictograma personalizado do perfil."""

    # 1. Verifica a propriedade do perfil.
    profile = get_owned_profile(
        db,
        profile_id,
        current_user.id,
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado.",
        )

    # 2. Busca somente pictogramas personalizados do perfil.
    pictogram = db.execute(
        select(Pictogram).where(
            Pictogram.id == pictogram_id,
            Pictogram.profile_id == profile_id,
        )
    ).scalar_one_or_none()

    if pictogram is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pictograma personalizado nao encontrado.",
        )

    # 3. Verifica se o pictograma esta sendo utilizado.
    board_item = db.execute(
        select(BoardItem.id).where(
            BoardItem.pictogram_id == pictogram_id,
        ).limit(1)
    ).scalar_one_or_none()

    if board_item is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Remova o pictograma das pranchas antes de exclui-lo.",
        )

    storage_path = pictogram.storage_path

    # 4. Exclui primeiro o registro do banco.
    db.delete(pictogram)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nao foi possivel excluir o pictograma.",
        ) from error

    # 5. Depois remove o arquivo do Supabase.
    # Se a remocao falhar, o registro ja foi excluido do banco.
    # O erro fica registrado para uma futura limpeza do Storage.
    cleanup_storage_object(storage_path)

    return None