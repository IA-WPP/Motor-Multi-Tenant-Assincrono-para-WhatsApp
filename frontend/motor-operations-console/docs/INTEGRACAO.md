# Instalação no motor

## 1. Copiar os arquivos

Mantenha esta pasta como `motor-operations-console/` na raiz do seu clone do motor. Copie apenas `integration/ops_router.py` para `app/ops_router.py`.

Em `app/main.py`, depois de definir `get_redis_client`, acrescente:

```python
from app.ops_router import create_ops_router

app.include_router(create_ops_router(get_redis_client))
```

Não substitua main.py, lifespan, dependências ou endpoints existentes. O router usa SQLAlchemy/FastAPI já presentes no motor. Não exige dependências Python de produção adicionais nem mudanças no banco.

## 2. Configurar operadores no servidor

```bash
python motor-operations-console/integration/create_operator.py
```

O script lê uma senha ASCII de pelo menos 16 caracteres sem exibi-la e gera JSON com salt aleatório e PBKDF2-HMAC-SHA256 (600.000 iterações). Mantenha esse JSON em `OPS_USERS_JSON` no ambiente **da API**, sem colocar no frontend ou Git. Para vários operadores, una as entradas em um único objeto JSON. Guarde o valor em aspas simples no `.env` para preservar o `$` do hash; verifique como seu gerenciador de segredos trata interpolação.

Formato ilustrativo (valores não funcionais):

```json
{
  "operador": {
    "password_hash": "SALT_HEX$HASH_HEX",
    "tenant_ids": ["UUID_REAL_DA_EMPRESA"],
    "global_access": false
  }
}
```

Um administrador global recebe `global_access: true`; ele pode consultar todos os tenants, mesmo fora de `tenant_ids`. Não conceda esse papel a um operador de cliente. Não usar a mesma senha da chave administrativa.

`OPS_USERS_JSON` vazio impede o acesso com HTTP 503. HTTPS é obrigatório. `OPS_ALLOW_HTTP_LOCAL=true` existe exclusivamente para desenvolvimento em máquina local; nunca habilitar na VPS pública. Não colocar esses valores em `VITE_*`.

## 3. Desenvolvimento integrado

No terminal do backend, carregue `OPS_USERS_JSON` pelo mecanismo de ambiente da sua aplicação e, somente localmente, configure `OPS_ALLOW_HTTP_LOCAL=true`. Suba o backend em `127.0.0.1:8000`.

No frontend:

```dotenv
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=
```

```bash
npm ci
npm run dev
```

O Vite encaminha `/ops-api` para `http://127.0.0.1:8000`. Entre com o usuário e senha do operador. Nenhuma credencial é gravada em localStorage, cookies ou parâmetros de URL. Ao recarregar a página, autentique-se novamente.

## 4. Produção

Prefira console e API na mesma origem HTTPS para evitar CORS. O frontend gera arquivos estáticos:

```bash
npm ci
npm run build
```

As variáveis Vite são aplicadas durante o build. Alterar variáveis do container estático depois do build não muda o bundle. O `dist/` entregue é de demonstração; para conectar, reconstrua com `.env.local` em modo `api` ou use o Dockerfile, cujo padrão é `api`.

Há exemplos de extensão Compose e Caddy em `integration/`. Eles precisam ser incorporados à sua configuração existente:

1. Copie `compose.console.yml` para a raiz do motor, mantendo o frontend no caminho indicado.
2. Configure `OPS_USERS_JSON` no ambiente da API.
3. Acrescente o bloco `Caddyfile.console.example` ao Caddyfile existente e passe `DOMAIN_CONSOLE` para o serviço Caddy.
4. Configure o Uvicorn para confiar **somente no proxy interno conhecido** usando `--proxy-headers --forwarded-allow-ips=<IP_DO_CADDY>`. Garanta IP estável ou mecanismo confiável equivalente. Não habilite confiança irrestrita se a API puder ser alcançada por clientes fora do proxy. O router verifica `request.url.scheme`; sem proxy confiável o HTTPS externo pode aparecer como HTTP e será recusado.
5. Suba a extensão apenas após revisar os caminhos e redes:

```bash
docker compose -f docker-compose.prod.yml -f compose.console.yml up -d --build api motor-console caddy
```

Esses exemplos não foram implantados nem testados no seu Docker. Não publicam portas de Redis/PostgreSQL nem expõem Docker socket. Configure rate limiting de autenticação no gateway e mantenha os endpoints administrativos antigos protegidos por ADMIN_API_KEY.

## Novas rotas do console

Todas usam autenticação de operador. São novas rotas **implementadas no arquivo entregue**, não rotas preexistentes do README.

| GET | Resposta |
|---|---|
| `/ops-api/v1/session` | Operador, tenants autorizados e permissão global |
| `/ops-api/v1/overview?from=ISO&to=ISO&tenantId=UUID` | KPIs e 24 intervalos do throughput |
| `/ops-api/v1/conversations?from=ISO&to=ISO&tenantId=UUID&search=texto&status=handoff&cursor=0` | 6 sessões e nextCursor |
| `/ops-api/v1/events?from=ISO&to=ISO&tenantId=UUID` | Até 200 logs persistidos, sem payload bruto |
| `/ops-api/v1/instances?tenantId=UUID` | Instâncias ativas e estado observado |
| `/ops-api/v1/queues?tenantId=UUID` | Profundidades globais somente na visão global autorizada |
| `/ops-api/v1/orders?from=ISO&to=ISO&tenantId=UUID` | Até 200 pedidos |

`tenantId` é filtro, nunca prova de autorização. O servidor verifica a allowlist antes da consulta. Sua omissão é permitida apenas para operador global. Períodos são timezone-aware e limitados a 31 dias, com intervalo `[from, to)`. O inbox ordena por last_interaction DESC e ID; paginação por offset pode deslocar registros enquanto novas mensagens entram. Atualização automática é opcional e desligada inicialmente.

Mapeamento e validação de respostas estão em `src/api/contracts.ts`. O cliente trata 401/403 e contratos incompatíveis sem carregar dados demo. Alterações no seu schema local devem ser refletidas no router e no contrato, com revisão dos testes.

## Testar o módulo sem executar o motor conversacional

No ambiente Python do motor, com extras de teste instalados e a pasta ao lado de `app/`:

```bash
PYTHONPATH=.:motor-operations-console/integration DATABASE_URL=sqlite+aiosqlite:///:memory: \
  uv run python -m pytest motor-operations-console/integration/tests -q
```

A suíte usa os modelos reais com SQLite em memória e não inicia app.main, LangGraph, Gemini ou Evolution. Para verificar a agregação PostgreSQL percentile_cont, execute a validação em homologação com PostgreSQL; SQLite retorna latências indisponíveis intencionalmente.
