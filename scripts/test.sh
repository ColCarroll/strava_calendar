# Install dev dependencies
pip install ".[dev]"

# Run type checking
pytype

# Run linter
ruff check .

# Run tests with coverage
pytest