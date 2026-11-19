# 05 — Avaliação do Assistente de Triagem (RAG, latência e custo)

Atende à Parte 4, item 6.2 do enunciado: avaliação do RAG com 5 perguntas **com e sem recuperação**, e análise de **latência e custo** do LLM tratado como dependência remota falível.

## Como reproduzir

```bash
docker compose up --build -d            # com GEMINI_API_KEY (ou OPENAI_API_KEY) preenchida no .env
docker compose exec ms-triagem python -m app.avaliacao --saida /tmp/avaliacao.md
docker compose cp ms-triagem:/tmp/avaliacao.md docs/05-avaliacao-triagem.md
```

Opções: `--timeout` (timeout por tentativa só na avaliação, padrão 30 s), `--retries` (padrão 3, só em 503/timeout) e `--taxa-cache` (hipótese de acerto do cache na projeção, padrão 20%). Sem chave de API o script roda igual, mas todas as respostas saem do fallback por regras e não há custo a projetar.

## Metodologia

- 5 descrições reais de problemas residenciais (elétrica, gás, infiltração, chaveiro, estrutura), cada uma com gabarito de **categoria**, **urgências aceitáveis** e **grupos de fatos de segurança** tirados da base de conhecimento (`services/ms-triagem/app/conhecimento/`).
- Cada pergunta roda duas vezes pela cadeia completa (RAG → LLM → tool `buscar_prestadores`): **com RAG** (4 trechos do ChromaDB no prompt) e **sem RAG** (o modelo responde só com o conhecimento próprio). Cache desligado.
- **Cobertura de segurança** = % dos grupos de fatos presentes nas orientações geradas (cada grupo vale se qualquer termo dele aparecer). É uma métrica por palavra-chave: mede aderência à base, não a qualidade geral do texto.
- Custo = tokens reais devolvidos pelo provedor (`usage_metadata`) × preço por 1M tokens do modelo (tabela oficial do Gemini, nível pago Standard; no nível gratuito o custo é zero).

## Análise

**Qualidade: o RAG quase dobra a cobertura de segurança (75% contra 40%)**, com o mesmo acerto de categoria e urgência (5/5 nos dois casos). A classificação o modelo já faz bem sozinho; o ganho do RAG está nas **orientações específicas da base**:
- *Infiltração (3):* com RAG o modelo manda desligar as luminárias próximas e não tocar no forro estufado (risco elétrico e de queda). Sem RAG dá conselhos genéricos (balde, afastar móveis) e cobre 0%.
- *Chave quebrada (4):* com RAG aparecem as regras da base (não usar cola/óleo, pinça só se a ponta estiver visível). Sem RAG, 0%.
- *Rachadura (5):* com RAG sai o procedimento de monitoramento da base (marcar a lápis com data, foto com régua, observar portas emperrando).
- *Gás (2):* o modelo já sabe o protocolo de segurança sem RAG (100% nos dois). É o caso em que a recuperação pouco acrescenta.

Limitação: a métrica é por palavra-chave e penaliza paráfrases (ex.: "objetos pontiagudos" no lugar de "não force", na pergunta 4 sem RAG). Ela serve para comparar as duas configurações, não como nota absoluta.

**Latência: o provedor é o gargalo e varia muito.** Na data da medição o Gemini estava com alta demanda (respostas 503 "high demand" e timeouts), e a latência p50 ficou perto de 10 s, com cauda acima de 30 s (incluindo retries). A parte local da cadeia (RAG no ChromaDB + tool no `ms-prestadores`) custa só algumas centenas de ms. Em chamadas avulsas no mesmo dia, o mesmo modelo respondeu entre 1,5 s e 17 s. Por isso a triagem trata o LLM como dependência falível:
- orçamento total de **5 s** para o LLM em produção (somando RAG, tool e o cancelamento da chamada, a resposta volta em até ~7,5 s) (abaixo do timeout do BFF, 9 s, e do Kong, 10 s); estourou → **fallback por regras + trechos do RAG**, a resposta chega com `modo: "fallback"` e um aviso;
- **retry com backoff** só em erros transitórios (503, timeout); chave inválida não é repetida;
- **circuit breaker**: 3 falhas seguidas → 30 s sem chamar o provedor (respostas em ~200 ms nesse período);
- **cache Redis** por chave: resposta repetida em **< 1 ms** e custo zero (medido: 19 s na 1ª chamada, 0,6 ms na 2ª).

