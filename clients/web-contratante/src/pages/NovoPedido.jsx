import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso } from "../components.jsx";
import { CATEGORIAS, nomeCategoria } from "../format.js";

// Criação do pedido em duas etapas: descrever (com triagem opcional) e confirmar o local.
export default function NovoPedido() {
  const { token } = useAuth();
  const navegar = useNavigate();
  const [descricao, setDescricao] = useState("");
  const [categoria, setCategoria] = useState("eletricista");
  const [endereco, setEndereco] = useState({ cep: "", cidade: "Lavras", uf: "MG", bairro: "", logradouro: "" });
  const [triagem, setTriagem] = useState(null);
  const [ocupado, setOcupado] = useState("");
  const [erro, setErro] = useState("");

  const campo = (nome) => (e) => setEndereco({ ...endereco, [nome]: e.target.value });

  async function analisar() {
    setOcupado("triagem"); setErro("");
    try {
      const data = await api.triagem(token, { descricao: descricao.trim(), cidade: endereco.cidade, uf: endereco.uf });
      setTriagem(data);
      if (data.categoria) setCategoria(data.categoria);
    } catch (e) { setErro("A análise não funcionou agora, mas você pode continuar. " + e.message); }
    finally { setOcupado(""); }
  }

  async function criar(event) {
    event.preventDefault();
    setOcupado("criar"); setErro("");
    const local = { cep: endereco.cep.trim(), cidade: endereco.cidade.trim(), uf: endereco.uf.trim().toUpperCase(),
      ...(endereco.bairro.trim() ? { bairro: endereco.bairro.trim() } : {}),
      ...(endereco.logradouro.trim() ? { logradouro: endereco.logradouro.trim() } : {}) };
    try {
      const pedido = await api.criarPedido(token, { categoria, descricao: descricao.trim(), endereco: local });
      navegar("/pedidos/" + (pedido.id || pedido.solicitacao_id), { state: { recemCriado: true } });
    } catch (e) { setErro(e.message); setOcupado(""); }
  }

  return (
    <section className="estreito">
      <h1>Novo pedido</h1>
      <p className="muted">Conte o que aconteceu. Os profissionais da sua região vão enviar orçamentos.</p>

      <form className="cartao pilha" onSubmit={criar}>
        <h2>1. O que está acontecendo?</h2>
        <label>Descrição do problema
          <textarea rows="4" required minLength="10" value={descricao} onChange={(e) => setDescricao(e.target.value)}
            placeholder="Ex.: o chuveiro parou de esquentar e o disjuntor desarma" />
        </label>
        <div>
          <button type="button" className="botao-secundario" onClick={analisar}
            disabled={descricao.trim().length < 10 || ocupado === "triagem"}>
            {ocupado === "triagem" ? "Analisando…" : "Analisar com o assistente (opcional)"}
          </button>
        </div>

        {triagem && (
          <div className="triagem">
            <div className="linha entre">
              <strong>Sugestão: {nomeCategoria(triagem.categoria)}</strong>
              <span className={"selo selo-" + (["ALTA", "EMERGENCIA"].includes(triagem.urgencia) ? "erro" : "aviso")}>
                Urgência {triagem.urgencia?.toLowerCase()}
              </span>
            </div>
            <p>{triagem.resumo}</p>
            {triagem.orientacoesSeguranca?.length > 0 && (
              <>
                <p className="rotulo">Antes de o profissional chegar</p>
                <ul>{triagem.orientacoesSeguranca.map((o) => <li key={o}>{o}</li>)}</ul>
              </>
            )}
            {triagem.prestadoresSugeridos?.length > 0 && (
              <p className="muted pequeno">
                Profissionais da região: {triagem.prestadoresSugeridos.map((p) => p.nome).join(", ")}.
              </p>
            )}
            <p className="muted pequeno">
              {triagem.modo === "llm" ? "Resposta do assistente de IA." : "Orientação por regras (assistente de IA indisponível)."}
            </p>
          </div>
        )}

        <h2>2. Tipo de serviço e local</h2>
        <label>Categoria
          <select value={categoria} onChange={(e) => setCategoria(e.target.value)}>
            {CATEGORIAS.map(([valor, nome]) => <option key={valor} value={valor}>{nome}</option>)}
          </select>
        </label>
        <div className="linha">
          <label>Cidade<input required value={endereco.cidade} onChange={campo("cidade")} /></label>
          <label className="curto">UF<input required maxLength="2" value={endereco.uf} onChange={campo("uf")} /></label>
          <label>CEP<input required placeholder="37200-000" value={endereco.cep} onChange={campo("cep")} /></label>
        </div>
        <label>Bairro<input value={endereco.bairro} onChange={campo("bairro")} /></label>
        <label>Rua e número
          <input value={endereco.logradouro} onChange={campo("logradouro")} placeholder="Só o profissional escolhido verá" />
        </label>
        <p className="muted pequeno">
          Os profissionais veem a cidade e o bairro. A rua e o número só são liberados depois que você confirma o serviço.
        </p>

        <Aviso tipo="erro">{erro}</Aviso>
        <button className="botao" disabled={ocupado === "criar" || descricao.trim().length < 10}>
          {ocupado === "criar" ? "Criando…" : "Criar pedido"}
        </button>
      </form>
    </section>
  );
}
