"""Identical archive protections for table creation and normal upgrades."""
from sqlalchemy import DDL, event, text


def statements():
    fields = ("id user_id request_json request_hash context_json summary intention parent_id "
              "command_key title product_family pricing_date created_at").split()
    terminal = "('COMPLETED','PARTIAL','FAILED','INTERRUPTED')"
    changes = " OR ".join(f"NEW.{key} IS NOT OLD.{key}" for key in fields)
    final = " OR ".join(f"NEW.{key} IS NOT OLD.{key}" for key in
                        ("status", "result_json", "progress_json", "error", "finished_at"))
    return [
        "DROP TRIGGER IF EXISTS optimizer_research_immutable",
        f"""CREATE TRIGGER optimizer_research_immutable BEFORE UPDATE ON optimizer_researches
        WHEN {changes} OR (OLD.status IN {terminal} AND ({final}))
        BEGIN SELECT RAISE(ABORT, 'Optimizer research evidence is immutable'); END""",
        f"""CREATE TRIGGER IF NOT EXISTS optimizer_research_no_delete BEFORE DELETE ON optimizer_researches
        WHEN OLD.status IN {terminal}
        BEGIN SELECT RAISE(ABORT, 'Archive the terminal research instead of deleting its evidence'); END""",
    ]


def register(optimizer, archive, study):
    for sql in statements():
        event.listen(optimizer, "after_create", DDL(sql).execute_if(dialect="sqlite"))
    for sql in document_statements():
        event.listen(archive, "after_create", DDL(sql).execute_if(dialect="sqlite"))
    for sql in study_statements():
        event.listen(study, "after_create", DDL(sql).execute_if(dialect="sqlite"))


def study_statements():
    return [f"""CREATE TRIGGER IF NOT EXISTS variant_study_archives_no_{action.lower()}
        BEFORE {action} ON variant_study_archives BEGIN
        SELECT RAISE(ABORT, 'Archived study is immutable'); END""" for action in ("UPDATE", "DELETE")]


def document_statements():
    commands = []
    for action in ("UPDATE", "DELETE"):
        condition = ("WHEN NOT EXISTS (SELECT 1 FROM deals WHERE id=OLD.deal_id AND uat_batch_id IS NOT NULL)"
                     if action == "DELETE" else "")
        sql = f"""CREATE TRIGGER IF NOT EXISTS archived_documents_no_{action.lower()}
        BEFORE {action} ON archived_documents {condition} BEGIN
        SELECT RAISE(ABORT, 'Archived document is immutable'); END"""
        commands.append(sql)
    return commands


def migrate(conn):
    if conn.execute(text("SELECT 1 FROM sqlite_master WHERE name='optimizer_researches' AND type='table'")).first():
        for sql in statements():
            conn.execute(text(sql))
    if conn.execute(text("SELECT 1 FROM sqlite_master WHERE name='archived_documents' AND type='table'")).first():
        for sql in document_statements():
            conn.execute(text(sql))
    if conn.execute(text("SELECT 1 FROM sqlite_master WHERE name='variant_study_archives' AND type='table'")).first():
        for sql in study_statements():
            conn.execute(text(sql))
