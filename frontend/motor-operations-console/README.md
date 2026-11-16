# Motor Operations Console

Frontend independente para o **Motor-Multi-Tenant-Assincrono-para-WhatsApp**, com módulo FastAPI aditivo para integração. Interface em português, navegação conforme o briefing e tema escuro operacional.

## Abrir a demonstração

Requisitos: Node.js 22+ e npm.

```bash
npm ci
cp .env.example .env.local
npm run dev
```

Abra a URL informada pelo Vite. O padrão é `VITE_DATA_SOURCE=demo`; todos os dados fictícios são identificados na interface. A demonstração não envia mensagens nem executa ações no motor.

## Integrar ao backend

Leia **[docs/INTEGRACAO.md](docs/INTEGRACAO.md)**. A pasta pode ser colocada como `motor-operations-console/` na raiz do seu repositório.

1. Copie `integration/ops_router.py` para `app/ops_router.py` no motor.
2. Registre o router em `app/main.py`, depois da definição de `get_redis_client`.
3. Configure os operadores no servidor com `integration/create_operator.py`.
4. Use `VITE_DATA_SOURCE=api` e reinicie o Vite ou gere um novo build.

**Não basta apontar o frontend para a API antiga.** O módulo aditivo fornece as rotas de consulta que ainda não existiam. As rotas antigas ficam preservadas. Não coloque `ADMIN_API_KEY`, segredos Evolution, PostgreSQL ou Redis em variáveis `VITE_*`.

## Entrega

```text
motor-operations-console/
├── src/
│   ├── api/                 # contratos Zod, cliente HTTP e demo separados
│   ├── main.tsx             # shell, telas e interações
│   └── styles.css           # design system, responsividade e acessibilidade
├── integration/
│   ├── ops_router.py        # consultas reais, autenticação e escopo no servidor
│   ├── create_operator.py   # geração interativa de hash PBKDF2
│   ├── tests/               # testes de autorização e isolamento
│   └── *.yml / Caddyfile*   # exemplos de implantação
├── docs/                    # diagnóstico, integração e limites
├── tests/                   # testes do cliente HTTP
├── dist/                    # build de demonstração já gerado
└── Dockerfile               # build de produção em modo API
```

## Funcionalidades

- Shell com 11 destinos, seletor de tenant autorizado, busca na tela, período, atualização manual, atualização automática opcional e alertas derivados da amostra carregada.
- Overview com métricas definidas, throughput em 24 intervalos, tabela acessível dos valores, instâncias e filas.
- Inbox em três painéis; paginação de 6 sessões, busca por nome/telefone, filtro de handoff, histórico somente leitura e inspetor Context/Events/Logs/Trace.
- Pedidos registrados, eventos/auditoria, falhas, bloqueios persistidos, tenants e conexões.
- Modo API sem fallback silencioso para dados fictícios; validação dos contratos; credencial de operador apenas em memória, descartada ao sair ou recarregar a página.

## Limites explícitos

Não há envio manual, replay/exclusão de DLQ, provisionamento de tenants, conciliação bancária, coleta de VPS, heartbeat de workers ou tracing distribuído. Telas e estados indicam a indisponibilidade. Pedidos/auditoria são amostras de até 200 registros; histórico mostra as últimas 200 mensagens por sessão. Consulte [docs/DIAGNOSTICO.md](docs/DIAGNOSTICO.md) e [docs/VALIDACAO.md](docs/VALIDACAO.md).

## Verificação

```bash
npm test
npm run build
```

Os testes do router usam SQLite e não chamam Gemini, WhatsApp ou Evolution. Integração ao ambiente real, PostgreSQL e implantação precisam de validação na sua homologação. Não foram feitas mudanças no seu backend remoto nem publicação.
