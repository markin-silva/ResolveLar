import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setUnauthorizedHandler } from "./api.js";

const CHAVE = "resolvelar-prestador";
const AuthContext = createContext(null);

// O token fica só nesta aba (sessionStorage). Guardamos também o usuário para exibir o nome.
function lerSessao() {
  try {
    const bruto = sessionStorage.getItem(CHAVE);
    return bruto ? JSON.parse(bruto) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [sessao, setSessao] = useState(lerSessao);
  const [aviso, setAviso] = useState("");

  const sair = useCallback((mensagem = "") => {
    try { sessionStorage.removeItem(CHAVE); } catch { /* sem storage: segue sem lembrar */ }
    setSessao(null);
    setAviso(mensagem);
  }, []);

  useEffect(() => { setUnauthorizedHandler(() => sair("Sua sessão expirou. Entre novamente.")); }, [sair]);

  const entrar = useCallback(async (usuario, senha) => {
    const data = await api.login(usuario, senha);
    const nova = { token: data.access_token, usuario: data.usuario };
    try { sessionStorage.setItem(CHAVE, JSON.stringify(nova)); } catch { /* idem */ }
    setSessao(nova);
    setAviso("");
  }, []);

  const valor = useMemo(() => ({ sessao, token: sessao?.token, usuario: sessao?.usuario, entrar, sair, aviso }),
    [sessao, entrar, sair, aviso]);
  return <AuthContext.Provider value={valor}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
