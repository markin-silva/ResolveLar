# Avaliação do Assistente de Triagem (RAG × sem RAG)

- Data: 2026-11-27 01:00
- Provedor/modelo: `gemini` / `gemini-3.5-flash-lite`
- Preço usado: US$ 0.3/1M tokens de entrada, US$ 2.5/1M de saída (estimativa)
- Cache desligado; latência = cadeia completa (RAG + LLM + tool de prestadores).
- Timeout do LLM nesta avaliação: 30 s por tentativa, com retry em 503/timeout (produção: orçamento total de 5 s; acima disso a triagem cai no fallback).

| # | RAG | Modo | Categoria | Urgência | Cobertura segurança | Fontes | Prestadores | Latência (ms) | Tokens (in/out) | Custo (US$) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | sim | llm | ✅ eletricista | ✅ ALTA | 100% | 4 | 0 | 8209 | 919/236 | 0.000866 |
| 1 | não | llm | ✅ eletricista | ✅ MEDIA | 75% | 0 | 0 | 5559 | 340/199 | 0.000599 |
| 2 | sim | llm | ✅ tecnico-gas | ✅ EMERGENCIA | 100% | 4 | 0 | 6346 | 855/214 | 0.000791 |
| 2 | não | llm | ✅ tecnico-gas | ✅ EMERGENCIA | 80% | 0 | 0 | 5507 | 330/202 | 0.000604 |
| 3 | sim | llm | ✅ encanador | ✅ MEDIA | 50% | 4 | 0 | 6304 | 771/154 | 0.000616 |
| 3 | não | llm | ✅ encanador | ✅ MEDIA | 25% | 0 | 0 | 5527 | 339/189 | 0.000574 |
| 4 | sim | llm | ✅ chaveiro | ✅ ALTA | 75% | 4 | 0 | 6239 | 756/202 | 0.000732 |
| 4 | não | llm | ✅ chaveiro | ✅ ALTA | 25% | 0 | 0 | 5381 | 340/180 | 0.000552 |
| 5 | sim | llm | ✅ pedreiro | ✅ EMERGENCIA | 25% | 4 | 0 | 6902 | 866/168 | 0.000680 |
| 5 | não | llm | ✅ pedreiro | ✅ ALTA | 25% | 0 | 0 | 5554 | 337/186 | 0.000566 |

## Resumo

| Configuração | Categoria correta | Urgência aceitável | Cobertura média | Latência média (ms) | Latência máx (ms) | Custo total (US$) | Custo médio/consulta (US$) |
|---|---|---|---|---|---|---|---|
| Com RAG | 5/5 | 5/5 | 70% | 6800 | 8209 | 0.003685 | 0.000737 |
| Sem RAG | 5/5 | 5/5 | 46% | 5506 | 5559 | 0.002895 | 0.000579 |

## Latência e custo em escala

- Respostas do LLM: 10/10. Latência p50 = 5559 ms, p95 = 8209 ms, máx = 8209 ms.
- 10/10 chamadas passaram do orçamento de produção (5 s): em produção essas cairiam no fallback por regras (a resposta chega, só que sem o LLM).

| Configuração | Tokens médios (in/out) | Custo/consulta (US$) | 1.000/mês | 100.000/mês | 1.000.000/mês | 1.000.000/mês com 20% de cache |
|---|---|---|---|---|---|---|
| Com RAG | 833/195 | 0.000737 | US$ 0.74 | US$ 73.70 | US$ 737.00 | US$ 589.60 |
| Sem RAG | 337/191 | 0.000579 | US$ 0.58 | US$ 57.90 | US$ 579.00 | US$ 463.20 |

Leitura: o custo cresce linearmente com o volume; o cache por chave (`triagem:v1:*`, 1 h) só economiza em descrições repetidas, por isso a taxa de acerto é uma hipótese (`--taxa-cache`). O RAG aumenta os tokens de entrada (contexto), mas a saída domina o preço.

## Orientações geradas

**1 · com RAG (llm)**: Desligue o disjuntor do chuveiro antes de abrir o aparelho. / Nunca mexa em fiação com as mãos ou os pés molhados e não use escada metálica. / Não troque o disjuntor por um de amperagem maior para ele parar de desarmar. / Se a fiação estiver escurecida, derretida ou com cheiro de queimado, não religue e chame um eletricista.

**1 · sem RAG (llm)**: Desligue o disjuntor exclusivo do chuveiro no quadro de distribuição antes de mexer ou verificar qualquer conexão. / Evite tocar nos fios ou no aparelho com as mãos molhadas ou descalço para prevenir choques elétricos. / Não tente forçar o disjuntor a permanecer ligado caso ele volte a desarmar.

**2 · com RAG (llm)**: Acione o Corpo de Bombeiros (193) imediatamente e garanta a retirada de todas as pessoas e animais do local. / Não acenda fósforos, isqueiros ou velas e não fume. / Não acione interruptores de luz, campainha ou aparelhos elétricos para evitar faíscas. / Feche o registro do gás (botijão ou registro geral encanado) e abra portas e janelas para ventilar.

**2 · sem RAG (llm)**: Ligue imediatamente para o Corpo de Bombeiros (193) se houver risco iminente ou mal-estar. / Feche o registro geral de gás imediatamente. / Não acenda luzes, fósforos, isqueiros e não utilize nenhum aparelho eletrônico para evitar faíscas. / Abra portas e janelas para ventilar o ambiente.

**3 · com RAG (llm)**: Desligue a energia das luminárias próximas se a mancha estiver estufada ou pingando. / Não toque no forro do teto para evitar acidentes ou quedas de material.

**3 · sem RAG (llm)**: Evite usar o chuveiro ou o banheiro do andar superior, se houver, para cessar a alimentação do vazamento. / Coloque um balde e panos no chão para conter a água que está pingando e evitar escorregões. / Afaste móveis, tapetes e objetos eletrônicos ou de valor da área afetada.

**4 · com RAG (llm)**: Não force a fechadura nem tente girar o pedaço da chave com objetos metálicos para evitar empurrar o fragmento para dentro e danificar o cilindro. / Não coloque cola, óleo de cozinha ou palito no mecanismo. / Caso uma ponta do fragmento esteja visível, você pode tentar puxá-la com uma pinça fina, sem girar.

**4 · sem RAG (llm)**: Mantenha-se em um local seguro e iluminado enquanto aguarda o atendimento. / Não tente forçar a abertura da porta com ferramentas inadequadas para evitar danificar ainda mais a fechadura ou a porta. / Tenha em mãos um documento de identificação que comprove sua residência no local.

**5 · com RAG (llm)**: Saia do imóvel imediatamente. / Ligue para a Defesa Civil (199) ou para os Bombeiros (193). / Não retorne ao interior do imóvel até que uma avaliação estrutural seja realizada.

**5 · sem RAG (llm)**: Afafaste móveis e objetos próximos à parede afetada para evitar danos ou acidentes. / Evite permanecer no cômodo por longos períodos até a avaliação de um profissional. / Monitore o crescimento da rachadura com uma marcação a lápis se necessário, mas não tente consertá-la por conta própria.

