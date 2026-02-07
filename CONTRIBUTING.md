# Contributing to Code-Swap

Thanks for your interest in contributing. This guide covers the basics.

## Development Setup

```bash
git clone https://github.com/AskSid/code-swap.git
cd code-swap/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

You will need an [OpenRouter](https://openrouter.ai/) API key. Run `code-swap config` to set it up.

## Running Tests

```bash
cd backend
pytest
```

## Making Changes

1. Fork the repository.
2. Create a feature branch: `git checkout -b my-feature`
3. Make your changes and add tests if applicable.
4. Run linting: `ruff check . --fix`
5. Commit with a clear message.
6. Open a pull request against `main`.

## Code Style

- Formatter/linter: [Ruff](https://docs.astral.sh/ruff/)
- Line length: 100 characters
- Follow existing patterns in the codebase.

## Reporting Issues

Open an issue on GitHub with:
- Steps to reproduce
- Expected vs. actual behavior
- Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
