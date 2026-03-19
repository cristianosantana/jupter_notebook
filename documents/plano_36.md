Entendido! Com essas definições, o fluxo ganha uma lógica de **"Maestro de Orquestra"** muito mais robusta. O Classificador de Intenção agora é o nó central (*hub*) que garante que ninguém trabalhe no escuro.

Abaixo, apresento o **Plano de Arquitetura Revisado e Coerente**, eliminando as redundâncias anteriores e estruturando o grafo para ser funcional no LangGraph.

---

## 1. Objetivo e Lógica Central

Construir um orquestrador **stateful** onde o **Classificador (Maestro)** gerencia o estado da conversação. O sistema é preguiçoso e seguro: só executa código se o Especialista garantir (via metadados) que possui os dados necessários.

## 2. Arquitetura do Grafo (Nós e Arestas)

* **Nó Maestro (Classificador/Roteador):** Recebe o input. Se a intenção for clara, delega. Se for `NENHUM`, gera um "Menu de Capacidades" para o usuário.
* **Nó Especialista (Executor Completo):** 1.  Recebe a pergunta e o `df.info()`.
2.  Gera um **Score de Autoconfiança**.
3.  **Decisão Interna:** Se `Score > Score_Min`, gera o código Pandas, executa e devolve (Resposta + Score). Se não, devolve apenas (Aviso de Incapacidade + Score Baixo).
* **Nó Avaliador (Sintetizador):** Consolida as respostas.
* Regra: Se 2 ou mais respostas tiverem `Score > Score_Min`, **concatena**. Se apenas 1, entrega ela.


* **Nó de Clarificação:** Ativado quando o Avaliador ou Maestro falham em obter dados suficientes. Ele usa o histórico para fazer perguntas específicas (ex: "Qual cor?" ou "Qual período?").

---

## 3. Fluxo de Execução Refinado (Step-by-step)

1. **Entrada do Usuário** $\rightarrow$ **Maestro**.
2. **Maestro** identifica a intenção:
* **Vaga/Nula:** Retorna ao usuário: "Não entendi, mas posso ajudar com [Lista de DFs disponíveis]. O que prefere?".
* **Clara:** Decompõe em tarefas e envia para os **Especialistas**.


3. **Especialistas** realizam o "Check de Dados":
* Roda internamente um `df.info()` ou `df.columns`.
* Calcula o Score de viabilidade.
* **Condicional:** `Score >= 0.8`?
* **SIM:** Gera query Pandas $\rightarrow$ Executa $\rightarrow$ Salva no Estado.
* **NÃO:** Reporta erro de cobertura $\rightarrow$ Salva no Estado.




4. **Avaliador** analisa o quadro geral:
* **Sucesso (2+ respostas boas):** Concatena e finaliza (`END`).
* **Sucesso Parcial (1 resposta boa):** Entrega a única e finaliza (`END`).
* **Falha Total (0 respostas boas):** Envia para o **Maestro**, que gera uma pergunta de clarificação baseada no que os especialistas disseram que faltava.



---

## 4. Templates de Prompt (Ajustados)

### Maestro (O Classificador Central)

> "Você é o Maestro. Sua função é classificar a intenção entre [Vendas, Faturamento, Financeiro].
> Se a intenção for vaga, você deve listar o que podemos fazer.
> Se houver uma pergunta anterior no histórico, use-a para completar a intenção atual."

### Especialista (Executor com Crivo)

> "Você tem acesso ao Dataframe {nome_df}. Colunas: {df_info}.
> 1. Analise se a pergunta '{pergunta}' pode ser respondida.
> 2. Responda em JSON: `{"score": float, "executar": bool}`.
> 3. Se `executar` for true, adicione a chave `"resultado"` com o output do Pandas."
> 
> 

---

## 5. Regras de Segurança e Guardrails (Crucial)

* **Sandboxing de Código:** O Especialista sugere a query, mas uma função `safe_execute()` deve filtrar comandos perigosos (ex: `.drop()`, `.fillna()` com inplace, ou comandos de sistema).
* **Controle de Loop:** O Maestro possui um contador no `State`. Se o ciclo de clarificação ocorrer mais de 3 vezes, o sistema encerra com: "Infelizmente, não tenho esses dados no momento. Gostaria de tentar outra análise?".
* **Modelos:** Configurados como **GPT-5-Mini** conforme solicitado (ajustando os endpoints de chamada para aceitar essa string).

---

## 6. Próximos Passos (O que posso fazer agora?)

O plano agora está logicamente fechado: o Maestro controla, o Especialista decide se trabalha e o Avaliador resume.

**Como próximo passo, você gostaria que eu:**

1. Escrevesse o **código completo do Grafo (LangGraph)** em Python para você colar no seu Jupyter Notebook?
2. Criasse os **Dataframes de exemplo** (CSV/Pandas) com dados de faturamento e vendas para testarmos o fluxo?
3. Detalhasse a função de **Clarificação Proativa** (como o Maestro formula perguntas quando o especialista falha)?