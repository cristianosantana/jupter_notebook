export const demoUserId = import.meta.env.VITE_DEMO_USER_ID as
  | string
  | undefined

/** Etapas fictícias de “pipeline” no servidor — só para reduzir ansiedade à espera. */
export const PIPELINE_STEPS = [
  'Consultando base de dados…',
  'Buscando informações relevantes…',
  'Analisando resultados…',
  'Acertando detalhes…',
  'Formando resposta…',
] as const
