# Fechamento Gerencial Por Mes

Esta colecao de queries responde perguntas de fechamento gerencial mensal a partir de OS pagas, producao, comissoes, pagamentos, parcelamentos e taxas de cartao.

Use estas queries sempre que a pergunta mencionar fechamento gerencial, fechamento mensal, resumo gerencial do mes, composicao do faturamento mensal, producao do mes, comissoes de concessionarias, parcelamento de cartao ou taxas de cartao.

## Filtros conceituais

- `periodo`: mes ou ano analisado. Nas queries documentais, `@mes = 0` significa ano inteiro.
- `business_unit_id`: unidade de negocio. Valor `0` significa todas.
- `tipo_grupo_servico`: recorte de grupo de servico. Valor `0` significa completo, `1` sem couro e `2` apenas couro.
- `caixa_tipo_id`: tipo de caixa/pagamento usado em consultas de parcelamento.
- `empresa_faturamento_id`: empresa de faturamento usada em consultas de parcelamento. Valor `0` significa todas.

## Queries da colecao

- `ComissaoConcessionaria1.sql`: total de servicos e comissao por concessionaria para OS dos tipos 1, 2 e 11.
- `ComissaoConcessionaria2.sql`: composicao de valores por concessionaria em corte, financeiro e prestacao.
- `ProducaoPorServico.sql`: quantidade, total e custo fixo por servico vendido.
- `ProducaoPorProduto.sql`: quantidade e total por produto vendido.
- `FaturamentoPorTipoDePagamento.sql`: pagamentos, estornos e total liquido por forma de pagamento.
- `FaturamentoPorTipoDeVenda.sql`: faturamento de servicos por tipo de venda/OS.
- `FaturamentoPorTipoDeVendaIncluiOsTipoId11.sql`: faturamento de produtos do tipo de venda/OS 11.
- `ParcelamentoCartao.sql`: quantidade de OS e total por quantidade de parcelas no cartao.
- `TaxasCartaoCreditoAgrupadas.sql`: valor bruto, liquido, taxa e bandeira por empresa e quantidade de parcelas.

## Perguntas que esta colecao responde

- "Faca o fechamento gerencial de maio de 2026."
- "Como ficou o faturamento por tipo de pagamento no mes?"
- "Quanto produzimos por servico e por produto?"
- "Qual concessionaria gerou mais comissao?"
- "Qual foi a composicao do faturamento por tipo de venda?"
- "Quais parcelas concentraram mais valor no cartao?"
- "Quais taxas de cartao tivemos por empresa e bandeira?"

Perguntas amplas de fechamento gerencial devem acionar varias queries desta colecao. Perguntas especificas devem acionar apenas a query relacionada ao recorte pedido.
