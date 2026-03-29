# Introdução

## 1ª Aula Bem-vindo(a) ao curso

* Direct link to the UV install guide: https://docs.astral.sh/uv/
* Model Context Protocol introduction: https://modelcontextprotocol.io/introduction

## 2ª Aula Apresentando o MCP

* O Model Context Protocol (MCP) é uma camada de comunicação que fornece ao Claude contexto e ferramentas sem exigir que você escreva uma série de códigos de integração tediosos. Pense nisso como uma forma de transferir a responsabilidade pelas definições e execução das ferramentas do seu servidor para servidores MCP especializados.
* Ao se deparar com o MCP pela primeira vez, você verá diagramas que mostram a arquitetura básica: um Cliente MCP (seu servidor) conectando-se a Servidores MCP que contêm ferramentas, prompts e recursos. Cada Servidor MCP atua como uma interface para algum serviço externo.
* O problema que a MCP resolve
    * Digamos que você esteja criando uma interface de chat onde os usuários podem perguntar ao Claude sobre seus dados do GitHub. Um usuário poderia perguntar: "Quais pull requests estão abertos em todos os meus repositórios?". Para lidar com isso, o Claude precisa de ferramentas para acessar a API do GitHub.
    * O GitHub possui uma funcionalidade enorme — repositórios, pull requests, issues, projetos e muito mais. Sem o MCP, você precisaria criar uma quantidade incrível de esquemas e funções de ferramentas para lidar com todos os recursos do GitHub.
    * Isso significa escrever, testar e manter todo esse código de integração por conta própria. É um trabalho árduo e uma carga de manutenção constante.
* Como funciona o MCP
    * O MCP transfere essa responsabilidade, movendo as definições e a execução das ferramentas do seu servidor para servidores MCP dedicados. Em vez de você criar todas essas ferramentas do GitHub, um servidor MCP para GitHub cuida disso.
    * O servidor MCP reúne diversas funcionalidades do GitHub e as disponibiliza como um conjunto padronizado de ferramentas. Seu aplicativo se conecta a esse servidor MCP em vez de você implementar tudo do zero.
* Explicação sobre os servidores MCP
    * Os servidores MCP fornecem acesso a dados ou funcionalidades implementadas por serviços externos. Eles atuam como interfaces especializadas que expõem ferramentas, prompts e recursos de forma padronizada.
    * Em nosso exemplo do GitHub, o servidor MCP para GitHub contém ferramentas como [exemplo de ferramenta] get_repos()e se conecta diretamente à API do GitHub. Seu servidor se comunica com o servidor MCP, que lida com todos os detalhes de implementação específicos do GitHub.
* Perguntas frequentes
    * Quem desenvolve os servidores MCP?
        *Qualquer pessoa pode criar uma implementação de servidor MCP. Frequentemente, os próprios provedores de serviços criam suas próprias implementações oficiais de MCP. Por exemplo, a AWS pode lançar um servidor MCP oficial com ferramentas para seus diversos serviços.
    * Qual a diferença entre isso e chamar APIs diretamente?
        * Os servidores MCP fornecem esquemas e funções de ferramentas já definidos para você. Se você quiser chamar uma API diretamente, precisará criar essas definições de ferramentas por conta própria. O MCP evita esse trabalho de implementação.
    * MCP não é simplesmente a mesma coisa que usar uma ferramenta?
        * Essa é uma ideia equivocada bastante comum. Servidores MCP e uso de ferramentas são conceitos complementares, porém distintos. Os servidores MCP fornecem esquemas e funções de ferramentas já definidos, enquanto o uso de ferramentas se refere a como o Claude realmente invoca essas ferramentas. A principal diferença reside em quem realiza o trabalho: com o MCP, outra pessoa já implementou as ferramentas para você.
        * A vantagem é clara: em vez de manter um conjunto complexo de integrações por conta própria, você pode aproveitar os servidores MCP que cuidam da parte mais complexa da conexão com serviços externos.

## 3ª Aula Clientes MCP

* O cliente MCP serve como ponte de comunicação entre o seu servidor e os servidores MCP. É o seu ponto de acesso a todas as ferramentas que um servidor MCP oferece, gerenciando a troca de mensagens e os detalhes do protocolo para que sua aplicação não precise se preocupar com isso.

