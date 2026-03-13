# Jupyter notebook - agente_mysql_exemplo.ipynb
# Demonstra uso da skill agente-mysql standalone e via Maestro

"""
## agente-mysql — Exemplos de uso

Demonstra como usar a skill de carregamento MySQL:
1. Uso direto (standalone) no notebook
2. Uso via função de conveniência
3. Integração com o fluxo do Maestro
"""

import os
import sys
sys.path.insert(0, os.path.abspath("."))  # garante que mnt/skills é encontrado

from mnt.skills.agente_mysql.helpers import MySQLAgent, carregar_tabela_mysql
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# EXEMPLO 1 — Uso direto com MySQLAgent
# ─────────────────────────────────────────────────────────────────────────────

agent = MySQLAgent(
    host=os.environ.get("MYSQL_HOST", "localhost"),
    porta=int(os.environ.get("MYSQL_PORT", 3306)),
    usuario=os.environ.get("MYSQL_USER", "root"),
    senha=os.environ.get("MYSQL_PASSWORD", ""),
    banco=os.environ.get("MYSQL_DATABASE", "comercial"),
)

# Testa conexão
print("Conexão OK:", agent.testar_conexao())

# Lista tabelas disponíveis
print("Tabelas:", agent.listar_tabelas())

# Resumo rápido sem carregar dados
agent.resumo_tabela("vendas")

# ─────────────────────────────────────────────────────────────────────────────
# EXEMPLO 2 — Carregamento completo
# ─────────────────────────────────────────────────────────────────────────────

resultado = agent.carregar_tabela(
    tabela="vendas",
    limite=10000,
    filtro_where="status = 'ativo'",   # opcional
    verbose=True,
)

# DataFrame disponível direto
df_vendas = resultado["dataframe"]
print(df_vendas.head())
print(df_vendas.dtypes)

# Injeta no namespace global (df_vendas fica como variável global)
agent.injetar_no_namespace(resultado, globals())

# ─────────────────────────────────────────────────────────────────────────────
# EXEMPLO 3 — Função de conveniência (1 linha)
# ─────────────────────────────────────────────────────────────────────────────

resultado2 = carregar_tabela_mysql(
    tabela="clientes",
    host=os.environ.get("MYSQL_HOST", "localhost"),
    banco=os.environ.get("MYSQL_DATABASE", "comercial"),
    usuario=os.environ.get("MYSQL_USER", "root"),
    senha=os.environ.get("MYSQL_PASSWORD", ""),
    limite=5000,
    injetar_globals=globals(),  # df_clientes fica disponível automaticamente
)

print(df_clientes.shape)  # type: ignore  # injetado pelo injetar_globals

# ─────────────────────────────────────────────────────────────────────────────
# EXEMPLO 4 — Integração com o fluxo do Maestro
# ─────────────────────────────────────────────────────────────────────────────

"""
O agente-mysql pode ser integrado ao executar_fluxo_maestro como um passo
de pré-carregamento de dados, antes de invocar agentes analíticos.

Fluxo sugerido:
  1. Usuário pergunta algo sobre dados de uma tabela MySQL
  2. Maestro detecta que precisa de dados → invoca agente-mysql
  3. agente-mysql carrega o DataFrame e retorna o payload JSON
  4. Maestro passa o payload para agente-dados ou agente-financeiro
  5. Agentes analíticos usam o df carregado para responder
"""

import json
from openai import OpenAI
from mnt.skills.agente_mysql.helpers import carregar_tabela_mysql

# Passo A: carrega os dados via agente-mysql
resultado_mysql = carregar_tabela_mysql(
    tabela="vendas",
    host=os.environ.get("MYSQL_HOST", "localhost"),
    banco=os.environ.get("MYSQL_DATABASE", "comercial"),
    usuario=os.environ.get("MYSQL_USER", "root"),
    senha=os.environ.get("MYSQL_PASSWORD", ""),
    limite=50000,
    injetar_globals=globals(),
    verbose=True,
)

# Passo B: payload pronto para o Maestro
payload_para_maestro = resultado_mysql["agente_json"]
print(json.dumps(payload_para_maestro, ensure_ascii=False, indent=2))

# Passo C: se o carregamento foi bem-sucedido, passa para o agente analítico
if resultado_mysql["sucesso"]:
    df_info_str = resultado_mysql["metadados"]["df_info"]
    variavel = resultado_mysql["variavel"]

    print(f"\n✅ Dados disponíveis em: {variavel}")
    print(f"\ndf.info():\n{df_info_str}")

    # Aqui você chamaria executar_fluxo_maestro com agente-dados ou agente-financeiro
    # passando o df_info como contexto adicional para os agentes analíticos.

    # Exemplo:
    # from agentes_simples_4 import executar_fluxo_maestro, skills_loaded
    # client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    # model = os.environ.get("MODELO_DEFAULT")
    #
    # pergunta_com_contexto = (
    #     f"Com base nos dados da tabela '{resultado_mysql['metadados']['tabela']}' "
    #     f"já carregados no DataFrame '{variavel}' com as seguintes colunas:\n{df_info_str}\n\n"
    #     "Quais são os 5 produtos mais vendidos e qual a receita total por mês?"
    # )
    #
    # resultado = executar_fluxo_maestro(
    #     client=client,
    #     pergunta=pergunta_com_contexto,
    #     model=model,
    #     agentes=["agente-dados", "agente-financeiro"],
    #     verbose=True,
    # )
    # print(resultado["entrega_final"])
