"""在临时 MySQL 库中验证 v1.7 Alembic 降级再升级。"""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings


TEMP_DB = f"edu_tutor_v17_migration_check_{uuid4().hex[:12]}"
V17_REVISION = "31b933ce603d"
PRE_V17_REVISION = "39c8a7d1e2f4"
REQUIRED_TABLES = {
    "textbooks",
    "knowledge_versions",
    "knowledge_build_tasks",
    "knowledge_build_units",
    "knowledge_source_chunks",
    "knowledge_reviews",
    "knowledge_review_items",
    "answer_evidence_ledgers",
    "correction_tickets",
}


def _connection(database: str | None = None):
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def _alembic(*args: str) -> None:
    env = os.environ.copy()
    env["MYSQL_DB"] = TEMP_DB
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, env=env)


def run() -> dict:
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE `{TEMP_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    _alembic("upgrade", "head")
    with _connection(TEMP_DB) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM alembic_version")
        initial_revision = cursor.fetchone()[0]
        cursor.execute("SHOW TABLES")
        upgraded_tables = {row[0] for row in cursor.fetchall()}
    _alembic("downgrade", PRE_V17_REVISION)
    with _connection(TEMP_DB) as connection, connection.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE 'textbooks'")
        textbooks_after_downgrade = bool(cursor.fetchone())
    _alembic("upgrade", V17_REVISION)
    with _connection(TEMP_DB) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM alembic_version")
        restored_revision = cursor.fetchone()[0]
        cursor.execute("SHOW TABLES")
        restored_tables = {row[0] for row in cursor.fetchall()}
    return {
        "temporary_database": TEMP_DB,
        "initial_revision": initial_revision,
        "v17_downgrade_removed_textbooks": not textbooks_after_downgrade,
        "restored_revision": restored_revision,
        "required_tables_restored": sorted(REQUIRED_TABLES - restored_tables) == [],
        "initial_upgrade_has_required_tables": sorted(REQUIRED_TABLES - upgraded_tables) == [],
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=2))