* Comunicação agnóstica ao transporte
    * Um dos principais pontos fortes do MCP é ser agnóstico em relação ao transporte – uma maneira sofisticada de dizer que o cliente e o servidor podem se comunicar por meio de diferentes protocolos, dependendo da sua configuração.
    * A configuração mais comum executa o cliente e o servidor MCP na mesma máquina, comunicando-se por meio de entrada/saída padrão. Mas você também pode conectá-los através de:
        * HTTP
        * WebSockets
        * Vários outros protocolos de rede

* Tipos de mensagens MCP
    * Uma vez conectados, o cliente e o servidor trocam tipos de mensagens específicos definidos na especificação MCP. Os principais com os quais você trabalhará são:
    * ListToolsRequest/ListToolsResult: O cliente pergunta ao servidor "quais ferramentas vocês fornecem?" e recebe uma lista das ferramentas disponíveis.
    * CallToolRequest/CallToolResult: O cliente solicita ao servidor que execute uma ferramenta específica com argumentos fornecidos e, em seguida, recebe os resultados.

* Como tudo funciona em conjunto
    * Aqui está um exemplo completo que mostra como uma consulta de usuário flui por todo o sistema - do seu servidor, passando pelo cliente MCP, para serviços externos como o GitHub e de volta para o Claude.
    * Digamos que um usuário pergunte "Quais repositórios eu tenho?" Aqui está o fluxo passo a passo:
        * Consulta do usuário: O usuário envia sua pergunta para o seu servidor.
        * Descoberta de ferramentas: Seu servidor precisa saber quais ferramentas estão disponíveis para enviar ao Claude.
        * Troca de ferramentas de listagem: Seu servidor solicita ao cliente MCP as ferramentas disponíveis.
        * Comunicação MCP: O cliente MCP envia um sinal ListToolsRequestpara o servidor MCP e recebe um sinal.ListToolsResult
        * Solicitação de Claude: Seu servidor envia a consulta do usuário, juntamente com as ferramentas disponíveis, para Claude.
        * Decisão sobre o uso da ferramenta: Claude decide que precisa acionar uma ferramenta para responder à pergunta.
        * Solicitação de Execução de Ferramenta: Seu servidor solicita ao cliente MCP que execute a ferramenta especificada por Claude.
        * Chamada de API externa: O cliente MCP envia uma solicitação CallToolRequestao servidor MCP, que realiza a chamada de API do GitHub.
        * Fluxo de resultados: O GitHub responde com dados do repositório, que fluem de volta através do servidor MCP como umCallToolResult
        * Resultado da ferramenta para Claude: Seu servidor envia os resultados da ferramenta de volta para Claude.
        * Resposta final: Claude formula uma resposta final usando os dados do repositório.
        * Usuário recebe resposta: Seu servidor envia a resposta de Claude de volta para o usuário.

    * Sim, esse fluxo envolve muitas etapas, mas cada componente tem uma responsabilidade clara. O cliente MCP abstrai a complexidade da comunicação com o servidor, permitindo que você se concentre na lógica do seu aplicativo, ao mesmo tempo que obtém acesso a ferramentas externas poderosas e fontes de dados.
    * Compreender esse fluxo é crucial, pois você verá todas essas peças ao construir seus próprios clientes e servidores MCP nas próximas seções.

## 4ª Aula Definindo ferramentas com MCP

* Criar um servidor MCP torna-se muito mais simples ao usar o SDK oficial do Python. Em vez de escrever esquemas JSON complexos manualmente, você pode definir ferramentas com decoradores e deixar que o SDK cuide do trabalho pesado.

* Neste exemplo, estamos criando um servidor de gerenciamento de documentos com duas ferramentas principais: uma para ler documentos e outra para atualizá-los. Todos os documentos existem na memória como um dicionário simples, onde as chaves são os IDs dos documentos e os valores são o conteúdo.

