FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir pip setuptools wheel \
    && pip install --no-cache-dir -e .
ENV PYTHONPATH=/app/src
EXPOSE 8010
CMD ["python", "-m", "uvicorn", "orion_mcp_v2.main:app", "--host", "0.0.0.0", "--port", "8010"]
