// CJOV1 carries semantic snapshots, never per-second screen contents.
export type OverviewState = {
  generation: number; session: string; sequence: number; sampledAt: number;
  mode: number; phase: number; group: number; elapsed: number; remaining: number;
  nextStart: number; roundEnd: number; dayEnd: number; completedAt: number;
  running: number[]; completed: number[]; waiting: number[]; fault: boolean;
  receivedAt: number;
};
export const OVERVIEW_STALE_MS = 85000;

export function decodeGroups(hex: string): number[] {
  const result: number[] = [];
  for (let i = 0; i < 16; i += 1) {
    const byte = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
    for (let bit = 0; bit < 8; bit += 1) if (byte & (1 << bit)) result.push(i * 8 + bit + 1);
  }
  return result;
}

export function parseOverview(frame: string, token: string, now: number): OverviewState | null {
  if (frame.length > 550) return null;
  const p = frame.split('|');
  if (p.length !== 20 || p[0] !== 'CJOV1' || p[1] !== 'S' || p[2] !== token
      || !/^[0-9A-F]{8}$/.test(token) || !/^[0-9A-F]+-[0-9A-F]+$/.test(p[4])) return null;
  for (const i of [3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 19]) {
    if (!/^\d{1,10}$/.test(p[i]) || !Number.isSafeInteger(Number(p[i]))) return null;
  }
  if (!p.slice(16, 19).every(mask => /^[0-9A-F]{32}$/.test(mask))) return null;
  const n = p.map(Number);
  if (n[3] < 1 || n[5] < 1 || n[7] > 2 || n[8] > 6 || n[9] > 128
      || n[10] > 31536000 || n[11] > 31536000 || n[19] > 1) return null;
  return { generation: n[3], session: p[4], sequence: n[5], sampledAt: n[6],
    mode: n[7], phase: n[8], group: n[9], elapsed: n[10], remaining: n[11],
    nextStart: n[12], roundEnd: n[13], dayEnd: n[14], completedAt: n[15],
    running: decodeGroups(p[16]), completed: decodeGroups(p[17]), waiting: decodeGroups(p[18]),
    fault: n[19] === 1, receivedAt: now };
}

// Injectable clock/transport makes foreground, reconnect and expiry behavior testable.
export class OverviewSubscription {
  readonly token: string;
  current: OverviewState | null = null;
  private active = false;
  private started = 0;
  private lastKeep = 0;
  private retries = 0;
  private retiredSessions: string[] = [];
  constructor(private send: (frame: string) => void, private clock: () => number,
    token: string) { this.token = token; }
  start() {
    if (this.active) return;
    this.active = true; this.started = this.clock(); this.lastKeep = this.started;
    this.send(`CJOV1|Q|${this.token}`);
  }
  stop() {
    if (!this.active) return;
    this.active = false; this.send(`CJOV1|U|${this.token}`);
  }
  accept(frame: string): OverviewState | null {
    if (!this.active) return null;
    const next = parseOverview(frame, this.token, this.clock());
    if (!next || this.retiredSessions.includes(next.session)) return null;
    if (this.current?.session === next.session && next.sequence <= this.current.sequence) return null;
    if (this.current && this.current.session !== next.session) {
      this.retiredSessions = [...this.retiredSessions.slice(-7), this.current.session];
    }
    this.current = next; this.retries = 0;
    return next;
  }
  tick() {
    if (!this.active) return;
    const now = this.clock();
    if (now - this.lastKeep >= 60000) {
      this.lastKeep = now; this.send(`CJOV1|K|${this.token}`);
    }
    // Recover a lost entry snapshot, but never poll endlessly on old firmware.
    const age = now - (this.current?.receivedAt ?? this.started);
    const threshold = this.current ? OVERVIEW_STALE_MS : 10000;
    if (age >= threshold + this.retries * 20000 && this.retries < 3) {
      this.retries += 1; this.send(`CJOV1|Q|${this.token}`);
    }
  }
}

export function overviewSeconds(s: OverviewState, now: number) {
  const delta = Math.max(0, Math.min(OVERVIEW_STALE_MS, now - s.receivedAt)) / 1000;
  return { elapsed: s.elapsed + Math.floor(s.phase === 3 ? delta : 0),
    remaining: Math.max(0, s.remaining - Math.floor(s.phase === 3 ? delta : 0)),
    pending: Math.max(0, s.nextStart - s.sampledAt - Math.floor(delta)) };
}

export function formatGroups(groups: number[]): string {
  if (!groups.length) return '--';
  const ranges: string[] = [];
  let start = groups[0], end = start;
  const add = () => ranges.push(start === end ? String(start) : `${start}-${end}`);
  for (const group of groups.slice(1)) {
    if (group === end + 1) end = group;
    else { add(); start = group; end = group; }
  }
  add();
  return ranges.join(',');
}
