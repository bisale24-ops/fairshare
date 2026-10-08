import { useEffect, useState } from "react";
import { api } from "../api";

export function JoinPage({ token }: { token: string }) {
  const [info, setInfo] = useState<{ name: string; currency: string; closed: boolean } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.joinInfo(token).then(setInfo).catch((e) => setError(e.message));
  }, [token]);

  async function join() {
    try {
      const g = await api.join(token);
      location.hash = `/groups/${g.id}`;
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="card narrow">
      {error && <div className="error">{error}</div>}
      {info && (
        <>
          <h2>Приглашение в группу «{info.name}»</h2>
          <p className="muted">Валюта группы: {info.currency}</p>
          <button className="primary" onClick={join} disabled={info.closed}>Присоединиться</button>
          {info.closed && <p className="muted">Группа закрыта.</p>}
        </>
      )}
    </div>
  );
}
