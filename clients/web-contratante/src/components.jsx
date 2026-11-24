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
