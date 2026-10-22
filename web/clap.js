// Double-clap state machine. Input comes only from explicitly enabled microphone monitoring.
class DoubleClapDetector {
  constructor() { this.reset(); }
  reset() { this.first = null; this.last = -Infinity; this.armed = true; this.floor = 0.001; }
  feed(level, now) {
    if (!Number.isFinite(level) || level < 0 || !Number.isFinite(now)) return false;
    if (level < this.floor * 2.2) this.floor = Math.max(0.0001, this.floor * 0.992 + level * 0.008);
    const threshold = Math.max(0.012, this.floor * 7);
    if (level < threshold * 0.55) this.armed = true;
    if (!this.armed || level < threshold || now - this.last < 1.2) return false;
    this.armed = false;
    if (this.first !== null && now - this.first >= 0.05 && now - this.first <= 0.35) {
      this.first = null; this.last = now; return true;
    }
    this.first = now;
    return false;
  }
}
if (typeof module !== 'undefined') module.exports = { DoubleClapDetector };
