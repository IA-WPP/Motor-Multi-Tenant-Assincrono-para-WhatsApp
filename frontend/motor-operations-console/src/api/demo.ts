import type { Conversation, Instance, OperationsApi, OpsEvent, Overview, Queue } from './contracts';

const now = Date.now();
const ago = (minutes: number) => new Date(now - minutes * 60_000).toISOString();
const tenants = [{ id: 't-acme', name: 'Acme Commerce' }, { id: 't-orbita', name: 'Órbita Digital' }, { id: 't-nova', name: 'Nova Saúde' }];
const names = ['Mariana Costa', 'Rafael Almeida', 'Beatriz Santos', 'Lucas Oliveira', 'Camila Ferreira', 'Pedro Martins', 'Ana Rodrigues', 'Bruno Lima', 'Juliana Rocha', 'Diego Souza', 'Laura Alves', 'Gabriel Melo'];
const previews = ['Perfeito, pode confirmar o pedido.', 'Qual o prazo de entrega para Manaus?', 'Não consegui finalizar o pagamento.', 'Gostaria de falar com um atendente.', 'Vocês têm esse produto disponível?', 'Obrigado pelo atendimento!'];
const conversations: Conversation[] = names.map((customer, i) => ({
  id: `conv-${String(i + 1).padStart(4, '0')}`, tenantId: tenants[i % 3].id, customer,
  phone: `+55 •• •••••-${String(2000 + i * 137)}`, preview: previews[i % 6], updatedAt: ago(i * 4 + 1),
  status: i === 2 || i === 8 ? 'error' : i === 3 || i === 7 ? 'handoff' : i === 5 ? 'closed' : 'active',
  unread: i < 3 ? i + 1 : 0, instance: `wa-${tenants[i % 3].id.slice(2)}-01`, sessionId: `session-demo-${i + 1}`,
  graphState: i === 2 ? 'send_response_failed' : 'awaiting_customer', orderId: i === 0 ? 'DEMO-1042' : null,
  messages: [
    { id: `m-${i}-1`, role: 'customer', text: 'Olá! Gostaria de saber mais sobre o meu pedido.', at: ago(i * 4 + 10), delivery: 'delivered' },
    { id: `m-${i}-2`, role: 'ai', text: 'Olá! Sou o assistente da loja. Posso ajudar com o status, pagamento ou entrega do seu pedido. Como posso ajudar?', at: ago(i * 4 + 9), delivery: 'delivered' },
    { id: `m-${i}-3`, role: 'customer', text: previews[i % 6], at: ago(i * 4 + 1), delivery: 'delivered' },
    ...(i === 2 ? [{ id: `m-${i}-4`, role: 'ai' as const, text: 'Vamos verificar as opções de pagamento para você.', at: ago(i * 4), delivery: 'failed' as const }] : []),
  ],
}));
const events: OpsEvent[] = Array.from({ length: 36 }, (_, i) => ({
  id: `evt-demo-${i + 1}`, tenantId: tenants[i % 3].id, conversationId: conversations[i % 12].id,
  at: ago(i * 2), service: ['webhook-api', 'queue-worker', 'evolution-client', 'guardrails'][i % 4],
  kind: ['WEBHOOK_RECEIVED', 'MESSAGE_PROCESSED', 'SEND_FAILED', 'GUARDRAIL_PASSED'][i % 4],
  severity: i % 4 === 2 ? 'error' : 'info',
  summary: ['Webhook recebido e validado', 'Mensagem processada pelo worker', 'Evolution API não respondeu no tempo limite', 'Conteúdo aprovado pelo guardrail'][i % 4],
  code: i % 4 === 2 ? 'EVOLUTION_TIMEOUT' : null,
}));
const instances: Instance[] = tenants.map((t, i) => ({ id: `inst-${i}`, tenantId: t.id, name: `wa-${t.id.slice(2)}-01`, status: i === 2 ? 'reconnecting' : 'connected', observedAt: ago(1), phone: '+55 •• •••••-0000' }));
const queues: Queue[] = [
  { key: 'queue:webhooks:pending', depth: 24, oldestAgeSeconds: 18 },
  { key: 'queue:webhooks:processing', depth: 8, oldestAgeSeconds: 4 },
  { key: 'queue:webhooks:dlq', depth: 3, oldestAgeSeconds: 560 },
];
const wait = async <T,>(value: T, signal?: AbortSignal): Promise<T> => {
  signal?.throwIfAborted();
  await new Promise(resolve => setTimeout(resolve, 180));
  signal?.throwIfAborted();
  return structuredClone(value);
};
const scope = <T extends { tenantId: string }>(rows: T[], tenantId: string | null) => rows.filter(r => !tenantId || r.tenantId === tenantId);
export const demoApi: OperationsApi = {
  session: signal => wait({ operator: { name: 'Alex Morgan', role: 'Operador · demonstração' }, canViewGlobal: true, tenants }, signal),
  overview: (tenantId, from, to, signal) => {
    const rows = scope(conversations, tenantId).filter(c => c.updatedAt >= from && c.updatedAt <= to);
    const evs = scope(events, tenantId).filter(e => e.at >= from && e.at <= to);
    const start = Date.parse(from), end = Date.parse(to), step = (end - start) / 24;
    const data: Overview = { from, to, metrics: [
      { label: 'Instâncias conectadas', value: scope(instances, tenantId).filter(i => i.status === 'connected').length, unit: 'instâncias', definition: 'Último estado observado nas instâncias fictícias; medição atual, sem relação com o período.' },
      { label: 'Conversas ativas', value: rows.filter(c => c.status === 'active').length, unit: 'conversas', definition: 'Conversas fictícias ativas com interação no período selecionado.' },
      { label: 'Mensagens processadas', value: evs.filter(e => e.kind === 'MESSAGE_PROCESSED').length, unit: 'mensagens', definition: 'Eventos fictícios MESSAGE_PROCESSED no período.' },
      { label: 'Handoffs humanos', value: rows.filter(c => c.status === 'handoff').length, unit: 'conversas', definition: 'Conversas fictícias em handoff com interação no período.' },
      ...['Latência P50', 'Latência P95', 'Sucesso no envio', 'Workers ativos'].map(label => ({ label, value: null, unit: label.includes('Latência') ? 'ms' : label.includes('Sucesso') ? '%' : 'workers', definition: 'Indisponível: requer instrumentação e definição de agregação no backend.' })),
    ], throughput: Array.from({ length: 24 }, (_, i) => ({
      at: new Date(start + i * step).toISOString(), p95: null,
      count: evs.filter(e => e.kind === 'MESSAGE_PROCESSED' && Date.parse(e.at) >= start + i * step && Date.parse(e.at) < start + (i + 1) * step).length,
    })) };
    return wait(data, signal);
  },
  conversations: (query, signal) => {
    const filtered = scope(conversations, query.tenantId).filter(c =>
      (!query.status || c.status === query.status) && c.updatedAt >= query.from && c.updatedAt <= query.to &&
      `${c.customer} ${c.phone}`.toLowerCase().includes(query.search.toLowerCase()));
    const offset = Number(query.cursor || 0), items = filtered.slice(offset, offset + 6);
    return wait({ items, nextCursor: offset + 6 < filtered.length ? String(offset + 6) : null }, signal);
  },
  events: (tenantId, from, to, signal) => wait(scope(events, tenantId).filter(e => e.at >= from && e.at <= to), signal),
  instances: (tenantId, signal) => wait(scope(instances, tenantId), signal),
  queues: (tenantId, signal) => wait(tenantId ? queues.map(q => ({ ...q, depth: null, oldestAgeSeconds: null })) : queues, signal),
  orders: (tenantId, from, to, signal) => wait(scope(conversations, tenantId).filter(c => c.orderId && c.updatedAt >= from && c.updatedAt <= to).map(c => ({
    id: c.orderId!, tenantId: c.tenantId, customer: c.customer, phone: c.phone,
    status: 'recebido', paymentMethod: 'pix', at: c.updatedAt,
    items: [{ name: 'Produto de demonstração', quantity: 2 }],
  })), signal),
};
