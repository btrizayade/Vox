from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import DATABASE_URL

if not DATABASE_URL:
    raise ValueError("DATABASE_URL não foi definida no arquivo .env")

engine_options = {"pool_pre_ping": True}

if DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg2://")):
    engine_options["connect_args"] = {"connect_timeout": 10}

engine = create_engine(DATABASE_URL, **engine_options)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
