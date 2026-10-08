import { useState } from "react";
import { api } from "../api";
import { useResource } from "../hooks";
import { formatMoney } from "../money";
import { Money } from "../components/Money";

export function GroupsPage() {
  const groups = useResource(() => api.groups(), []);
  const global = useResource(() => api.myBalances(), []);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [days, setDays] = useState(7);
  const [error, setError] = useState("");

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const g = await api.createGroup(name, currency, days);
      location.hash = `/groups/${g.id}`;
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <>
      <section className="card">
        <h2>Всего по всем группам</h2>
        {(global.data ?? []).length === 0 && <p className="muted">Пока нет расчётов. Создайте группу и добавьте расход.</p>}
        {(global.data ?? []).map((c) => (
          <div key={c.currency} className="currency-block">
            <div className="row">
              <strong>{c.currency}</strong>
              <span className="spacer" />
              <Money minor={c.net_minor} currency={c.currency} big />
            </div>
            {c.people.map((p) => (
              <div key={p.user_id} className="row small">
                <span>{p.amount_minor > 0 ? `${p.name} должен(на) вам` : `Вы должны: ${p.name}`}</span>
                <span className="spacer" />
                <Money minor={p.amount_minor} currency={c.currency} />
              </div>
            ))}
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Группы</h2>
        {(groups.data ?? []).length === 0 && <p className="muted">Групп пока нет.</p>}
        <ul className="list">
          {(groups.data ?? []).map((g) => (
            <li key={g.id}>
              <a href={`#/groups/${g.id}`} className="row link-row">
                <span>
                  {g.name} {g.closed && <span className="tag">закрыта</span>}
                  <span className="muted small"> · {g.members} уч.</span>
                </span>
                <span className="spacer" />
                <Money minor={g.my_balance_minor} currency={g.currency} />
              </a>
            </li>
          ))}
        </ul>
      </section>

      <form className="card" onSubmit={create}>
        <h2>Новая группа</h2>
        <div className="grid3">
          <label>Название<input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} placeholder="Поездка в Сочи" /></label>
          <label>Валюта<input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} required maxLength={3} minLength={3} /></label>
          <label>Напоминать через (дней)<input type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value))} /></label>
        </div>
        {error && <div className="error">{error}</div>}
        <button className="primary">Создать группу</button>
      </form>
    </>
  );
}

export { formatMoney };
