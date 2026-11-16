# Validação da entrega

Verificações locais executadas em 16/11/2026:

| Verificação | Resultado |
|---|---|
| TypeScript em modo strict + Vite production build | Aprovado |
| Cliente HTTP (Vitest) | 5 testes: erros, contrato, headers, escopo, HTTPS e timestamp com offset |
| Router FastAPI com modelos reais e SQLite em memória | 16 casos aprovados |
| Leitura do ZIP e integridade dos arquivos | Conferida na geração da entrega |

Os testes do router cobrem autenticação, configuração ausente, HTTPS obrigatório, autorização em todas as seis rotas de dados, escopo global, isolamento de mensagens com o mesmo telefone em tenants distintos, mascaramento de telefone, omissão de payload bruto, filtros, paginação, contagens reais, ausência de métricas não instrumentadas e conexão com telemetria antiga.

O build `dist/` incluído está em modo **demo**. O Dockerfile reconstrói em modo **api** por padrão. Execute a demonstração pelo Vite ou por um servidor estático; abrir index.html diretamente por file:// não carrega corretamente os módulos.

## Limites da verificação

- Não foi executado navegador: o controlador de browser exigido pelo fluxo Sites não estava disponível neste ambiente. Responsividade e interações foram implementadas, mas a inspeção visual e a verificação assistiva manual permanecem pendentes.
- Não houve acesso à VPS, ao PostgreSQL ou ao Redis do usuário. LLEN foi testado com um fake. Percentis PostgreSQL estão implementados, mas a execução dessa agregação precisa de homologação no PostgreSQL.
- Não foram executados os testes originais do motor nem seus prompt evals. Nenhum arquivo existente do motor foi alterado.
- Docker/Compose/Caddy são exemplos de implantação; não houve build de imagem ou publicação.
- As consultas existentes no README foram verificadas no código público no commit documentado. A versão da instalação do usuário pode divergir.

## Conferência antes de usar com dados reais

Compare os modelos locais com o commit de referência, rode os testes do router no ambiente Python do motor e os checks originais exigidos pelo seu CI. Em homologação, confirme que um operador de tenant A recebe 403 ao pedir tenant B ou visão global; que o browser não contém ADMIN_API_KEY; que os timestamps e percentis correspondem ao PostgreSQL; e que dados antigos de conexão aparecem como desconhecidos.