Na medição, 9 das 10 chamadas passaram de 7 s (e portanto também do orçamento atual de 5 s): com o provedor naquele estado, a maioria das triagens em produção sairia do fallback. A resposta continua útil (categoria, urgência e orientações da base acertaram 5/5 no fallback), mas a explicação personalizada do LLM se perde. Alternativas se isso persistir: trocar o modelo por variável (`LLM_MODEL`), usar o OpenAI (`OPENAI_API_KEY`) ou contratar um nível de prioridade do provedor.

**Custo: cerca de US$ 0,0007 por triagem com RAG** (~830 tokens de entrada e ~195 de saída). O RAG aumenta a entrada em ~500 tokens, mas a saída custa 8× mais por token, então o acréscimo fica em ~33% (US$ 0,00074 contra US$ 0,00055). Projeção: ~US$ 74/mês para 100 mil triagens e ~US$ 740/mês para 1 milhão (~US$ 590 com 20% de acerto no cache). O custo é linear no volume; as alavancas são o cache, limitar o tamanho da resposta e enviar menos trechos (`RAG_TOP_K`).

---

## Relatório gerado pelo script

- Data: 2026-11-19 17:38
- Provedor/modelo: `gemini` / `gemini-3.5-flash-lite`
- Preço usado: US$ 0.3/1M tokens de entrada, US$ 2.5/1M de saída (estimativa)
- Cache desligado; latência = cadeia completa (RAG + LLM + tool de prestadores).
- Timeout do LLM nesta avaliação: 30 s por tentativa, com retry em 503/timeout (produção: orçamento total de 7 s; acima disso a triagem cai no fallback).

| # | RAG | Modo | Categoria | Urgência | Cobertura segurança | Fontes | Prestadores | Latência (ms) | Tokens (in/out) | Custo (US$) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | sim | llm | ✅ eletricista | ✅ ALTA | 100% | 4 | 2 | 32212 | 919/234 | 0.000861 |
| 1 | não | llm | ✅ eletricista | ✅ ALTA | 75% | 0 | 2 | 9043 | 340/143 | 0.000460 |
| 2 | sim | llm | ✅ tecnico-gas | ✅ EMERGENCIA | 100% | 4 | 2 | 6529 | 855/239 | 0.000854 |
| 2 | não | llm | ✅ tecnico-gas | ✅ EMERGENCIA | 100% | 0 | 2 | 10180 | 330/198 | 0.000594 |
| 3 | sim | llm | ✅ encanador | ✅ MEDIA | 50% | 4 | 2 | 10016 | 771/180 | 0.000681 |
| 3 | não | llm | ✅ encanador | ✅ MEDIA | 0% | 0 | 2 | 13700 | 339/180 | 0.000552 |
| 4 | sim | llm | ✅ chaveiro | ✅ ALTA | 75% | 4 | 1 | 7656 | 756/203 | 0.000734 |
| 4 | não | llm | ✅ chaveiro | ✅ ALTA | 0% | 0 | 1 | 9062 | 340/218 | 0.000647 |
| 5 | sim | llm | ✅ pedreiro | ✅ ALTA | 50% | 4 | 1 | 23105 | 866/121 | 0.000562 |
| 5 | não | llm | ✅ pedreiro | ✅ ALTA | 25% | 0 | 1 | 9740 | 337/164 | 0.000511 |

### Resumo

| Configuração | Categoria correta | Urgência aceitável | Cobertura média | Latência média (ms) | Latência máx (ms) | Custo total (US$) | Custo médio/consulta (US$) |
|---|---|---|---|---|---|---|---|
| Com RAG | 5/5 | 5/5 | 75% | 15904 | 32212 | 0.003692 | 0.000738 |
| Sem RAG | 5/5 | 5/5 | 40% | 10345 | 13700 | 0.002764 | 0.000553 |

### Latência e custo em escala

- Respostas do LLM: 10/10. Latência p50 = 9740 ms, p95 = 32212 ms, máx = 32212 ms.
- 9/10 chamadas passaram do orçamento de produção (7 s): em produção essas cairiam no fallback por regras (a resposta chega, só que sem o LLM).