* Configurando o servidor MCP
    * O SDK do MCP para Python facilita a criação de servidores. Você pode inicializar um servidor com apenas uma linha:
    ```py
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("DocumentMCP", log_level="ERROR")
    ```

    * Seus documentos podem ser armazenados em uma estrutura de dicionário simples:

    ```py
    docs = {
        "deposition.md": "This deposition covers the testimony of Angela Smith, P.E.",
        "report.pdf": "The report details the state of a 20m condenser tower.",
        "financials.docx": "These financials outline the project's budget and expenditures",
        "outlook.pdf": "This document presents the projected future performance of the system",
        "plan.md": "The plan outlines the steps for the project's implementation.",
        "spec.txt": "These specifications define the technical requirements for the equipment"
    }
    ```

* Definição de Ferramentas com Decoradores
    * O SDK usa decoradores para definir ferramentas. Em vez de escrever esquemas JSON manualmente, você pode usar dicas de tipo do Python e descrições de campos. O SDK gera automaticamente o esquema adequado que o Claude consegue entender.

* Criando uma Ferramenta de Leitura de Documentos
    * A primeira ferramenta lê o conteúdo de documentos por ID. Aqui está a implementação completa:
    ```py
    @mcp.tool(
        name="read_doc_contents",
        description="Read the contents of a document and return it as a string."
    )
    def read_document(
        doc_id: str = Field(description="Id of the document to read")
    ):
        if doc_id not in docs:
            raise ValueError(f"Doc with id {doc_id} not found")
        
        return docs[doc_id]
    ```
    * O decrador especifica o nome e a descrição da ferramenta, enquanto os parâmetros da função definem os argumentos necessários. A classe Field do Pydantic fornece descrições de argumentos que ajudam o Claude a entender o que cada parâmetro espera.

* Criando uma Ferramenta de Edição de Documentos
    * A segunda ferramenta realiza operações simples de localizar e substituir em documentos:
    ```py
    @mcp.tool(
        name="edit_document",
        description="Edit a document by replacing a string in the documents content with a new string."
    )
    def edit_document(
        doc_id: str = Field(description="Id of the document that will be edited"),
        old_str: str = Field(description="The text to replace. Must match exactly, including whitespace."),
        new_str: str = Field(description="The new text to insert in place of the old text.")
    ):
        if doc_id not in docs:
            raise ValueError(f"Doc with id {doc_id} not found")
        
        docs[doc_id] = docs[doc_id].replace(old_str, new_str)
    ```
    * Esta ferramenta recebe três parâmetros: o ID do documento, o texto a ser encontrado e o texto de substituição. A implementação inclui tratamento de erros para documentos ausentes e realiza uma substituição de string simples.

* Principais benefícios da abordagem do SDK
    * Não é necessário escrever esquemas JSON manualmente
    * Dicas de tipo fornecem validação automática
    * Descrições claras dos parâmetros ajudam o Claude a entender o uso da ferramenta
    * O tratamento de erros se integra naturalmente com exceções do Python
    * O registro da ferramenta ocorre automaticamente por meio de decoradores

* O SDK Python do MCP transforma a criação de ferramentas de um exercício complexo de escrita de esquemas em definições de funções Python simples. Essa abordagem facilita muito a criação e a manutenção de servidores MCP, garantindo que o Claude receba especificações de ferramentas formatadas corretamente.

## 5ª Aula O inspetor de servidores

* Ao criar servidores MCP, você precisa de uma maneira de testar sua funcionalidade sem se conectar a um aplicativo completo. O SDK Python MCP inclui um inspetor integrado baseado em navegador que permite depurar e testar seu servidor em tempo real.

* Iniciando o Inspetor
    * Primeiro, certifique-se de que seu ambiente Python esteja ativado (consulte o arquivo README do seu projeto para obter o comando exato). Em seguida, execute o inspetor com:
    
    ```py
    mcp dev mcp_server.py
    ```
    * Isso inicia um servidor de desenvolvimento e fornece um URL local, geralmente algo como http://127.0.0.1:6274. Abra este URL no seu navegador para acessar o MCP Inspector.

* Utilizando a interface do inspetor
    * A interface do inspetor está em constante desenvolvimento, portanto, pode apresentar algumas diferenças ao ser utilizada. No entanto, a funcionalidade principal permanece a mesma. Procure por estes elementos-chave:
        * Um botão Conectar para iniciar seu servidor MCP
        * Guias de navegação para Recursos , Ferramentas , Dicas e outras funcionalidades.
        * Um painel de listagem e teste de ferramentas

    * Primeiro, clique no botão Conectar para inicializar o servidor. Você verá o status da conexão mudar de "Desconectado" para "Conectado".

