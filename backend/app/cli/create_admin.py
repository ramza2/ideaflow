"""CLI: create initial SYSTEM_ADMIN (Self Signup is OFF)."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.errors import AppError
from app.core.logging import setup_logging
from app.db.session import get_session_factory, reset_engine
from app.models.enums import SystemRole, UserStatus
from app.models.user import User
from app.services.auth import create_admin_user


def active_system_admin_exists(session) -> bool:
    stmt = (
        select(User.id)
        .where(
            User.system_role == SystemRole.SYSTEM_ADMIN.value,
            User.deleted_at.is_(None),
            User.status == UserStatus.ACTIVE.value,
        )
        .limit(1)
    )
    return session.scalar(stmt) is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or check SYSTEM_ADMIN")
    parser.add_argument(
        "--exists",
        action="store_true",
        help="Exit 0 if an ACTIVE SYSTEM_ADMIN exists, 1 if none, 2 on error",
    )
    args = parser.parse_args()

    setup_logging("INFO")
    reset_engine()
    session = get_session_factory()()
    try:
        if args.exists:
            try:
                return 0 if active_system_admin_exists(session) else 1
            except Exception as exc:
                print(f"Error checking SYSTEM_ADMIN: {exc}", file=sys.stderr)
                return 2

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
