import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando, Dica, Estrelas, Icone, Vazio } from "../components.jsx";
import { CATEGORIAS, nomeCategoria } from "../format.js";

// Consulta informativa dos profissionais (modelo de leitura do CQRS). O pedido é por categoria e cidade;
// quem envia o orçamento é o profissional.
export default function Profissionais() {
  const { token } = useAuth();
  const [categoria, setCategoria] = useState("eletricista");
  const [cidade, setCidade] = useState("Lavras");
  const [lista, setLista] = useState(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let ativo = true;
    setLista(null); setErro("");
    api.profissionais(token, { cidade, categoria, page: "1", size: "20" })
      .then((d) => { if (ativo) setLista(d.items || []); })
      .catch((e) => { if (ativo) { setLista([]); setErro(e.message); } });
    return () => { ativo = false; };
  }, [token, categoria, cidade]);

  return (
    <section>
      <div className="cabecalho-pagina">
        <span className="cabecalho-icone"><Icone nome="usuarios" tamanho={24} /></span>
        <div>
          <h1>Profissionais</h1>
          <p className="muted">Veja quem atende a sua região. Para contratar, crie um pedido: os profissionais enviam orçamentos.</p>
        </div>
      </div>
      <div className="linha filtros-linha">
        <label>Categoria
          <select value={categoria} onChange={(e) => setCategoria(e.target.value)}>
            {CATEGORIAS.map(([valor, nome]) => <option key={valor} value={valor}>{nome}</option>)}
          </select>
        </label>
        <label>Cidade<input value={cidade} onChange={(e) => setCidade(e.target.value)} /></label>
      </div>
      <Dica icone="estrela">As notas vêm de moradores que já contrataram pela ResolveLar. Confiança construída serviço a serviço.</Dica>
      <Aviso tipo="erro">{erro}</Aviso>
      {lista === null && <Carregando />}
      {lista?.length === 0 && !erro && <Vazio titulo="Nenhum profissional encontrado">Tente outra categoria ou cidade.</Vazio>}
      <ul className="lista">
        {lista?.map((p) => (
          <li key={p.prestador_id} className="item">
            <div>
              <strong>{p.nome}</strong> <Estrelas nota={p.nota} />
              <p className="muted pequeno">{(p.categorias || []).map(nomeCategoria).join(", ")} · {p.cidade}</p>
            </div>
            <span className="muted pequeno">{p.servicos_realizados || 0} serviços</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