* Testando suas ferramentas
    * Acesse a seção Ferramentas e clique em "Listar ferramentas" para ver todas as ferramentas disponíveis no seu servidor. Ao selecionar uma ferramenta, o painel à direita exibe seus detalhes e campos de entrada.
    * Por exemplo, para testar uma ferramenta de leitura de documentos:
        * Selecione a read_doc_contentsferramenta
        * Insira um ID de documento (como "deposition.md")
        * Clique em "Executar ferramenta"
        * Verifique os resultados para garantir o sucesso e o resultado esperado.
    * O inspetor mostra tanto o status de sucesso quanto os dados retornados, facilitando a verificação de que sua ferramenta está funcionando corretamente.

* Interações da ferramenta de teste
    * Você pode testar várias ferramentas em sequência para verificar fluxos de trabalho complexos. Por exemplo, após usar uma ferramenta de edição para modificar um documento, teste imediatamente a ferramenta de leitura para confirmar se as alterações foram aplicadas corretamente.

    * O inspetor mantém o estado do seu servidor entre as chamadas da ferramenta, de modo que as edições sejam mantidas e você possa verificar a funcionalidade completa do seu servidor MCP.

* Fluxo de trabalho de desenvolvimento
    * O MCP Inspector torna-se uma parte essencial do seu processo de desenvolvimento. Em vez de escrever scripts de teste separados ou conectar-se a aplicações completas, você pode:
        * Iterar rapidamente nas implementações das ferramentas.
        * Teste casos extremos e condições de erro
        * Verificar interações de ferramentas e gerenciamento de estado
        * Depurar problemas em tempo real
    * Esse ciclo de feedback imediato torna o desenvolvimento do servidor MCP muito mais eficiente e ajuda a detectar problemas logo no início do processo de desenvolvimento.

## 6ª Aula Implementando um cliente

* Agora que nosso servidor MCP está funcionando, é hora de construir o lado do cliente. O cliente é o que permite que o código do nosso aplicativo se comunique com o servidor MCP e acesse suas funcionalidades.

* Entendendo a Arquitetura do Cliente
    * Na maioria dos projetos do mundo real, você implementará um cliente MCP ou um servidor MCP — não ambos. Estamos construindo os dois neste projeto apenas para que você possa ver como eles funcionam juntos.
    * O cliente MCP consiste em dois componentes principais:
        * Cliente MCP - Uma classe personalizada que criamos para facilitar o uso da sessão.
        * Sessão do Cliente - A conexão propriamente dita com o servidor (parte do SDK Python do MCP)

    * A sessão do cliente exige um gerenciamento cuidadoso de recursos — precisamos limpar as conexões adequadamente quando terminarmos. É por isso que a encapsulamos em nossa própria classe, que lida com toda a limpeza automaticamente.

* Como o cliente se encaixa em nossa aplicação
    * Lembra-se do nosso diagrama de fluxo da aplicação? O cliente é o que permite que nosso código interaja com o servidor MCP em dois pontos principais:
    * Nosso código CLI usa o cliente para:
        * Obtenha uma lista das ferramentas disponíveis para enviar a Claude.
        * Execute as ferramentas quando Claude as solicitar.

* Implementando as funções principais do cliente
    * Precisamos implementar duas funções essenciais: list_tools()e call_tool().

    * Listar ferramentas Função
        * Esta função obtém todas as ferramentas disponíveis do servidor MCP:
        ```py
        async def list_tools(self) -> list[types.Tool]:
            result = await self.session().list_tools()
            return result.tools
        ```
        * É simples: acessamos nossa sessão (a conexão com o servidor), chamamos o método integrado list_tools()e retornamos as ferramentas a partir do resultado.

    * Função da ferramenta de chamada
        * Esta função executa uma ferramenta específica no servidor:
        ```py
        async def call_tool(
            self, tool_name: str, tool_input: dict
        ) -> types.CallToolResult | None:
            return await self.session().call_tool(tool_name, tool_input)
        ```
        * Passamos o nome da ferramenta e os parâmetros de entrada (fornecidos por Claude) para o servidor e retornamos o resultado.

