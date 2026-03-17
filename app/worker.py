# app/worker.py — Loop do worker: consome fila e chama MaestroService
import logging
import threading
from typing import Optional

from app.core.deps import get_config, get_maestro_service
from app.infrastructure.queue import InMemoryQueue

logger = logging.getLogger("app.worker")

# Fila global (pode ser injetada depois)
_default_queue: Optional[InMemoryQueue] = None


def get_queue() -> InMemoryQueue:
    global _default_queue
    if _default_queue is None:
        _default_queue = InMemoryQueue()
    return _default_queue


def _run_job(job_id: str):
    """Executa um job (chamado em thread)."""
    q = get_queue()
    job = q.get_job(job_id)
    if not job or job.status != "pending":
        return
    q.set_job_running(job_id)
    try:
        settings = get_config()
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key or None)
        maestro = get_maestro_service(settings=settings, client=client)
        resultado = maestro.run(
            pergunta=job.pergunta,
            verbose=job.params.get("verbose", False),
            **{k: v for k, v in job.params.items() if k != "verbose"},
        )
        q.set_job_result(job_id, resultado=resultado)
    except Exception as e:
        logger.exception("Job %s falhou: %s", job_id, e)
        q.set_job_result(job_id, erro=str(e))


def run_worker_loop(block: bool = True, timeout: Optional[float] = 1.0):
    """Consome a fila e processa jobs (loop infinito até não haver mais job ou timeout)."""
    q = get_queue()
    while True:
        job_id = q.get(block=block, timeout=timeout)
        if job_id is None:
            if block:
                continue
            break
        _run_job(job_id)


def start_worker_thread(daemon: bool = True) -> threading.Thread:
    """Inicia o worker em uma thread em background."""
    def _loop():
        run_worker_loop(block=True, timeout=1.0)
    t = threading.Thread(target=_loop, daemon=daemon)
    t.start()
    return t
