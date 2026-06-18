FROM python:3.12-slim

# uv for dependency management (matches local workflow).
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App code + the access policy (policy.yaml must be present at runtime).
COPY . .

EXPOSE 8000

# Serves Streamable HTTP at /mcp/. The ChatGPT connector URL is https://<host>/mcp/.
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
