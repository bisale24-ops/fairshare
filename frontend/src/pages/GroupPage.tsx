import { useState } from "react";
import { api, getToken, type Activity, type Expense, type Group, type Report, type Settlement, type User } from "../api";
import { ExpenseForm } from "../components/ExpenseForm";
import { Money } from "../components/Money";
import { useResource } from "../hooks";
import { useLive } from "../live";
import { formatMoney, minorToInput, parseMoney, pluralize } from "../money";

type Tab = "expenses" | "balances" | "settlements" | "activity" | "settings";
const TABS: [Tab, string][] = [
  ["expenses", "Расходы"], ["balances", "Балансы"], ["settlements", "Погашения"], ["activity", "Лента"], ["settings", "Настройки"],
];
const LIVE_LABEL: Record<string, string> = {
  expense_added: "добавлен расход", expense_edited: "расход изменён", expense_deleted: "расход удалён", receipt_attached: "приложен чек",
  settlement_proposed: "новый платёж ждёт подтверждения", settlement_confirmed: "платёж подтверждён", settlement_rejected: "платёж отклонён",
  joined: "новый участник", group_closed: "группа закрыта", group_reopened: "группа открыта снова", group_updated: "настройки изменены", reminder: "напоминание",
};
const liveLabel = (kind?: string) => (kind && LIVE_LABEL[kind]) || "изменения в группе";

const CATEGORY_LABEL: Record<string, string> = {
  food: "Еда", transport: "Транспорт", housing: "Жильё", entertainment: "Развлечения", groceries: "Продукты", utilities: "Коммунальные", other: "Другое",
};

export function GroupPage({ id, user }: { id: number; user: User }) {
  const [tab, setTab] = useState<Tab>("expenses");
  const group = useResource(() => api.group(id), [id]);
  const g = group.data;
  const { last } = useLive();

  if (group.error) return <div className="card error">{group.error}</div>;
  if (!g) return <div className="muted">Загрузка…</div>;

  return (
    <>
      <div className="row head">
        <h1>{g.name} {g.closed && <span className="tag">закрыта</span>}</h1>
        <span className="spacer" />
        <div className="right">
          <div className="muted small">Ваш баланс</div>
          <Money minor={g.my_balance_minor} currency={g.currency} big />
        </div>
      </div>
      {last?.group_id === id && <div className="live small" aria-live="polite">Обновлено в реальном времени: {liveLabel(last.kind)}</div>}
      <nav className="tabs" role="tablist">
        {TABS.map(([t, l]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{l}</button>
        ))}
      </nav>
      {tab === "expenses" && <ExpensesTab g={g} user={user} />}
      {tab === "balances" && <BalancesTab g={g} user={user} />}
      {tab === "settlements" && <SettlementsTab g={g} user={user} />}
      {tab === "activity" && <ActivityTab g={g} />}
      {tab === "settings" && <SettingsTab g={g} onChange={group.reload} />}
    </>
  );
}

