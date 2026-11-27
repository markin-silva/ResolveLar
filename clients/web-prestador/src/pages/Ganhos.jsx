import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Aviso, Carregando, Dica, Icone, Vazio } from "../components.jsx";
import { brl, nomeCategoria } from "../format.js";

// Extrato: bruto, taxa e líquido de cada serviço confirmado. Os totais vêm do BFF (soma em centavos).
export default function Ganhos() {
  const { token } = useAuth();
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let ativo = true;
    api.ganhos(token)
      .then((d) => { if (ativo) setDados(d); })
      .catch((e) => { if (ativo) { setDados({ items: [], totais: null }); setErro(e.message); } });
    return () => { ativo = false; };
  }, [token]);

  const t = dados?.totais;
  return (
    <section>
      <div className="cabecalho-pagina">
        <span className="cabecalho-icone"><Icone nome="grafico" tamanho={24} /></span>
        <div>
          <h1>Ganhos</h1>
          <p className="muted">O que você recebe por serviço, já descontada a taxa da plataforma.</p>
        </div>
      </div>
      <Aviso tipo="erro">{erro}</Aviso>
      {dados === null && <Carregando />}

      {t && dados.items.length > 0 && (
        <div className="totais">
          <div className="cartao"><small>Você recebe (total)</small><strong className="liquido-grande">{brl(t.valor_liquido_centavos)}</strong></div>
          <div className="cartao"><small>Valor bruto</small><strong>{brl(t.valor_bruto_centavos)}</strong></div>
          <div className="cartao"><small>Taxa da plataforma</small><strong>− {brl(t.taxa_plataforma_centavos)}</strong></div>
        </div>
      )}

      {dados?.items?.length > 0 && (
        <Dica icone="estrela">Cada serviço bem feito vira uma avaliação, e cada avaliação traz novos clientes.</Dica>
      )}
      {dados?.items?.length === 0 && !erro && <Vazio titulo="Ainda não há ganhos">Eles aparecem quando um serviço seu é confirmado e pago.</Vazio>}
      {dados?.items?.length > 0 && (
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead><tr><th>Serviço</th><th className="num">Bruto</th><th className="num">Taxa</th><th className="num">Líquido</th></tr></thead>
            <tbody>
              {dados.items.map((i) => (
                <tr key={i.solicitacao_id}>
                  <td><Link to={"/solicitacoes/" + i.solicitacao_id}>{nomeCategoria(i.categoria)}</Link></td>
                  <td className="num">{brl(i.valor_bruto_centavos)}</td>
                  <td className="num">− {brl(i.taxa_plataforma_centavos)}</td>
                  <td className="num"><strong>{brl(i.valor_liquido_centavos)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
