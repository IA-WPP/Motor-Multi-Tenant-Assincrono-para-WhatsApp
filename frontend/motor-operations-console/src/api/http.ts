import { z } from 'zod';
import { ConversationPageSchema, EventSchema, InstanceSchema, OrderSchema, OverviewSchema, QueueSchema, SessionSchema, type OperationsApi } from './contracts';

let authorization = '';
export function setOperatorCredentials(username: string, password: string) {
  authorization = username ? `Basic ${btoa(String.fromCharCode(...new TextEncoder().encode(`${username}:${password}`)))}` : '';
}

const prefix = '/ops-api/v1';
// Rotas PROPOSTAS para um BFF/adapter. Ajustar após inspecionar o backend real.
export function createHttpApi(baseUrl: string): OperationsApi {
  if (baseUrl && !/^https?:\/\//.test(baseUrl)) throw new Error('VITE_API_BASE_URL deve ser uma URL HTTP(S) absoluta ou vazia.');
  if (baseUrl && new URL(baseUrl).origin !== window.location.origin && new URL(baseUrl).protocol !== 'https:' && window.location.hostname !== 'localhost') {
    throw new Error('Use HTTPS para o backend remoto.');
  }
  async function get<T>(path: string, schema: z.ZodType<T>, values: Record<string, string | null | undefined> = {}, signal?: AbortSignal): Promise<T> {
    const url = new URL(`${baseUrl.replace(/\/$/, '')}${prefix}${path}`, window.location.origin);
    Object.entries(values).forEach(([key, value]) => { if (value) url.searchParams.set(key, value); });
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json', ...(authorization ? { Authorization: authorization } : {}) }, signal });
    if (response.status === 401) throw new Error('Sessão expirada. Autentique-se pelo fluxo do seu backend.');
    if (response.status === 403) throw new Error('O operador não tem autorização para este escopo.');
    if (!response.ok) throw new Error(`API indisponível (HTTP ${response.status}). Nenhum dado de demonstração foi usado.`);
    const parsed = schema.safeParse(await response.json());
    if (!parsed.success) throw new Error('Resposta incompatível com o contrato do console. Verifique o adaptador do backend.');
    return parsed.data;
  }
  return {
    session: signal => get('/session', SessionSchema, {}, signal),
    overview: (tenantId, from, to, signal) => get('/overview', OverviewSchema, { tenantId, from, to }, signal),
    conversations: (query, signal) => get('/conversations', ConversationPageSchema, query, signal),
    events: (tenantId, from, to, signal) => get('/events', z.array(EventSchema), { tenantId, from, to }, signal),
    instances: (tenantId, signal) => get('/instances', z.array(InstanceSchema), { tenantId }, signal),
    queues: (tenantId, signal) => get('/queues', z.array(QueueSchema), { tenantId }, signal),
    orders: (tenantId, from, to, signal) => get('/orders', z.array(OrderSchema), { tenantId, from, to }, signal),
  };
}
