# Diagnóstico do backend

## Fonte inspecionada

README enviado pelo usuário e clone de leitura do repositório público `https://github.com/IA-WPP/Motor-Multi-Tenant-Assincrono-para-WhatsApp`, commit `b0cb9a81c09de1d40d129fea01bba7a85357e4dc`. Inspeção em 16/11/2026. O ambiente de produção do usuário não foi acessado. O briefing recebido termina no início da seção 7; não há requisitos posteriores nesse arquivo.

Foram consultados README, `app/main.py`, modelos, schemas, database, security, logging_config, queue_worker, connection_monitor, webhook_processor, graph, guardrails_service, vision, evolution_client, Docker Compose de produção, Caddy e CI. O código é a referência para contratos; o README descreve intenções que não substituem os contratos reais.

## Já existente

| Endpoint | Uso confirmado |
|---|---|
| `GET /health` | Retorna status fixo do processo; não testa Redis, PostgreSQL ou Evolution |
| `POST /webhook/evolution` | Ingestão de mensagens e conexão; não é endpoint de envio humano |
| `GET /api/instances/health` | Lista instâncias de empresas ativas e resumo de conexão |
| `GET /api/companies/{company_id_or_instance}/connection-status` | Estado e duração de desconexão |
| `GET /audit/logs/{company_id_or_instance}?limit=50` | Até 200 logs persistidos; sem cursor/período |
| `GET /docs` | OpenAPI da aplicação |

O nome dos parâmetros de caminho na implementação aceita UUID **ou** instance_name. A proteção administrativa usa uma chave global e pode ser desativada quando `ADMIN_API_KEY` está vazia. Essa chave não define permissões de operador por empresa.

Modelos confirmados: `Company`, `CustomerSession`, `MessageHistory`, `OrderRecord`, `AuditLog`, `KnowledgeChunk`. `CustomerSession.session_data` persiste `human_handoff` e `order_id`. `MessageHistory` contém role, conteúdo e timestamp; não contém estado de entrega, ID Evolution, mídia estruturada ou unread. `OrderRecord.items` usa `descricao` e `quantidade`; não há total financeiro normalizado nem confirmação de liquidação.

`AuditLog` contém id, company_id, event_type, phone_number, payload, execution_time_ms e created_at. Registros persistidos incluem `message_processed`, `WHATSAPP_SEND_FAILED` (em certos fluxos de envio aguardado), conexão e desconexão. `log_audit_event()` emite **stdout**; não grava automaticamente em `audit_logs`. Não se pode presumir que todos os eventos de fila, locks ou guardrails estejam consultáveis pela API de auditoria.

## Lacunas e decisões de implementação

| Necessidade | Entrega / limite |
|---|---|
| Autenticação de operador e permissão por tenant | Router separado com credencial própria, hashes PBKDF2 e allowlist no servidor |
| Leitura de conversas e pedidos | Novas rotas aditivas consultam os modelos existentes; zero migrações obrigatórias |
| Filtragem e paginação do inbox | SQL no servidor; offset limitado, 6 sessões/página, desempate por ID |
| Conexão fresca | Usa `Company.settings.last_connection_update`; após 300s, `unknown` |
| Throughput | Conta somente `message_processed` persistido, com período UTC e 24 intervalos |
| Latência P50/P95 | PostgreSQL percentile_cont sobre execution_time_ms de message_processed. Não inclui espera da fila. SQLite: indisponível |
| Sucesso no envio | Indisponível: faltam denominador e confirmações persistidas suficientes |
| Filas Redis | LLEN global somente para operador global; por tenant fica indisponível |
| Idade, retries, locks e evolução da fila | Exigem instrumentação/snapshots adicionais; não inferidos |
| Workers ativos | Indisponível sem heartbeat |
| Correlacionar auditoria com sessão | Associação por company_id + telefone; não é trace distribuído nem relação causal comprovada |
| Guardrails | Mostra bloqueios persistidos se existirem; stdout ainda requer coletor |
| VPS/containers | Requer coletor autenticado no servidor; sem Docker socket no frontend |
| Ações operacionais | Sem envio humano, replay ou exclusão |

## Segurança e compatibilidade

- Todas as novas consultas aplicam autorização de operador e filtro SQL de tenant. Telefones iguais em empresas distintas não compartilham lookup de mensagens ou eventos.
- Operadores restritos não podem omitir tenant para obter visão global. Somente `global_access=true` permite essa visão e filas compartilhadas.
- Payload bruto da auditoria, segredos e telefone completo são omitidos das novas respostas. Conteúdo de mensagens continua sendo dado pessoal e requer operador autorizado.
- Estado `unknown` não é contado como saudável. O resumo global antigo calcula online como total menos offline; o novo console usa estado `open` fresco explicitamente.
- Rotas antigas permanecem intactas; o módulo não altera o motor conversacional. A configuração `OPS_USERS_JSON` é independente de `ADMIN_API_KEY`.
- HTTPS é obrigatório no router por padrão. A credencial de operador usa Basic sobre TLS e fica em memória do frontend. Para múltiplos operadores em produção, recomenda-se substituir essa dependência por SSO/sessões corporativas, rate limiting no gateway e gestão central de acesso.
- Não houve inspeção da base real, aprovação de contratos no seu deploy, migração ou acesso a credenciais.

## Plano incremental

1. Copiar pasta e router, configurar operador restrito e validar em homologação; comparar a versão local do motor com o commit de referência.
2. Confirmar consultas/isolamento no PostgreSQL e configurar Caddy/HTTPS. Não mudar rotas existentes.
3. Após observar volume, avaliar índices compostos em audit_logs(company_id, created_at), customer_sessions(company_id, last_interaction) e message_history(company_id, customer_phone, created_at). Criar migração Alembic revisada somente se necessária.
4. Instrumentar tracing OpenTelemetry, heartbeat de workers, métricas de envio e snapshots de filas. Correlacionar message_id/trace_id desde o webhook, evitando PII em atributos.
5. Definir e testar fluxo autorizado/auditado de handoff e envio humano antes de habilitar mutações. DLQ exige autorização, idempotência e auditoria próprias.