* Testando o Cliente
    * O arquivo do cliente inclui um ambiente de teste simples na parte inferior. Você pode executá-lo diretamente para verificar se tudo funciona corretamente:
    ```py 
    uv run mcp_client.py
    ```
    * Isso se conectará ao seu servidor MCP e exibirá as ferramentas disponíveis. Você deverá ver uma saída mostrando as definições das suas ferramentas, incluindo descrições e esquemas de entrada.

* Juntando tudo
    * Após a implementação das funções do cliente, você pode testar o fluxo completo executando sua aplicação principal:
    ```py
    uv run main.py
    ```
    * Tente perguntar: "Qual é o conteúdo do documento report.pdf?"
    * Eis o que acontece nos bastidores:
        * Seu aplicativo usa o cliente para obter as ferramentas disponíveis.
        * Essas ferramentas são enviadas para Claude juntamente com sua pergunta.
        * Claude decide usar a ferramenta read_doc_contents.
        * Seu aplicativo usa o cliente para executar essa ferramenta.
        * O resultado é devolvido a Claude, que então responde a você.
    * O cliente atua como uma ponte entre a lógica do seu aplicativo e a funcionalidade do servidor MCP, facilitando a integração de ferramentas poderosas em seus fluxos de trabalho de IA.

## 8ª Aula Definindo recursos

* Os recursos nos servidores MCP permitem expor dados aos clientes, de forma semelhante aos manipuladores de requisições GET em um servidor HTTP típico. Eles são perfeitos para cenários em que você precisa buscar informações em vez de executar ações.

* Entendendo os recursos por meio de um exemplo
    * Suponhamos que você queira criar um recurso de menção de documentos onde os usuários possam digitar @document_namepara referenciar arquivos. Isso requer duas operações:
        * Obtendo uma lista de todos os documentos disponíveis (para preenchimento automático)
        * Recuperar o conteúdo de um documento específico (quando mencionado)
    * Quando um usuário menciona um documento, seu sistema insere automaticamente o conteúdo do documento no prompt enviado a Claude, eliminando a necessidade de Claude usar ferramentas para buscar as informações.

* Como funcionam os recursos
    * Os recursos seguem um padrão de solicitação-resposta. Quando seu cliente precisa de dados, ele envia uma solicitação ReadResourceRequestcom um URI para identificar qual recurso deseja. O servidor MCP processa essa solicitação e retorna os dados em um objeto ReadResourceResult.
    * O fluxo funciona da seguinte forma: seu código solicita um recurso do cliente MCP, que encaminha a solicitação para o servidor MCP. O servidor processa o URI, executa a função apropriada e retorna o resultado.

* Tipos de Recursos
    * Existem dois tipos de recursos:
        * Recursos diretos
            * Recursos diretos possuem URIs estáticas que nunca mudam. São perfeitos para operações que não precisam de parâmetros.
            ```py
            @mcp.resource(
                "docs://documents",
                mime_type="application/json"
            )
            def list_docs() -> list[str]:
                return list(docs.keys())
            ```
        * Recursos com modelos
            * Os recursos com modelos incluem parâmetros em seus URIs. O SDK do Python analisa automaticamente esses parâmetros e os passa como argumentos nomeados para sua função.
            ```py
            @mcp.resource(
                "docs://documents/{doc_id}",
                mime_type="text/plain"
            )
            def fetch_doc(doc_id: str) -> str:
                if doc_id not in docs:
                    raise ValueError(f"Doc with id {doc_id} not found")
                return docs[doc_id]
            ```

* Detalhes da implementação
    * Os recursos podem retornar qualquer tipo de dado — strings, JSON, dados binários etc. Use o mime_typeparâmetro para dar aos clientes uma dica sobre o tipo de dado que você está retornando:
        * "application/json"para dados estruturados
        * "text/plain"para texto simples
        * "application/pdf"para arquivos binários
    * O SDK Python do MCP serializa automaticamente os valores de retorno. Você não precisa converter manualmente os objetos em strings JSON — basta retornar a estrutura de dados e deixar que o SDK cuide da serialização.

