export function brl(centavos) {
  if (centavos == null) return "—";
  return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function dataHora(valor) {
  if (!valor) return "A confirmar";
  return new Date(valor).toLocaleString("pt-BR", { dateStyle: "medium", timeStyle: "short" });
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

// Rótulos do estado da solicitação para o contratante, com o tom do selo.
export function rotuloStatus(codigo) {
  switch (codigo) {
    case "AGUARDANDO_ACEITE": return { texto: "Aguardando sua escolha", tom: "aviso" };
    case "EM_CONFIRMACAO": return { texto: "Confirmando agenda e pagamento", tom: "info" };
    case "CONFIRMADA": return { texto: "Serviço confirmado", tom: "ok" };
    case "CONCLUIDA": return { texto: "Serviço concluído", tom: "ok" };
    default: return { texto: codigo || "—", tom: "neutro" };
  }
}