function ExpensesTab({ g, user }: { g: Group; user: User }) {
  const list = useResource(() => api.expenses(g.id), [g.id]);
  const [editing, setEditing] = useState<Expense | "new" | null>(null);
  const [error, setError] = useState("");

  async function remove(e: Expense) {
    if (!confirm(`Удалить «${e.title || e.category}»? Балансы пересчитаются.`)) return;
    try { await api.deleteExpense(g.id, e.id); list.reload(); } catch (err: any) { setError(err.message); }
  }

  return (
    <>
      {error && <div className="error">{error}</div>}
      {!editing && !g.closed && <button className="primary" onClick={() => setEditing("new")}>+ Добавить расход</button>}
      {g.closed && <div className="card muted">Группа закрыта: новые расходы не добавляются. Её можно открыть обратно в настройках.</div>}
      {editing && (
        <ExpenseForm group={g} meId={user.id} expense={editing === "new" ? undefined : editing} onDone={() => { setEditing(null); list.reload(); }} />
      )}
      <ul className="list">
        {(list.data ?? []).length === 0 && <li className="muted">Расходов пока нет.</li>}
        {(list.data ?? []).map((e) => (
          <li key={e.id} className="card expense">
            <div className="row">
              <strong>{e.title || CATEGORY_LABEL[e.category] || e.category}</strong>
              <span className="tag">{CATEGORY_LABEL[e.category] ?? e.category}</span>
              <span className="spacer" />
              <strong>{formatMoney(e.amount_minor, g.currency)}</strong>
            </div>
            <div className="muted small">
              {e.spent_on} · платил(а) {e.payer_name} · {e.split_type === "equal" ? "поровну" : e.split_type === "shares" ? "долями" : "точными суммами"}
              {e.comment && ` · ${e.comment}`}
            </div>
            <div className="chips">
              {e.shares.map((s) => <span key={s.user_id} className="chip">{s.name}: {formatMoney(s.amount_minor, g.currency)}</span>)}
            </div>
            <div className="row small">
              {e.has_receipt && <a href="#" onClick={async (ev) => { ev.preventDefault(); await openReceipt(g.id, e.id); }}>📎 {e.receipt_name}</a>}
              <span className="spacer" />
              {!g.closed && <button className="link" onClick={() => setEditing(e)}>Изменить</button>}
              {!g.closed && <button className="link danger" onClick={() => remove(e)}>Удалить</button>}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

async function openReceipt(gid: number, eid: number) {
  const res = await fetch(api.receiptUrl(gid, eid), { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) return alert("Не удалось открыть чек");
  window.open(URL.createObjectURL(await res.blob()), "_blank");
}

function BalancesTab({ g, user }: { g: Group; user: User }) {
  const [paying, setPaying] = useState<{ to: number; toName: string; amount: string } | null>(null);
  const [error, setError] = useState("");

  async function pay() {
    if (!paying) return;
    const minor = parseMoney(paying.amount);
    if (!minor) return setError("Неверная сумма");
    try {
      await api.settle(g.id, paying.to, minor);
      setPaying(null);
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <>
      <section className="card">
        <h3>Баланс участников</h3>
        {g.members.map((m) => (
          <div key={m.id} className="row">
            <span>{m.name}{m.id === user.id && " (вы)"}</span>
            <span className="spacer" />
            <Money minor={m.balance_minor} currency={g.currency} />
          </div>
        ))}
      </section>
      <section className="card">
        <h3>Как рассчитаться — минимум переводов</h3>
        {g.transfers.length === 0 && <p className="muted">Все в расчёте.</p>}
        {g.transfers.map((t, i) => (
          <div key={i} className="row">
            <span><strong>{t.from_user === user.id ? "Вы" : t.from_name}</strong> → <strong>{t.to_user === user.id ? "вам" : t.to_name}</strong></span>
            <span className="spacer" />
            <span>{formatMoney(t.amount_minor, g.currency)}</span>
            {t.from_user === user.id && (
              <button className="primary small-btn" onClick={() => setPaying({ to: t.to_user, toName: t.to_name, amount: minorToInput(t.amount_minor) })}>Я заплатил(а)</button>
            )}
          </div>
        ))}
        {paying && (
          <div className="card inner">
            <div>Платёж для {paying.toName} (можно часть суммы). Получатель должен подтвердить.</div>
            <div className="row">
              <input value={paying.amount} onChange={(e) => setPaying({ ...paying, amount: e.target.value })} aria-label="Сумма платежа" />
              <button className="primary" onClick={pay}>Отправить на подтверждение</button>
              <button className="ghost" onClick={() => setPaying(null)}>Отмена</button>
            </div>
            {error && <div className="error">{error}</div>}
          </div>
        )}
      </section>
    </>
  );
}

function SettlementsTab({ g, user }: { g: Group; user: User }) {
  const list = useResource(() => api.settlements(g.id), [g.id]);
  const [error, setError] = useState("");
  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); setError(""); list.reload(); } catch (e: any) { setError(e.message); }
  };
  const label = { pending: "ждёт подтверждения", confirmed: "подтверждено", rejected: "отклонено" } as const;

  return (
    <section className="card">
      <h3>Погашения</h3>
      {error && <div className="error">{error}</div>}
      {(list.data ?? []).length === 0 && <p className="muted">Платежей пока не было.</p>}
      {(list.data ?? []).map((s: Settlement) => (
        <div key={s.id} className="row">
          <span>{s.from_name} → {s.to_name}: {formatMoney(s.amount_minor, g.currency)}</span>
          <span className={`tag ${s.status}`}>{label[s.status]}</span>
          <span className="spacer" />
          {s.status === "pending" && s.to_user === user.id && (
            <>
              <button className="primary small-btn" onClick={() => act(() => api.confirm(s.id))}>Подтвердить</button>
              <button className="ghost small-btn" onClick={() => act(() => api.reject(s.id))}>Отклонить</button>
            </>
          )}
        </div>
      ))}
    </section>
  );
}

function describe(a: Activity, currency: string): string {
  const p = a.payload;
  const who = a.actor ?? "Система";
  switch (a.kind) {
    case "group_created": return `${who} создал(а) группу`;
    case "joined": return `${who} присоединился(ась)`;
    case "invited": return `${who} пригласил(а) ${p.email}`;
    case "expense_added": return `${who} добавил(а) «${p.title}» на ${formatMoney(p.amount_minor, currency)}`;
    case "expense_edited": return `${who} изменил(а) «${p.title}», теперь ${formatMoney(p.amount_minor, currency)}`;
    case "expense_deleted": return `${who} удалил(а) «${p.title}»`;
    case "receipt_attached": return `${who} приложил(а) чек к «${p.title}»`;
    case "settlement_proposed": return `${who} отметил(а) платёж ${formatMoney(p.amount_minor, currency)}`;
    case "settlement_confirmed": return `${who} подтвердил(а) платёж ${formatMoney(p.amount_minor, currency)}`;
    case "settlement_rejected": return `${who} отклонил(а) платёж ${formatMoney(p.amount_minor, currency)}`;
    case "group_closed": return `${who} закрыл(а) группу`;
    case "group_reopened": return `${who} открыл(а) группу снова`;
    case "group_updated": return `${who} изменил(а) настройки группы`;
    default: return `${who}: ${a.kind}`;
  }
}

function ActivityTab({ g }: { g: Group }) {
  const feed = useResource(() => api.activity(g.id), [g.id]);
  return (
    <section className="card">
      <h3>Лента активности</h3>
      <ul className="list">
        {(feed.data ?? []).map((a) => (
          <li key={a.id} className="row">
            <span>{describe(a, g.currency)}</span>
            <span className="spacer" />
            <span className="muted small">{new Date(a.created_at).toLocaleString("ru-RU")}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SettingsTab({ g, onChange }: { g: Group; onChange: () => void }) {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [days, setDays] = useState(g.remind_after_days);
  const [report, setReport] = useState<Report | null>(null);
  const link = `${location.origin}/#/join/${g.invite_token}`;

  async function run(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); setMsg(ok); onChange(); } catch (e: any) { setMsg(e.message); }
  }

  async function close() {
    if (!confirm("Закрыть группу? Новые расходы будут недоступны, всем уйдёт письмо с итогом.")) return;
    try { setReport(await api.close(g.id)); setMsg("Группа закрыта, письма с итогом отправлены."); onChange(); } catch (e: any) { setMsg(e.message); }
  }

  return (
    <>
      <section className="card">
        <h3>Пригласить</h3>
        <div className="row">
          <input readOnly value={link} aria-label="Ссылка-приглашение" />
          <button className="ghost" onClick={() => navigator.clipboard?.writeText(link).then(() => setMsg("Ссылка скопирована"))}>Копировать</button>
        </div>
        <form className="row" onSubmit={(e) => { e.preventDefault(); run(() => api.invite(g.id, email), `Приглашение отправлено на ${email}`).then(() => setEmail("")); }}>
          <input type="email" placeholder="friend@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <button className="primary">Пригласить по e-mail</button>
        </form>
      </section>
      <section className="card">
        <h3>Напоминания должникам</h3>
        <div className="row">
          <label>Напоминать, если долг не погашен дольше (дней)
            <input type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value))} />
          </label>
          <button className="primary" onClick={() => run(() => api.patchGroup(g.id, { remind_after_days: days }), "Сохранено")}>Сохранить</button>
        </div>
        <p className="muted small">Письмо уходит не чаще раза в неделю и не уходит, если долг уже погашен.</p>
      </section>
      <section className="card">
        <h3>Закрытие группы</h3>
        {g.closed ? (
          <button className="primary" onClick={() => run(() => api.reopen(g.id), "Группа открыта снова")}>Открыть группу снова</button>
        ) : (
          <button className="danger-btn" onClick={close}>Закрыть группу и отправить итог</button>
        )}
        <ReportView g={g} report={report} />
      </section>
      {msg && <div className="live small" aria-live="polite">{msg}</div>}
    </>
  );
}

function ReportView({ g, report }: { g: Group; report: Report | null }) {
  const data = useResource(() => (g.closed ? api.report(g.id) : Promise.resolve(null)), [g.id, g.closed]);
  const r = report ?? data.data;
  if (!r) return null;
  return (
    <div className="report">
      <h4>Итоговый отчёт</h4>
      <div>Потрачено: <strong>{formatMoney(r.total_spent_minor, g.currency)}</strong>, {pluralize(r.expense_count, ["расход", "расхода", "расходов"])}; погашено {formatMoney(r.settled_minor, g.currency)}</div>
      <div className="chips">
        {Object.entries(r.by_category).map(([c, v]) => <span key={c} className="chip">{CATEGORY_LABEL[c] ?? c}: {formatMoney(v, g.currency)}</span>)}
      </div>
      <table>
        <thead><tr><th>Участник</th><th>Заплатил</th><th>Его доля</th><th>Баланс</th></tr></thead>
        <tbody>
          {r.members.map((m) => (
            <tr key={m.id}><td>{m.name}</td><td>{formatMoney(m.paid_minor, g.currency)}</td><td>{formatMoney(m.share_minor, g.currency)}</td><td><Money minor={m.balance_minor} currency={g.currency} /></td></tr>
          ))}
        </tbody>
      </table>
      {r.transfers.length === 0 ? <div className="muted">Все в расчёте.</div> : r.transfers.map((t, i) => (
        <div key={i}>{t.from_name} → {t.to_name}: {formatMoney(t.amount_minor, g.currency)}</div>
      ))}
    </div>
  );
}