* Testando seus recursos
    * Você pode testar recursos usando o MCP Inspector. Inicie seu servidor com:
    ```py
    uv run mcp dev mcp_server.py
    ```
    * Em seguida, acesse o inspetor no seu navegador. Você verá duas seções:
        * Recursos - Lista seus recursos diretos/estáticos
        * Modelos de Recursos - Lista seus recursos com modelos predefinidos

    * Clique em qualquer recurso para testá-lo. Para recursos com modelos, você precisará fornecer valores para os parâmetros. O inspetor mostra a estrutura exata da resposta que seu cliente receberá, incluindo o tipo MIME e os dados serializados.

    * Os recursos oferecem uma maneira simples de expor dados somente leitura do seu servidor MCP, facilitando para os clientes a obtenção de informações sem a complexidade de chamadas de ferramentas.

## 9ª Aula Acesso a recursos
* Os recursos do MCP permitem que seu servidor exponha informações que podem ser incluídas diretamente em prompts, em vez de exigir chamadas de ferramentas para acessar dados. Isso cria uma maneira mais eficiente de fornecer contexto aos modelos de IA.


* O diagrama acima mostra como os recursos funcionam: quando um usuário digita algo como "O que tem no @...", nosso código reconhece isso como uma solicitação de recurso, envia um ReadResourceRequest para o servidor MCP e recebe um ReadResourceResult com o conteúdo real.

* Implementando a leitura de recursos
    * Para habilitar o acesso a recursos no seu cliente MCP, você precisa implementar uma read_resourcefunção. Primeiro, adicione as importações necessárias:
    ```py
    import json
    from pydantic import AnyUrl
    ```
    * A função principal faz uma solicitação ao servidor MCP e processa a resposta com base em seu tipo MIME:
    ```py
    async def read_resource(self, uri: str) -> Any:
        result = await self.session().read_resource(AnyUrl(uri))
        resource = result.contents[0]
        
        if isinstance(resource, types.TextResourceContents):
            if resource.mimeType == "application/json":
                return json.loads(resource.text)
        
        return resource.text
    ```
* Compreendendo a estrutura da resposta
    * Ao solicitar um recurso, o servidor retorna uma contentslista como resultado. Acessamos o primeiro elemento, pois normalmente precisamos apenas de um recurso por vez. A resposta inclui:
        * O conteúdo propriamente dito (texto ou dados)
        * Um tipo MIME que nos indica como analisar o conteúdo.
        * Outros metadados sobre o recurso

* Tratamento de tipos de conteúdo
    * A função verifica o tipo MIME para determinar como processar o conteúdo:
        * Se for application/json, analise o texto como JSON e retorne o objeto analisado.
        * Caso contrário, retorne o conteúdo de texto bruto.
    * Essa abordagem lida perfeitamente tanto com dados estruturados (como JSON) quanto com documentos de texto simples.

* Acesso aos recursos de teste
    * Após a implementação, você pode testar a funcionalidade do recurso por meio do seu aplicativo de linha de comando (CLI). Ao digitar "@" seguido do nome do recurso, o sistema fará o seguinte:
        * Exibir os recursos disponíveis em uma lista de preenchimento automático.
        * Permite selecionar um recurso usando as teclas de seta e a barra de espaço.
        * Inclua o conteúdo do recurso diretamente em sua pergunta.
        * Envie tudo para o modelo de IA sem a necessidade de chamadas de ferramentas adicionais.
* Isso cria uma experiência de usuário muito mais fluida em comparação com a situação em que o modelo de IA faz chamadas de ferramentas separadas para acessar o conteúdo do documento. O conteúdo do recurso passa a fazer parte do contexto inicial, permitindo respostas imediatas sobre os dados.

## 10ª Aula Definindo instruções

* Os prompts nos servidores MCP permitem que você defina instruções pré-construídas e de alta qualidade que os clientes podem usar em vez de escrever seus próprios prompts do zero. Pense neles como modelos cuidadosamente elaborados que oferecem resultados melhores do que aqueles que os usuários poderiam criar por conta própria.

* Por que usar prompts?
    * Eis a principal conclusão: os usuários já podem pedir ao Claude para executar a maioria das tarefas diretamente. Por exemplo, um usuário pode digitar "reformatar o relatório.pdf em Markdown" e obter resultados satisfatórios. Mas obterá resultados muito melhores se você fornecer um comando específico e rigorosamente testado que lide com casos extremos e siga as melhores práticas.
    * Como autor do servidor MCP, você pode dedicar tempo à criação, teste e avaliação de prompts que funcionem de forma consistente em diferentes cenários. Os usuários se beneficiam dessa expertise sem precisar se tornarem especialistas em engenharia de prompts.

