from sqlalchemy import select

from app.database.connection import SessionLocal
from app.models.category import Category
from app.models.pictogram import Pictogram


DEFAULT_CATEGORIES = [
    "Rotina",
    "Alimentação",
    "Higiene",
    "Escola",
    "Esportes",
    "Sentimentos",
    "Números",
]


DEFAULT_PICTOGRAMS = [
    {
        "name": "1",
        "image_url": (
            "https://eokzfjylmjaxxzhpxwqx.supabase.co/"
            "storage/v1/object/public/"
            "pictograms/numeros/1.png"
        ),
        "category": "Números",
    },
]

def seed_categories(db) -> None:
    for category_name in DEFAULT_CATEGORIES:
        result = db.execute(
            select(Category).where(Category.name == category_name)
        )

        category = result.scalar_one_or_none()

        if category is None:
            db.add(Category(name=category_name))

    db.flush()


def seed_pictograms(db) -> None:
    for pictogram_data in DEFAULT_PICTOGRAMS:
        result = db.execute(
            select(Pictogram).where(
                Pictogram.name == pictogram_data["name"]
            )
        )

        pictogram = result.scalar_one_or_none()

        if pictogram is not None:
            continue

        result = db.execute(
            select(Category).where(
                Category.name == pictogram_data["category"]
            )
        )

        category = result.scalar_one_or_none()

        if category is None:
            raise ValueError(
                f"Categoria não encontrada: "
                f"{pictogram_data['category']}"
            )

        db.add(
            Pictogram(
                name=pictogram_data["name"],
                image_url=pictogram_data["image_url"],
                category_id=category.id,
            )
        )


def seed() -> None:
    db = SessionLocal()

    try:
        seed_categories(db)
        seed_pictograms(db)

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("Seed executado com sucesso.")