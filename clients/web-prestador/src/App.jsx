import { useState } from "react";

// Todas as chamadas são relativas ao próprio origin: o Nginx do contêiner encaminha /v1/ ao Kong.
const GW = "/v1/prestador";

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

// O identificador do profissional vem do claim `sub` do token (leitura apenas; quem valida é o Kong).
function idDoToken(token) {
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload)).sub || "";
  } catch {
    return "";
  }
}

function brl(centavos) {
  if (centavos == null) return "—";
  return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function dataHora(valor) {
  if (!valor) return "A confirmar";
  return new Date(valor).toLocaleString("pt-BR", { dateStyle: "medium", timeStyle: "short" });
}

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("resolvelar-prestador-token") || "");
  const [tokenDraft, setTokenDraft] = useState("");
  const [notice, setNotice] = useState(null); // { type, text }
  const [solicitacaoId, setSolicitacaoId] = useState("");
  const [tarefa, setTarefa] = useState(null);
  const [busy, setBusy] = useState("");
  const [orcamento, setOrcamento] = useState({ valor: "", descricao: "", dias: "1" });
  const [enviado, setEnviado] = useState(null);

  const conectado = Boolean(token);
  const profissional = conectado ? idDoToken(token) : "";

  function falha(error, contexto) {
    setNotice({
      type: "erro",
      text: error.status === 401 ? "Sessão sem autorização (401). Conecte outro token." : contexto + ": " + error.message,
    });
  }

  function salvarToken(event) {
    event.preventDefault();
    const next = tokenDraft.trim();
    if (!next) return;
    sessionStorage.setItem("resolvelar-prestador-token", next);
    setToken(next);
    setTokenDraft("");
    setNotice({ type: "ok", text: "Conectado. O token fica só nesta aba do navegador." });
  }

  function desconectar() {
    sessionStorage.removeItem("resolvelar-prestador-token");
    setToken(""); setTarefa(null); setEnviado(null); setNotice(null);
  }

  async function abrirTarefa(event) {
    event.preventDefault();
    setBusy("tarefa"); setNotice(null); setEnviado(null);
    try {
      const data = await api(GW + "/tarefas/" + encodeURIComponent(solicitacaoId.trim()), { token });
      setTarefa(data);
    } catch (error) {
      setTarefa(null);
      falha(error, "Não foi possível abrir a solicitação");
    } finally { setBusy(""); }
  }

  async function enviarOrcamento(event) {
    event.preventDefault();
    if (!tarefa) return;
    setBusy("orcamento"); setNotice(null);
    const payload = {
      valor: { centavos: Math.round(Number(orcamento.valor.replace(",", ".")) * 100), moeda: "BRL" },
      descricaoServico: orcamento.descricao.trim(),
      prazoEstimadoDias: Number(orcamento.dias),
      validoAte: new Date(Date.now() + 7 * 86400000).toISOString(),
    };
    try {
      const data = await api(GW + "/solicitacoes/" + encodeURIComponent(tarefa.tarefa_id) + "/orcamentos", {
        token, method: "POST", body: JSON.stringify(payload),
      });
      setEnviado(data);
      setNotice({ type: "ok", text: "Orçamento enviado ao cliente." });
    } catch (error) {
      falha(error, "Não foi possível enviar o orçamento");
    } finally { setBusy(""); }
  }

  // ------------------------------------------------------------------ tela de conexão
  if (!conectado) {
    return (
      <div className="connect-screen">
        <form className="connect-card" onSubmit={salvarToken}>
          <p className="eyebrow">ResolveLar · Profissional</p>
          <h1>Entrar</h1>
          <p className="muted">Cole o token de acesso do profissional. Ele fica apenas nesta aba do navegador.</p>
          <label htmlFor="token">Token de acesso</label>
          <input id="token" type="password" autoComplete="off" value={tokenDraft}
            onChange={(event) => setTokenDraft(event.target.value)} placeholder="eyJhbGciOi…" required />
          <button className="primary-button" disabled={!tokenDraft.trim()}>Entrar</button>
          {notice && <p className={"notice notice-" + notice.type} role="alert">{notice.text}</p>}
        </form>
      </div>
    );
  }

  // ------------------------------------------------------------------ aplicação
  const liquido = tarefa?.financeiro?.valor_liquido_centavos;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">R</span>resolvelar <span className="muted">· profissional</span></div>
        <span className="muted small-text">{profissional}</span>
        <button className="link-button" onClick={desconectar}>Sair</button>
      </header>

      <main>
        {notice && <p className={"notice notice-" + notice.type} role="status">{notice.text}</p>}

        <section className="card">
          <h2>Consultar solicitação</h2>
          <p className="muted">Informe o ID da solicitação para ver os detalhes técnicos e enviar seu orçamento.</p>
          <form className="row" onSubmit={abrirTarefa}>
            <label>ID da solicitação
              <input value={solicitacaoId} onChange={(event) => setSolicitacaoId(event.target.value)}
                placeholder="sol_…" required />
            </label>
            <button className="primary-button compact" disabled={busy === "tarefa"}>
              {busy === "tarefa" ? "Buscando…" : "Abrir"}
            </button>
          </form>
        </section>

        {tarefa && (
          <section className="card">
            <div className="row between">
              <div>
                <p className="eyebrow">{tarefa.categoria || "Serviço"}</p>
                <h2>{tarefa.descricao || "Solicitação"}</h2>
              </div>
              <span className="badge">{tarefa.status || "—"}</span>
            </div>

            <dl className="facts">
              <div><dt>Agendamento</dt><dd>{dataHora(tarefa.agendamento?.inicio)}{tarefa.agendamento?.fim ? " até " + dataHora(tarefa.agendamento.fim) : ""}</dd></div>
              {tarefa.detalhes_tecnicos && Object.keys(tarefa.detalhes_tecnicos).length > 0 && (
                <div>
                  <dt>Detalhes técnicos</dt>
                  <dd>
                    {tarefa.detalhes_tecnicos.tensao && <>Tensão {tarefa.detalhes_tecnicos.tensao}. </>}
                    {tarefa.detalhes_tecnicos.potencia_w && <>Potência {tarefa.detalhes_tecnicos.potencia_w} W. </>}
                    {tarefa.detalhes_tecnicos.materiais_sugeridos?.length > 0 && <>Materiais: {tarefa.detalhes_tecnicos.materiais_sugeridos.join(", ")}.</>}
                  </dd>
                </div>
              )}
              {tarefa.local && (
                <div><dt>Local</dt><dd>{[tarefa.local.endereco, tarefa.local.bairro, tarefa.local.cidade].filter(Boolean).join(", ")}</dd></div>
              )}
              {tarefa.cliente && (
                <div><dt>Cliente</dt><dd>{tarefa.cliente.nome} · {tarefa.cliente.telefone}</dd></div>
              )}
            </dl>

            {tarefa.financeiro && (
              <div className="finance">
                <p className="eyebrow">Repasse</p>
                <div className="finance-grid">
                  <div><span className="muted small-text">Valor bruto</span><strong>{brl(tarefa.financeiro.valor_bruto_centavos)}</strong></div>
                  <div><span className="muted small-text">Taxa da plataforma ({tarefa.financeiro.taxa_plataforma_percentual}%)</span><strong>− {brl(tarefa.financeiro.taxa_plataforma_centavos)}</strong></div>
                  <div className="net"><span className="muted small-text">Você recebe</span><strong>{brl(liquido)}</strong></div>
                </div>
                {tarefa.financeiro.previsao_repasse && <p className="muted small-text">Previsão de repasse: {tarefa.financeiro.previsao_repasse}</p>}
              </div>
            )}

            {enviado ? (
              <p className="notice notice-ok">Orçamento enviado. Aguardando a escolha do cliente.</p>
            ) : (
              <form className="stack" onSubmit={enviarOrcamento}>
                <h3>Enviar orçamento</h3>
                <div className="row">
                  <label className="small">Valor (R$)
                    <input inputMode="decimal" required value={orcamento.valor}
                      onChange={(event) => setOrcamento({ ...orcamento, valor: event.target.value })} placeholder="180,00" />
                  </label>
                  <label className="small">Prazo (dias)
                    <select value={orcamento.dias} onChange={(event) => setOrcamento({ ...orcamento, dias: event.target.value })}>
                      {[1, 2, 3, 5, 7].map((d) => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </label>
                </div>
                <label>O que está incluído?
                  <textarea rows="3" required minLength="3" value={orcamento.descricao}
                    onChange={(event) => setOrcamento({ ...orcamento, descricao: event.target.value })} />
                </label>
                <button className="primary-button" disabled={busy === "orcamento"}>
                  {busy === "orcamento" ? "Enviando…" : "Enviar orçamento"}
                </button>
              </form>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
