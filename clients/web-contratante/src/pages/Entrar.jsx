import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando } from "../components.jsx";

// Tela de entrada: o contratante escolhe um dos usuários de demonstração e informa a senha.
export default function Entrar() {
  const { entrar, aviso } = useAuth();
  const [usuarios, setUsuarios] = useState(null);
  const [escolhido, setEscolhido] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    api.usuarios()
      .then((data) => {
        const lista = (data.items || []).filter((u) => u.perfil === "contratante");
        setUsuarios(lista);
        if (lista.length) setEscolhido(lista[0].usuario);
      })
      .catch((e) => { setUsuarios([]); setErro(e.message); });
  }, []);

  async function enviar(event) {
    event.preventDefault();
    setEnviando(true); setErro("");
    try {
      await entrar(escolhido, senha);
    } catch (e) {
      setErro(e.status === 401 ? "Senha incorreta. Confira com quem organizou o teste." : e.message);
    } finally { setEnviando(false); }
  }

  return (
    <div className="entrada">
      <div className="entrada-grade">
      <aside className="entrada-vitrine">
        <h2>Sua casa em <em>boas mãos</em>.</h2>
        <p>Descreva o problema, compare orçamentos e agende com profissionais de confiança da sua região.</p>
        <ul>
          <li>Orçamentos de vários profissionais</li>
          <li>Pagamento seguro pela plataforma</li>
          <li>Avaliações reais de outros moradores</li>
        </ul>
        <img className="entrada-ilustracao" src="/boas-vindas.png" alt="" />
      </aside>
      <form className="cartao entrada-cartao" onSubmit={enviar}>
        <img className="entrada-logo" src="/logo.png" alt="ResolveLar" />
        <p className="sobretitulo">Área do contratante</p>
        <h1>Entrar</h1>
        <p className="muted">Escolha o usuário de demonstração e informe a senha de teste.</p>

        {usuarios === null && <Carregando texto="Carregando usuários…" />}
        {usuarios?.length > 0 && (
          <fieldset className="usuarios">
            <legend className="sr-only">Usuário</legend>
            {usuarios.map((u) => (
              <label key={u.usuario} className={"usuario" + (escolhido === u.usuario ? " usuario-ativo" : "")}>
                <input type="radio" name="usuario" value={u.usuario} checked={escolhido === u.usuario}
                  onChange={() => setEscolhido(u.usuario)} />
                <span><strong>{u.nome}</strong><small>{u.resumo}</small></span>
              </label>
            ))}
          </fieldset>
        )}

        <label>Senha
          <input type="password" autoComplete="current-password" value={senha}
            onChange={(e) => setSenha(e.target.value)} required />
        </label>
        <button className="botao" disabled={enviando || !escolhido || !senha}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
        <Aviso tipo="erro">{erro}</Aviso>
        <Aviso tipo="info">{aviso}</Aviso>
      </form>
      </div>
    </div>
  );
}
