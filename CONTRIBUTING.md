# Contributing

Thanks for helping improve UNIVERSAL CONVERTER.

## Development setup

1. Use Windows 10/11 and Python 3.12 or newer.
2. Clone the repository and run `Install.bat`.
3. Run the tests with `\.\.venv\Scripts\python.exe -m pytest -q`.
4. Start the local app with `Start.bat` and stop it with `Stop.bat`.

## Changes

- Keep pull requests focused and explain the user-visible behavior they change.
- Add or update tests for behavior changes. Tests must use generated or in-memory fixtures, not local uploads or databases.
- Do not commit `.env` files, API keys, database files, uploads, generated conversions, virtual environments, or installer build output.
- For UI changes, include a screenshot in the pull request when it helps reviewers understand the result.
- For conversion changes, list the source and output formats and any optional external tools required.

## Pull requests

Open an issue for larger changes before starting implementation. Run `python -m pytest -q` before submitting. GitHub Actions runs the test suite on Windows for pushes and pull requests to `main`.