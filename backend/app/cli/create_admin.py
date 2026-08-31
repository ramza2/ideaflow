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

_MIN_PASSWORD_LENGTH = 10
_MAX_PASSWORD_LENGTH = 256


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


def _prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print(f"{label} is required.", file=sys.stderr)
        print("Please try again.\n", file=sys.stderr)


def _password_validation_error(password: str, password_confirm: str) -> str | None:
    if password != password_confirm:
        return "Passwords do not match."
    if len(password) < _MIN_PASSWORD_LENGTH or len(password) > _MAX_PASSWORD_LENGTH:
        return "Password must be 10–256 characters."
    return None


def _prompt_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        error = _password_validation_error(password, password_confirm)
        if error is None:
            return password
        print(error, file=sys.stderr)
        print("Please try again.\n", file=sys.stderr)


def _prompt_interactive_credentials() -> tuple[str, str, str]:
    print("IdeaFlow — create SYSTEM_ADMIN")
    email = _prompt_required("Email")
    name = _prompt_required("Name")
    password = _prompt_password()
    return email, name, password


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

        email, name, password = _prompt_interactive_credentials()

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
