import { ApiError } from '../api/client';
import { shouldRetry } from './queryClient';

describe('shouldRetry', () => {
  it('never retries a client error such as 404', () => {
    const notFound = new ApiError('http', 'Incident INC-9999 not found.', { status: 404 });
    expect(shouldRetry(0, notFound)).toBe(false);
  });

  it('retries once when the backend is unreachable or failing', () => {
    const unreachable = new ApiError('unreachable', 'Sentinel API unreachable.');
    const serverError = new ApiError('http', 'Unexpected server error.', { status: 500 });
    expect(shouldRetry(0, unreachable)).toBe(true);
    expect(shouldRetry(0, serverError)).toBe(true);
    expect(shouldRetry(1, unreachable)).toBe(false);
  });
});
