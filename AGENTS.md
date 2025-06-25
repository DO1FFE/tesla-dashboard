# AGENTS instructions

This repository contains a Flask dashboard for monitoring Tesla vehicles. It uses
`app.py` as the entry point, HTML templates under `templates/`, and static files
under `static/`.  Documentation and example files are located in `docs/`.

## General workflow

- Run `pytest -q` after every change. The project currently has no tests so the
  command should report `no tests ran`.
- Avoid automatic code formatters like `black` or `isort` unless explicitly
  requested. Follow PEP 8 conventions manually.
- Keep commit messages short and in English, describing what the change does.
- Update `requirements.txt` whenever new Python dependencies are added.
- Do not delete or rename existing files without strong justification.

## Documentation

- The `docs/` directory contains reference material and example data in German.
  Do **not** modify these files when altering code. Any new documentation must
  also be written in German.

## Templates and static assets

- HTML templates in `templates/` may be updated to support code changes but
  should remain compatible with Flask's `render_template` function.
- Static JavaScript and CSS files live in `static/`. Keep them organised and
  minimise external dependencies.

## Versioning

- `version.py` derives the application version from the Git commit count.
  Incrementing the version happens automatically through commits.

## Running locally

- Use `python app.py` to start the development server on port 8013.
- The application loads configuration from a `.env` file using `python-dotenv`.


