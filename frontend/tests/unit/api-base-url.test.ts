import { describe, expect, it, vi } from 'vitest';
import { DEV_API_BASE_URL, resolveApiBaseUrl } from '../../src/api/client';

describe('API base URL resolution', () => {
  it('uses the local backend in development', () => {
    expect(resolveApiBaseUrl({ DEV: true })).toBe(DEV_API_BASE_URL);
    expect(resolveApiBaseUrl({ DEV: true, VITE_API_BASE_URL: 'http://localhost:9000/' })).toBe('http://localhost:9000');
  });

  it('uses the same origin in production when nothing is configured', () => {
    expect(resolveApiBaseUrl({ DEV: false })).toBe('');
    expect(resolveApiBaseUrl({ DEV: false, VITE_API_BASE_URL: '   ' })).toBe('');
    // requests then go to /api/v1/... and /health on the deployed origin
    expect(`${resolveApiBaseUrl({ DEV: false })}/api/v1/rag/sources`).toBe('/api/v1/rag/sources');
  });

  it('honours a valid explicit production backend', () => {
    expect(resolveApiBaseUrl({ DEV: false, VITE_API_BASE_URL: 'https://api.example.org/' })).toBe('https://api.example.org');
    expect(resolveApiBaseUrl({ DEV: false, VITE_API_BASE_URL: '/backend' })).toBe('/backend');
  });

  it('ignores loopback or plain-http overrides in production (the live-site bug)', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    for (const bad of ['http://127.0.0.1:8000', 'https://localhost:8000', 'http://api.example.org', 'https://[::1]:8000', 'ftp://x']) {
      expect(resolveApiBaseUrl({ DEV: false, VITE_API_BASE_URL: bad }), bad).toBe('');
    }
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