* Criando um comando de formatação
    * Vamos implementar um exemplo prático: um comando de formatação que converte documentos para Markdown. Os usuários digitarão o texto /format doc_ide receberão uma versão em Markdown formatada profissionalmente do documento.
    * O fluxo de trabalho é o seguinte:
        * O usuário digita /para ver os comandos disponíveis.
        * Eles selecionam formate especificam um ID de documento.
        * Claude usa o seu prompt predefinido para ler e reformatar o documento.
        * O resultado é um Markdown limpo, com cabeçalhos, listas e formatação adequados.

* Definindo os prompts
    * Os prompts usam um padrão de decoração semelhante ao das ferramentas e recursos:
    ```py
    @mcp.prompt(
        name="format",
        description="Rewrites the contents of the document in Markdown format."
    )
    def format_document(
        doc_id: str = Field(description="Id of the document to format")
    ) -> list[base.Message]:
        prompt = f"""
    Your goal is to reformat a document to be written with markdown syntax.

    The id of the document you need to reformat is:
    <document_id>
    {doc_id}
    </document_id>

    Add in headers, bullet points, tables, etc as necessary. Feel free to add in structure.
    Use the 'edit_document' tool to edit the document. After the document has been reformatted...
    """
        
        return [
            base.UserMessage(prompt)
        ]
    ```
    * A função retorna uma lista de mensagens que são enviadas diretamente para Claude. Você pode incluir várias mensagens de usuário e do assistente para criar fluxos de conversa mais complexos.

* Testando suas instruções
    * Use o MCP Inspector para testar seus prompts antes de implementá-los:
    * O inspetor mostra exatamente quais mensagens serão enviadas para Claude, incluindo como as variáveis ​​são interpoladas no seu modelo de prompt. Isso permite que você verifique se o prompt está correto antes que os usuários comecem a depender dele.
* Principais benefícios
    * Consistência - Os usuários obtêm resultados confiáveis ​​sempre.
    * Especialização - Você pode codificar conhecimento de domínio em instruções.
    * Reutilização - Vários aplicativos cliente podem usar os mesmos prompts.
    * Manutenção - Atualize os avisos em um único local para melhorar o atendimento a todos os clientes.
* Os prompts funcionam melhor quando são específicos para o domínio do seu servidor MCP. Um servidor de gerenciamento de documentos pode ter prompts para formatar, resumir ou analisar documentos. Um servidor de análise de dados pode ter prompts para gerar relatórios ou visualizações.
* O objetivo é fornecer instruções tão bem elaboradas e testadas que os usuários as prefiram a escrever suas próprias instruções do zero.

## 11ª Aula Instruções no cliente

* A etapa final na construção do nosso cliente MCP é a implementação da funcionalidade de prompts. Isso nos permite listar todos os prompts disponíveis no servidor e recuperar prompts específicos com variáveis ​​preenchidas.

* Implementando sugestões de lista
    * O list_promptsmétodo é simples. Ele chama a função de lista de prompts da sessão e retorna os prompts:
    ```py
    async def list_prompts(self) -> list[types.Prompt]:
        result = await self.session().list_prompts()
        return result.prompts
    ```
* Recebendo instruções individuais
    * O get_promptmétodo é mais interessante porque lida com interpolação de variáveis. Ao solicitar um prompt, você fornece argumentos que são passados ​​para a função de prompt como argumentos nomeados:
    ```py
    async def get_prompt(self, prompt_name, args: dict[str, str]):
        result = await self.session().get_prompt(prompt_name, args)
        return result.messages
    ```
    * Por exemplo, se o seu servidor tiver um format_documentprompt que espera um doc_idparâmetro, o dicionário de argumentos conterá {"doc_id": "plan.md"}. Esse valor é interpolado no modelo do prompt.
