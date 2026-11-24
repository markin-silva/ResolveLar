// Cliente HTTP. Tudo é relativo ao próprio origin: o Nginx do contêiner encaminha /v1/ ao Kong.
const GW = "/v1/prestador";

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

  // fila de demandas (categorias e cidade do perfil do profissional) e detalhe da demanda
  fila: (token) => request(GW + "/solicitacoes", { token }),
  demanda: (token, id) => request(GW + "/solicitacoes/" + encodeURIComponent(id), { token }),

  // orçamento
  enviarOrcamento: (token, id, dados) =>
    request(GW + "/solicitacoes/" + encodeURIComponent(id) + "/orcamentos", { token, method: "POST", body: dados }),
  meusOrcamentos: (token) => request(GW + "/orcamentos", { token }),

  // agenda e ganhos
  agenda: (token) => request(GW + "/agenda", { token }),
  ganhos: (token) => request(GW + "/ganhos", { token }),
};
