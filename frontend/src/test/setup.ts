import '@testing-library/jest-dom/vitest';

// jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one. The charts then
// render at their initialDimension, which is enough to test what they draw.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
