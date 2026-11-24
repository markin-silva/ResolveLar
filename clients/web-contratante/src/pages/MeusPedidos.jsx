import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando, Selo, Vazio } from "../components.jsx";
import { nomeCategoria } from "../format.js";

const FILTROS = [
  ["", "Todos"],
  ["AGUARDANDO_ACEITE", "Aguardando escolha"],
  ["CONFIRMADA", "Confirmados"],
];

export default function MeusPedidos() {
  const { token } = useAuth();
  const [filtro, setFiltro] = useState("");
  const [pedidos, setPedidos] = useState(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let ativo = true;
    setPedidos(null); setErro("");
    api.meusPedidos(token, filtro)
      .then((data) => { if (ativo) setPedidos(data.items || []); })
      .catch((e) => { if (ativo) { setPedidos([]); setErro(e.message); } });
    return () => { ativo = false; };
  }, [token, filtro]);

  return (
    <section>
      <div className="cabecalho">
        <div><h1>Meus pedidos</h1><p className="muted">Acompanhe cada pedido e escolha o melhor orçamento.</p></div>
        <Link className="botao" to="/novo">Novo pedido</Link>
      </div>

      <div className="filtros" role="group" aria-label="Filtrar pedidos">
        {FILTROS.map(([valor, rotulo]) => (
          <button key={valor} className={"filtro" + (filtro === valor ? " filtro-ativo" : "")}
            onClick={() => setFiltro(valor)}>{rotulo}</button>
        ))}
      </div>

      <Aviso tipo="erro">{erro}</Aviso>
      {pedidos === null && <Carregando />}
      {pedidos?.length === 0 && !erro && (
        <Vazio titulo="Nenhum pedido por aqui">
          {filtro ? "Tente outro filtro." : "Descreva o problema da sua casa e receba orçamentos de profissionais."}
        </Vazio>
      )}
      <ul className="lista">
        {pedidos?.map((p) => (
          <li key={p.solicitacao_id}>
            <Link className="item-pedido" to={"/pedidos/" + p.solicitacao_id}>
              <div>
                <strong>{nomeCategoria(p.categoria)}</strong>
                <p className="resumo">{p.descricao}</p>
                {p.motivo && p.status_codigo === "AGUARDANDO_ACEITE" && (
                  <p className="muted pequeno">Última tentativa não concluída: {p.motivo}</p>
                )}
              </div>
              <Selo status={p.status_codigo} />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
