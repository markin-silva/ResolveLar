import { useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const DEMO_PROVIDERS = [
  { prestador_id: "prest_17", nome: "Carlos Silva", categorias: ["eletricista", "chuveiro"], cidade: "Lavras", nota: 4.8, servicos_realizados: 132, disponivel_hoje: true, valor_formatado: "R$ 180,00", prazo: "Amanhã, 14h–16h" },
  { prestador_id: "prest_23", nome: "Ana Souza", categorias: ["eletricista", "instalação"], cidade: "Lavras", nota: 4.9, servicos_realizados: 87, disponivel_hoje: true, valor_formatado: "R$ 150,00", prazo: "Hoje, 18h–20h" },
  { prestador_id: "prest_31", nome: "Rafael Martins", categorias: ["encanador", "reparo"], cidade: "Lavras", nota: 4.7, servicos_realizados: 64, disponivel_hoje: false, valor_formatado: "R$ 120,00", prazo: "Em até 2 dias" },
];
const DEMO_BUDGETS = [
  { orcamento_id: "orc_42", prestador: { nome: "Carlos Silva", nota: 4.8, servicos_realizados: 132 }, valor_formatado: "R$ 180,00", prazo: "Amanhã, 14h–16h" },
  { orcamento_id: "orc_43", prestador: { nome: "Ana Souza", nota: 4.9, servicos_realizados: 87 }, valor_formatado: "R$ 150,00", prazo: "Hoje, 18h–20h" },
];

async function api(path, { token, ...options } = {}) {
  if (!token) throw new Error("Configure um token JWT para chamar o sistema.");
  const response = await fetch(API_BASE + path, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token, ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || ("A API respondeu " + response.status));
  return body;
}

function money(value) {
  if (value?.valor_formatado) return value.valor_formatado;
  if (value?.valor?.centavos != null) return (value.valor.centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: value.valor.moeda || "BRL" });
  return "Consulte o orçamento";
}
function linkPath(link) { return typeof link === "string" ? link : link?.href || link?.url || ""; }

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("resolvelar-token") || "");
  const [tokenDraft, setTokenDraft] = useState(token);
  const [showSettings, setShowSettings] = useState(false);
  const [description, setDescription] = useState("");
  const [city, setCity] = useState("Lavras");
  const [uf, setUf] = useState("MG");
  const [category, setCategory] = useState("eletricista");
  const [triage, setTriage] = useState(null);
  const [providers, setProviders] = useState([]);
  const [budgets, setBudgets] = useState([]);
  const [solicitationId, setSolicitationId] = useState("sol_8f21");
  const [selectedBudget, setSelectedBudget] = useState(null);
  const [cardMode, setCardMode] = useState("pm_tok_aprovado");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState(null);
  const isDemo = !token;
  const safeText = useMemo(() => description.trim(), [description]);

  function saveToken(event) {
    event.preventDefault();
    const next = tokenDraft.trim();
    if (next) sessionStorage.setItem("resolvelar-token", next); else sessionStorage.removeItem("resolvelar-token");
    setToken(next); setShowSettings(false); setNotice(next ? "Token guardado nesta sessão do navegador." : "Modo demonstração ativado.");
  }

  async function runTriage(event) {
    event.preventDefault(); setBusy("triagem"); setNotice(""); setResult(null);
    const fallback = { triagemId: "triagem-demo", categoria: category, urgencia: /g[aá]s|fuma[cç]a|fa[ií]sca/i.test(safeText) ? "ALTA" : "MEDIA", resumo: "A triagem organizou o relato como um serviço de " + category + " em " + city + ". Revise os detalhes com o profissional antes de confirmar.", orientacoesSeguranca: ["A orientação é preliminar e não substitui uma avaliação no local.", "Se houver risco imediato, afaste-se e procure o serviço de emergência adequado."], perguntasComplementares: ["Quando o problema começou?", "Você sabe informar a marca ou o modelo do equipamento?"], prestadoresSugeridos: [], fontes: [], modo: "fallback", rag: false, _links: { buscarPrestadores: { href: "/v1/contratante/prestadores" }, criarSolicitacao: { href: "/v1/contratante/solicitacoes" } } };
    try {
      if (!token) throw new Error("Modo demonstração");
      const answer = await api("/v1/contratante/triagem?rag=true&cache=true", { token, method: "POST", body: JSON.stringify({ descricao: safeText, cidade: city, uf }) });
      setTriage(answer); setCategory(answer.categoria || category); setNotice("Triagem recebida do sistema.");
    } catch (error) {
      if (token) { setNotice("A triagem real não respondeu: " + error.message); }
      else setNotice("Demonstração local: conecte um token para consultar o assistente real.");
      setTriage(fallback);
    } finally { setBusy(""); }
  }

  async function searchProviders(event) {
    event?.preventDefault(); setBusy("busca"); setNotice("");
    const params = new URLSearchParams({ cidade: city, categoria, page: "1", size: "12" });
    try {
      if (!token) throw new Error("Modo demonstração");
      const data = await api("/v1/contratante/prestadores?" + params.toString(), { token });
      setProviders(Array.isArray(data) ? data : data.items || []); setNotice("Resultados carregados pela busca do sistema.");
    } catch (error) {
      setProviders(DEMO_PROVIDERS.filter((item) => item.cidade.toLowerCase() === city.toLowerCase() && item.categorias.some((itemCategory) => (category || "").toLowerCase().includes(itemCategory) || itemCategory.includes((category || "").toLowerCase()))));
      if (!token) setNotice("Resultados de demonstração. A busca real usa o modelo de leitura do CQRS.");
      else setNotice("Não foi possível consultar a API: " + error.message);
    } finally { setBusy(""); }
  }

  async function createRequest() {
    setBusy("solicitacao"); setNotice("");
    const payload = { categoria: category, descricao: safeText, endereco: { cep: "37200-000", cidade, uf } };
    try {
      if (!token) throw new Error("Modo demonstração");
      const data = await api("/v1/contratante/solicitacoes", { token, method: "POST", body: JSON.stringify(payload) });
      const id = data.solicitacao_id || data.solicitacaoId || data.id || "sol_8f21";
      setSolicitationId(id); setNotice("Solicitação criada: " + id);
    } catch (error) {
      if (!token) { setSolicitationId("sol_8f21"); setNotice("Solicitação simulada com ID sol_8f21. No ambiente real, o ID virá do BFF."); }
      else setNotice("Não foi possível criar a solicitação: " + error.message);
    } finally { setBusy(""); }
  }

  async function loadBudgets(event) {
    event?.preventDefault(); setBusy("orcamentos"); setNotice("");
    try {
      if (!token) throw new Error("Modo demonstração");
      const data = await api("/v1/contratante/solicitacoes/" + encodeURIComponent(solicitationId) + "/orcamentos", { token });
      setBudgets(data.orcamentos || []); setNotice("Orçamentos recebidos do BFF.");
    } catch (error) {
      setBudgets(DEMO_BUDGETS);
      if (!token) setNotice("Orçamentos de demonstração. ID de exemplo: sol_8f21.");
      else setNotice("Não foi possível carregar os orçamentos: " + error.message);
    } finally { setBusy(""); }
  }

  async function approveBudget() {
    if (!selectedBudget) return; setBusy("pagamento"); setNotice(""); setResult(null);
    const body = { horarioEscolhido: new Date(Date.now() + 86400000).toISOString(), meioPagamentoId: cardMode };
    try {
      if (!token) throw new Error("Modo demonstração");
      const data = await api("/v1/contratante/orcamentos/" + encodeURIComponent(selectedBudget) + "/aprovacao", { token, method: "POST", headers: { "Idempotency-Key": "web-" + selectedBudget + "-" + cardMode }, body: JSON.stringify(body) });
      setResult(data); setNotice(data.status === "RECUSADA" ? "Pagamento recusado; confira a compensação da reserva no fluxo SAGA." : "Pedido enviado. A SAGA está confirmando o agendamento e o pagamento.");
    } catch (error) { setNotice(token ? "A aprovação não foi concluída: " + error.message : "Simulação: " + (cardMode === "pm_tok_recusado" ? "cartão recusado; a SAGA deve liberar a reserva." : "pagamento enviado; a SAGA confirmaria o agendamento.")); }
    finally { setBusy(""); }
  }

  const triageLinks = triage?._links || {};
  return (
    <div className="app-shell contractor-app">
      <header className="topbar">
        <a className="brand" href="#inicio" aria-label="ResolveLar, início"><span className="brand-mark">R</span><span>resolve<span>lar</span><small>cuidado que conecta</small></span></a>
        <nav aria-label="Navegação principal"><a href="#buscar">Encontrar profissional</a><a href="#orcamentos">Meus orçamentos</a></nav>
        <button className="profile-button" onClick={() => { setTokenDraft(token); setShowSettings(true); }}><span className="avatar">MC</span><span>Minha conta</span></button>
      </header>
      <main id="inicio">
        <section className="welcome-grid">
          <div className="welcome-copy"><p className="eyebrow"><span className="live-dot"></span> RESOLVELAR · LAVRAS, MG</p><h1>Casa em ordem.<br/><em>Você tranquilo.</em></h1><p className="welcome-text">Conte o que aconteceu. A triagem ajuda a organizar o pedido e encontrar quem pode resolver.</p><div className="trust-row"><span>◉ Profissionais avaliados</span><span>↗ Acompanhamento do pedido</span></div></div>
          <div className="welcome-art" aria-hidden="true"><div className="sun"></div><div className="house house-back"></div><div className="house house-front"><div className="window"></div><div className="door"></div></div><div className="plant plant-one">✳</div><div className="plant plant-two">✳</div><div className="art-note"><span>01</span><span>Um bom começo<br/>faz diferença.</span></div></div>
        </section>
        <div className="status-row"><span className={isDemo ? "mode-pill demo-pill" : "mode-pill live-pill"}>{isDemo ? "Demonstração local" : "Conectado ao ResolveLar"}</span><span className="status-copy">{isDemo ? "Os dados de exemplo estão identificados nas telas." : "Sua sessão usa o token somente nesta aba."}</span><button className="text-button" onClick={() => { setTokenDraft(token); setShowSettings(true); }}>{isDemo ? "Conectar API" : "Trocar token"}</button></div>
        {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Fechar aviso">×</button></div>}
        <section className="work-grid">
          <div className="panel triage-panel" id="triagem"><div className="panel-heading"><div><p className="eyebrow">PASSO 1 · TRIAGEM</p><h2>O que aconteceu?</h2></div><span className="sparkle">✳</span></div><p className="muted">Uma descrição simples já ajuda a orientar os próximos passos.</p>
            <form onSubmit={runTriage}><label htmlFor="problem">Descreva o problema</label><textarea id="problem" rows="4" required minLength="5" placeholder="Ex.: O chuveiro parou de esquentar depois de uma queda de energia..." value={description} onChange={(event) => setDescription(event.target.value)} /><div className="form-row"><label>Cidade<input value={city} onChange={(event) => setCity(event.target.value)} /></label><label>UF<input maxLength="2" value={uf} onChange={(event) => setUf(event.target.value.toUpperCase())} /></label><label>Categoria<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="eletricista">Elétrica</option><option value="encanador">Encanamento</option><option value="pintor">Pintura</option><option value="montador">Montagem</option><option value="reparo">Reparos gerais</option></select></label></div><button className="primary-button" disabled={busy === "triagem"}>{busy === "triagem" ? "Analisando…" : "Fazer triagem"}<span>→</span></button></form>
            <p className="fine-print">A triagem é uma orientação inicial; o profissional confirma os detalhes no local.</p>
          </div>
          <div className="panel result-panel">
            {triage ? <><div className="panel-heading"><div><p className="eyebrow">RESULTADO DA TRIAGEM</p><h2>{triage.categoria || category}</h2></div><span className={"urgency urgency-" + String(triage.urgencia || "media").toLowerCase()}>{triage.urgencia || "MEDIA"}</span></div><p className="result-summary">{triage.resumo}</p>{triage.orientacoesSeguranca?.length > 0 && <div className="safety-box"><strong>Antes de prosseguir</strong>{triage.orientacoesSeguranca.slice(0, 2).map((item) => <p key={item}>• {item}</p>)}</div>}{triage.perguntasComplementares?.length > 0 && <div className="question-list"><strong>Para ajudar o profissional</strong>{triage.perguntasComplementares.slice(0, 3).map((item) => <p key={item}>↳ {item}</p>)}</div>}<div className="result-footer"><span className="source-pill">{triage.modo === "llm" ? "Assistente IA" : "Resposta de demonstração"}{triage.rag ? " · com base de conhecimento" : ""}</span><button className="secondary-button" onClick={searchProviders} disabled={busy === "busca"}>Ver profissionais →</button></div>{Object.keys(triageLinks).length > 0 && <div className="hateoas-note"><strong>Próximas ações do recurso</strong>{Object.entries(triageLinks).map(([rel, link]) => <span key={rel}><code>{rel}</code> {linkPath(link)}</span>)}</div>}</> : <div className="empty-result"><span className="empty-orbit">✳</span><p className="eyebrow">SEU PRÓXIMO PASSO</p><h2>Uma orientação clara<br/>começa pelo contexto.</h2><p>Preencha a descrição ao lado para receber uma triagem e seguir para a busca.</p><div className="empty-steps"><span>01 <b>Descreva</b></span><span>02 <b>Compare</b></span><span>03 <b>Escolha</b></span></div></div>}
          </div>
        </section>
        <section className="section-block" id="buscar"><div className="section-title"><div><p className="eyebrow">PASSO 2 · BUSCA</p><h2>Profissionais para você comparar</h2></div><button className="quiet-button" onClick={searchProviders} disabled={busy === "busca"}>{busy === "busca" ? "Buscando…" : "Atualizar busca ↻"}</button></div><div className="filter-strip"><span>⌖ {city}, {uf}</span><span>Categoria · {category}</span><span>Ordenação · melhor avaliados</span></div><div className="provider-grid">{providers.length ? providers.map((person) => <article className="provider-card" key={person.prestador_id || person.nome}><div className="provider-top"><span className="provider-avatar">{(person.nome || "P").split(" ").map((part) => part[0]).slice(0,2).join("")}</span><span className="rating">★ {person.nota || "—"}</span></div><h3>{person.nome}</h3><p className="muted">{person.cidade || city} · {person.servicos_realizados || 0} serviços concluídos</p><div className="provider-categories">{(person.categorias || [category]).slice(0,2).map((tag) => <span key={tag}>{tag}</span>)}</div><div className="provider-bottom"><div><strong>{money(person)}</strong><small>{person.prazo || (person.disponivel_hoje ? "Disponível hoje" : "Consulte agenda")}</small></div><button className="outline-button" onClick={() => { setDescription(description || "Preciso de um serviço de " + category); document.getElementById("triagem")?.scrollIntoView({ behavior: "smooth" }); }}>Solicitar</button></div></article>) : <div className="inline-empty">Clique em “Ver profissionais” depois da triagem para carregar a busca do BFF.</div>}</div></section>
        <section className="section-block budget-block" id="orcamentos"><div className="section-title"><div><p className="eyebrow">PASSO 3 · ORÇAMENTOS</p><h2>Compare e escolha com calma</h2><p className="muted">O recurso disponibiliza os links de navegação enviados pela API; a confirmação começa a SAGA.</p></div></div><form className="request-row" onSubmit={loadBudgets}><label>ID da solicitação<input value={solicitationId} onChange={(event) => setSolicitationId(event.target.value)} /></label><button className="secondary-button" type="button" onClick={createRequest} disabled={!safeText || busy === "solicitacao"}>{busy === "solicitacao" ? "Criando…" : "Criar solicitação"}</button><button className="primary-button compact" disabled={busy === "orcamentos"}>{busy === "orcamentos" ? "Carregando…" : "Ver orçamentos →"}</button></form><div className="budget-grid">{budgets.map((budget) => <article className={"budget-card " + (selectedBudget === budget.orcamento_id ? "selected" : "")} key={budget.orcamento_id}><label className="select-budget"><input type="radio" name="budget" checked={selectedBudget === budget.orcamento_id} onChange={() => setSelectedBudget(budget.orcamento_id)} /><span>Selecionar</span></label><h3>{budget.prestador?.nome || "Profissional"}</h3><p className="rating">★ {budget.prestador?.nota || "—"} <span>· {budget.prestador?.servicos_realizados || 0} serviços</span></p><strong className="budget-price">{money(budget)}</strong><p className="muted">{budget.prazo || "Prazo a confirmar"}</p><code>{budget.orcamento_id}</code></article>)}</div>{budgets.length > 0 && <div className="payment-row"><div><strong>Pagamento demonstrativo</strong><small>Use o token de recusa para mostrar a compensação da reserva pela SAGA.</small></div><select value={cardMode} onChange={(event) => setCardMode(event.target.value)}><option value="pm_tok_aprovado">Cartão válido · aprovado</option><option value="pm_tok_recusado">Cartão de demonstração · recusado</option></select><button className="primary-button compact" onClick={approveBudget} disabled={!selectedBudget || busy === "pagamento"}>{busy === "pagamento" ? "Enviando…" : "Confirmar orçamento"}</button></div>}{result && <pre className="api-result">{JSON.stringify(result, null, 2)}</pre>}</section>
        <footer className="footer"><span className="brand-mark">R</span><span>ResolveLar · uma casa bem cuidada começa com boas escolhas.</span><button className="text-button" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>Voltar ao início ↑</button></footer>
      </main>
      {showSettings && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowSettings(false); }}><section className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title"><button className="modal-close" onClick={() => setShowSettings(false)} aria-label="Fechar">×</button><p className="eyebrow">CONEXÃO DE DEMONSTRAÇÃO</p><h2 id="settings-title">Conectar ao ResolveLar</h2><p className="muted">Cole o token de teste gerado pelo projeto. Ele fica somente nesta sessão do navegador e nunca é incluído no código.</p><form onSubmit={saveToken}><label htmlFor="api-token">Token JWT</label><input id="api-token" type="password" autoComplete="off" value={tokenDraft} onChange={(event) => setTokenDraft(event.target.value)} placeholder="Cole o token aqui" /><div className="modal-actions"><button className="quiet-button" type="button" onClick={() => { setTokenDraft(""); sessionStorage.removeItem("resolvelar-token"); setToken(""); setShowSettings(false); setNotice("Modo demonstração local ativado."); }}>Usar demonstração</button><button className="primary-button compact">Salvar nesta sessão</button></div></form></section></div>}
    </div>
  );
}
