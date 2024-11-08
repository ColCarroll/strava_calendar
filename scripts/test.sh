# Install dev dependencies
pip install ".[dev]"

# Format code
black .

# Run type checking
pytype

# Run linter
ruff check .

# Run tests with coverage
pytest