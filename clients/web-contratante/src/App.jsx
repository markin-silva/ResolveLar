import { useEffect, useRef, useState } from "react";

// Todas as chamadas são relativas ao próprio origin: o Nginx do contêiner encaminha /v1/ ao Kong.
const GW = "/v1/contratante";
const POLL_MS = 2000;
const POLL_MAX = 10; // acompanha a SAGA por ~20 s

const CATEGORIAS = [
  ["eletricista", "Elétrica"],
  ["encanador", "Encanamento"],
  ["tecnico-gas", "Gás"],
  ["pedreiro", "Alvenaria"],
  ["pintor", "Pintura"],
  ["marceneiro", "Marcenaria"],
  ["chaveiro", "Chaveiro"],
  ["instalador", "Instalação"],
];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Erros da API chegam como RFC 7807 (`detail`/`title`).
async function api(path, { token, ...options } = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + token,
      ...(options.headers || {}),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.detail || body.title || "A API respondeu " + response.status);
    error.status = response.status;
    throw error;
  }
  return body;
}

// Idempotency-Key nova a cada tentativa de aprovação.
function newKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return "web-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

// Os links podem vir como /v1/... (do ms-*); o cliente só fala com o gateway, em /v1/contratante/...
function gwPath(href) {
  if (!href) return "";
  if (href.startsWith(GW)) return href;
  if (href.startsWith("/v1/")) return GW + href.slice(3);
  return href;
}

