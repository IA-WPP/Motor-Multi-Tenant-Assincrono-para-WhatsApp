import { demoApi } from './demo';
import { createHttpApi } from './http';

const source = import.meta.env.VITE_DATA_SOURCE ?? 'demo';
if (!['demo', 'api'].includes(source)) throw new Error('VITE_DATA_SOURCE deve ser demo ou api.');
export const isDemo = source === 'demo';
export const api = isDemo ? demoApi : createHttpApi(import.meta.env.VITE_API_BASE_URL ?? '');
