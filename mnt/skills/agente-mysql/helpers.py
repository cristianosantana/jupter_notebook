"""
agente-mysql/helpers.py
=======================
Métodos auxiliares para a skill agente-mysql.
Conecta ao MySQL via SQLAlchemy, inspeciona metadados
e carrega a tabela como pd.DataFrame.

Uso direto no notebook:
    from mnt.skills.agente_mysql.helpers import MySQLAgent
    agent = MySQLAgent(host=..., usuario=..., senha=..., banco=...)
    resultado = agent.carregar_tabela("nome_tabela")
    df = resultado["dataframe"]
"""

from __future__ import annotations

import json
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
    """Parâmetros de conexão com o banco MySQL."""
    host: str = "localhost"
    porta: int = 3306
    usuario: str = "root"
    senha: str = ""
    banco: str = ""
    charset: str = "utf8mb4"
    dsn: Optional[str] = None  # Se fornecido, sobrescreve os demais

    def build_dsn(self) -> str:
        """Monta a string de conexão SQLAlchemy."""
        if self.dsn:
            return self.dsn
        return (
            f"mysql+pymysql://{self.usuario}:{self.senha}"
            f"@{self.host}:{self.porta}/{self.banco}"
            f"?charset={self.charset}"
        )


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
            "nome": self.nome,
            "tipo": self.tipo,
            "nullable": self.nullable,
            "primary_key": self.primary_key,
            "cardinalidade": self.cardinalidade,
            "nulos": self.nulos,
            "percentual_nulos": self.percentual_nulos,
        }


# ---------------------------------------------------------------------------
# Resultado do carregamento
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCarregamento:
    sucesso: bool
    tabela: str
    banco: str
    total_linhas: int = 0
    linhas_carregadas: int = 0
    colunas: List[MetadadosColuna] = field(default_factory=list)
    dataframe: Optional[pd.DataFrame] = None
    variavel_notebook: str = ""
    amostra_head: Optional[pd.DataFrame] = None
    df_info_str: str = ""
    erro: Optional[str] = None
    scores: Dict[str, float] = field(default_factory=dict)

    def to_agent_json(self) -> Dict[str, Any]:
        """Serializa no formato padrão de retorno dos agentes do Maestro."""
        if not self.sucesso:
            return {
                "agente_id": "agente-mysql",
                "agente_nome": "MySQL Data Loader",
                "pode_responder": False,
                "justificativa_viabilidade": self.erro or "Falha desconhecida.",
                "resposta": "",
                "metadados": {},
                "scores": {"relevancia": 0.0, "completude": 0.0, "confianca": 0.0, "score_final": 0.0},
                "limitacoes_da_resposta": "Falha na conexão ou tabela não encontrada.",
                "aspectos_para_outros_agentes": "",
            }

        colunas_dict = [c.to_dict() for c in self.colunas]
        completude = (
            self.linhas_carregadas / self.total_linhas
            if self.total_linhas > 0
            else 1.0
        )
        scores = {
            "relevancia": 1.0,
            "completude": round(completude, 4),
            "confianca": 1.0,
            "score_final": round(0.4 + completude * 0.3 + 0.3, 4),
        }

        justificativa = (
            f"Conexão estabelecida. Tabela '{self.tabela}' encontrada "
            f"com {self.total_linhas:,} linhas."
        )
        resposta = (
            f"DataFrame '{self.variavel_notebook}' carregado com "
            f"{self.linhas_carregadas:,} linhas e {len(self.colunas)} colunas."
        )
        if self.linhas_carregadas < self.total_linhas:
            resposta += (
                f" (carregamento parcial: {self.linhas_carregadas:,} "
                f"de {self.total_linhas:,} linhas totais)"
            )

        outros_agentes = (
            f"DataFrame '{self.variavel_notebook}' disponível para análise. "
            f"Colunas numéricas adequadas para agente-dados ou agente-financeiro. "
            f"Use df_info abaixo para orientar qual agente invocar."
        )

        return {
            "agente_id": "agente-mysql",
            "agente_nome": "MySQL Data Loader",
            "pode_responder": True,
            "justificativa_viabilidade": justificativa,
            "resposta": resposta,
            "metadados": {
                "tabela": self.tabela,
                "banco": self.banco,
                "total_linhas": self.total_linhas,
                "linhas_carregadas": self.linhas_carregadas,
                "colunas": colunas_dict,
                "amostra": f"Disponível em {self.variavel_notebook}.head()",
                "df_info": self.df_info_str,
                "variavel_notebook": self.variavel_notebook,
            },
            "scores": scores,
            "limitacoes_da_resposta": (
                "Carregamento parcial ativo." if self.linhas_carregadas < self.total_linhas
                else "Nenhuma."
            ),
            "aspectos_para_outros_agentes": outros_agentes,
        }

    def __repr__(self) -> str:
        status = "✅" if self.sucesso else "❌"
        return (
            f"{status} ResultadoCarregamento(tabela={self.tabela!r}, "
            f"linhas={self.linhas_carregadas}/{self.total_linhas}, "
            f"colunas={len(self.colunas)})"
        )


