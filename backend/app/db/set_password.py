# Copyright (c) 2025–2026 Athena Decisions Systems SAS. All rights reserved.
# Proprietary and confidential — unauthorized copying or distribution is prohibited.

"""Reset a user's password from the command line.

Usage: python -m app.db.set_password <email> <new-password>
Invoked by `./xcape.sh reset-password <env> <email> <password>`.
"""

from __future__ import annotations

import sys

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: python -m app.db.set_password <email> <password>")
        sys.exit(2)
    email, password = sys.argv[1].strip().lower(), sys.argv[2]
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print(f"User not found: {email}")
            sys.exit(1)
        user.password_hash = hash_password(password)
        db.commit()
        print(f"Password reset for {user.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
