from sqlalchemy import select

from app.database.connection import SessionLocal
from app.models.category import Category


DEFAULT_CATEGORIES = [
    "Rotina",
    "Alimentação",
    "Higiene",
    "Escola",
    "Esportes",
    "Sentimentos",
    "Números",
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


def seed() -> None:
    db = SessionLocal()

    try:
        seed_categories(db)
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("Seed executado com sucesso.")