* Instruções de teste em ação
    * Após a implementação, você pode testar os prompts através da CLI. Ao digitar uma barra ( /), os prompts disponíveis aparecem como comandos. Selecionar um prompt como "format" solicitará que você escolha entre os documentos disponíveis.
    * Após selecionar um documento, o sistema envia a solicitação completa para Claude. A IA recebe tanto as instruções de formatação quanto o ID do documento e, em seguida, utiliza as ferramentas disponíveis para buscar e processar o conteúdo.
* Como funcionam os prompts
    * Os prompts definem um conjunto de mensagens de usuário e assistente que os clientes podem usar. Devem ser de alta qualidade, bem testadas e relevantes para a finalidade do seu servidor MCP. O fluxo de trabalho é:
        * Escreva e avalie um prompt relevante para a funcionalidade do seu servidor.
        * Defina o prompt no seu servidor MCP usando o @mcp.promptdecorador.
        * Os clientes podem solicitar o lembrete a qualquer momento.
        * Os argumentos fornecidos pelo cliente tornam-se argumentos nomeados na sua função de prompt.
        * A função retorna mensagens formatadas prontas para o modelo de IA.
    * Este sistema cria prompts reutilizáveis ​​e parametrizados que mantêm a consistência, permitindo ao mesmo tempo a personalização por meio de variáveis. É particularmente útil para fluxos de trabalho complexos, nos quais se deseja garantir que a IA receba instruções estruturadas adequadamente em todas as situações.

## 12ª Aula Revisão MCP

* Agora que construímos nosso servidor MCP, vamos revisar os três elementos básicos do servidor e entender quando usar cada um deles. A principal ideia é que cada elemento básico é controlado por uma parte diferente da sua pilha de aplicações.

* Ferramentas: Controladas por Modelo
    * As ferramentas são controladas inteiramente por Claude. O modelo de IA decide quando chamar essas funções, e os resultados são usados ​​diretamente por Claude para realizar tarefas.

    * As ferramentas são perfeitas para dar ao Claude capacidades adicionais que ele pode usar de forma autônoma. Quando você pede ao Claude para "calcular a raiz quadrada de 3 usando JavaScript", é o próprio Claude que decide usar uma ferramenta de execução de JavaScript para realizar o cálculo.

* Recursos: Controlados por aplicativo
    * Os recursos são controlados pelo código do seu aplicativo. Seu aplicativo decide quando buscar dados de recursos e como usá-los — normalmente para elementos da interface do usuário ou para adicionar contexto às conversas.
    * Em nosso projeto, utilizamos recursos de duas maneiras:
        * Obtenção de dados para preencher as opções de autocompletar na interface do usuário.
        * Recuperar conteúdo para complementar as sugestões com contexto adicional.
    * Pense na funcionalidade "Adicionar do Google Drive" na interface do Claude: o código do aplicativo determina quais documentos exibir e lida com a inserção do conteúdo deles no contexto do chat.

* Instruções: Controladas pelo usuário
    * Os prompts são acionados por ações do usuário. Os usuários decidem quando executar esses fluxos de trabalho predefinidos por meio de interações na interface do usuário, como cliques em botões, seleções de menu ou comandos de barra.
    * Os prompts são ideais para implementar fluxos de trabalho que os usuários podem acionar sob demanda. Na interface do Claude, os botões de fluxo de trabalho abaixo da entrada de chat são exemplos de prompts — fluxos de trabalho predefinidos e otimizados que os usuários podem iniciar com um único clique.

* Escolhendo o primitivo certo
    * Aqui está um guia rápido para tomada de decisões:
        * Precisa dar novas capacidades ao Claude? Use as ferramentas.
        * Precisa inserir dados no seu aplicativo para a interface do usuário ou para fornecer contexto? Use os recursos.
        * Deseja criar fluxos de trabalho predefinidos para os usuários? Use prompts.

    * Você pode ver os três elementos básicos em ação na interface oficial do Claude. Os botões de fluxo de trabalho demonstram as instruções, a integração com o Google Drive mostra os recursos em uso e, quando o Claude executa código ou realiza cálculos, ele utiliza ferramentas nos bastidores.

    * Estas são diretrizes gerais para ajudar você a escolher a primitiva certa para o seu caso de uso específico. Cada uma serve a uma parte diferente da sua pilha de aplicações: as ferramentas servem ao modelo, os recursos servem ao seu aplicativo e os prompts servem aos seus usuários.