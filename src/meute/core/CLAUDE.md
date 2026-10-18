# meute.core rules

- Standard library only; import only `meute.core.*` (see the import-linter contracts).
- `__init__.py` holds a docstring and no import; import the precise submodule.
- Google-style docstrings on every public item.
- All `datetime` values are timezone-aware; instants are normalised to UTC.
- Errors derive from `MeuteError` (`errors.py`); `OSError` and `sqlite3.Error` propagate as is.
- Frozen, slotted, keyword-only dataclasses; files under 300 lines.
