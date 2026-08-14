/* Trailing debounce and one-at-a-time process coordination. */

export class EventQueue {
  constructor({ delayMs = 15000, setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout,
                onQuiet, onError = () => {} }) {
    this.delayMs = delayMs;
    this.setTimeoutFn = setTimeoutFn;
    this.clearTimeoutFn = clearTimeoutFn;
    this.onQuiet = onQuiet;
    this.onError = onError;
    this.pending = new Set();
    this.timer = null;
    this.running = false;
  }

  add(keys) {
    for (const key of keys ?? []) if (key) this.pending.add(key);
    this._restartTimer();
  }

  addOne(key) { this.add([key]); }

  _restartTimer() {
    if (this.timer !== null) this.clearTimeoutFn(this.timer);
    this.timer = this.setTimeoutFn(() => this._quiet(), this.delayMs);
  }

  async _quiet() {
    this.timer = null;
    if (this.running || this.pending.size === 0) return;
    const keys = [...this.pending];
    this.pending.clear();
    this.running = true;
    try {
      await this.onQuiet(keys);
    } catch (error) {
      this.onError(error);
    } finally {
      this.running = false;
      if (this.pending.size > 0) this._restartTimer();
    }
  }

  cancel() {
    if (this.timer !== null) this.clearTimeoutFn(this.timer);
    this.timer = null;
    this.pending.clear();
  }
}
