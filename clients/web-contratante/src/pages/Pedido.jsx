import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api, gwPath } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando, Dica, Estrelas, Passos, Selo, Vazio } from "../components.jsx";
import { brl, nomeCategoria } from "../format.js";

const POLL_MS = 2000;
const POLL_MAX = 10; // acompanha a SAGA por ~20 s

// Próxima data útil sugerida (amanhã às 14h), no formato do <input type="datetime-local">.
function sugestaoDeHorario() {
  const d = new Date(Date.now() + 86400000);
  d.setHours(14, 0, 0, 0);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const ORDENACOES = {
  preco: (a, b) => (a.valor?.centavos ?? 0) - (b.valor?.centavos ?? 0),
  nota: (a, b) => (b.prestador?.nota ?? 0) - (a.prestador?.nota ?? 0),
};

function etapa(status, avaliado) {
  if (avaliado) return 4;
  if (status === "CONFIRMADA" || status === "CONCLUIDA") return 3;
  if (status === "EM_CONFIRMACAO") return 2;
  return 1;
}

export default function Pedido() {
  const { id } = useParams();
  const { state } = useLocation();
  const { token } = useAuth();

  const [pedido, setPedido] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState(state?.recemCriado ? "Pedido criado! Os profissionais já podem enviar orçamentos." : "");
  const [ordem, setOrdem] = useState("preco");
  const [cartao, setCartao] = useState("pm_tok_ok");
  const [horario, setHorario] = useState(sugestaoDeHorario);
  const [ocupado, setOcupado] = useState("");
  const [acompanhando, setAcompanhando] = useState(false);
  const [nota, setNota] = useState({ valor: "5", comentario: "" });
  const [avaliado, setAvaliado] = useState(false);
  const rodada = useRef(0);

  const carregar = useCallback(async ({ silencioso = false } = {}) => {
    if (!silencioso) setCarregando(true);
    try {
      const dados = await api.pedido(token, id);
      setPedido(dados); setErro("");
      return dados;
    } catch (e) { setErro(e.message); return null; }
    finally { setCarregando(false); }
  }, [token, id]);

  useEffect(() => { carregar(); return () => { rodada.current += 1; }; }, [carregar]);

  // Acompanha a SAGA enquanto o pedido estiver EM_CONFIRMACAO (a cada 2 s, por ~20 s).
  async function acompanhar() {
    const minha = ++rodada.current;
    setAcompanhando(true);
    const alvo = pedido?._links?.self?.href || "/v1/contratante/solicitacoes/" + id;
    for (let i = 0; i < POLL_MAX; i++) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      if (minha !== rodada.current) return;
      try {
        const estado = await api.estadoDoPedido(token, gwPath(alvo));
        if (estado.status_codigo !== "EM_CONFIRMACAO") {
          setAcompanhando(false);
          const dados = await carregar({ silencioso: true });
          if (estado.status_codigo === "CONFIRMADA") setAviso("Serviço confirmado! A agenda foi reservada e o pagamento aprovado.");
          else setAviso("O pagamento não foi concluído e a reserva foi liberada" + (estado.motivo ? " (" + estado.motivo + ")" : "") + ". Escolha outro orçamento ou tente outro cartão.");
          return dados;
        }
      } catch (e) { setErro(e.message); setAcompanhando(false); return; }
    }
    if (minha === rodada.current) { setAcompanhando(false); setAviso("A confirmação está demorando. Atualize a página em instantes."); }
  }

  async function aprovar(orcamento) {
    setOcupado("aprovar"); setErro(""); setAviso("");
    const href = gwPath(orcamento._links?.aprovar?.href) || "/v1/contratante/orcamentos/" + orcamento.orcamento_id + "/aprovacao";
    try {
      await api.aprovar(token, href, { horarioEscolhido: new Date(horario).toISOString(), meioPagamentoId: cartao });
      setPedido((p) => ({ ...p, status_codigo: "EM_CONFIRMACAO", motivo: null }));
      setAviso("Pedido aceito. Estamos confirmando a agenda e o pagamento…");
      setOcupado("");
      await acompanhar();
    } catch (e) {
      setErro(e.status === 409
        ? "Esse orçamento não pode mais ser aprovado (vencido, recusado ou o horário já está ocupado). Atualize a página ou escolha outro horário."
        : e.message);
      setOcupado("");
    }
  }

  async function recusar(orcamento) {
    setOcupado("recusar"); setErro("");
    const href = gwPath(orcamento._links?.recusar?.href) || "/v1/contratante/orcamentos/" + orcamento.orcamento_id + "/recusa";
    try {
      await api.recusar(token, href);
      setAviso("Orçamento recusado.");
      await carregar({ silencioso: true });
    } catch (e) { setErro(e.message); }
    finally { setOcupado(""); }
  }

  async function avaliar(event) {
    event.preventDefault();
    setOcupado("avaliar"); setErro("");
    try {
      await api.avaliar(token, id, { nota: Number(nota.valor), ...(nota.comentario.trim() ? { comentario: nota.comentario.trim() } : {}) });
      setAvaliado(true);
      setAviso("Obrigado! Sua avaliação foi registrada e já ajuda outros moradores.");
    } catch (e) {
      if (e.status === 409) { setAvaliado(true); setAviso("Este serviço já foi avaliado."); }
      else setErro(e.message);
    } finally { setOcupado(""); }
  }

  const orcamentos = useMemo(() => [...(pedido?.orcamentos || [])].sort(ORDENACOES[ordem]), [pedido, ordem]);
  const status = pedido?.status_codigo;
  const podeEscolher = status === "AGUARDANDO_ACEITE" && !acompanhando;
  const confirmado = status === "CONFIRMADA" || status === "CONCLUIDA";

  if (carregando && !pedido) return <Carregando texto="Carregando pedido…" />;
  if (!pedido) return (
    <section>
      <Aviso tipo="erro">{erro}</Aviso>
      <p><Link to="/">← Voltar aos meus pedidos</Link></p>
    </section>
  );

  return (
    <section>
      <p><Link to="/">← Meus pedidos</Link></p>
      <div className="cabecalho">
        <div>
          <h1>{pedido.titulo || "Pedido"}</h1>
          <p className="muted">{nomeCategoria(pedido.categoria)}</p>
        </div>
        <Selo status={status} />
      </div>
      <Passos atual={etapa(status, avaliado)} />

      <Aviso tipo="erro" onFechar={() => setErro("")}>{erro}</Aviso>
      <Aviso tipo={confirmado ? "ok" : "info"} onFechar={() => setAviso("")}>{aviso}</Aviso>

      {status === "EM_CONFIRMACAO" && (
        <div className="cartao confirmando" role="status">
          <strong>Confirmando agenda e pagamento…</strong>
          <p className="muted">Isso leva alguns segundos. Você não precisa fazer nada.</p>
        </div>
      )}

      {pedido.motivo && status === "AGUARDANDO_ACEITE" && (
        <Aviso tipo="aviso">Última tentativa não concluída: {pedido.motivo}. A reserva foi liberada.</Aviso>
      )}

      {confirmado ? (
        <div className="cartao">
          <h2>Serviço confirmado</h2>
          <p className="muted">O profissional foi avisado e a agenda está reservada.</p>
          {avaliado ? <p className="ok-texto">Avaliação enviada.</p> : (
            <form className="pilha" onSubmit={avaliar}>
              <h3>Como foi o atendimento?</h3>
              <div className="linha">
                <label className="curto">Nota
                  <select value={nota.valor} onChange={(e) => setNota({ ...nota, valor: e.target.value })}>
                    {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} de 5</option>)}
                  </select>
                </label>
                <label>Comentário (opcional)
                  <textarea rows="2" maxLength="1000" value={nota.comentario}
                    onChange={(e) => setNota({ ...nota, comentario: e.target.value })} />
                </label>
              </div>
              <div><button className="botao" disabled={ocupado === "avaliar"}>{ocupado === "avaliar" ? "Enviando…" : "Enviar avaliação"}</button></div>
            </form>
          )}
        </div>
      ) : (
        <>
          <div className="cabecalho secao">
            <h2>Orçamentos recebidos</h2>
            {orcamentos.length > 1 && (
              <label className="ordem">Ordenar por
                <select value={ordem} onChange={(e) => setOrdem(e.target.value)}>
                  <option value="preco">Menor preço</option>
                  <option value="nota">Melhor avaliação</option>
                </select>
              </label>
            )}
          </div>

          {orcamentos.length > 1 && podeEscolher && (
            <Dica>O menor preço nem sempre é a melhor escolha: compare também o prazo e a avaliação de cada profissional.</Dica>
          )}

          {orcamentos.length === 0 && status !== "EM_CONFIRMACAO" && (
            <Vazio titulo="Ainda não há orçamentos">
              Os profissionais de {nomeCategoria(pedido.categoria) || "sua região"} foram avisados.
              <br /><button className="botao-secundario espaco" onClick={() => carregar()}>Atualizar</button>
            </Vazio>
          )}

          {orcamentos.length > 0 && podeEscolher && (
            <div className="cartao pilha pagamento">
              <h3>Como você quer pagar e quando?</h3>
              <div className="linha">
                <label>Dia e horário do atendimento
                  <input type="datetime-local" value={horario} onChange={(e) => setHorario(e.target.value)} />
                </label>
                <label>Cartão
                  <select value={cartao} onChange={(e) => setCartao(e.target.value)}>
                    <option value="pm_tok_ok">Cartão aprovado (teste)</option>
                    <option value="pm_tok_recusado">Cartão recusado (teste)</option>
                  </select>
                </label>
              </div>
              <p className="muted pequeno">Pagamento simulado. O cartão recusado mostra como o sistema desfaz a reserva sozinho.</p>
            </div>
          )}

          <ul className="orcamentos">
            {orcamentos.map((o, i) => (
              <li key={o.orcamento_id} className={"orcamento" + (i === 0 && ordem === "preco" && orcamentos.length > 1 ? " orcamento-destaque" : "")}>
                <div>
                  <strong>{o.prestador?.nome || "Profissional"}</strong> <Estrelas nota={o.prestador?.nota} />
                  <p className="preco">{o.valor_formatado || brl(o.valor?.centavos)}</p>
                  <p className="muted pequeno">{o.prazo || "Prazo a combinar"}</p>
                </div>
                <div className="acoes">
                  {o._links?.aprovar && (
                    <button className="botao" onClick={() => aprovar(o)} disabled={!podeEscolher || ocupado !== ""}>
                      {ocupado === "aprovar" ? "Enviando…" : "Aprovar"}
                    </button>
                  )}
                  {o._links?.recusar && (
                    <button className="botao-secundario" onClick={() => recusar(o)} disabled={!podeEscolher || ocupado !== ""}>Recusar</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
