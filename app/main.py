# app/main.py — FastAPI app, rotas e lifespan
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from app.api.routes import health, pergunta, relatorio_os


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: carregar .env se necessário (opcional)
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Serviço Maestro",
    description="API do fluxo Maestro (perguntas + agentes + avaliador)",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(pergunta.router)
app.include_router(relatorio_os.router)
