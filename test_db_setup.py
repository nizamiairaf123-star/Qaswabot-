# [AUDIT F7 FIX, 2026-09-16] This file had zero guarding and zero
# sandboxing -- merely running `python3 test_db_setup.py` called
# database.init_db() straight against the real release-tree data/,
# with no __main__ guard and no isolation at all. `import conftest`
# activates the same temp-dir sandbox pytest already gets (see
# conftest.py) -- safe as a no-op if pytest already imported it,
# and self-cleaning (atexit) if run standalone.
import conftest  # noqa: F401
import database
database.init_db()
