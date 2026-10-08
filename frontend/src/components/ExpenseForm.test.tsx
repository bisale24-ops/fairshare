import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExpenseForm } from "./ExpenseForm";
import { api, type Group } from "../api";

vi.mock("../api", async (orig) => {
  const real = await orig<typeof import("../api")>();
  return { ...real, api: { saveExpense: vi.fn(), uploadReceipt: vi.fn() } };
});

const group = (currency = "USD"): Group => ({
  id: 1, name: "Trip", currency, remind_after_days: 7, closed: false, invite_token: "t", created_by: 1, my_balance_minor: 0, transfers: [],
  members: [{ id: 1, name: "Алиса", balance_minor: 0 }, { id: 2, name: "Боб", balance_minor: 0 }],
});
const saved = { id: 9, version: 1, warnings: [] } as any;

beforeEach(() => {
  vi.mocked(api.saveExpense).mockReset();
  vi.mocked(api.uploadReceipt).mockReset();
});

async function fillAmount(user: ReturnType<typeof userEvent.setup>, value: string) {
  await user.type(screen.getByPlaceholderText(/^0(\.00)?$/), value);
}

describe("ExpenseForm", () => {
  it("sends integer minor units and the chosen participants for an equal split", async () => {
    vi.mocked(api.saveExpense).mockResolvedValue(saved);
    const done = vi.fn();
    const user = userEvent.setup();
    render(<ExpenseForm group={group()} meId={1} onDone={done} />);
    await fillAmount(user, "10.01");
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const [gid, eid, body] = vi.mocked(api.saveExpense).mock.calls[0] as any[];
    expect([gid, eid]).toEqual([1, null]);
    expect(body).toMatchObject({ amount_minor: 1001, payer_id: 1, split: { type: "equal", participants: [1, 2] } });
  });

  it("uses the group's currency digits: yen has no cents", async () => {
    vi.mocked(api.saveExpense).mockResolvedValue(saved);
    const user = userEvent.setup();
    render(<ExpenseForm group={group("JPY")} meId={1} onDone={vi.fn()} />);
    await fillAmount(user, "1500");
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    await waitFor(() => expect(api.saveExpense).toHaveBeenCalled());
    expect((vi.mocked(api.saveExpense).mock.calls[0] as any[])[2].amount_minor).toBe(1500);
  });

  it("refuses an exact split that does not add up, without calling the server", async () => {
    const user = userEvent.setup();
    render(<ExpenseForm group={group()} meId={1} onDone={vi.fn()} />);
    await fillAmount(user, "10");
    await user.click(screen.getByRole("button", { name: "Точными суммами" }));
    await user.type(screen.getByLabelText("Сумма: Алиса"), "3");
    await user.type(screen.getByLabelText("Сумма: Боб"), "4");
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Суммы должны давать/);
    expect(api.saveExpense).not.toHaveBeenCalled();
  });

  it("rejects a non-integer share weight", async () => {
    const user = userEvent.setup();
    render(<ExpenseForm group={group()} meId={1} onDone={vi.fn()} />);
    await fillAmount(user, "10");
    await user.click(screen.getByRole("button", { name: "Долями" }));
    const w = screen.getByLabelText("Доля: Алиса");
    await user.clear(w);
    await user.type(w, "1.5");
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Доли — целые числа/);
    expect(api.saveExpense).not.toHaveBeenCalled();
  });

  it("after a failed receipt upload the next press EDITS the saved expense instead of creating a duplicate", async () => {
    vi.mocked(api.saveExpense).mockResolvedValue({ id: 9, version: 1, warnings: [] } as any);
    vi.mocked(api.uploadReceipt).mockRejectedValue(new Error("Чек должен быть настоящим файлом"));
    const done = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<ExpenseForm group={group()} meId={1} onDone={done} />);
    await fillAmount(user, "5");
    await user.upload(container.querySelector('input[type="file"]') as HTMLInputElement, new File(["x"], "r.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Расход сохранён, но чек не загрузился/);
    expect(done).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const calls = vi.mocked(api.saveExpense).mock.calls as any[][];
    expect(calls).toHaveLength(2);
    expect(calls[0][1]).toBeNull();      // first: create
    expect(calls[1][1]).toBe(9);         // second: edit the same expense
    expect(calls[1][2].version).toBe(1); // ...with the version it got back
  });

  it("shows the server's translated message when saving fails", async () => {
    vi.mocked(api.saveExpense).mockRejectedValue(new Error("Расход только что изменил кто-то другой"));
    const user = userEvent.setup();
    render(<ExpenseForm group={group()} meId={1} onDone={vi.fn()} />);
    await fillAmount(user, "5");
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("кто-то другой");
  });

  it("retries after a lost connection with the SAME key, so the server can answer with the original instead of making a copy", async () => {
    vi.mocked(api.saveExpense)
      .mockRejectedValueOnce(new Error("Нет связи с сервером"))
      .mockResolvedValueOnce(saved);
    const done = vi.fn();
    const user = userEvent.setup();
    render(<ExpenseForm group={group()} meId={1} onDone={done} />);
    await fillAmount(user, "5");
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Нет связи с сервером");
    expect(screen.getByPlaceholderText("0.00")).toHaveValue("5");   // what the person typed is still there
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const calls = vi.mocked(api.saveExpense).mock.calls as any[][];
    expect(calls).toHaveLength(2);
    expect(calls[0][3]).toBeTruthy();
    expect(calls[1][3]).toBe(calls[0][3]);                          // identical key on the retry
    expect(calls[1][1]).toBeNull();                                 // still a create: the first one never got an answer
  });

  it("uses a fresh key for a fresh form", async () => {
    vi.mocked(api.saveExpense).mockResolvedValue(saved);
    const user = userEvent.setup();
    const keys: string[] = [];
    for (let i = 0; i < 2; i++) {
      const { unmount } = render(<ExpenseForm group={group()} meId={1} onDone={vi.fn()} />);
      await fillAmount(user, "5");
      await user.click(screen.getByRole("button", { name: "Добавить расход" }));
      await waitFor(() => expect(api.saveExpense).toHaveBeenCalledTimes(i + 1));
      keys.push((vi.mocked(api.saveExpense).mock.calls[i] as any[])[3]);
      unmount();
    }
    expect(keys[0]).not.toBe(keys[1]);
  });

  it("includes somebody who joins the group while the form is open, unless the person chose participants themselves", async () => {
    vi.mocked(api.saveExpense).mockResolvedValue(saved);
    const user = userEvent.setup();
    const alone = { ...group(), members: [{ id: 1, name: "Алиса", balance_minor: 0 }] };
    const { rerender } = render(<ExpenseForm group={alone} meId={1} onDone={vi.fn()} />);
    await fillAmount(user, "10");
    rerender(<ExpenseForm group={group()} meId={1} onDone={vi.fn()} />);   // Боб joined meanwhile
    expect(screen.getByLabelText("Участвует: Боб")).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Добавить расход" }));
    await waitFor(() => expect(api.saveExpense).toHaveBeenCalled());
    expect((vi.mocked(api.saveExpense).mock.calls[0] as any[])[2].split.participants).toEqual([1, 2]);
  });

  it("keeps a manual choice even when the group changes", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ExpenseForm group={group()} meId={1} onDone={vi.fn()} />);
    await user.click(screen.getByLabelText("Участвует: Боб"));          // Боб deliberately left out
    const three = { ...group(), members: [...group().members, { id: 3, name: "Вика", balance_minor: 0 }] };
    rerender(<ExpenseForm group={three} meId={1} onDone={vi.fn()} />);
    expect(screen.getByLabelText("Участвует: Алиса")).toBeChecked();
    expect(screen.getByLabelText("Участвует: Боб")).not.toBeChecked();
    expect(screen.getByLabelText("Участвует: Вика")).not.toBeChecked();  // not ticked behind the person's back
  });
});
