"""Explicit, backed-up repairs for jobs saved before alternative grouping was fixed."""
import argparse
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from . import database
from .models import RequirementsUpdate
from .requirements import repair_education


def repair_saved_education():
    changes = []
    for job in database.list_jobs():
        requirements = repair_education(job["requirements"], job["description"])
        if requirements != job["requirements"]:
            RequirementsUpdate(requirements=requirements)
            changes.append((job, requirements))
    if not changes:
        return {"changed_jobs": [], "backup": None}
    backup_dir = database.data_dir() / "backups"
    backup_dir.mkdir(exist_ok=True)
    path = backup_dir / f"before-education-repair-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}.sqlite3"
    with database.connection() as source:
        with closing(sqlite3.connect(path)) as target:
            source.backup(target)
    for job, requirements in changes:
        database.update_requirements(job["id"], requirements)
    return {"changed_jobs": [job["id"] for job, _ in changes], "backup": str(path)}


def main():
    parser = argparse.ArgumentParser(description="Repair previously split education alternatives; back up first.")
    parser.add_argument("operation", choices=["repair-education"])
    parser.parse_args()
    import json
    print(json.dumps(repair_saved_education(), indent=2))


if __name__ == "__main__":
    main()
