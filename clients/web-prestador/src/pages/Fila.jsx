import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando, Faixa, Vazio } from "../components.jsx";
import { nomeCategoria } from "../format.js";

// Caixa de entrada: demandas abertas das categorias e da cidade do profissional. O contato e o endereço
// do cliente não aparecem aqui; só depois da confirmação do serviço.
export default function Fila() {
  const { token, usuario } = useAuth();
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState("");

  function carregar() {
    setDados(null); setErro("");
    api.fila(token).then(setDados).catch((e) => { setDados({ items: [] }); setErro(e.message); });
  }
  useEffect(carregar, [token]);

  return (
    <section>
      <Faixa
        sobretitulo={usuario?.nome ? "Olá, " + usuario.nome.split(" ")[0] : "Olá"}
        titulo="Quem sabe fazer, trabalha."
        selos={[["pin", "Pedidos perto de você"], ["calendario", "Agenda organizada"], ["dinheiro", "Pagamento pela plataforma"]]}
      >
        Moradores da sua região estão precisando de alguém como você. Responda rápido e saia na frente.
      </Faixa>

      <div className="cabecalho secao">
        <div>
          <h1>Novas solicitações</h1>
          {dados?.filtros && (
            <p className="muted">
              {(dados.filtros.categorias || []).map(nomeCategoria).join(", ")} · {dados.filtros.cidade}
            </p>
          )}
        </div>
        <button className="botao-secundario" onClick={carregar}>Atualizar</button>
      </div>

      <Aviso tipo="erro">{erro}</Aviso>
      {dados === null && <Carregando />}
      {dados?.items?.length === 0 && !erro && (
        <Vazio titulo="Nenhuma solicitação aberta agora">
          Quando um morador da sua região pedir um serviço da sua área, ele aparece aqui.
        </Vazio>
      )}
      <ul className="lista">
        {dados?.items?.map((d) => (
          <li key={d.solicitacao_id}>
            <Link className="demanda" to={"/solicitacoes/" + d.solicitacao_id}>
              <div>
                <span className="selo selo-info">{nomeCategoria(d.categoria)}</span>
                <p className="resumo-demanda">{d.descricao}</p>
                <p className="muted pequeno">{[d.bairro, d.cidade].filter(Boolean).join(" · ")}</p>
              </div>
              <span className="seta" aria-hidden="true">›</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
