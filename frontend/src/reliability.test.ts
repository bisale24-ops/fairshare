import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, openStream, setToken } from "./api";

beforeEach(() => { setToken("tok"); vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); setToken(null); });

describe("when the server cannot be reached", () => {
  it("says so in Russian instead of the browser's 'Failed to fetch'", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.groups()).rejects.toThrow(/Нет связи с сервером/);
  });

  it("treats a proxy error while the API restarts the same way", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502, statusText: "Bad Gateway", json: async () => ({}) }));
    await expect(api.groups()).rejects.toThrow(/Нет связи с сервером/);
  });

  it("gives up on a request that never answers (a dead server that does not even refuse) and says so", async () => {
    // fetch that only ends when it is aborted, like a connection to an address nobody listens on any more
    vi.stubGlobal("fetch", vi.fn((_url: string, opts: any) => new Promise((_res, rej) => opts.signal.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError"))))));
    const pending = api.groups().catch((e) => e);
    await vi.advanceTimersByTimeAsync(19_000);
    let settled = false;
    pending.then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);                       // still waiting at 19 s
    await vi.advanceTimersByTimeAsync(2_000);          // 21 s: aborted
    expect((await pending).message).toMatch(/Нет связи с сервером/);
  });

  it("sends the same Idempotency-Key header it was given, only for creating", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: 1 }) });
    vi.stubGlobal("fetch", f);
    await api.saveExpense(1, null, { a: 1 }, "key-123456789");
    await api.saveExpense(1, 5, { a: 1 }, "key-123456789"); // an edit does not need one
    expect((f.mock.calls[0][1] as any).headers["Idempotency-Key"]).toBe("key-123456789");
    expect((f.mock.calls[1][1] as any).headers["Idempotency-Key"]).toBeUndefined();
  });
});

describe("the live stream", () => {
  class FakeES {
    static instances: FakeES[] = [];
    static CLOSED = 2;
    static CONNECTING = 0;
    readyState = 1;
    onopen: (() => void) | null = null;
    onmessage: ((m: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(public url: string) { FakeES.instances.push(this); }
    close() { this.readyState = FakeES.CLOSED; }
  }

  beforeEach(() => { FakeES.instances = []; vi.stubGlobal("EventSource", FakeES); });

  it("opens a new stream after the server was down (HTTP error closes an EventSource for good), with a growing delay", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 502 }));
    const stop = openStream(() => {});
    expect(FakeES.instances).toHaveLength(1);
    FakeES.instances[0].readyState = FakeES.CLOSED;
    await FakeES.instances[0].onerror!();
    await vi.advanceTimersByTimeAsync(1000);
    expect(FakeES.instances).toHaveLength(2);          // retried after 1 s
    FakeES.instances[1].readyState = FakeES.CLOSED;
    await FakeES.instances[1].onerror!();
    await vi.advanceTimersByTimeAsync(1500);
    expect(FakeES.instances).toHaveLength(2);          // second wait is longer (2 s), not yet
    await vi.advanceTimersByTimeAsync(600);
    expect(FakeES.instances).toHaveLength(3);
    stop();
  });

  it("ends the session only when the server says 401, not when it is merely down", async () => {
    const expired = vi.fn();
    window.addEventListener("auth-expired", expired);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    const stop = openStream(() => {});
    FakeES.instances[0].readyState = FakeES.CLOSED;
    await FakeES.instances[0].onerror!();
    expect(expired).not.toHaveBeenCalled();             // unreachable server: keep the session, keep trying
    stop();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 401 }));
    openStream(() => {});
    const es = FakeES.instances[FakeES.instances.length - 1];
    es.readyState = FakeES.CLOSED;
    await es.onerror!();
    expect(expired).toHaveBeenCalledTimes(1);           // the token was rejected: back to login
    window.removeEventListener("auth-expired", expired);
  });

  it("does not open anything after being closed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 502 }));
    const stop = openStream(() => {});
    FakeES.instances[0].readyState = FakeES.CLOSED;
    const pending = FakeES.instances[0].onerror!();
    stop();
    await pending;
    await vi.advanceTimersByTimeAsync(20000);
    expect(FakeES.instances).toHaveLength(1);
  });
});
