import { Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Entrar from "./pages/Entrar.jsx";
import MeusPedidos from "./pages/MeusPedidos.jsx";
import NovoPedido from "./pages/NovoPedido.jsx";
import Pedido from "./pages/Pedido.jsx";
import Profissionais from "./pages/Profissionais.jsx";

// Rotas que exigem sessão. Sem token, vai para a tela de entrada.
function Protegido() {
  const { token } = useAuth();
  if (!token) return <Navigate to="/entrar" replace />;
  return <Layout />;
}

function Layout() {
  const { usuario, sair } = useAuth();
  return (
    <div className="app">
      <header className="topo">
        <div className="marca"><span className="marca-icone">R</span>resolvelar</div>
        <nav>
          <NavLink to="/" end>Meus pedidos</NavLink>
          <NavLink to="/novo">Novo pedido</NavLink>
          <NavLink to="/profissionais">Profissionais</NavLink>
        </nav>
        <div className="sessao">
          <span>{usuario?.nome}</span>
          <button className="botao-link" onClick={() => sair()}>Sair</button>
        </div>
      </header>
      <main><Outlet /></main>
    </div>
  );
}

export default function App() {
  const { token } = useAuth();
  return (
    <Routes>
      <Route path="/entrar" element={token ? <Navigate to="/" replace /> : <Entrar />} />
      <Route element={<Protegido />}>
        <Route path="/" element={<MeusPedidos />} />
        <Route path="/novo" element={<NovoPedido />} />
        <Route path="/pedidos/:id" element={<Pedido />} />
        <Route path="/profissionais" element={<Profissionais />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
