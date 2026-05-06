FROM postgres:16-bookworm

# HNSW do pgvector limita dimensões a 2000 por defeito; ORION usa 3072.
# Compilar pgvector com HNSW_MAX_DIM=4096 (ver src/hnsw.h no upstream).
ARG PGVECTOR_VERSION=v0.8.2
ARG HNSW_MAX_DIM=4096

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        git \
        postgresql-server-dev-16; \
    git clone --depth 1 --branch "${PGVECTOR_VERSION}" https://github.com/pgvector/pgvector.git /tmp/pgvector; \
    sed -i "s/^#define HNSW_MAX_DIM 2000\$/#define HNSW_MAX_DIM ${HNSW_MAX_DIM}/" /tmp/pgvector/src/hnsw.h; \
    make -C /tmp/pgvector -j"$(nproc)"; \
    make -C /tmp/pgvector install; \
    rm -rf /tmp/pgvector; \
    apt-get purge -y --auto-remove build-essential git postgresql-server-dev-16; \
    rm -rf /var/lib/apt/lists/*
