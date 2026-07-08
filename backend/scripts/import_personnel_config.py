from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import SessionLocal
from app.personnel_importer import import_personnel_config, resolve_personnel_config_file


def main() -> None:
    source_file = Path(sys.argv[1]) if len(sys.argv) > 1 else resolve_personnel_config_file()
    with SessionLocal() as db:
        result = import_personnel_config(db, source_file)
        db.commit()
    print(json.dumps({"source_file": str(source_file), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
