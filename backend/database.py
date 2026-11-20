import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import load_local_env

load_local_env()
DATABASE_URL = os.getenv("SMARTBIZ_DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("Set SMARTBIZ_DATABASE_URL to your MySQL connection URL.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()