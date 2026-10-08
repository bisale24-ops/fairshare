import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let push: (e: any) => void = () => {};
vi.mock("./api", async (orig) => ({ ...(await orig<typeof import("./api")>()), openStream: (cb: (e: any) => void) => { push = cb; return () => {}; } }));

import { useResource } from "./hooks";
import { LiveProvider } from "./live";

function Show({ load, group, deps = [] }: { load: () => Promise<string>; group?: number; deps?: unknown[] }) {
  const { data, error } = useResource(load, deps, group);
  return <div>{error ? `error:${error}` : data ?? "loading"}</div>;
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => vi.useRealTimers());

describe("live refetching", () => {
  it("a screen about one group refetches only when THAT group changes, and once per burst", async () => {
    const load = vi.fn().mockResolvedValue("v");
    render(<LiveProvider><Show load={load} group={5} /></LiveProvider>);
    await act(async () => {});
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => { push({ type: "group_changed", group_id: 7, kind: "expense_added" }); vi.advanceTimersByTime(200); });
    expect(load).toHaveBeenCalledTimes(1);   // other group: ignored
    await act(async () => {
      push({ type: "group_changed", group_id: 5, kind: "expense_added" });
      push({ type: "group_changed", group_id: 5, kind: "joined" });
      vi.advanceTimersByTime(200);
    });
    expect(load).toHaveBeenCalledTimes(2);   // two events in one burst: one refetch
  });

  it("refetches everything after a reconnect, because events may have been missed", async () => {
    const load = vi.fn().mockResolvedValue("v");
    render(<LiveProvider><Show load={load} group={5} /></LiveProvider>);
    await act(async () => { push({ type: "hello" }); });
    expect(load).toHaveBeenCalledTimes(1);   // first hello: just connected
    await act(async () => { push({ type: "hello" }); });
    expect(load).toHaveBeenCalledTimes(2);   // second hello: it came back
  });
});

describe("useResource", () => {
  it("ignores an older, slower answer that arrives after a newer one", async () => {
    let resolveSlow!: (v: string) => void;
    const load = vi.fn().mockReturnValueOnce(new Promise<string>((r) => { resolveSlow = r; })).mockResolvedValueOnce("new");
    render(<LiveProvider><Show load={load} /></LiveProvider>);
    await act(async () => { push({ type: "group_changed", group_id: 1 }); vi.advanceTimersByTime(200); });
    expect(await screen.findByText("new")).toBeInTheDocument();
    await act(async () => { resolveSlow("OLD"); });
    expect(screen.getByText("new")).toBeInTheDocument();
    expect(screen.queryByText("OLD")).toBeNull();
  });

  it("drops the previous dependency's data at once instead of showing it under the new one", async () => {
    const load = vi.fn((): Promise<string> => new Promise(() => {}));
    load.mockResolvedValueOnce("group A");
    const { rerender } = render(<LiveProvider><Show load={load} deps={["A"]} /></LiveProvider>);
    expect(await screen.findByText("group A")).toBeInTheDocument();
    rerender(<LiveProvider><Show load={load} deps={["B"]} /></LiveProvider>);
    expect(screen.queryByText("group A")).toBeNull();
    expect(screen.getByText("loading")).toBeInTheDocument();
  });
});
