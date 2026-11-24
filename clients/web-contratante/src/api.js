// Cliente HTTP. Tudo é relativo ao próprio origin: o Nginx do contêiner encaminha /v1/ ao Kong.
const GW = "/v1/contratante";

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

// Erros da API chegam como RFC 7807 (`detail`/`title`). O status HTTP fica em `error.status`.
export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request(path, { token, method = "GET", body, headers = {} } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: "Bearer " + token } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Não foi possível falar com o servidor. Verifique sua conexão.", 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && token) onUnauthorized();
    throw new ApiError(mensagemDeErro(response.status, data), response.status, data);
  }
  return data;
}

// Mensagens em português para os erros mais comuns; o detalhe do servidor vem junto quando ajuda.
function mensagemDeErro(status, data) {
  const detalhe = data?.detail || data?.title || "";
  if (status === 401) return detalhe || "Sessão expirada. Entre novamente.";
  if (status === 403) return detalhe || "Você não tem permissão para isso.";
  if (status === 404) return detalhe || "Não encontramos o que você procurou.";
  if (status === 409) return detalhe || "Isso não pode ser feito no estado atual.";
  if (status === 422) return "Confira os dados informados e tente de novo.";
  if (status === 429) return "Muitas tentativas em pouco tempo. Aguarde um instante e tente de novo.";
  if (status >= 500) return detalhe || "O serviço está indisponível no momento. Tente novamente em instantes.";
  return detalhe || "Algo deu errado (" + status + ").";
}

export const api = {
  // sessão (pública)
  usuarios: () => request("/v1/auth/usuarios"),
  login: (usuario, senha) => request("/v1/auth/login", { method: "POST", body: { usuario, senha } }),

  // pedidos
  meusPedidos: (token, status) =>
    request(GW + "/solicitacoes" + (status ? "?status=" + encodeURIComponent(status) : ""), { token }),
  pedido: (token, id) => request(GW + "/solicitacoes/" + encodeURIComponent(id) + "/orcamentos", { token }),
  estadoDoPedido: (token, href) => request(href, { token }),
  criarPedido: (token, dados) => request(GW + "/solicitacoes", { token, method: "POST", body: dados }),

  // orçamentos
  aprovar: (token, href, corpo) =>
    request(href, { token, method: "POST", body: corpo, headers: { "Idempotency-Key": novaChave() } }),
  recusar: (token, href) => request(href, { token, method: "POST", body: {} }),

  // triagem, profissionais, avaliação
  triagem: (token, dados) => request(GW + "/triagem", { token, method: "POST", body: dados }),
  profissionais: (token, params) => request(GW + "/prestadores?" + new URLSearchParams(params), { token }),
  avaliar: (token, id, dados) =>
    request(GW + "/solicitacoes/" + encodeURIComponent(id) + "/avaliacao", { token, method: "POST", body: dados }),
};

// Idempotency-Key nova a cada tentativa de aprovação.
function novaChave() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return "web-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

// Os links podem vir como /v1/... (do ms-*); o cliente só fala com o gateway, em /v1/contratante/...
export function gwPath(href) {
  if (!href) return "";
  if (href.startsWith(GW)) return href;
  if (href.startsWith("/v1/")) return GW + href.slice(3);
  return href;
}
