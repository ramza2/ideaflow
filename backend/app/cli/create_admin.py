"""CLI: create initial SYSTEM_ADMIN (Self Signup is OFF)."""

from __future__ import annotations

import getpass
import sys

from app.core.errors import AppError
from app.core.logging import setup_logging
from app.db.session import get_session_factory, reset_engine
from app.services.auth import create_admin_user


def main() -> int:
    setup_logging("INFO")
    print("IdeaFlow — create SYSTEM_ADMIN")
    email = input("Email: ").strip()
    name = input("Name: ").strip()
    password = getpass.getpass("Password: ")
    password2 = getpass.getpass("Confirm password: ")
    if password != password2:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    if not email or not name:
        print("Email and name are required.", file=sys.stderr)
        return 1

    reset_engine()
    session = get_session_factory()()
    try:
        user = create_admin_user(session, email=email, name=name, password=password)
        session.commit()
        print(
            f"Created SYSTEM_ADMIN id={user.id} email={user.email} "
            "(personal workspace provisioned)"
        )
        return 0
    except AppError as exc:
        session.rollback()
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:
        session.rollback()
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
