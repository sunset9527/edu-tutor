"""运行 v1.7 MySQL 知识构建 worker。"""

import argparse
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.services.knowledge.build_repository import claim_next_task  # noqa: E402
from app.services.knowledge.build_worker import KnowledgeBuildWorker  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="EduTutor 知识构建 worker")
    parser.add_argument("--once", action="store_true", help="无任务或处理一项后退出")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    worker_id = f"worker-{uuid.uuid4().hex[:12]}"
    worker = KnowledgeBuildWorker()

    while True:
        db = SessionLocal()
        try:
            task = claim_next_task(
                db,
                worker_id=worker_id,
                now=datetime.now(),
                lease_seconds=120,
            )
        finally:
            db.close()
        if task is None:
            if args.once:
                return 0
            time.sleep(max(0.2, args.poll_seconds))
            continue
        result = worker.process_task(task.id, worker_id=worker_id)
        print(f"task={task.id} status={result['status']} version={result['version_id']}")
        if args.once:
            return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
