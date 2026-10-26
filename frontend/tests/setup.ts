import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom ne fournit pas ResizeObserver (utilise par react-chessboard).
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

afterEach(() => cleanup());
