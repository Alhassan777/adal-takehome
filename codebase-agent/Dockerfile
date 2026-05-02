FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ripgrep \
    nodejs \
    npm \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g pyright && pyright --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/.cache

ENV PYTHONPATH=/app/src

ENTRYPOINT ["python", "-m", "codebase_agent.cli.main"]
CMD ["--help"]
