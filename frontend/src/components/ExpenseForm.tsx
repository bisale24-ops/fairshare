import { useMemo, useState } from "react";
import { api, type Expense, type Group } from "../api";
import { formatMoney, minorToInput, parseMoney } from "../money";

const CATEGORIES: [string, string][] = [
  ["food", "Еда"], ["transport", "Транспорт"], ["housing", "Жильё"], ["entertainment", "Развлечения"],
  ["groceries", "Продукты"], ["utilities", "Коммунальные"], ["other", "Другое"],
];

export function ExpenseForm({ group, meId, expense, onDone }: { group: Group; meId: number; expense?: Expense; onDone: () => void }) {
  const ids = group.members.map((m) => m.id);
  const [title, setTitle] = useState(expense?.title ?? "");
  const [amount, setAmount] = useState(expense ? minorToInput(expense.amount_minor) : "");
  const [payer, setPayer] = useState(expense?.payer_id ?? meId);
  const [category, setCategory] = useState(expense?.category ?? "food");
  const [date, setDate] = useState(expense?.spent_on ?? new Date().toISOString().slice(0, 10));
  const [comment, setComment] = useState(expense?.comment ?? "");
  const [type, setType] = useState<"equal" | "shares" | "exact">(expense?.split_type ?? "equal");
  const [picked, setPicked] = useState<Set<number>>(new Set(expense ? expense.shares.map((s) => s.user_id) : ids));
  const [weights, setWeights] = useState<Record<number, string>>(
    Object.fromEntries(ids.map((i) => [i, String(expense?.shares.find((s) => s.user_id === i)?.weight ?? 1)])),
  );
  const [amounts, setAmounts] = useState<Record<number, string>>(
    Object.fromEntries(ids.map((i) => [i, expense?.split_type === "exact" ? minorToInput(expense.shares.find((s) => s.user_id === i)?.amount_minor ?? 0) : ""])),
  );
  const [file, setFile] = useState<File | null>(null);
  // Set once the expense is saved. If the receipt upload then fails, pressing the button again edits this expense
  // instead of creating a second one (which would count the money twice).
  const [savedId, setSavedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const total = parseMoney(amount);
  const exactSum = useMemo(
    () => ids.reduce((acc, i) => acc + (parseMoney(amounts[i] || "0") ?? 0), 0),
    [amounts, ids],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!total || total <= 0) return setError("Введите сумму, например 12.50");
    let split: Record<string, unknown>;
    if (type === "equal") {
      if (picked.size === 0) return setError("Выберите участников");
      split = { type, participants: [...picked] };
    } else if (type === "shares") {
      const w: Record<number, number> = {};
      for (const i of picked) {
        const n = Number(weights[i] ?? "1");
        if (!Number.isInteger(n) || n < 1) return setError("Доли — целые числа от 1");
        w[i] = n;
      }
      if (!Object.keys(w).length) return setError("Выберите участников");
      split = { type, weights: w };
    } else {
      const a: Record<number, number> = {};
      for (const i of ids) {
        const v = parseMoney(amounts[i] || "0");
        if (v === null) return setError("Неверная сумма у участника");
        if (v > 0) a[i] = v;
      }
      if (exactSum !== total) return setError(`Суммы должны давать ${formatMoney(total, group.currency)}, сейчас ${formatMoney(exactSum, group.currency)}`);
      split = { type, amounts: a };
    }
    setBusy(true);
    try {
      const saved = await api.saveExpense(group.id, expense?.id ?? savedId, {
        payer_id: payer, amount_minor: total, title, category, spent_on: date, comment, split,
      });
      setSavedId(saved.id);
      if (file) {
        try {
          await api.uploadReceipt(group.id, saved.id, file);
        } catch (err: any) {
          setError(`Расход сохранён, но чек не загрузился: ${err.message}. Выберите другой файл или нажмите «Сохранить» без чека.`);
          setFile(null);
          return;
        }
      }
      onDone();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const toggle = (i: number) => {
    const next = new Set(picked);
    next.has(i) ? next.delete(i) : next.add(i);
    setPicked(next);
  };

  return (
    <form className="card form" onSubmit={submit} aria-label={expense ? "Редактировать расход" : "Новый расход"}>
      <h3>{expense ? "Редактировать расход" : "Новый расход"}</h3>
      <div className="grid3">
        <label>Название<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ужин" maxLength={200} /></label>
        <label>Сумма ({group.currency})<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" required /></label>
        <label>Кто заплатил
          <select value={payer} onChange={(e) => setPayer(Number(e.target.value))}>
            {group.members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
        <label>Категория
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label>Дата<input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
        <label>Чек (PNG, JPG, PDF до 5 МБ)<input type="file" accept="image/png,image/jpeg,image/webp,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
      </div>
      <label>Комментарий<input value={comment} onChange={(e) => setComment(e.target.value)} maxLength={2000} /></label>

      <fieldset>
        <legend>Как делим</legend>
        <div className="seg">
          {([["equal", "Поровну"], ["shares", "Долями"], ["exact", "Точными суммами"]] as const).map(([v, l]) => (
            <button type="button" key={v} className={type === v ? "on" : ""} aria-pressed={type === v} onClick={() => setType(v)}>{l}</button>
          ))}
        </div>
        <div className="split">
          {group.members.map((m) => (
            <div key={m.id} className="row">
              {type !== "exact" && <input type="checkbox" checked={picked.has(m.id)} onChange={() => toggle(m.id)} aria-label={`Участвует: ${m.name}`} />}
              <span>{m.name}</span>
              <span className="spacer" />
              {type === "shares" && picked.has(m.id) && (
                <input className="narrow-input" inputMode="numeric" value={weights[m.id] ?? "1"} onChange={(e) => setWeights({ ...weights, [m.id]: e.target.value })} aria-label={`Доля: ${m.name}`} />
              )}
              {type === "exact" && (
                <input className="narrow-input" inputMode="decimal" placeholder="0.00" value={amounts[m.id] ?? ""} onChange={(e) => setAmounts({ ...amounts, [m.id]: e.target.value })} aria-label={`Сумма: ${m.name}`} />
              )}
            </div>
          ))}
        </div>
        {type === "exact" && total ? (
          <div className={`small ${exactSum === total ? "ok" : "warn"}`}>Распределено {formatMoney(exactSum, group.currency)} из {formatMoney(total, group.currency)}</div>
        ) : null}
      </fieldset>

      {error && <div className="error" role="alert">{error}</div>}
      <div className="row">
        <button className="primary" disabled={busy}>{expense || savedId ? "Сохранить" : "Добавить расход"}</button>
        <button type="button" className="ghost" onClick={onDone}>Отмена</button>
      </div>
    </form>
  );
}
