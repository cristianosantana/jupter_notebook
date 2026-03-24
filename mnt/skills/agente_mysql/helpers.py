"""
agente_mysql/helpers.py
=======================
Conecta ao MySQL via SQLAlchemy e carrega tabelas como pd.DataFrame.

Tabela única:
    agent = MySQLAgent(host=..., banco=..., usuario=..., senha=...)
    resultado = agent.carregar_tabela("os_servicos", limite=50.000)
    df = resultado["dataframe"]

Múltiplas tabelas com LEFT JOINs (retorna 1 único DataFrame):
    resultado = agent.carregar_multiplas_tabelas([
        {"tabela": "os_servicos",  "alias": "os"},
        {"tabela": "servicos",     "alias": "s",  "fk": "os.servico_id = s.id"},
        {"tabela": "clientes",     "alias": "c",  "fk": "os.cliente_id = c.id"},
    ], limite=50.000)
    df = resultado["dataframe"]   # único df com colunas de todas as tabelas

Onde a query principal roda e o resultado sai:
    - ``pd.read_sql(...)`` em ``carregar_tabela``, ``carregar_multiplas_tabelas`` e ``executar_select`` (SELECT nos dados).
    - O dict padronizado é montado em ``_montar_retorno`` (chave ``dataframe`` + metadados).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError


# ---------------------------------------------------------------------------
# Configuração de conexão
# ---------------------------------------------------------------------------

@dataclass
class MySQLConexao:
    host: str = "localhost"
    porta: int = 3306
    usuario: str = "root"
    senha: str = ""
    banco: str = ""
    charset: str = "utf8mb4"
    dsn: Optional[str] = None

    def build_dsn(self) -> str:
        if self.dsn:
            return self.dsn
        return (
            f"mysql+pymysql://{self.usuario}:{self.senha}"
            f"@{self.host}:{self.porta}/{self.banco}"
            f"?charset={self.charset}"
        )


# ---------------------------------------------------------------------------
# Definição de tabela para JOIN
# ---------------------------------------------------------------------------

@dataclass
class DefinicaoTabela:
    """
    Descreve uma tabela participante do JOIN.

    tabela  : nome da tabela no banco.
    alias   : alias SQL (ex: "os" para "os_servicos").
              Se omitido, usa o nome da tabela.
    fk      : condição de JOIN no formato "alias_a.col = alias_b.col"
              (obrigatório para tabelas não-principais).
              Ex: "os.servico_id = s.id"
    colunas : lista de "alias.coluna" ou "alias.*" a selecionar.
              None = alias.* (todas as colunas da tabela).
    """
    tabela: str
    alias: str = ""
    fk: Optional[str] = None
    colunas: Optional[List[str]] = None

    def __post_init__(self):
        if not self.alias:
            self.alias = self.tabela

    @staticmethod
    def from_dict(d: Dict) -> "DefinicaoTabela":
        return DefinicaoTabela(
            tabela  = d["tabela"],
            alias   = d.get("alias", d["tabela"]),
            fk      = d.get("fk"),
            colunas = d.get("colunas"),
        )

    def select_clause(self) -> str:
        """Gera o trecho SELECT desta tabela."""
        if self.colunas:
            return ", ".join(self.colunas)
        return f"`{self.alias}`.*"

    def join_clause(self) -> str:
        """Gera o LEFT JOIN desta tabela (exige fk definida)."""
        if not self.fk:
            raise ValueError(f"DefinicaoTabela '{self.tabela}' requer 'fk' para fazer JOIN.")
        return f"LEFT JOIN `{self.tabela}` AS `{self.alias}` ON {self.fk}"


# ---------------------------------------------------------------------------
# Metadados de coluna
# ---------------------------------------------------------------------------

@dataclass
class MetadadosColuna:
    nome: str
    tipo: str
    nullable: bool
    primary_key: bool
    cardinalidade: Optional[int] = None
    nulos: Optional[int] = None
    percentual_nulos: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "nome": self.nome, "tipo": self.tipo,
            "nullable": self.nullable, "primary_key": self.primary_key,
            "cardinalidade": self.cardinalidade,
            "nulos": self.nulos, "percentual_nulos": self.percentual_nulos,
        }


# ---------------------------------------------------------------------------
# Resultado de carregamento
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCarregamento:
    sucesso: bool
    tabela: str          # nome da tabela principal (ou "join" para múltiplas)
    banco: str
    total_linhas: int = 0
    linhas_carregadas: int = 0
    colunas: List[MetadadosColuna] = field(default_factory=list)
    dataframe: Optional[pd.DataFrame] = None
    variavel_notebook: str = ""
    df_info_str: str = ""
    query_executada: str = ""
    erro: Optional[str] = None

    def to_agent_json(self) -> Dict[str, Any]:
        if not self.sucesso:
            return {
                "agente_id": "agente_mysql", "agente_nome": "MySQL Data Loader",
                "pode_responder": False,
                "justificativa_viabilidade": self.erro or "Falha desconhecida.",
                "resposta": "", "metadados": {},
                "scores": {"relevancia": 0.0, "completude": 0.0, "confianca": 0.0, "score_final": 0.0},
                "limitacoes_da_resposta": "Falha na conexão ou tabela não encontrada.",
                "aspectos_para_outros_agentes": "",
            }
        completude = self.linhas_carregadas / self.total_linhas if self.total_linhas > 0 else 1.0
        resposta = (
            f"DataFrame '{self.variavel_notebook}' carregado com "
            f"{self.linhas_carregadas:,} linhas e {len(self.colunas)} colunas."
        )
        if self.linhas_carregadas < self.total_linhas:
            resposta += f" (parcial: {self.linhas_carregadas:,} de {self.total_linhas:,})"
        return {
            "agente_id": "agente_mysql", "agente_nome": "MySQL Data Loader",
            "pode_responder": True,
            "justificativa_viabilidade": f"Tabela '{self.tabela}' com {self.total_linhas:,} linhas.",
            "resposta": resposta,
            "metadados": {
                "tabela": self.tabela, "banco": self.banco,
                "total_linhas": self.total_linhas,
                "linhas_carregadas": self.linhas_carregadas,
                "colunas": [c.to_dict() for c in self.colunas],
                "df_info": self.df_info_str,
                "variavel_notebook": self.variavel_notebook,
                "query_executada": self.query_executada,
            },
            "scores": {
                "relevancia": 1.0, "completude": round(completude, 4), "confianca": 1.0,
                "score_final": round(0.4 + completude * 0.3 + 0.3, 4),
            },
            "limitacoes_da_resposta": (
                "Carregamento parcial ativo." if self.linhas_carregadas < self.total_linhas
                else "Nenhuma."
            ),
            "aspectos_para_outros_agentes": f"DataFrame '{self.variavel_notebook}' disponível para análise.",
        }

    def __repr__(self) -> str:
        s = "✅" if self.sucesso else "❌"
        return f"{s} ResultadoCarregamento(tabela={self.tabela!r}, linhas={self.linhas_carregadas}/{self.total_linhas})"


# ---------------------------------------------------------------------------
# Agente principal
# ---------------------------------------------------------------------------

class MySQLAgent:
    """
    Agente de carregamento de tabelas MySQL como DataFrame Pandas.

    Tabela única:
        agent = MySQLAgent(host=..., banco=..., usuario=..., senha=...)
        r = agent.carregar_tabela("os_servicos", limite=50.000)
        df = r["dataframe"]

    Múltiplas tabelas via LEFT JOIN (1 único DataFrame):
        r = agent.carregar_multiplas_tabelas([
            {"tabela": "os_servicos", "alias": "os"},
            {"tabela": "servicos",    "alias": "s", "fk": "os.servico_id = s.id"},
            {"tabela": "clientes",    "alias": "c", "fk": "os.cliente_id = c.id"},
        ], limite=50.000)
        df = r["dataframe"]   # colunas de todas as tabelas num único df

    SELECT arbitrário:
        r = agent.executar_select("SELECT id, nome FROM concessionarias LIMIT 10")
        df = r["dataframe"]
    """

    def __init__(
        self,
        host: str = "localhost",
        porta: int = 3306,
        usuario: str = "root",
        senha: str = "",
        banco: str = "",
        charset: str = "utf8mb4",
        dsn: Optional[str] = None,
    ):
        self.conexao = MySQLConexao(
            host=host, porta=porta, usuario=usuario,
            senha=senha, banco=banco, charset=charset, dsn=dsn,
        )
        self._engine: Optional[Engine] = None

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------

    def _get_engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(self.conexao.build_dsn(), pool_pre_ping=True)
        return self._engine

    def testar_conexao(self) -> bool:
        try:
            with self._get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))  # ping ao banco (não carrega dados de negócio)
            return True
        except (OperationalError, SQLAlchemyError):
            return False

    def listar_tabelas(self) -> List[str]:
        return inspect(self._get_engine()).get_table_names()

    # ------------------------------------------------------------------
    # Inspeção de metadados
    # ------------------------------------------------------------------

    def _inspecionar_colunas(self, tabela: str, total_linhas: int) -> List[MetadadosColuna]:
        engine    = self._get_engine()
        inspector = inspect(engine)
        cols_raw  = inspector.get_columns(tabela)
        pks       = set(inspector.get_pk_constraint(tabela).get("constrained_columns", []))
        colunas: List[MetadadosColuna] = []
        for col in cols_raw:
            nome = col["name"]
            cardinalidade = nulos = percentual_nulos = None
            if total_linhas <= 500_000:
                try:
                    with engine.connect() as conn:
                        # Execução auxiliar (metadados): DISTINCT + COUNT de nulos por coluna — não é o SELECT de dados.
                        cardinalidade = conn.execute(
                            text(f"SELECT COUNT(DISTINCT `{nome}`) FROM `{tabela}`")
                        ).scalar()
                        nulos = conn.execute(
                            text(f"SELECT COUNT(*) FROM `{tabela}` WHERE `{nome}` IS NULL")
                        ).scalar()
                        if total_linhas > 0:
                            percentual_nulos = round(nulos / total_linhas * 100, 2)
                except SQLAlchemyError:
                    pass
            colunas.append(MetadadosColuna(
                nome=nome, tipo=str(col["type"]),
                nullable=bool(col.get("nullable", True)),
                primary_key=nome in pks,
                cardinalidade=cardinalidade, nulos=nulos,
                percentual_nulos=percentual_nulos,
            ))
        return colunas

    def _inspecionar_colunas_df(self, df: pd.DataFrame) -> List[MetadadosColuna]:
        """Gera MetadadosColuna a partir de um DataFrame já carregado (para resultado de JOIN)."""
        colunas = []
        for i in range(len(df.columns)):
            serie = df.iloc[:, i]
            nome = str(df.columns[i]) if isinstance(df.columns[i], str) else str(i)
            colunas.append(MetadadosColuna(
                nome=nome, tipo=str(serie.dtype),
                nullable=bool(serie.isna().any()),
                primary_key=False,
                cardinalidade=int(serie.nunique()),
                nulos=int(serie.isna().sum()),
                percentual_nulos=round(serie.isna().mean() * 100, 2),
            ))
        return colunas

    def _contar_linhas(self, tabela: str, filtro_where: str = "") -> int:
        """Execução auxiliar: COUNT(*) na tabela (total ou com filtro). Não carrega linhas no Python."""
        where = f"WHERE {filtro_where}" if filtro_where.strip() else ""
        with self._get_engine().connect() as conn:
            return conn.execute(text(f"SELECT COUNT(*) FROM `{tabela}` {where}")).scalar() or 0

    def _capturar_df_info(self, df: pd.DataFrame) -> str:
        buf = io.StringIO()
        df.info(buf=buf)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Tabela única — API original inalterada
    # ------------------------------------------------------------------

    def carregar_tabela(
        self,
        tabela: str,
        limite: int = 50.000,
        filtro_where: str = "",
        colunas: Optional[List[str]] = None,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """Carrega uma tabela MySQL como DataFrame. API original inalterada."""
        resultado = ResultadoCarregamento(
            sucesso=False, tabela=tabela, banco=self.conexao.banco,
            variavel_notebook=f"df_{tabela}",
        )

        if verbose:
            print(f"[agente_mysql] Conectando ao banco '{self.conexao.banco}'...")

        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))  # valida conexão antes do SELECT de dados
        except (OperationalError, SQLAlchemyError) as e:
            resultado.erro = f"Falha na conexão: {e}"
            if verbose: print(f"[agente_mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        if tabela not in self.listar_tabelas():
            resultado.erro = f"Tabela '{tabela}' não encontrada no banco '{self.conexao.banco}'."
            if verbose: print(f"[agente_mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        if verbose: print(f"[agente_mysql] ✅ Tabela '{tabela}' encontrada.")

        total_linhas = self._contar_linhas(tabela, filtro_where)
        resultado.total_linhas = total_linhas
        if verbose:
            print(f"[agente_mysql] Total de linhas: {total_linhas:,}")
            print(f"[agente_mysql] Inspecionando metadados das colunas...")

        resultado.colunas = self._inspecionar_colunas(tabela, total_linhas)

        cols_sql = ", ".join(f"`{c}`" for c in colunas) if colunas else "*"
        where    = f"WHERE {filtro_where}" if filtro_where.strip() else ""
        query    = f"SELECT {cols_sql} FROM `{tabela}` {where} ORDER BY id DESC LIMIT {limite}"
        resultado.query_executada = query

        if verbose:
            print(f"[agente_mysql] Carregando dados (limite={limite:,})...")
            print(f"[agente_mysql] Query: {query}")

        try:
            # --- Ponto principal: execução da query de dados (tabela única) no MySQL e materialização em DataFrame ---
            df = pd.read_sql(query, con=engine)
        except SQLAlchemyError as e:
            resultado.erro = f"Erro ao executar query: {e}"
            if verbose: print(f"[agente_mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        resultado.sucesso = True
        resultado.linhas_carregadas = len(df)
        resultado.dataframe   = df
        resultado.df_info_str = self._capturar_df_info(df)

        if verbose:
            print(f"[agente_mysql] ✅ {len(df):,} linhas × {len(df.columns)} colunas → '{resultado.variavel_notebook}'")
            if len(df) < total_linhas:
                print(f"[agente_mysql] ⚠️  Parcial: {len(df):,} de {total_linhas:,}")

        # --- Retorno ao chamador: dict com dataframe + metadados (via _montar_retorno) ---
        return self._montar_retorno(resultado, df)

    # ------------------------------------------------------------------
    # Múltiplas tabelas via LEFT JOIN — retorna 1 único DataFrame
    # ------------------------------------------------------------------

    def carregar_multiplas_tabelas(
        self,
        definicoes: List[Dict],
        limite: int = 50.000,
        filtro_where: str = "",
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """
        Executa um SELECT com LEFT JOINs e retorna 1 único DataFrame.

        Parâmetros:
            definicoes   : lista de dicts, cada um com:
                - tabela  (obrigatório) — nome da tabela no banco
                - alias   (opcional)   — alias SQL; padrão = nome da tabela
                - fk      (obrigatório para tabelas não-principais)
                           formato: "alias_principal.col = alias_join.col"
                           ex:      "os.servico_id = s.id"
                - colunas (opcional)   — lista de "alias.col" a selecionar
                                         padrão = alias.* (todas)

            limite        : LIMIT na query principal (padrão 50.000).
            filtro_where  : cláusula WHERE adicional (sem a palavra WHERE).
                            Referencie colunas com alias: "os.cancelado = 0"
            verbose       : imprime progresso e query gerada.

        Retorna:
            Dict com as mesmas chaves de carregar_tabela():
                "dataframe"  → pd.DataFrame único com colunas de todas as tabelas
                "metadados"  → dict com colunas, df_info, query_executada
                "variavel"   → nome sugerido: "df_<tabela_principal>"
                "sucesso"    → bool
                "erro"       → str ou None

        Exemplo:
            resultado = agent.carregar_multiplas_tabelas([
                {"tabela": "os_servicos", "alias": "os"},
                {"tabela": "servicos",    "alias": "s", "fk": "os.servico_id = s.id"},
                {"tabela": "clientes",    "alias": "c", "fk": "os.cliente_id = c.id"},
            ], limite=50.000, filtro_where="os.cancelado = 0")

            df = resultado["dataframe"]
            # df tem colunas de os_servicos + servicos + clientes numa linha só
        """
        if not definicoes:
            r = ResultadoCarregamento(sucesso=False, tabela="", banco=self.conexao.banco,
                                      erro="Lista de definicoes vazia.")
            return self._montar_retorno(r, None)

        defs = [DefinicaoTabela.from_dict(d) for d in definicoes]
        tabela_principal = defs[0].tabela
        alias_principal  = defs[0].alias
        variavel_notebook = f"df_{tabela_principal}"

        resultado = ResultadoCarregamento(
            sucesso=False, tabela=tabela_principal,
            banco=self.conexao.banco, variavel_notebook=variavel_notebook,
        )

        if verbose:
            print(f"[agente_mysql] Conectando ao banco '{self.conexao.banco}'...")

        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))  # valida conexão antes do SELECT com JOIN
        except (OperationalError, SQLAlchemyError) as e:
            resultado.erro = f"Falha na conexão: {e}"
            if verbose: print(f"[agente_mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        # Valida que todas as tabelas existem
        tabelas_banco = self.listar_tabelas()
        for defn in defs:
            if defn.tabela not in tabelas_banco:
                resultado.erro = f"Tabela '{defn.tabela}' não encontrada no banco."
                if verbose: print(f"[agente_mysql] ❌ {resultado.erro}")
                return self._montar_retorno(resultado, None)

        if verbose:
            print(f"[agente_mysql] ✅ {len(defs)} tabela(s) validada(s): {[d.tabela for d in defs]}")

        # Conta linhas da tabela principal
        total_linhas = self._contar_linhas(tabela_principal, "")
        resultado.total_linhas = total_linhas
        if verbose:
            print(f"[agente_mysql] Linhas na tabela principal '{tabela_principal}': {total_linhas:,}")

        # Monta a query com LEFT JOINs
        select_parts = [defn.select_clause() for defn in defs]
        select_sql   = ", ".join(select_parts)

        join_clauses = [defn.join_clause() for defn in defs[1:]]
        joins_sql    = "\n  ".join(join_clauses)

        where_clause = f"WHERE {filtro_where}" if filtro_where.strip() else ""

        query = (
            f"SELECT {select_sql}\n"
            f"FROM `{tabela_principal}` AS `{alias_principal}`\n"
            + (f"  {joins_sql}\n" if joins_sql else "")
            + (f"{where_clause}\n" if where_clause else "")
            + f"ORDER BY `{alias_principal}`.id DESC\n"
            f"LIMIT {limite}"
        )
        resultado.query_executada = query

        if verbose:
            print(f"[agente_mysql] Query gerada:\n{query}\n")
            print(f"[agente_mysql] Executando query (limite={limite:,})...")

        try:
            # --- Ponto principal: execução da query de dados (JOIN multi-tabela) no MySQL e materialização em DataFrame ---
            df = pd.read_sql(query, con=engine)
        except SQLAlchemyError as e:
            resultado.erro = f"Erro ao executar query com JOIN: {e}"
            if verbose: print(f"[agente_mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        resultado.sucesso = True
        resultado.linhas_carregadas = len(df)
        resultado.dataframe   = df
        resultado.colunas     = self._inspecionar_colunas_df(df)
        resultado.df_info_str = self._capturar_df_info(df)

        if verbose:
            print(f"[agente_mysql] ✅ DataFrame carregado: {len(df):,} linhas × {len(df.columns)} colunas → '{variavel_notebook}'")
            if len(df) < total_linhas:
                print(f"[agente_mysql] ⚠️  Parcial: {len(df):,} de {total_linhas:,}")

        # --- Retorno ao chamador: dict com dataframe + metadados (via _montar_retorno) ---
        return self._montar_retorno(resultado, df)

    def executar_select(
        self,
        sql: str,
        verbose: bool = True,
        variavel_notebook: str = "df_select",
    ) -> Dict[str, Any]:
        """
        Executa um SELECT SQL arbitrário e retorna o mesmo dict padronizado que ``carregar_tabela``.

        Parâmetros:
            sql: texto completo do SELECT (sem ponto e vírgula obrigatório no final).
            verbose: imprime progresso e query.
            variavel_notebook: nome sugerido para injeção no namespace.

        Retorno:
            ``sucesso``, ``dataframe``, ``erro``, ``metadados`` (inclui ``query_executada``), ``variavel``.
        """
        sql = (sql or "").strip()
        resultado = ResultadoCarregamento(
            sucesso=False,
            tabela="(select)",
            banco=self.conexao.banco,
            variavel_notebook=variavel_notebook,
            query_executada=sql,
        )

        if not sql:
            resultado.erro = "SQL vazio."
            if verbose:
                print(f"[agente_mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        if verbose:
            print(f"[agente_mysql] Conectando ao banco '{self.conexao.banco}'...")

        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except (OperationalError, SQLAlchemyError) as e:
            resultado.erro = f"Falha na conexão: {e}"
            if verbose:
                print(f"[agente_mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        if verbose:
            print("[agente_mysql] Executando SELECT livre...")
            print(f"[agente_mysql] Query:\n{sql}\n")

        try:
            engine = self._get_engine()
            df = pd.read_sql(text(sql), con=engine)
        except SQLAlchemyError as e:
            resultado.erro = f"Erro ao executar query: {e}"
            if verbose:
                print(f"[agente_mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        resultado.sucesso = True
        resultado.linhas_carregadas = len(df)
        resultado.total_linhas = len(df)
        resultado.dataframe = df
        resultado.colunas = self._inspecionar_colunas_df(df)
        resultado.df_info_str = self._capturar_df_info(df)

        if verbose:
            print(
                f"[agente_mysql] ✅ {len(df):,} linhas × {len(df.columns)} colunas "
                f"→ '{variavel_notebook}'"
            )

        return self._montar_retorno(resultado, df)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _montar_retorno(self, resultado: ResultadoCarregamento, df) -> Dict[str, Any]:
        """Único lugar que estrutura o retorno público: ``dataframe``, ``metadados``, ``variavel``, ``sucesso``, ``erro``."""
        return {
            "dataframe": df,
            "metadados": {
                "tabela": resultado.tabela, "banco": resultado.banco,
                "total_linhas": resultado.total_linhas,
                "linhas_carregadas": resultado.linhas_carregadas,
                "colunas": [c.to_dict() for c in resultado.colunas],
                "variavel_notebook": resultado.variavel_notebook,
                "df_info": resultado.df_info_str,
                "query_executada": resultado.query_executada,
            },
            "agente_json": resultado.to_agent_json(),
            "variavel": resultado.variavel_notebook,
            "sucesso": resultado.sucesso,
            "erro": resultado.erro,
        }

    def resumo_tabela(self, tabela: str) -> None:
        inspector = inspect(self._get_engine())
        colunas   = inspector.get_columns(tabela)
        pks       = inspector.get_pk_constraint(tabela).get("constrained_columns", [])
        total     = self._contar_linhas(tabela)
        print(f"\n📋 Tabela: {tabela} ({total:,} linhas)")
        print(f"{'Coluna':<30} {'Tipo':<25} {'Nullable':<10} PK")
        print("-" * 75)
        for col in colunas:
            print(f"{col['name']:<30} {str(col['type']):<25} {'SIM' if col.get('nullable') else 'NÃO':<10} {'✅' if col['name'] in pks else ''}")

    def injetar_no_namespace(self, resultado: Dict[str, Any], namespace: Dict) -> None:
        if resultado["sucesso"] and resultado["dataframe"] is not None:
            var = resultado["variavel"]
            namespace[var] = resultado["dataframe"]
            print(f"[agente_mysql] ✅ '{var}' injetado com {len(resultado['dataframe']):,} linhas.")
        else:
            print(f"[agente_mysql] ❌ {resultado['erro']}")


# ---------------------------------------------------------------------------
# Conveniência
# ---------------------------------------------------------------------------

def carregar_tabela_mysql(
    tabela: str,
    host: str = "localhost", porta: int = 3306,
    usuario: str = "root", senha: str = "", banco: str = "",
    limite: int = 50.000, filtro_where: str = "",
    injetar_globals: Optional[Dict] = None, verbose: bool = True,
) -> Dict[str, Any]:
    """Função de conveniência para tabela única."""
    agent = MySQLAgent(host=host, porta=porta, usuario=usuario, senha=senha, banco=banco)
    resultado = agent.carregar_tabela(tabela=tabela, limite=limite,
                                      filtro_where=filtro_where, verbose=verbose)
    if injetar_globals is not None:
        agent.injetar_no_namespace(resultado, injetar_globals)
    return resultado

def carregar_multiplas_tabelas_mysql(
    definicoes: List[Dict],
    host: str = "localhost", porta: int = 3306,
    usuario: str = "root", senha: str = "", banco: str = "",
    limite: int = 50.000, filtro_where: str = "",
    injetar_globals: Optional[Dict] = None, verbose: bool = True,
) -> Dict[str, Any]:
    """Função de conveniência para múltiplas tabelas."""
    agent = MySQLAgent(host=host, porta=porta, usuario=usuario, senha=senha, banco=banco)
    resultado = agent.carregar_multiplas_tabelas(definicoes=definicoes, limite=limite,
                                                 filtro_where=filtro_where, verbose=verbose)
    if injetar_globals is not None:
        agent.injetar_no_namespace(resultado, injetar_globals)
    return resultado

def executar_select_mysql(
    sql: str,
    host: str = "localhost", porta: int = 3306,
    usuario: str = "root", senha: str = "", banco: str = "",
    injetar_globals: Optional[Dict] = None, verbose: bool = True,
) -> Dict[str, Any]:
    """Função de conveniêdo executar SELECT."""
    agent = MySQLAgent(host=host, porta=porta, usuario=usuario, senha=senha, banco=banco)
    resultado = agent.executar_select(sql=sql, verbose=verbose)

    if injetar_globals is not None:
        agent.injetar_no_namespace(resultado, injetar_globals)
    return resultado