| Configuração | Tokens médios (in/out) | Custo/consulta (US$) | 1.000/mês | 100.000/mês | 1.000.000/mês | 1.000.000/mês com 20% de cache |
|---|---|---|---|---|---|---|
| Com RAG | 833/195 | 0.000738 | US$ 0.74 | US$ 73.84 | US$ 738.40 | US$ 590.72 |
| Sem RAG | 337/181 | 0.000553 | US$ 0.55 | US$ 55.28 | US$ 552.80 | US$ 442.24 |

Leitura: o custo cresce linearmente com o volume; o cache por chave (`triagem:v1:*`, 1 h) só economiza em descrições repetidas, por isso a taxa de acerto é uma hipótese (`--taxa-cache`). O RAG aumenta os tokens de entrada (contexto), mas a saída domina o preço.

### Orientações geradas

**1 · com RAG (llm)**: Desligue o disjuntor do chuveiro antes de abrir o aparelho. / Nunca mexa em fiação com as mãos ou os pés molhados e não use escada metálica. / Se a fiação estiver escurecida, derretida ou com cheiro de queimado, não religue o disjuntor. / Não troque o disjuntor por um de amperagem maior para ele parar de desarmar.

**1 · sem RAG (llm)**: Desligue o disjuntor correspondente ao chuveiro imediatamente para evitar curtos-circuitos. / Não tente manusear a fiação ou o aparelho com as mãos molhadas ou descalço.

**2 · com RAG (llm)**: Ligue imediatamente para o Corpo de Bombeiros (193) ou para a distribuidora de gás e garanta a segurança das pessoas e animais. / Não acenda fósforos, isqueiros ou velas e não fume. / Não acione interruptores de luz, campainha ou aparelhos elétricos para evitar faíscas. / Feche o registro do gás, seja o do botijão ou o registro geral do gás encanado. / Abra portas e janelas para ventilar o ambiente e saia do imóvel.

**2 · sem RAG (llm)**: Ligue imediatamente para os Bombeiros (193) ou para a companhia de gás e evacue o local. / Não acenda luzes, fósforos, isqueiros e não utilize nenhum interruptor ou aparelho elétrico para evitar faíscas. / Feche o registro geral de gás se for seguro e fácil de fazer. / Abra portas e janelas para ventilar o ambiente.

**3 · com RAG (llm)**: Desligue a energia das luminárias próximas caso a mancha esteja estufada ou pingando. / Não toque no forro do teto para evitar acidentes com a estrutura ou umidade. / Evite usar o chuveiro por longos períodos até a verificação do problema.

**3 · sem RAG (llm)**: Evite usar o chuveiro ou a área superior correspondente até a verificação do problema. / Coloque um balde ou recipiente para recolher a água que está pingando e proteger o piso. / Afaste móveis, tapetes e objetos que possam ser danificados pela umidade.

**4 · com RAG (llm)**: Não force a fechadura nem tente girar o pedaço da chave com objetos metálicos para evitar empurrar o fragmento para dentro ou danificar o cilindro. / Não coloque cola, óleo de cozinha ou palito na fechadura. / Se uma ponta do fragmento estiver visível, você pode tentar puxá-la com uma pinça fina, sem girar.

**4 · sem RAG (llm)**: Mantenha a calma e permaneça em um local seguro do lado de fora da residência. / Evite inserir objetos pontiagudos ou arames na fechadura para não empurrar o pedaço da chave ainda mais para o fundo ou danificar o miolo. / Caso esteja em horário noturno ou em área sem iluminação adequada, procure um abrigo seguro nas proximidades enquanto aguarda o prestador.

**5 · com RAG (llm)**: Marque as pontas da rachadura a lápis com a data e fotografie com uma régua ao lado para acompanhar o crescimento. / Evite ficar próximo à parede afetada e verifique se portas e janelas estão emperrando.

**5 · sem RAG (llm)**: Evite permanecer no cômodo afetado até a avaliação de um profissional. / Afaste móveis e objetos de valor que estejam próximos à parede danificada. / Monitore o crescimento da trinca utilizando uma marcação a lápis ou fita crepe com data.

