"""在临时 MySQL 库中验证 v1.8 迁移可升级、降级和恢复。"""
import os, subprocess, sys
from pathlib import Path
from uuid import uuid4
import pymysql
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings

TEMP_DB=f"edu_tutor_v18_migration_check_{uuid4().hex[:12]}"
V18="e8b4a907c512"; PRE_V18="7efb3126a01c"
REQUIRED={"diagnostic_questions","diagnostic_sessions","diagnostic_answers","diagnostic_knowledge_results","learning_plan_versions","learning_plan_items"}
def conn(db=None): return pymysql.connect(host=settings.mysql_host,port=settings.mysql_port,user=settings.mysql_user,password=settings.mysql_password,database=db,charset="utf8mb4",autocommit=True)
def alembic(*args):
    env=os.environ.copy();env["MYSQL_DB"]=TEMP_DB
    subprocess.run([sys.executable,"-m","alembic",*args],check=True,env=env)
def run():
    with conn() as c:
        with c.cursor() as x:x.execute(f"CREATE DATABASE `{TEMP_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    alembic("upgrade",V18)
    with conn(TEMP_DB) as c:
        with c.cursor() as x:x.execute("SHOW TABLES");up={r[0] for r in x.fetchall()}
    alembic("downgrade",PRE_V18)
    with conn(TEMP_DB) as c:
        with c.cursor() as x:x.execute("SHOW TABLES LIKE 'diagnostic_questions'");removed=not bool(x.fetchone())
    alembic("upgrade",V18)
    with conn(TEMP_DB) as c:
        with c.cursor() as x:x.execute("SHOW TABLES");restored={r[0] for r in x.fetchall()}
    return {"temporary_database":TEMP_DB,"upgrade_has_required":REQUIRED<=up,"downgrade_removed_diagnostic_tables":removed,"restore_has_required":REQUIRED<=restored}
if __name__=="__main__":
    import json;print(json.dumps(run(),ensure_ascii=False,indent=2))