function brl(centavos) {
  if (centavos == null) return "—";
  return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function nomeCategoria(slug) {
  return CATEGORIAS.find(([value]) => value === slug)?.[1] || slug;
}

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("resolvelar-token") || "");
  const [tokenDraft, setTokenDraft] = useState("");
  const [notice, setNotice] = useState(null); // { type: "ok" | "erro" | "info", text }

  const [descricao, setDescricao] = useState("");
  const [cidade, setCidade] = useState("Lavras");
  const [uf, setUf] = useState("MG");
  const [categoria, setCategoria] = useState("eletricista");
  const [triagem, setTriagem] = useState(null);

  const [prestadores, setPrestadores] = useState(null); // null = ainda não buscou
  const [solicitacaoId, setSolicitacaoId] = useState("");
  const [solicitacao, setSolicitacao] = useState(null); // estado do BFF: status_codigo, motivo, saga, _links
  const [orcamentos, setOrcamentos] = useState([]);
  const [cartao, setCartao] = useState("pm_tok_ok");
  const [polling, setPolling] = useState(""); // "" | "ativo" | "esgotado"
  const [avaliacao, setAvaliacao] = useState({ nota: "5", comentario: "" });
  const [avaliada, setAvaliada] = useState(false);
  const [busy, setBusy] = useState("");

  const pollRun = useRef(0);
  useEffect(() => () => { pollRun.current += 1; }, []); // cancela o polling ao sair da página

  const conectado = Boolean(token);

  function falha(error, contexto) {
    if (error.status === 401) {
      setNotice({ type: "erro", text: "Sessão sem autorização (401). Conecte outro token." });
    } else {
      setNotice({ type: "erro", text: contexto + ": " + error.message });
    }
  }

  function salvarToken(event) {
    event.preventDefault();
    const next = tokenDraft.trim();
    if (!next) return;
    sessionStorage.setItem("resolvelar-token", next);
    setToken(next);
    setTokenDraft("");
    setNotice({ type: "ok", text: "Conectado. O token fica só nesta aba do navegador." });
  }

  function desconectar() {
    sessionStorage.removeItem("resolvelar-token");
    pollRun.current += 1;
    setToken("");
    setTriagem(null);
    setPrestadores(null);
    setSolicitacao(null);
    setOrcamentos([]);
    setPolling("");
    setNotice(null);
  }

  async function triar(event) {
    event.preventDefault();
    setBusy("triagem"); setNotice(null);
    try {
      const data = await api(GW + "/triagem", {
        token, method: "POST", body: JSON.stringify({ descricao: descricao.trim(), cidade, uf }),
      });
      setTriagem(data);
      setCategoria(data.categoria || categoria);
    } catch (error) {
      falha(error, "A triagem não respondeu");
    } finally { setBusy(""); }
  }

  async function buscarPrestadores() {
    setBusy("busca"); setNotice(null);
    try {
      const params = new URLSearchParams({ cidade, categoria, page: "1", size: "12" });
      const data = await api(GW + "/prestadores?" + params.toString(), { token });
      setPrestadores(data.items || []);
    } catch (error) {
      falha(error, "Não foi possível buscar profissionais");
    } finally { setBusy(""); }
  }

  async function criarSolicitacao() {
    setBusy("solicitacao"); setNotice(null);
    try {
      const data = await api(GW + "/solicitacoes", {
        token, method: "POST",
        body: JSON.stringify({ categoria, descricao: descricao.trim(), endereco: { cep: "37200-000", cidade, uf } }),
      });
      const id = data.id || data.solicitacao_id;
      setSolicitacaoId(id);
      setSolicitacao(null); setOrcamentos([]); setAvaliada(false);
      setNotice({ type: "ok", text: "Solicitação criada: " + id + ". Quando um profissional enviar orçamento, clique em “Ver orçamentos”." });
    } catch (error) {
      falha(error, "Não foi possível criar a solicitação");
    } finally { setBusy(""); }
  }

  async function carregarOrcamentos(event) {
    event?.preventDefault();
    setBusy("orcamentos"); setNotice(null);
    try {
      const data = await api(GW + "/solicitacoes/" + encodeURIComponent(solicitacaoId), { token }).catch(() => null);
      const lista = await api(GW + "/solicitacoes/" + encodeURIComponent(solicitacaoId) + "/orcamentos", { token });
      setOrcamentos(lista.orcamentos || []);
      setSolicitacao({ ...lista, ...(data || {}) });
      if (!lista.orcamentos?.length) setNotice({ type: "info", text: "Ainda não há orçamentos para esta solicitação." });
    } catch (error) {
      setOrcamentos([]);
      falha(error, "Não foi possível carregar os orçamentos");
    } finally { setBusy(""); }
  }

  // Acompanha a SAGA: consulta a solicitação a cada 2 s, enquanto estiver EM_CONFIRMACAO.
  async function acompanharSaga(href) {
    const run = ++pollRun.current;
    setPolling("ativo");
    for (let i = 0; i < POLL_MAX; i++) {
      await sleep(POLL_MS);
      if (run !== pollRun.current) return;
      try {
        const estado = await api(gwPath(href), { token });
        setSolicitacao((anterior) => ({ ...anterior, ...estado, _links: estado._links || anterior?._links }));
        if (estado.status_codigo !== "EM_CONFIRMACAO") {
          setPolling("");
          if (estado.status_codigo === "CONFIRMADA") {
            setNotice({ type: "ok", text: "Serviço confirmado. Agenda reservada e pagamento aprovado." });
          } else {
            setNotice({ type: "info", text: "A SAGA compensou a operação e a reserva foi liberada. Você pode escolher outro orçamento ou tentar outro cartão." });
            carregarOrcamentos();
          }
          return;
        }
      } catch (error) {
        falha(error, "Falha ao consultar o andamento");
        setPolling("");
        return;
      }
    }
    if (run === pollRun.current) {
      setPolling("esgotado");
      setNotice({ type: "info", text: "A confirmação ainda está em andamento. Você pode continuar acompanhando." });
    }
  }

  async function aprovar(orcamento) {
    setBusy("pagamento"); setNotice(null); setAvaliada(false);
    const href = gwPath(orcamento._links?.aprovar?.href) || GW + "/orcamentos/" + encodeURIComponent(orcamento.orcamento_id) + "/aprovacao";
    const selfHref = solicitacao?._links?.self?.href || GW + "/solicitacoes/" + encodeURIComponent(solicitacaoId);
    const body = { horarioEscolhido: new Date(Date.now() + 86400000).toISOString(), meioPagamentoId: cartao };
    try {
      await api(href, { token, method: "POST", headers: { "Idempotency-Key": newKey() }, body: JSON.stringify(body) });
      setSolicitacao((anterior) => ({ ...anterior, status_codigo: "EM_CONFIRMACAO", status: "Confirmando seu agendamento", motivo: null, saga: null }));
      setNotice({ type: "info", text: "Pedido aceito. A SAGA está confirmando agenda e pagamento." });
      await acompanharSaga(selfHref);
    } catch (error) {
      falha(error, "A aprovação não foi concluída");
    } finally { setBusy(""); }
  }

  async function recusar(orcamento) {
    const href = gwPath(orcamento._links?.recusar?.href) || GW + "/orcamentos/" + encodeURIComponent(orcamento.orcamento_id) + "/recusa";
    setBusy("recusa"); setNotice(null);
    try {
      await api(href, { token, method: "POST", body: "{}" });
      setOrcamentos((lista) => lista.filter((item) => item.orcamento_id !== orcamento.orcamento_id));
      setNotice({ type: "ok", text: "Orçamento recusado." });
    } catch (error) {
      falha(error, "Não foi possível recusar");
    } finally { setBusy(""); }
  }

  async function avaliar(event) {
    event.preventDefault();
    const prestadorId = solicitacao?.prestador_id;
    if (!prestadorId) { setNotice({ type: "erro", text: "Não foi possível identificar o profissional desta solicitação." }); return; }
    setBusy("avaliacao"); setNotice(null);
    const body = { prestadorId, nota: Number(avaliacao.nota), ...(avaliacao.comentario.trim() ? { comentario: avaliacao.comentario.trim() } : {}) };
    try {
      await api(GW + "/solicitacoes/" + encodeURIComponent(solicitacaoId) + "/avaliacao", { token, method: "POST", body: JSON.stringify(body) });
      setAvaliada(true);
      setNotice({ type: "ok", text: "Avaliação registrada. A nota será atualizada na busca em instantes." });
      setTimeout(() => buscarPrestadores(), 1500); // o AvaliacaoRegistrada chega ao Read DB pelo CQRS
    } catch (error) {
      falha(error, "Não foi possível enviar a avaliação");
    } finally { setBusy(""); }
  }

  // ------------------------------------------------------------------ tela de conexão
  if (!conectado) {
    return (
      <div className="connect-screen">
        <form className="connect-card" onSubmit={salvarToken}>
          <p className="eyebrow">ResolveLar · Contratante</p>
          <h1>Entrar</h1>
          <p className="muted">Cole o token de acesso do contratante. Ele fica apenas nesta aba do navegador.</p>
          <label htmlFor="token">Token de acesso</label>
          <input id="token" type="password" autoComplete="off" value={tokenDraft}
            onChange={(event) => setTokenDraft(event.target.value)} placeholder="eyJhbGciOi…" required />
          <button className="primary-button" disabled={!tokenDraft.trim()}>Entrar</button>
          {notice && <p className={"notice notice-" + notice.type} role="alert">{notice.text}</p>}
        </form>
      </div>
    );
  }

  const status = solicitacao?.status_codigo;
  const podeAvaliar = status === "CONFIRMADA" || status === "CONCLUIDA";

  // ------------------------------------------------------------------ aplicação
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">R</span>resolvelar</div>
        <nav>
          <a href="#triagem">Triagem</a>
          <a href="#profissionais">Profissionais</a>
          <a href="#pedido">Meu pedido</a>
        </nav>
        <button className="link-button" onClick={desconectar}>Sair</button>
      </header>

      <main>
        {notice && <p className={"notice notice-" + notice.type} role="status">{notice.text}</p>}

        <section id="triagem" className="card">
          <h2>1. Descreva o problema</h2>
          <form onSubmit={triar} className="stack">
            <label>O que está acontecendo?
              <textarea rows="4" required minLength="10" value={descricao}
                onChange={(event) => setDescricao(event.target.value)}
                placeholder="Ex.: o chuveiro parou de esquentar depois de uma queda de energia" />
            </label>
            <div className="row">
              <label>Cidade<input value={cidade} onChange={(event) => setCidade(event.target.value)} /></label>
              <label className="small">UF<input maxLength="2" value={uf} onChange={(event) => setUf(event.target.value.toUpperCase())} /></label>
              <label>Categoria
                <select value={categoria} onChange={(event) => setCategoria(event.target.value)}>
                  {CATEGORIAS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
            </div>
            <button className="primary-button" disabled={busy === "triagem"}>
              {busy === "triagem" ? "Analisando…" : "Analisar com o assistente"}
            </button>
          </form>

          {triagem && (
            <div className="triagem-result">
              <div className="row between">
                <strong>{nomeCategoria(triagem.categoria)}</strong>
                <span className={"badge badge-" + String(triagem.urgencia).toLowerCase()}>{triagem.urgencia}</span>
              </div>
              <p>{triagem.resumo}</p>
              {triagem.orientacoesSeguranca?.length > 0 && (
                <div>
                  <p className="label">Antes de prosseguir</p>
                  <ul>{triagem.orientacoesSeguranca.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
              )}
              {triagem.avisos?.length > 0 && <p className="muted small-text">{triagem.avisos.join(" ")}</p>}
              <p className="muted small-text">
                {triagem.modo === "llm" ? "Resposta do assistente de IA" : "Orientação por regras (assistente de IA indisponível)"}
                {triagem.rag ? " · com base de conhecimento" : ""}
              </p>
              <button className="secondary-button" onClick={buscarPrestadores} disabled={busy === "busca"}>
                Ver profissionais
              </button>
            </div>
          )}
        </section>

        <section id="profissionais" className="card">
          <div className="row between">
            <h2>2. Profissionais</h2>
            <button className="link-button" onClick={buscarPrestadores} disabled={busy === "busca"}>
              {busy === "busca" ? "Buscando…" : "Atualizar"}
            </button>
          </div>
          <p className="muted">{cidade}, {uf} · {nomeCategoria(categoria)} · melhor avaliados primeiro</p>
          {prestadores === null && <p className="muted">Faça a triagem ou clique em “Atualizar” para ver os profissionais.</p>}
          {prestadores?.length === 0 && <p className="muted">Nenhum profissional encontrado para esta categoria e cidade.</p>}
          {prestadores?.length > 0 && (
            <ul className="list">
              {prestadores.map((p) => (
                <li key={p.prestador_id}>
                  <div>
                    <strong>{p.nome}</strong>
                    <span className="muted"> · ★ {p.nota ?? "—"} · {p.servicos_realizados || 0} serviços</span>
                    <div className="muted small-text">{(p.categorias || []).map(nomeCategoria).join(", ")}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section id="pedido" className="card">
          <h2>3. Meu pedido</h2>
          <div className="row">
            <label>ID da solicitação
              <input value={solicitacaoId} onChange={(event) => setSolicitacaoId(event.target.value)} placeholder="sol_…" />
            </label>
            <button className="secondary-button" type="button" onClick={criarSolicitacao}
              disabled={!descricao.trim() || busy === "solicitacao"}>
              {busy === "solicitacao" ? "Criando…" : "Criar solicitação"}
            </button>
            <button className="primary-button compact" onClick={carregarOrcamentos}
              disabled={!solicitacaoId.trim() || busy === "orcamentos"}>
              {busy === "orcamentos" ? "Carregando…" : "Ver orçamentos"}
            </button>
          </div>

          {solicitacao?.status_codigo && (
            <div className={"status status-" + status.toLowerCase()} role="status">
              <strong>{rotuloStatus(status)}</strong>
              {solicitacao.saga?.status && <span className="muted small-text">SAGA: {solicitacao.saga.status}</span>}
              {solicitacao.motivo && <span className="small-text">Motivo: {solicitacao.motivo}</span>}
              {polling === "ativo" && <span className="muted small-text">Atualizando a cada 2 s…</span>}
              {polling === "esgotado" && (
                <button className="link-button" onClick={() => acompanharSaga(solicitacao._links?.self?.href || GW + "/solicitacoes/" + solicitacaoId)}>
                  Continuar acompanhando
                </button>
              )}
            </div>
          )}

          {orcamentos.length > 0 && (
            <>
              <ul className="list">
                {orcamentos.map((o) => (
                  <li key={o.orcamento_id}>
                    <div>
                      <strong>{o.prestador?.nome || "Profissional"}</strong>
                      <span className="muted"> · ★ {o.prestador?.nota ?? "—"}</span>
                      <div className="price">{o.valor_formatado || brl(o.valor?.centavos)}</div>
                      <div className="muted small-text">{o.prazo || "Prazo a confirmar"}</div>
                    </div>
                    <div className="actions">
                      {o._links?.aprovar && (
                        <button className="primary-button compact" onClick={() => aprovar(o)}
                          disabled={busy === "pagamento" || polling === "ativo"}>Aprovar</button>
                      )}
                      {o._links?.recusar && (
                        <button className="secondary-button compact" onClick={() => recusar(o)}
                          disabled={busy === "recusa" || polling === "ativo"}>Recusar</button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              <label>Cartão para o pagamento
                <select value={cartao} onChange={(event) => setCartao(event.target.value)}>
                  <option value="pm_tok_ok">Cartão aprovado (pm_tok_ok)</option>
                  <option value="pm_tok_recusado">Cartão recusado (pm_tok_recusado)</option>
                </select>
              </label>
            </>
          )}

          {podeAvaliar && !avaliada && (
            <form className="stack avaliacao" onSubmit={avaliar}>
              <h3>Avalie o atendimento</h3>
              <div className="row">
                <label className="small">Nota
                  <select value={avaliacao.nota} onChange={(event) => setAvaliacao({ ...avaliacao, nota: event.target.value })}>
                    {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} de 5</option>)}
                  </select>
                </label>
                <label>Comentário (opcional)
                  <textarea rows="2" maxLength="1000" value={avaliacao.comentario}
                    onChange={(event) => setAvaliacao({ ...avaliacao, comentario: event.target.value })} />
                </label>
              </div>
              <button className="primary-button compact" disabled={busy === "avaliacao"}>
                {busy === "avaliacao" ? "Enviando…" : "Enviar avaliação"}
              </button>
            </form>
          )}
        </section>
      </main>
    </div>
  );
}

function rotuloStatus(codigo) {
  switch (codigo) {
    case "EM_CONFIRMACAO": return "Confirmando agenda e pagamento…";
    case "CONFIRMADA": return "Serviço confirmado";
    case "CONCLUIDA": return "Serviço concluído";
    case "AGUARDANDO_ACEITE": return "Aguardando sua escolha";
    case "ABERTA": return "Aguardando orçamentos";
    default: return codigo;
  }
}
