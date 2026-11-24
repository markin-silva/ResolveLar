export function brl(centavos) {
  if (centavos == null) return "—";
  return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function dataHora(valor) {
  if (!valor) return "A confirmar";
  return new Date(valor).toLocaleString("pt-BR", { dateStyle: "medium", timeStyle: "short" });
}

export function dia(valor) {
  if (!valor) return "—";
  return new Date(valor).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" });
}

export function hora(valor) {
  if (!valor) return "";
  return new Date(valor).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export const CATEGORIAS = [
  ["eletricista", "Elétrica"],
  ["encanador", "Encanamento"],
  ["tecnico-gas", "Gás"],
  ["pedreiro", "Alvenaria"],
  ["pintor", "Pintura"],
  ["marceneiro", "Marcenaria"],
  ["chaveiro", "Chaveiro"],
  ["instalador", "Instalação"],
];

export const nomeCategoria = (slug) => CATEGORIAS.find(([valor]) => valor === slug)?.[1] || slug;

// Estado da solicitação do ponto de vista do profissional, com o tom do selo.
export function rotuloStatus(codigo) {
  switch (codigo) {
    case "AGUARDANDO_ACEITE": return { texto: "Aberta para orçamentos", tom: "info" };
    case "EM_CONFIRMACAO": return { texto: "Confirmando", tom: "aviso" };
    case "CONFIRMADA": return { texto: "Confirmada", tom: "ok" };
    case "CONCLUIDA": return { texto: "Concluída", tom: "ok" };
    case "APROVADO": return { texto: "Aprovado", tom: "ok" };
    case "PENDENTE": return { texto: "Aguardando o cliente", tom: "info" };
    case "RECUSADO": return { texto: "Recusado", tom: "erro" };
    case "EXPIRADO": return { texto: "Expirado", tom: "neutro" };
    case "RESERVADA": return { texto: "Reservado", tom: "aviso" };
    default: return { texto: codigo || "—", tom: "neutro" };
  }
}
