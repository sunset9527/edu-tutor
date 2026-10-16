"""显式设置 EduTutor 用户角色。"""

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="设置用户角色")
    parser.add_argument("username")
    parser.add_argument("role", choices=("user", "admin"))
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if not user:
            print(f"用户不存在: {args.username}", file=sys.stderr)
            return 1
        user.role = args.role
        db.commit()
        print(f"已将 {args.username} 设置为 {args.role}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
