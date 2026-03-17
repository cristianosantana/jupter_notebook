# app/infrastructure/queue.py — Fila em memória para jobs
import queue
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid


@dataclass
class Job:
    """Um job enfileirado (pergunta + parâmetros)."""
    id: str
    pergunta: str
    params: Dict[str, Any]
    status: str = "pending"  # pending | running | done | failed
    resultado: Optional[Dict[str, Any]] = None
    erro: Optional[str] = None


class InMemoryQueue:
    """Fila em memória de jobs para o Maestro."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._jobs: Dict[str, Job] = {}

    def put(self, pergunta: str, params: Optional[Dict[str, Any]] = None) -> str:
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, pergunta=pergunta, params=params or {})
        self._jobs[job_id] = job
        self._q.put(job_id)
        return job_id

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[str]:
        try:
            return self._q.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def set_job_result(self, job_id: str, resultado: Optional[Dict] = None, erro: Optional[str] = None):
        job = self._jobs.get(job_id)
        if job:
            job.status = "failed" if erro else "done"
            job.resultado = resultado
            job.erro = erro

    def set_job_running(self, job_id: str):
        job = self._jobs.get(job_id)
        if job:
            job.status = "running"
