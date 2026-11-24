import { Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Agenda from "./pages/Agenda.jsx";
import Demanda from "./pages/Demanda.jsx";
import Entrar from "./pages/Entrar.jsx";
import Fila from "./pages/Fila.jsx";
import Ganhos from "./pages/Ganhos.jsx";
import MeusOrcamentos from "./pages/MeusOrcamentos.jsx";

function Protegido() {
  const { token } = useAuth();
  if (!token) return <Navigate to="/entrar" replace />;
  return <Painel />;
}

// Visual de painel de trabalho (menu lateral), diferente do app do contratante.
function Painel() {
  const { usuario, sair } = useAuth();
  return (
    <div className="painel">
      <aside className="lateral">
        <div className="marca"><span className="marca-icone">R</span><span>resolvelar<small>área do profissional</small></span></div>
        <nav aria-label="Principal">
          <NavLink to="/" end>Novas solicitações</NavLink>
          <NavLink to="/orcamentos">Meus orçamentos</NavLink>
          <NavLink to="/agenda">Agenda</NavLink>
          <NavLink to="/ganhos">Ganhos</NavLink>
        </nav>
        <div className="lateral-rodape">
          <strong>{usuario?.nome}</strong>
          <small>{usuario?.resumo}</small>
          <button className="botao-link" onClick={() => sair()}>Sair</button>
        </div>
      </aside>
      <main className="conteudo"><Outlet /></main>
    </div>
  );
}

export default function App() {
  const { token } = useAuth();
  return (
    <Routes>
      <Route path="/entrar" element={token ? <Navigate to="/" replace /> : <Entrar />} />
      <Route element={<Protegido />}>
        <Route path="/" element={<Fila />} />
        <Route path="/solicitacoes/:id" element={<Demanda />} />
        <Route path="/orcamentos" element={<MeusOrcamentos />} />
        <Route path="/agenda" element={<Agenda />} />
        <Route path="/ganhos" element={<Ganhos />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
