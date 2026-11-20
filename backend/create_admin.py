from getpass import getpass

from backend.config import load_local_env

load_local_env()

from backend.auth import get_password_hash
from backend.database import Base, SessionLocal, engine
from backend.models import DBUser


def main() -> None:
    Base.metadata.create_all(bind=engine)
    username = input("Admin username: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass("Admin password (12+ characters): ")
    confirmation = getpass("Confirm password: ")

    if len(username) < 3 or len(username) > 50:
        raise SystemExit("Username must be between 3 and 50 characters.")
    if len(email) < 3 or len(email) > 100 or "@" not in email:
        raise SystemExit("Enter a valid email address.")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    db = SessionLocal()
    try:
        if db.query(DBUser).count():
            raise SystemExit("Users already exist; an existing administrator must add users.")

        db.add(
            DBUser(
                username=username,
                email=email,
                hashed_password=get_password_hash(password),
                role="Admin",
                is_active=True,
            )
        )
        db.commit()
        print("Initial administrator created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
