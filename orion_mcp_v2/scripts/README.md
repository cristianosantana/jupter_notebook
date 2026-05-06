## 3. Migrations “não rodaram”

O script **`scripts/migrate.py`** só corre se:

1. Existir **`ORION_V2_DATABASE_URL`** apontando para um Postgres **acessível** (mesmo host/porta que o cliente asyncpg alcança).
2. Executares o script **explicitamente** (`python scripts/migrate.py`) — **não** faz parte automática do `docker compose up` da API no compose que vimos.

Se o Postgres não estava a responder (como no log anterior “Connection refused”), **não há como aplicar migrações** até o URL estar certo e o serviço Postgres a aceitar ligações. Depois disso: definir `ORION_V2_DATABASE_URL`, correr `migrate.py`, e só então a API passa a poder persistir estado nas tabelas migradas.
