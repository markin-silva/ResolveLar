import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const DEMO_TASK = { tarefa_id: "sol_8f21", categoria: "eletricista", status: "AGENDADA", descricao: "Chuveiro parou de esquentar após uma queda de energia. Modelo Lorenzetti Advanced 220V, 7500W.", detalhes_tecnicos: { tensao: "220V", potencia_w: 7500, materiais_sugeridos: ["Resistência 7500W 220V", "Fita isolante"] }, agendamento: { inicio: "2026-11-24T17:00:00Z", fim: "2026-11-24T19:00:00Z" }, local: { endereco: "Rua das Flores, 120, apto 302", bairro: "Centro", cidade: "Lavras", referencia: "Portão azul, interfone 302" }, cliente: { nome: "Mariana", telefone: "+55 35 99999-0000" }, financeiro: { moeda: "BRL", valor_bruto_centavos: 18000, taxa_plataforma_percentual: 12, taxa_plataforma_centavos: 2160, valor_liquido_centavos: 15840, previsao_repasse: "2026-11-26" } };

async function api(path, { token, ...options } = {}) {
  if (!token) throw new Error("Configure um token JWT para chamar o sistema.");
  const response = await fetch(API_BASE + path, { ...options, headers: { "Content-Type": "application/json", Authorization: "Bearer " + token, ...(options.headers || {}) } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || ("A API respondeu " + response.status));
  return body;
}
function brl(cents) { return cents == null ? "—" : (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }
function dateTime(value) { if (!value) return "Horário a confirmar"; return new Date(value).toLocaleString("pt-BR", { dateStyle: "medium", timeStyle: "short" }); }

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("resolvelar-prestador-token") || "");
  const [tokenDraft, setTokenDraft] = useState(token);
  const [showSettings, setShowSettings] = useState(false);
  const [taskId, setTaskId] = useState("sol_8f21");
  const [task, setTask] = useState(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [amount, setAmount] = useState("180");
  const [description, setDescription] = useState("Diagnóstico no local e substituição da resistência, se necessário.");
  const [days, setDays] = useState("1");
  const [quoteResult, setQuoteResult] = useState(null);
  const isDemo = !token;

  function saveToken(event) {
    event.preventDefault(); const next = tokenDraft.trim();
    if (next) sessionStorage.setItem("resolvelar-prestador-token", next); else sessionStorage.removeItem("resolvelar-prestador-token");
    setToken(next); setShowSettings(false); setNotice(next ? "Token guardado nesta sessão do navegador." : "Modo demonstração ativado.");
  }

  async function loadTask(event) {
    event?.preventDefault(); setBusy("task"); setNotice(""); setQuoteResult(null);
    try {
      if (!token) throw new Error("Modo demonstração");
      const data = await api("/v1/prestador/tarefas/" + encodeURIComponent(taskId), { token });
      setTask(data); setNotice("Detalhe recebido do BFF Prestador.");
    } catch (error) {
      setTask(DEMO_TASK);
      if (!token) setNotice("Tarefa de demonstração. Conecte o token de prestador para consultar a API real.");
      else setNotice("Não foi possível carregar a tarefa: " + error.message);
    } finally { setBusy(""); }
  }

  async function sendQuote(event) {
    event.preventDefault(); if (!task) return; setBusy("quote"); setNotice(""); setQuoteResult(null);
    const payload = { valor: { centavos: Math.round(Number(amount) * 100), moeda: "BRL" }, descricaoServico: description.trim(), prazoEstimadoDias: Number(days), validoAte: new Date(Date.now() + 7 * 86400000).toISOString() };
    try {
      if (!token) throw new Error("Modo demonstração");
      const data = await api("/v1/prestador/solicitacoes/" + encodeURIComponent(task.tarefa_id || taskId) + "/orcamentos", { token, method: "POST", body: JSON.stringify(payload) });
      setQuoteResult(data); setNotice("Orçamento enviado ao BFF Prestador.");
    } catch (error) {
      if (!token) { setQuoteResult({ modo: "demo", solicitacao_id: task.tarefa_id, valor: payload.valor, descricaoServico: payload.descricaoServico, prazoEstimadoDias: payload.prazoEstimadoDias }); setNotice("Orçamento simulado. Com token conectado, a proposta será enviada ao sistema."); }
      else setNotice("Não foi possível enviar: " + error.message);
    } finally { setBusy(""); }
  }

  return (
    <div className="app-shell provider-app">
      <aside className="sidebar"><a className="brand" href="#inicio"><span className="brand-mark">R</span><span>resolve<span>lar</span><small>área do profissional</small></span></a><div className="side-label">ESPAÇO DE TRABALHO</div><nav className="side-nav"><a className="active" href="#inicio"><span>▦</span> Visão geral</a><a href="#tarefa"><span>⌂</span> Tarefa em destaque <i>01</i></a><a href="#orcamento"><span>◇</span> Enviar orçamento</a><a href="#financeiro"><span>↗</span> Repasse</a></nav><div className="side-help"><span className="help-icon">?</span><strong>Precisa de ajuda?</strong><p>Veja como funciona a jornada do prestador.</p><a href="https://github.com/markin-silva/ResolveLar/blob/main/docs/02-gateway-e-bff.md">Ler guia do projeto ↗</a></div><div className="side-user"><span className="provider-avatar">CS</span><span><strong>Carlos Silva</strong><small>Prestador verificado</small></span><button onClick={() => { setTokenDraft(token); setShowSettings(true); }} aria-label="Configurações da conta">···</button></div></aside>
      <main id="inicio" className="provider-main">
        <header className="provider-header"><div><p className="eyebrow">SEGUNDA-FEIRA, 23 DE NOVEMBRO</p><h1>Bom trabalho, Carlos <span>✳</span></h1><p className="muted">Acompanhe seus pedidos e mantenha seus clientes informados.</p></div><div className="header-actions"><span className={isDemo ? "mode-pill demo-pill" : "mode-pill live-pill"}>{isDemo ? "Demonstração" : "Conectado"}</span><button className="profile-button" onClick={() => { setTokenDraft(token); setShowSettings(true); }}><span className="avatar">CS</span></button></div></header>
        {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Fechar aviso">×</button></div>}
        <section className="stat-row"><article><span className="stat-icon green">▦</span><div><small>Tarefas em andamento</small><strong>01</strong></div><span className="stat-foot">em destaque</span></article><article><span className="stat-icon sand">◷</span><div><small>Próximo atendimento</small><strong>{task ? "Amanhã" : "—"}</strong></div><span className="stat-foot">17h–19h</span></article><article><span className="stat-icon blue">↗</span><div><small>Previsão de repasse</small><strong>{task?.financeiro ? brl(task.financeiro.valor_liquido_centavos) : "—"}</strong></div><span className="stat-foot">após conclusão</span></article></section>
        <section className="task-section" id="tarefa"><div className="section-head"><div><p className="eyebrow">PAINEL DO PRESTADOR</p><h2>Solicitações e tarefas</h2></div><form className="task-search" onSubmit={loadTask}><input aria-label="ID da solicitação" value={taskId} onChange={(event) => setTaskId(event.target.value)} placeholder="ID da solicitação"/><button className="primary-button compact" disabled={busy === "task"}>{busy === "task" ? "Buscando…" : "Abrir tarefa →"}</button></form></div>
          {task ? <div className="task-layout"><article className="task-card"><div className="task-top"><span className="category-tag">{task.categoria || "Serviço"}</span><span className="status-tag">● {task.status || "ABERTA"}</span></div><h3>{task.descricao || "Detalhes da solicitação"}</h3><p className="task-subtitle">Solicitação {task.tarefa_id || taskId} · Cliente {task.cliente?.nome || "identificado após confirmação"}</p><div className="task-details"><div><span className="detail-icon">⌖</span><span><small>Agendamento</small><strong>{dateTime(task.agendamento?.inicio)}</strong><small>{task.agendamento?.fim ? "Até " + dateTime(task.agendamento.fim) : "Janela sujeita à confirmação"}</small></span></div><div><span className="detail-icon">⚙</span><span><small>Informações técnicas</small><strong>{task.detalhes_tecnicos?.tensao || "A combinar"}{task.detalhes_tecnicos?.potencia_w ? " · " + task.detalhes_tecnicos.potencia_w + " W" : ""}</strong><small>{(task.detalhes_tecnicos?.materiais_sugeridos || []).join(" · ") || "Confirme os materiais necessários"}</small></span></div></div><div className="task-disclosure"><strong>Local e contato</strong>{task.local && task.cliente ? <p>{task.local.endereco}, {task.local.bairro} · {task.local.cidade}<br/>{task.local.referencia} · {task.cliente.nome} · {task.cliente.telefone}</p> : <p>Endereço e contato são liberados pelo BFF somente após o agendamento confirmado.</p>}</div></article><aside className="quote-card" id="orcamento"><p className="eyebrow">PROPOSTA PARA O CLIENTE</p><h3>Enviar orçamento</h3><form onSubmit={sendQuote}><label>Valor do serviço <span className="currency-input"><span>R$</span><input type="number" min="1" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} required /></span></label><label>Prazo estimado <select value={days} onChange={(event) => setDays(event.target.value)}><option value="1">Até 1 dia</option><option value="2">Até 2 dias</option><option value="3">Até 3 dias</option><option value="5">Até 5 dias</option></select></label><label>O que está incluído?<textarea rows="3" value={description} onChange={(event) => setDescription(event.target.value)} minLength="3" required /></label><p className="quote-hint">O valor é enviado em centavos para o BFF. Taxas e repasse são calculados pelo serviço de pagamentos.</p><button className="primary-button full-button" disabled={busy === "quote"}>{busy === "quote" ? "Enviando…" : "Enviar orçamento →"}</button></form>{quoteResult && <div className="quote-result"><strong>Proposta registrada</strong><pre>{JSON.stringify(quoteResult, null, 2)}</pre></div>}</aside></div> : <div className="empty-task"><span>▦</span><div><strong>Abra uma solicitação para ver os detalhes.</strong><p>Use o ID de demonstração <code>sol_8f21</code> ou conecte seu token para consultar o BFF real.</p></div><button className="secondary-button" onClick={loadTask}>Carregar exemplo</button></div>}
        </section>
        <section className="finance-section" id="financeiro"><div className="finance-title"><div><p className="eyebrow">REPASSE DO SERVIÇO</p><h2>Entenda o valor que você recebe</h2></div><span className="locked-tag">Dados do BFF · sem cálculo no navegador</span></div>{task?.financeiro ? <div className="finance-card"><div><small>Valor bruto</small><strong>{brl(task.financeiro.valor_bruto_centavos)}</strong></div><span className="minus">−</span><div><small>Taxa da plataforma ({task.financeiro.taxa_plataforma_percentual}%)</small><strong>{brl(task.financeiro.taxa_plataforma_centavos)}</strong></div><span className="equals">=</span><div className="net-value"><small>Valor líquido previsto</small><strong>{brl(task.financeiro.valor_liquido_centavos)}</strong></div><div className="payout-date"><small>Previsão de repasse</small><strong>{task.financeiro.previsao_repasse || "Após a conclusão"}</strong></div></div> : <div className="finance-empty">Quando o pagamento estiver disponível, o BFF exibirá aqui o valor bruto, as taxas e a previsão de repasse.</div>}</section>
        <footer className="provider-footer"><span>ResolveLar · Mais oportunidades para bons profissionais.</span><span>Suas tarefas são privadas e acessadas com token de prestador.</span></footer>
      </main>
      {showSettings && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowSettings(false); }}><section className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title"><button className="modal-close" onClick={() => setShowSettings(false)} aria-label="Fechar">×</button><p className="eyebrow">CONEXÃO DE DEMONSTRAÇÃO</p><h2 id="settings-title">Conectar como prestador</h2><p className="muted">Cole o token de teste do perfil prestador. Ele fica somente nesta sessão do navegador.</p><form onSubmit={saveToken}><label htmlFor="api-token">Token JWT</label><input id="api-token" type="password" autoComplete="off" value={tokenDraft} onChange={(event) => setTokenDraft(event.target.value)} placeholder="Cole o token de prestador" /><div className="modal-actions"><button className="quiet-button" type="button" onClick={() => { setTokenDraft(""); sessionStorage.removeItem("resolvelar-prestador-token"); setToken(""); setShowSettings(false); setNotice("Modo demonstração ativado."); }}>Usar demonstração</button><button className="primary-button compact">Salvar nesta sessão</button></div></form></section></div>}
    </div>
  );
}
