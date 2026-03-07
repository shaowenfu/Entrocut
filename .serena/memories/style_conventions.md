# Style and conventions
- Repository language mix: TypeScript frontend, Python backend.
- Prefer minimal, boundary-respecting edits; do not expand change scope in shared workspace.
- Keep frozen contracts, event names, and reserved entrypoints stable unless explicitly approved.
- Python code uses type hints and dataclass/Pydantic models; shell scripts commonly activate virtualenv with `source venv/bin/activate` before Python commands.
- Validation preference: small repeatable shell scripts with inline Python/Node assertions rather than introducing a new test framework.
- For local search in code, prefer `rg`; for manual edits, use focused patches instead of broad formatting sweeps.