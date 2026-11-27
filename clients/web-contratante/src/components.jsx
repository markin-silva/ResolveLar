import { rotuloStatus } from "./format.js";

export function Aviso({ tipo = "info", children, onFechar }) {
  if (!children) return null;
  return (
    <div className={"aviso aviso-" + tipo} role={tipo === "erro" ? "alert" : "status"}>
      <span>{children}</span>
      {onFechar && <button className="aviso-fechar" onClick={onFechar} aria-label="Fechar aviso">×</button>}
    </div>
  );
}

export function Carregando({ texto = "Carregando…" }) {
  return <p className="carregando" role="status">{texto}</p>;
}

export function Vazio({ titulo, children }) {
  return (
    <div className="vazio">
      <strong>{titulo}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

export function Selo({ status }) {
  const { texto, tom } = rotuloStatus(status);
  return <span className={"selo selo-" + tom}>{texto}</span>;
}

export function Estrelas({ nota }) {
  if (nota == null) return <span className="muted">sem avaliações</span>;
  return <span className="estrelas" title={nota + " de 5"}>★ {Number(nota).toFixed(1)}</span>;
}

// Passos do pedido, para o contratante saber em que etapa está.
export function Passos({ atual }) {
  const passos = ["Pedido", "Orçamentos", "Confirmação", "Avaliação"];
  return (
    <ol className="passos" aria-label="Etapas do pedido">
      {passos.map((nome, i) => (
        <li key={nome} className={i < atual ? "feito" : i === atual ? "atual" : ""}>
          <span className="passo-num">{i < atual ? "✓" : i + 1}</span>{nome}
        </li>
      ))}
    </ol>
  );
}

// ---------- elementos visuais (apenas apresentação) ----------
const ICONES = {
  casa: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9.5" /><path d="M10 21v-6h4v6" /></>,
  chave: <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />,
  escudo: <><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" /><path d="m9 12 2 2 4-4" /></>,
  estrela: <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z" />,
  relogio: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  dinheiro: <><rect x="2" y="6" width="20" height="12" rx="2" /><circle cx="12" cy="12" r="2.5" /><path d="M6 12h.01M18 12h.01" /></>,
  calendario: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
  cadeado: <><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>,
  pin: <><path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></>,
  lampada: <><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z" /></>,
  faisca: <><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><path d="M19 15v4M17 17h4" /></>,
  mensagem: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />,
  usuarios: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.8.7 3 2.5 3.5 5.2" /></>,
  grafico: <><path d="m3 17 6-6 4 4 8-8" /><path d="M15 7h6v6" /></>,
  lapis: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m13.5 6.5 4 4" /></>,
  check: <path d="m5 12 5 5 9-10" />,
};

export function Icone({ nome, tamanho = 20 }) {
  return (
    <svg className="icone" width={tamanho} height={tamanho} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {ICONES[nome]}
    </svg>
  );
}

// Faixa de destaque no topo das telas principais.
export function Faixa({ sobretitulo, titulo, children, selos, acao }) {
  return (
    <div className="faixa">
      <div className="faixa-texto">
        {sobretitulo && <p className="faixa-sobre">{sobretitulo}</p>}
        <p className="faixa-titulo">{titulo}</p>
        {children && <p className="faixa-desc">{children}</p>}
        {selos && (
          <ul className="faixa-selos">
            {selos.map(([icone, texto]) => <li key={texto}><Icone nome={icone} tamanho={16} />{texto}</li>)}
          </ul>
        )}
      </div>
      {acao && <div className="faixa-acao">{acao}</div>}
      <span className="faixa-arte" aria-hidden="true"><Icone nome="casa" tamanho={180} /></span>
    </div>
  );
}

export function Dica({ icone = "lampada", children }) {
  return (
    <div className="dica">
      <span className="dica-icone"><Icone nome={icone} /></span>
      <p>{children}</p>
    </div>
  );
}

// Lista de passos/benefícios com ícone.
export function Beneficios({ itens }) {
  return (
    <ul className="beneficios">
      {itens.map(([icone, titulo, texto]) => (
        <li key={titulo}>
          <span className="beneficio-icone"><Icone nome={icone} /></span>
          <span><strong>{titulo}</strong>{texto && <small>{texto}</small>}</span>
        </li>
      ))}
    </ul>
  );
}

export function Rodape({ itens }) {
  return (
    <footer className="rodape">
      <ul className="rodape-selos">
        {itens.map(([icone, texto]) => <li key={texto}><Icone nome={icone} tamanho={18} />{texto}</li>)}
      </ul>
      <p className="rodape-marca">
        <img src="/icone.png" alt="" /> <span><b>ResolveLar</b> · Quem precisa encontra. Quem sabe fazer, trabalha.</span>
      </p>
    </footer>
  );
}
