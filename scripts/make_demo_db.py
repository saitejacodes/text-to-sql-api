"""Build examples/university.sqlite from examples/university.sql (the demo database)."""

import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parent.parent
db = root / "examples" / "university.sqlite"
db.unlink(missing_ok=True)
conn = sqlite3.connect(db)
conn.executescript((root / "examples" / "university.sql").read_text())
conn.commit()
conn.close()
print(f"wrote {db}")
