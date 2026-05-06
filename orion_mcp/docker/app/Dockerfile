FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md ./
COPY src ./src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip list | grep protobuf

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Comando por defeito: API HTTP (override no compose para o serviço MCP)
CMD ["python", "-m", "uvicorn", "orion_mcp.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
