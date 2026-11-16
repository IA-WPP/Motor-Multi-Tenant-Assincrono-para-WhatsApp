import { afterEach, describe, expect, it, vi } from 'vitest';
import { createHttpApi, setOperatorCredentials } from '../src/api/http';
import { EventSchema } from '../src/api/contracts';

vi.stubGlobal('window', { location: { origin: 'https://console.test', hostname: 'console.test' } });
afterEach(() => { vi.unstubAllGlobals(); vi.stubGlobal('window', { location: { origin: 'https://console.test', hostname: 'console.test' } }); setOperatorCredentials('', ''); });
describe('API operacional', () => {
  it('não usa dados demo quando a API falha', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })));
    await expect(createHttpApi('').session()).rejects.toThrow('503');
  });
  it('rejeita contrato inválido em vez de renderizar dados parciais', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ canViewGlobal: true }))));
    await expect(createHttpApi('').session()).rejects.toThrow('contrato');
  });
  it('envia escopo como filtro e credencial de operador somente no header', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], nextCursor: null })));
    vi.stubGlobal('fetch', fetch);
    setOperatorCredentials('ops', 'test-secret');
    await createHttpApi('').conversations({ tenantId: 'tenant-a', search: 'Maria & Cia', status: '', from: '2026-01-01T00:00:00Z', to: '2026-01-02T00:00:00Z' });
    const [url, options] = fetch.mock.calls[0];
    expect(url.searchParams.get('tenantId')).toBe('tenant-a');
    expect(url.searchParams.get('search')).toBe('Maria & Cia');
    expect(url.href).not.toContain('test-secret');
    expect(options.headers.Authorization).toMatch(/^Basic /);
    expect(options.cache).toBe('no-store');
  });
  it('não permite backend remoto HTTP em produção HTTPS', () => {
    expect(() => createHttpApi('http://api.test')).toThrow('HTTPS');
  });
  it('aceita timestamps UTC com offset emitidos pelo FastAPI', () => {
    expect(EventSchema.safeParse({ id: 'a', tenantId: 't', conversationId: null,
      at: '2026-11-16T06:00:00+00:00', service: 'audit_logs', kind: 'message_processed',
      severity: 'info', summary: 'Evento persistido', code: null }).success).toBe(true);
  });
});
