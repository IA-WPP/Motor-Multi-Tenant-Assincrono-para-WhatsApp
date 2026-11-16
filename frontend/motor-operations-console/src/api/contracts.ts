import { z } from 'zod';

// Modelo de apresentação proposto. Não representa contratos verificados do motor.
export const TenantSchema = z.object({ id: z.string(), name: z.string() });
export const SessionSchema = z.object({
  operator: z.object({ name: z.string(), role: z.string() }),
  canViewGlobal: z.boolean(), tenants: z.array(TenantSchema),
});
export const MessageSchema = z.object({
  id: z.string(), role: z.enum(['customer', 'ai', 'operator']), text: z.string(),
  at: z.string().datetime({ offset: true }), delivery: z.enum(['sent', 'delivered', 'failed', 'unknown']),
  media: z.string().optional(),
});
export const ConversationSchema = z.object({
  id: z.string(), tenantId: z.string(), customer: z.string(), phone: z.string(),
  preview: z.string(), updatedAt: z.string().datetime({ offset: true }),
  status: z.enum(['active', 'handoff', 'error', 'closed']), unread: z.number().int().nonnegative().nullable(),
  instance: z.string().nullable(), sessionId: z.string().nullable(), graphState: z.string().nullable(),
  orderId: z.string().nullable(), messages: z.array(MessageSchema),
});
export const EventSchema = z.object({
  id: z.string(), tenantId: z.string(), conversationId: z.string().nullable(),
  at: z.string().datetime({ offset: true }), service: z.string(), kind: z.string(),
  severity: z.enum(['info', 'warning', 'error']), summary: z.string(), code: z.string().nullable(),
});
export const InstanceSchema = z.object({
  id: z.string(), tenantId: z.string(), name: z.string(),
  status: z.enum(['connected', 'disconnected', 'reconnecting', 'unknown']),
  observedAt: z.string().datetime({ offset: true }).nullable(), phone: z.string(),
});
export const MetricSchema = z.object({
  label: z.string(), value: z.number().nullable(), unit: z.string(), definition: z.string(),
});
export const OverviewSchema = z.object({
  from: z.string().datetime({ offset: true }), to: z.string().datetime({ offset: true }), metrics: z.array(MetricSchema),
  throughput: z.array(z.object({ at: z.string().datetime({ offset: true }), count: z.number().nonnegative(), p95: z.number().nonnegative().nullable() })),
});
export const QueueSchema = z.object({
  key: z.enum(['queue:webhooks:pending', 'queue:webhooks:processing', 'queue:webhooks:dlq']),
  depth: z.number().int().nonnegative().nullable(), oldestAgeSeconds: z.number().nonnegative().nullable(),
});
export const OrderSchema = z.object({
  id: z.string(), tenantId: z.string(), customer: z.string(), phone: z.string(),
  status: z.string(), paymentMethod: z.string().nullable(), at: z.string().datetime({ offset: true }),
  items: z.array(z.object({ name: z.string(), quantity: z.number().nullable() })),
});
export type Order = z.infer<typeof OrderSchema>;
export const ConversationPageSchema = z.object({ items: z.array(ConversationSchema), nextCursor: z.string().nullable() });
export type Session = z.infer<typeof SessionSchema>;
export type Conversation = z.infer<typeof ConversationSchema>;
export type OpsEvent = z.infer<typeof EventSchema>;
export type Instance = z.infer<typeof InstanceSchema>;
export type Overview = z.infer<typeof OverviewSchema>;
export type Queue = z.infer<typeof QueueSchema>;
export type ConversationQuery = {
  tenantId: string | null; search: string; status: string; from: string; to: string; cursor?: string;
};
export interface OperationsApi {
  session(signal?: AbortSignal): Promise<Session>;
  overview(tenantId: string | null, from: string, to: string, signal?: AbortSignal): Promise<Overview>;
  conversations(query: ConversationQuery, signal?: AbortSignal): Promise<z.infer<typeof ConversationPageSchema>>;
  events(tenantId: string | null, from: string, to: string, signal?: AbortSignal): Promise<OpsEvent[]>;
  instances(tenantId: string | null, signal?: AbortSignal): Promise<Instance[]>;
  queues(tenantId: string | null, signal?: AbortSignal): Promise<Queue[]>;
  orders(tenantId: string | null, from: string, to: string, signal?: AbortSignal): Promise<Order[]>;
}