# ---------------------------------------------------------------------------
# Agente principal
# ---------------------------------------------------------------------------

class MySQLAgent:
    """
    Agente de carregamento de tabelas MySQL como DataFrame Pandas.

    Exemplo de uso no notebook:
        agent = MySQLAgent(host="localhost", banco="vendas", usuario="root", senha="s3cr3t")
        resultado = agent.carregar_tabela("pedidos", limite=5000)
        df_pedidos = resultado["dataframe"]
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
            host=host,
            porta=porta,
            usuario=usuario,
            senha=senha,
            banco=banco,
            charset=charset,
            dsn=dsn,
        )
        self._engine: Optional[Engine] = None

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------

    def _get_engine(self) -> Engine:
        """Retorna (ou cria) o engine SQLAlchemy."""
        if self._engine is None:
            dsn = self.conexao.build_dsn()
            self._engine = create_engine(dsn, pool_pre_ping=True)
        return self._engine

    def testar_conexao(self) -> bool:
        """Verifica se a conexão com o banco está funcionando."""
        try:
            with self._get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except (OperationalError, SQLAlchemyError):
            return False

    def listar_tabelas(self) -> List[str]:
        """Retorna lista de tabelas disponíveis no banco."""
        inspector = inspect(self._get_engine())
        return inspector.get_table_names()

    # ------------------------------------------------------------------
    # Inspeção de metadados
    # ------------------------------------------------------------------

    def _inspecionar_colunas(self, tabela: str, total_linhas: int) -> List[MetadadosColuna]:
        """Extrai metadados de colunas via SQLAlchemy Inspector."""
        engine = self._get_engine()
        inspector = inspect(engine)

        # Colunas e tipos
        colunas_raw = inspector.get_columns(tabela)
        pks = {col for col in inspector.get_pk_constraint(tabela).get("constrained_columns", [])}

        colunas: List[MetadadosColuna] = []
        for col in colunas_raw:
            nome = col["name"]
            tipo = str(col["type"])
            nullable = bool(col.get("nullable", True))
            is_pk = nome in pks

            # Cardinalidade e nulos por coluna (apenas se tabela não for gigante)
            cardinalidade = None
            nulos = None
            percentual_nulos = None

            if total_linhas <= 500_000:
                try:
                    with engine.connect() as conn:
                        q_card = text(
                            f"SELECT COUNT(DISTINCT `{nome}`) FROM `{tabela}`"
                        )
                        cardinalidade = conn.execute(q_card).scalar()

                        q_null = text(
                            f"SELECT COUNT(*) FROM `{tabela}` WHERE `{nome}` IS NULL"
                        )
                        nulos = conn.execute(q_null).scalar()
                        if total_linhas > 0:
                            percentual_nulos = round(nulos / total_linhas * 100, 2)
                except SQLAlchemyError:
                    pass

            colunas.append(
                MetadadosColuna(
                    nome=nome,
                    tipo=tipo,
                    nullable=nullable,
                    primary_key=is_pk,
                    cardinalidade=cardinalidade,
                    nulos=nulos,
                    percentual_nulos=percentual_nulos,
                )
            )

        return colunas

    def _contar_linhas(self, tabela: str, filtro_where: str = "") -> int:
        """Conta total de linhas da tabela (com filtro opcional)."""
        where_clause = f"WHERE {filtro_where}" if filtro_where.strip() else ""
        query = text(f"SELECT COUNT(*) FROM `{tabela}` {where_clause}")
        with self._get_engine().connect() as conn:
            return conn.execute(query).scalar() or 0

    def _capturar_df_info(self, df: pd.DataFrame) -> str:
        """Captura o output de df.info() como string."""
        import io
        buf = io.StringIO()
        df.info(buf=buf)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Carregamento principal
    # ------------------------------------------------------------------

    def carregar_tabela(
        self,
        tabela: str,
        limite: int = 50_000,
        filtro_where: str = "",
        colunas: Optional[List[str]] = None,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """
        Carrega uma tabela MySQL como DataFrame Pandas.

        Parâmetros:
            tabela       : Nome da tabela a carregar.
            limite       : Número máximo de linhas (padrão: 50.000).
            filtro_where : Condição SQL sem a palavra WHERE. Ex: "status = 'ativo'"
            colunas      : Lista de colunas a selecionar (None = todas).
            verbose      : Imprime progresso no notebook.

        Retorna:
            Dict com chaves:
                "dataframe"       → pd.DataFrame carregado
                "metadados"       → dict com info das colunas
                "agente_json"     → payload padrão para o Maestro
                "variavel"        → nome sugerido para a variável no notebook
        """
        resultado = ResultadoCarregamento(sucesso=False, tabela=tabela, banco=self.conexao.banco)
        variavel_notebook = f"df_{tabela}"
        resultado.variavel_notebook = variavel_notebook

        if verbose:
            print(f"[agente-mysql] Conectando ao banco '{self.conexao.banco}'...")

        # 1. Testa conexão
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except (OperationalError, SQLAlchemyError) as e:
            resultado.erro = f"Falha na conexão: {e}"
            if verbose:
                print(f"[agente-mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        # 2. Verifica se tabela existe
        tabelas_disponiveis = self.listar_tabelas()
        if tabela not in tabelas_disponiveis:
            resultado.erro = (
                f"Tabela '{tabela}' não encontrada no banco '{self.conexao.banco}'. "
                f"Tabelas disponíveis: {tabelas_disponiveis}"
            )
            if verbose:
                print(f"[agente-mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        if verbose:
            print(f"[agente-mysql] ✅ Tabela '{tabela}' encontrada.")

        # 3. Conta linhas totais
        total_linhas = self._contar_linhas(tabela, filtro_where)
        resultado.total_linhas = total_linhas
        if verbose:
            print(f"[agente-mysql] Total de linhas na tabela: {total_linhas:,}")

        # 4. Inspeciona metadados das colunas
        if verbose:
            print(f"[agente-mysql] Inspecionando metadados das colunas...")
        cols_meta = self._inspecionar_colunas(tabela, total_linhas)
        resultado.colunas = cols_meta

        # 5. Monta e executa query de carregamento
        cols_sql = (
            ", ".join(f"`{c}`" for c in colunas) if colunas else "*"
        )
        where_clause = f"WHERE {filtro_where}" if filtro_where.strip() else ""
        query = f"SELECT {cols_sql} FROM `{tabela}` {where_clause} ORDER BY id DESC LIMIT {limite}"

        if verbose:
            print(f"[agente-mysql] Carregando dados (limite={limite:,})...")
            print(f"[agente-mysql] Query: {query}")

        try:
            df = pd.read_sql(query, con=engine)
        except SQLAlchemyError as e:
            resultado.erro = f"Erro ao executar query: {e}"
            if verbose:
                print(f"[agente-mysql] ❌ {resultado.erro}")
            return self._montar_retorno(resultado, None)

        resultado.sucesso = True
        resultado.linhas_carregadas = len(df)
        resultado.dataframe = df
        resultado.amostra_head = df.head(5)
        resultado.df_info_str = self._capturar_df_info(df)

        if verbose:
            print(f"[agente-mysql] ✅ DataFrame carregado: {len(df):,} linhas × {len(df.columns)} colunas")
            print(f"[agente-mysql] 💾 Disponível como: {variavel_notebook}")
            if len(df) < total_linhas:
                print(f"[agente-mysql] ⚠️  Carregamento parcial: {len(df):,} de {total_linhas:,} linhas")

        return self._montar_retorno(resultado, df)

    # ------------------------------------------------------------------
    # Helpers de retorno
    # ------------------------------------------------------------------

    def _montar_retorno(
        self,
        resultado: ResultadoCarregamento,
        df: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """Monta o dict de retorno padronizado para o notebook."""
        return {
            "dataframe": df,
            "metadados": {
                "tabela": resultado.tabela,
                "banco": resultado.banco,
                "total_linhas": resultado.total_linhas,
                "linhas_carregadas": resultado.linhas_carregadas,
                "colunas": [c.to_dict() for c in resultado.colunas],
                "variavel_notebook": resultado.variavel_notebook,
                "df_info": resultado.df_info_str,
            },
            "agente_json": resultado.to_agent_json(),
            "variavel": resultado.variavel_notebook,
            "sucesso": resultado.sucesso,
            "erro": resultado.erro,
        }

    # ------------------------------------------------------------------
    # Utilitários para o notebook
    # ------------------------------------------------------------------

    def resumo_tabela(self, tabela: str) -> None:
        """Imprime um resumo rápido da tabela sem carregar os dados."""
        engine = self._get_engine()
        inspector = inspect(engine)
        colunas = inspector.get_columns(tabela)
        pks = inspector.get_pk_constraint(tabela).get("constrained_columns", [])
        total = self._contar_linhas(tabela)

        print(f"\n📋 Tabela: {tabela} ({total:,} linhas)")
        print(f"{'Coluna':<30} {'Tipo':<25} {'Nullable':<10} {'PK'}")
        print("-" * 75)
        for col in colunas:
            pk_flag = "✅" if col["name"] in pks else ""
            nullable = "SIM" if col.get("nullable") else "NÃO"
            print(f"{col['name']:<30} {str(col['type']):<25} {nullable:<10} {pk_flag}")

    def injetar_no_namespace(
        self,
        resultado: Dict[str, Any],
        namespace: Dict,
    ) -> None:
        """
        Injeta o DataFrame no namespace do notebook (uso com globals() ou locals()).

        Exemplo:
            resultado = agent.carregar_tabela("vendas")
            agent.injetar_no_namespace(resultado, globals())
            # Agora df_vendas está disponível como variável global
        """
        if resultado["sucesso"] and resultado["dataframe"] is not None:
            var_name = resultado["variavel"]
            namespace[var_name] = resultado["dataframe"]
            print(f"[agente-mysql] ✅ '{var_name}' injetado no namespace com {len(resultado['dataframe']):,} linhas.")
        else:
            print(f"[agente-mysql] ❌ Não foi possível injetar: {resultado['erro']}")


# ---------------------------------------------------------------------------
# Função de conveniência para uso rápido no notebook
# ---------------------------------------------------------------------------

def carregar_tabela_mysql(
    tabela: str,
    host: str = "localhost",
    porta: int = 3306,
    usuario: str = "root",
    senha: str = "",
    banco: str = "",
    limite: int = 50_000,
    filtro_where: str = "",
    injetar_globals: Optional[Dict] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Função de conveniência — instancia o MySQLAgent e carrega a tabela.

    Exemplo mínimo:
        from mnt.skills.agente_mysql.helpers import carregar_tabela_mysql

        resultado = carregar_tabela_mysql(
            tabela="vendas",
            host="localhost",
            banco="comercial",
            usuario="root",
            senha="s3cr3t",
            injetar_globals=globals()   # injeta df_vendas no namespace do notebook
        )

        df_vendas = resultado["dataframe"]
        print(resultado["agente_json"])  # payload para o Maestro
    """
    agent = MySQLAgent(
        host=host,
        porta=porta,
        usuario=usuario,
        senha=senha,
        banco=banco,
    )
    resultado = agent.carregar_tabela(
        tabela=tabela,
        limite=limite,
        filtro_where=filtro_where,
        verbose=verbose,
    )
    if injetar_globals is not None:
        agent.injetar_no_namespace(resultado, injetar_globals)
    return resultado
