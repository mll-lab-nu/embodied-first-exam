"""Package marker so `python -m tests.<name>` resolves to THIS directory.

Not optional, and not a style choice. `draccus` (pulled in by `lerobot`) installs
its own test suite into site-packages as a top-level `tests` package, `__init__.py`
and all. Python's import scan takes a directory with an `__init__.py` as a regular
package and stops there; a directory without one is only recorded as a namespace
portion, used only if nothing on the whole path provides the name. So an
`__init__.py`-less `tests/` at the front of `sys.path` still loses to
site-packages, and every `python -m tests.<name>` in `cli_commands.txt` fails with
`No module named tests.<name>` -- pointing at the module, not at the shadowing,
which is what makes it worth a file of its own to explain.

Deliberately empty otherwise: nothing here should import at collection time. The
scripts in this directory are run individually and several are written to work
outside the project venv (`check_axial_insert_tilt.py` loads the module under test
by path for exactly that reason).
"""
