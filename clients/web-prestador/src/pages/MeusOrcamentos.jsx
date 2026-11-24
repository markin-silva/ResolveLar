import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando, Selo, Vazio } from "../components.jsx";
import { brl } from "../format.js";

export default function MeusOrcamentos() {
  const { token } = useAuth();
  const [lista, setLista] = useState(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let ativo = true;
    api.meusOrcamentos(token)
      .then((d) => { if (ativo) setLista(d.items || []); })
      .catch((e) => { if (ativo) { setLista([]); setErro(e.message); } });
    return () => { ativo = false; };
  }, [token]);

  return (
    <section>
      <h1>Meus orçamentos</h1>
      <p className="muted">Propostas que você enviou e o que o cliente decidiu.</p>
      <Aviso tipo="erro">{erro}</Aviso>
      {lista === null && <Carregando />}
      {lista?.length === 0 && !erro && <Vazio titulo="Você ainda não enviou orçamentos">Abra uma solicitação em “Novas solicitações”.</Vazio>}
      <ul className="lista">
        {lista?.map((o) => (
          <li key={o.orcamento_id}>
            <Link className="demanda" to={"/solicitacoes/" + o.solicitacao_id}>
              <div>
                <strong className="valor">{brl(o.valor?.centavos)}</strong>
                <p className="resumo-demanda">{o.descricaoServico}</p>
                <p className="muted pequeno">Prazo de {o.prazoEstimadoDias} dia(s)</p>
              </div>
              <Selo status={o.status} />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
