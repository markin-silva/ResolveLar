import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando, Selo, Vazio } from "../components.jsx";
import { dia, hora } from "../format.js";

// Reservas do profissional agrupadas por dia, da mais próxima para a mais distante.
export default function Agenda() {
  const { token } = useAuth();
  const [lista, setLista] = useState(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let ativo = true;
    api.agenda(token)
      .then((d) => { if (ativo) setLista(d.items || []); })
      .catch((e) => { if (ativo) { setLista([]); setErro(e.message); } });
    return () => { ativo = false; };
  }, [token]);

  const dias = useMemo(() => {
    const grupos = new Map();
    for (const r of lista || []) {
      const chave = (r.inicio || "").slice(0, 10);
      if (!grupos.has(chave)) grupos.set(chave, []);
      grupos.get(chave).push(r);
    }
    return [...grupos.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [lista]);

  return (
    <section>
      <h1>Agenda</h1>
      <p className="muted">Seus atendimentos reservados, do mais próximo ao mais distante.</p>
      <Aviso tipo="erro">{erro}</Aviso>
      {lista === null && <Carregando />}
      {lista?.length === 0 && !erro && <Vazio titulo="Sua agenda está livre">Quando um cliente confirmar um orçamento seu, o horário aparece aqui.</Vazio>}
      {dias.map(([chave, reservas]) => (
        <div key={chave} className="dia">
          <h2 className="dia-titulo">{dia(reservas[0].inicio)}</h2>
          <ul className="lista">
            {reservas.map((r) => (
              <li key={r.reserva_id}>
                <Link className="demanda" to={"/solicitacoes/" + r.solicitacao_id}>
                  <div>
                    <strong>{hora(r.inicio)} – {hora(r.fim)}</strong>
                    <p className="muted pequeno">{r.solicitacao_id}</p>
                  </div>
                  <Selo status={r.status} />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
