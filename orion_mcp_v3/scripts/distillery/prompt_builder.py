"""
Construção do prompt de destilação enviado ao LLM.

Os valores válidos de dimension e metric_kind são derivados dos catálogos
em distillery.catalog — o prompt fica sempre em sincronia com o código.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from orion_mcp_v3.memory.remissive_models import RemissiveConversationWindow

from distillery.catalog import DIMENSION_CANONICAL, METRIC_KIND_CANONICAL


def build_distillation_prompt(
    windows: Sequence[RemissiveConversationWindow],
) -> str:
    """
    Monta o prompt completo para a chamada LLM de destilação.

    Os catálogos de dimension e metric_kind são injetados dinamicamente,
    garantindo que o prompt reflita sempre o estado atual do código.
    """
    payload = [
        {
            "session_id": w.session_id,
            "user_id": w.user_id,
            "messages": list(w.messages),
            "indexed_turns": list(w.indexed_turns),
        }
        for w in windows
    ]

    valid_metric_kinds = ", ".join(f"'{k}'" for k in sorted(METRIC_KIND_CANONICAL))
    valid_dimensions   = "\n".join(f"  '{k}'" for k in sorted(DIMENSION_CANONICAL))

    return (
        "Destile conversas supervisionadas em memoria remissiva V2.\n"
        "Responda somente JSON estrito com chaves: knowledge, essence, compression_log.\n"
        "\n"

        # ── Estrutura do item de knowledge ────────────────────────────────────
        "ESTRUTURA DE CADA ITEM DE KNOWLEDGE:\n"
        "{\n"
        '  "user_id": "sistema_background",\n'
        '  "category": "categoria (ex: Fechamento Gerencial)",\n'
        '  "theme": "slug da dimensao analitica (ver REGRAS abaixo)",\n'
        '  "metric_kind": "metrica principal (ver valores validos abaixo)",\n'
        '  "dimension": "como a metrica esta agrupada (ver valores validos abaixo)",\n'
        '  "periodo": "YYYY-MM (ex: PERIODO_YYYY_MM) ou null",\n'
        '  "validated_answer": "resposta direta e completa ao theme (minimo 50 chars)",\n'
        '  "recent_questions": ["1 a 5 perguntas ESPECIFICAS ao theme que os dados respondem"],\n'
        '  "key_metrics": {"chave": "valor"}  // 1 eixo; ver schema table para 2 eixos,\n'
        '  "index_questions": ["minimo 4 perguntas especificas a este theme"],\n'
        '  "confidence": "high | medium"\n'
        "}\n\n"

        # ── REGRA CENTRAL: 1 item = 1 dimensão ───────────────────────────────
        "REGRA DE GRANULARIDADE (obrigatoria):\n"
        "Cada item responde a UMA pergunta especifica. PROIBIDO misturar dimensoes.\n"
        "Exemplo de decomposicao correta para fechamento PERIODO_YYYY_MM:\n"
        "  theme='comissao_por_concessionaria'          metric_kind='comissao'     dimension='por_concessionaria'\n"
        "  theme='comissao_por_concessionaria_tipo_os'  metric_kind='comissao'     dimension='por_concessionaria_tipo_os'\n"
        "  theme='producao_por_servico'                 metric_kind='producao'     dimension='por_servico'\n"
        "  theme='producao_por_produto'                 metric_kind='producao'     dimension='por_produto'\n"
        "  theme='faturamento_por_forma_pagamento'      metric_kind='faturamento'  dimension='por_forma_pagamento'\n"
        "  theme='faturamento_por_tipo_venda'           metric_kind='faturamento'  dimension='por_tipo_venda'\n"
        "  theme='parcelamento_cartao'                  metric_kind='parcelamento' dimension='por_numero_parcelas'\n"
        "  theme='taxas_cartao_credito'                 metric_kind='taxa_cartao'  dimension='por_empresa'\n"
        "\n"

        # ── metric_kind ───────────────────────────────────────────────────────
        f"metric_kind VALIDOS: {valid_metric_kinds}\n\n"

        # ── dimension ─────────────────────────────────────────────────────────
        f"dimension VALIDOS:\n{valid_dimensions}\n\n"

        # ── Casos ambíguos conhecidos ─────────────────────────────────────────
        "CASOS ESPECIFICOS (use EXATAMENTE estes valores):\n"
        "  taxas_cartao_credito   → dimension: 'por_empresa'\n"
        "    (taxas cobradas pelos gateways/operadoras, nao pelas concessionarias)\n"
        "  comissao_por_concessionaria_tipo_os → dimension: 'por_concessionaria_tipo_os'\n"
        "    (diferente de 'por_concessionaria' — inclui tipo de OS como segunda dimensao)\n"
        "  parcelamento_cartao    → dimension: 'por_numero_parcelas'\n"
        "    (agrupado pela quantidade de parcelas: 1x, 2x ... 10x)\n"
        "\n"

        # ── theme ─────────────────────────────────────────────────────────────
        "theme: slug que combina metric_kind + dimension de forma unica.\n"
        "VALIDO:   'faturamento_por_forma_pagamento', 'comissao_por_concessionaria',\n"
        "          'producao_por_servico', 'parcelamento_cartao', 'taxas_cartao_credito'.\n"
        "INVALIDO: 'fechamento_gerencial', 'relatorio_periodo', 'analise_completa'.\n"
        "\n"

        # ── validated_answer ──────────────────────────────────────────────────
        "validated_answer: resposta direta ao theme — nada alem disso.\n"
        "PROIBIDO incluir dados de outras dimensoes no mesmo validated_answer.\n"
        "PROIBIDO resumir ou produzir resumo executivo.\n"
        "Copie valores, tabelas e listas exatamente como aparecem na conversa.\n"
        "Mantenha evidencias factuais preservadas por periodo e por theme.\n"
        "\n"

        # ── key_metrics ───────────────────────────────────────────────────────
        "key_metrics: dict de dados analiticos do tema deste item.\n"
        "Inclua todos os membros da dimensao — sem limitar a top 3 ou top 10.\n"
        "PROIBIDO incluir chaves de metadado como 'observacao', 'nota', 'truncado',\n"
        "'resumo', 'total_linhas' dentro de key_metrics.\n"
        "Dimensao SIMPLES (1 eixo, ex: por_forma_pagamento): mapa plano\n"
        '  {"chave": "valor — somente dados analiticos, sem metadados"}.\n'
        "Quando o theme tiver DUAS dimensoes (ex: concessionaria + tipo_os),\n"
        "key_metrics DEVE seguir este schema fixo, sem excecao:\n"
        "{\n"
        '  "_meta": {"schema": "table", "entity_field": "concessionaria",\n'
        '            "columns": ["venda_normal", "financiamento", "total_comissao"]},\n'
        '  "rows": [\n'
        '    {"concessionaria": "GWM BAMAQ", "venda_normal": "R$ 43.584,46",\n'
        '     "financiamento": "R$ 0,00", "total_comissao": "R$ 43.584,46"}\n'
        "  ]\n"
        "}\n"
        "Aplica-se a dimension='por_concessionaria_tipo_os' e qualquer dimensao matricial.\n"
        "PROIBIDO: embutir sub-valores como texto livre dentro de uma unica string\n"
        "('Label: R$X | Label: R$Y'). PROIBIDO: linhas posicionais sem nome de campo.\n"
        "SEMPRE um objeto JSON por linha, com as MESMAS chaves em toda linha do mesmo theme.\n"
        "\n"

         # ── recent_questions ──────────────────────────────────────────────────
        "recent_questions: liste de 1 a 5 perguntas ESPECIFICAS AO THEME que\n"
        "os dados deste item respondem diretamente.\n"
        "PROIBIDO repetir a pergunta generica que originou o fechamento completo.\n"
        "PROIBIDO: 'Quero o fechamento gerencial de MES_ANO?' (generico demais).\n"
        "CORRETO para theme='comissao_por_concessionaria':\n"
        "  - 'Qual concessionaria teve maior comissao em MES_ANO?'\n"
        "  - 'Ranking de comissao por concessionaria PERIODO_YYYY_MM'\n"
        "  - 'Quem mais comissionou em MES_ANO?'\n"
        "CORRETO para theme='parcelamento_cartao':\n"
        "  - 'Como ficou o parcelamento do cartao em MES_ANO?'\n"
        "  - 'Qual parcela foi mais usada em PERIODO_YYYY_MM?'\n"
        "Se nao houver pergunta especifica na conversa, gere perguntas coerentes\n"
        "com o theme. Prefira vazio a pergunta generica de fechamento.\n"
        "\n"

        # ── index_questions ───────────────────────────────────────────────────
        "index_questions: minimo 5 perguntas que um usuario leigo usaria para\n"
        "buscar EXATAMENTE este theme.\n"
        "OBRIGATORIO cobrir todos os angulos abaixo — um por pergunta:\n"
        "  1. maximo     — 'qual X mais/maior/lider?'\n"
        "  2. minimo     — 'qual X menos/menor/ultimo?'\n"
        "  3. proporcao  — 'qual percentual/quanto representa?'\n"
        "  4. comparacao — 'X superou Y? A diferenca entre X e Y?'\n"
        "  5. coloquial  — como um gerente perguntaria no dia a dia\n"
        "Exemplo para theme='faturamento_por_forma_pagamento' periodo='PERIODO_YYYY_MM':\n"
        "  1. 'qual forma de pagamento dominou o faturamento em MES_ANO?'\n"
        "  2. 'qual forma de pagamento teve menor participacao em PERIODO_YYYY_MM?'\n"
        "  3. 'qual percentual do faturamento veio de cartao de credito em MES_ANO?'\n"
        "  4. 'a forma de pagamento A superou a forma de pagamento B em MES_ANO?\n"
        " (OBS: A pode ser o PIX e B o Depósito Bancário e varias outras combinações)'\n"
        "  5. 'quanto a concessionaria X recebeu os pagamentos em MES_ANO?'\n"
        "\n"
        
        # ── NUNCA gerar context_key ───────────────────────────────────────────
        "NUNCA gere context_key — o sistema calcula a partir de user_id + category + theme + periodo.\n"
        "\n"

        # ── essence ───────────────────────────────────────────────────────────
        "essence[]: user_id, theme, observation, key_finding, recommendation,\n"
        "stable_metrics: objeto {} ou lista de strings 'label: valor' — NUNCA texto livre.\n"
        "confidence.\n"
        "Use essence para padroes recorrentes e estaveis — nao para fatos pontuais.\n"
        "\n"

        # ── compression_log ───────────────────────────────────────────────────
        "compression_log: user_id, from_state='raw_windows_v2', to_state='memoria_remissiva_v2',\n"
        "messages_compressed (int), compression_ratio (float 0-1),\n"
        "what_was_kept, what_was_dropped.\n"
        "PROIBIDO: from_state ou to_state como objetos/dicts.\n"
        "SEMPRE strings literais: from_state='raw_windows_v2', to_state='memoria_remissiva_v2'.\n"
        "\n"

        # ── periodo ───────────────────────────────────────────────────────────
        "periodo: formato YYYY-MM (ex: 'PERIODO_YYYY_MM').\n"
        "NUNCA texto livre como 'MES_ANO' — use o valor canonico PERIODO_YYYY_MM.\n"
        "\n"

        # ── Janelas ───────────────────────────────────────────────────────────
        f"Janelas:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
