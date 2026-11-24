import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando, Selo } from "../components.jsx";
import { brl, dataHora, nomeCategoria } from "../format.js";

// Uma demanda pode estar aberta (visão pública: sem endereço nem contato) ou já ser deste profissional
// (tarefa confirmada, com local e repasse).
export default function Demanda() {
  const { id } = useParams();
  const { token } = useAuth();
  const [demanda, setDemanda] = useState(null);
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [form, setForm] = useState({ valor: "", dias: "1", descricao: "" });

  useEffect(() => {
    let ativo = true;
    setDemanda(null); setErro("");
    api.demanda(token, id)
      .then((d) => { if (ativo) setDemanda(d); })
      .catch((e) => { if (ativo) { setDemanda(false); setErro(e.message); } });
    return () => { ativo = false; };
  }, [token, id]);

  async function enviar(event) {
    event.preventDefault();
    const reais = Number(form.valor.replace(",", "."));
    if (!Number.isFinite(reais) || reais <= 0) { setErro("Informe um valor válido, por exemplo 180,00."); return; }
    setEnviando(true); setErro("");
    try {
      await api.enviarOrcamento(token, id, {
        valor: { centavos: Math.round(reais * 100), moeda: "BRL" },
        descricaoServico: form.descricao.trim(),
        prazoEstimadoDias: Number(form.dias),
        validoAte: new Date(Date.now() + 7 * 86400000).toISOString(),
      });
      setEnviado(true);
      setAviso("Orçamento enviado! O cliente vai comparar as propostas e escolher.");
    } catch (e) {
      setErro(e.status === 409 ? "Esta solicitação não aceita mais orçamentos (já foi confirmada com outro profissional)." : e.message);
    } finally { setEnviando(false); }
  }

  if (demanda === null) return <Carregando texto="Carregando solicitação…" />;
  if (demanda === false) return (
    <section>
      <Aviso tipo="erro">{erro}</Aviso>
      <p><Link to="/">← Voltar às solicitações</Link></p>
    </section>
  );

  const aberta = (demanda.status_codigo || demanda.status) === "AGUARDANDO_ACEITE" || demanda.status_codigo === "AGUARDANDO_ACEITE";
  const minha = Boolean(demanda.tarefa_id); // detalhe completo: só vem quando o profissional foi escolhido
  const fin = demanda.financeiro;

  return (
    <section className="estreito">
      <p><Link to={minha ? "/agenda" : "/"}>← Voltar</Link></p>
      <div className="cabecalho">
        <div>
          <span className="selo selo-info">{nomeCategoria(demanda.categoria)}</span>
          <h1 className="demanda-titulo">{demanda.descricao}</h1>
        </div>
        <Selo status={demanda.status_codigo || demanda.status} />
      </div>
      <Aviso tipo="erro" onFechar={() => setErro("")}>{erro}</Aviso>
      <Aviso tipo="ok" onFechar={() => setAviso("")}>{aviso}</Aviso>

      <div className="cartao">
        <h2>Detalhes</h2>
        <dl className="fatos">
          <div><dt>Região</dt><dd>{[demanda.bairro, demanda.cidade && demanda.cidade + (demanda.uf ? "/" + demanda.uf : "")].filter(Boolean).join(" · ") || "—"}</dd></div>
          {minha && demanda.agendamento && (
            <div><dt>Atendimento</dt><dd>{dataHora(demanda.agendamento.inicio)}{demanda.agendamento.fim ? " até " + dataHora(demanda.agendamento.fim) : ""}</dd></div>
          )}
          {minha && demanda.local && (
            <div><dt>Endereço</dt><dd>{[demanda.local.logradouro, demanda.local.bairro, demanda.local.cidade].filter(Boolean).join(", ") || "—"}{demanda.local.cep ? " · CEP " + demanda.local.cep : ""}</dd></div>
          )}
          {minha && demanda.cliente && (
            <div><dt>Cliente</dt><dd>{demanda.cliente.nome} · {demanda.cliente.telefone}</dd></div>
          )}
        </dl>
        {!minha && (
          <p className="muted pequeno">
            O endereço completo e o contato do cliente são liberados só depois que ele confirma o serviço com você.
          </p>
        )}
      </div>

      {minha && fin && (
        <div className="cartao">
          <h2>Quanto você recebe</h2>
          <div className="repasse">
            <div><small>Valor do serviço</small><strong>{brl(fin.valor_bruto_centavos)}</strong></div>
            <div><small>Taxa da plataforma ({fin.taxa_plataforma_percentual}%)</small><strong>− {brl(fin.taxa_plataforma_centavos)}</strong></div>
            <div className="liquido"><small>Você recebe</small><strong>{brl(fin.valor_liquido_centavos)}</strong></div>
          </div>
        </div>
      )}

      {aberta && !minha && (enviado ? (
        <div className="cartao"><p className="ok-texto">Orçamento enviado. Acompanhe em “Meus orçamentos”.</p></div>
      ) : (
        <form className="cartao pilha" onSubmit={enviar}>
          <h2>Enviar orçamento</h2>
          <div className="linha">
            <label>Valor total (R$)
              <input inputMode="decimal" required placeholder="180,00" value={form.valor}
                onChange={(e) => setForm({ ...form, valor: e.target.value })} />
            </label>
            <label>Prazo
              <select value={form.dias} onChange={(e) => setForm({ ...form, dias: e.target.value })}>
                {[1, 2, 3, 5, 7].map((d) => <option key={d} value={d}>{d === 1 ? "Até 1 dia" : "Até " + d + " dias"}</option>)}
              </select>
            </label>
          </div>
          <label>O que está incluído?
            <textarea rows="3" required minLength="3" value={form.descricao}
              placeholder="Ex.: visita técnica, troca da peça e teste"
              onChange={(e) => setForm({ ...form, descricao: e.target.value })} />
          </label>
          <div><button className="botao" disabled={enviando}>{enviando ? "Enviando…" : "Enviar orçamento"}</button></div>
        </form>
      ))}
    </section>
  );
}
