# -*- coding: utf-8 -*-
"""
Núcleo da IA que escreve os "objetos do conhecimento": a instrução, a
limpeza do texto devolvido e a chamada ao Gemini (Google).

NÃO TEM TELA (nada de tkinter) DE PROPÓSITO: este mesmo arquivo roda em
dois lugares — dentro do programa (`assistente_ia.py`, quando o professor
usa a própria chave) e no servidor intermediário (`servidor-ia/`, que
guarda a chave da escola). Como o servidor é publicado sozinho, ele leva
uma CÓPIA EXATA deste arquivo em `servidor-ia/api/_ia_gemini.py`; um teste
(`tests/test_servidor_ia.py`) falha se as duas ficarem diferentes. Mexeu
aqui? Copie o arquivo por cima da cópia do servidor.

Só usa a biblioteca padrão (urllib): nada a mais para empacotar no .exe
nem para instalar no servidor.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

URL_API = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
URL_CHAVES = "https://aistudio.google.com/apikey"

# O modelo estável mais barato e rápido do Gemini — de sobra para um
# parágrafo de duas frases. Dá para trocar sem mexer no código, com a
# linha MODELO_IA=... no .env (por exemplo, para um modelo maior).
MODELO_PADRAO = "gemini-3.5-flash-lite"

TEMPO_LIMITE = 60  # segundos


# ---------------------------------------------------------------------------
# O pedido para a IA
# ---------------------------------------------------------------------------
INSTRUCOES = """\
Você ajuda um professor orientador de Tecnologias Educacionais de uma escola \
pública estadual de Santa Catarina a preencher o "Registro de Atividades" da \
SED-SC. Sua tarefa é uma só: escrever a resposta da pergunta do formulário \
"Quais os objetos do conhecimento (conteúdos temáticos) abordados?", a partir \
do que o professor contar sobre a aula.

COMO ESCREVER
- Português do Brasil, formal, objetivo, em terceira pessoa.
- Um parágrafo de 2 frases (no máximo 3), com cerca de 25 a 60 palavras.
- Siga o modelo: primeiro os conteúdos ("Foram abordados conteúdos de..." ou \
"Foram trabalhados..."); depois as habilidades ("Também foram desenvolvidas \
habilidades de...").
- A disciplina da aula é a dos DADOS DA AULA. Não deduza a disciplina pelo \
conteúdo: calcular média numa aula de Arte continua sendo uma aula de Arte. \
Quando o conteúdo parecer de outra área, deixe claro de quem foi a iniciativa \
(por exemplo: "Foram trabalhados pelo professor de Arte conteúdos \
relacionados ao cálculo da média...").
- Use o que o professor contou e os dados da aula. Muitas vezes a descrição \
é curta ou genérica, copiada da agenda (por exemplo, "atividade de geografia - \
mercantilismo"): nesse caso, desenvolva os objetos do conhecimento que fazem \
parte daquele tema no currículo escolar (no exemplo: metalismo, balança \
comercial favorável, protecionismo), sem afirmar sobre a aula nada além do \
que foi contado. Pode nomear as habilidades que decorrem diretamente do que \
foi feito (letramento digital, pensamento computacional, pesquisa...), mas \
não invente atividades, ferramentas, quantidades, nomes de pessoas nem \
códigos da BNCC.
- Os recursos utilizados (quando vierem nos dados da aula) podem aparecer no \
texto, do jeito natural ("utilizando os computadores do laboratório").
- Se o que foi contado (inclusive o assunto da agenda) citar a metodologia ou \
a estratégia da aula (por exemplo: gamificação, rotação por estações, \
aprendizagem baseada em projetos, aula expositiva dialogada), mencione-a numa \
frase curta, do jeito que foi dito. Não deduza nem invente a metodologia: se \
ninguém falou dela, não escreva nada sobre isso.
- O assunto anotado na agenda às vezes é só um link: você não consegue \
abri-lo, então use-o no máximo como pista e nunca copie o link no texto.
- Escreva nomes de plataformas do jeito certo (Google Sala de Aula, \
Estudante Online, MakeCode, Scratch, Canva...).
- Se o professor citar nomes de estudantes, não os repita no texto: fale em \
"os estudantes" ou "a turma".

FORMATO DA RESPOSTA
- Responda SOMENTE com o texto que vai no formulário: sem título, sem \
aspas, sem markdown (nada de asteriscos, negrito ou listas), sem comentário \
antes ou depois.
- Se o professor pedir uma mudança, devolva o texto inteiro já corrigido, no \
mesmo formato.

EXEMPLOS DO ESTILO QUE O PROFESSOR ESPERA

Dados da aula: Disciplina: Arte
Professor: Cálculo da média, acesso ao sistema Estudante Online e à \
plataforma Google Sala de Aula. O professor de artes projetou no datashow e \
mostrou aos alunos.
Resposta: Foram trabalhados pelo professor de Arte conteúdos relacionados ao \
cálculo da média e à utilização de ferramentas digitais para o acompanhamento \
das atividades escolares. Também foram apresentados aos alunos o Estudante \
Online e o Google Sala de Aula, utilizando o datashow como recurso tecnológico.

Dados da aula: Disciplina: Geografia; Recursos utilizados: \
Computadores/notebooks (pesquisa) no laboratório
Professor: atividade de geografia - mercantilismo
Resposta: Foram abordados conteúdos de Geografia relacionados ao \
mercantilismo, como o metalismo, a balança comercial favorável e o \
protecionismo, e sua influência no comércio entre metrópoles e colônias. \
Também foram desenvolvidas habilidades de pesquisa e análise de informações \
utilizando os computadores do laboratório.

Dados da aula: Clube de robótica
Professor: Os alunos do clube de robótica aprenderam os primeiros passos na \
configuração e montagem da lagarta pelo site do MakeCode.
Resposta: Foram abordados conteúdos de robótica educacional, com foco na \
configuração e montagem inicial do robô lagarta. Também foram desenvolvidas \
habilidades de programação e prototipagem utilizando o MakeCode."""

_ROTULOS_DO_CONTEXTO = (
    ("Disciplina", "disciplina"),
    ("Turma", "turma"),
    ("Etapa", "etapa"),
    ("Número de aulas", "numero_aulas"),
    ("Recursos utilizados", "recursos"),
    ("Assunto anotado na agenda", "assunto"),
)
# Os ÚNICOS campos da aula que podem sair do computador — de propósito,
# nenhum nome de pessoa. O programa só os envia, e o servidor só os aceita.
CHAVES_DO_CONTEXTO = tuple(chave for _rotulo, chave in _ROTULOS_DO_CONTEXTO)


def montar_instrucoes(contexto: dict) -> str:
    """
    As instruções fixas + os dados da aula selecionada. Só entram as
    chaves de _ROTULOS_DO_CONTEXTO — de propósito, nenhum nome de pessoa:
    mesmo que quem chama mande um "professor" no dicionário, ele fica de
    fora do que sai do computador.
    """
    linhas = []
    for rotulo, chave in _ROTULOS_DO_CONTEXTO:
        valor = (contexto or {}).get(chave)
        if isinstance(valor, (list, tuple)):
            valor = ", ".join(str(v) for v in valor)
        valor = " ".join(str(valor or "").split())
        if valor:
            linhas.append(f"- {rotulo}: {valor}")
    dados = "\n".join(linhas) or "- (nenhum dado da agenda: use só o que o professor contar)"
    return INSTRUCOES + "\n\nDADOS DA AULA\n" + dados


def limpar_texto(texto: str) -> str:
    """
    Deixa a resposta pronta para ir ao formulário mesmo se a IA escapar
    do formato pedido: sem markdown, sem aspas em volta, sem uma linha de
    apresentação ("Aqui está o texto:") e num parágrafo só. Quebra de
    linha é o que mais importa aqui — numa caixa de texto de uma linha, o
    navegador simplesmente apaga as quebras, e duas frases viravam
    "...educacionais.Também foram...", grudadas.
    """
    linhas = [l.strip() for l in (texto or "").replace("**", "").replace("__", "").splitlines()]
    linhas = [l for l in linhas if l]
    if len(linhas) > 1 and linhas[0].endswith(":"):
        linhas = linhas[1:]
    t = " ".join(" ".join(linhas).split())
    pares = {'"': '"', "“": "”", "'": "'"}
    if len(t) >= 2 and t[0] in pares and t[-1] == pares[t[0]]:
        t = t[1:-1].strip()
    return t


class ErroDaIA(RuntimeError):
    """
    Erro já explicado em português, pronto para aparecer na janela.

    `tipo` diz o que aconteceu: "chave", "permissao", "modelo", "limite",
    "indisponivel", "recusado", "rede", "resposta", "bloqueado" ou "vazio".
    O servidor intermediário usa isso para escrever a PRÓPRIA mensagem: o
    texto daqui fala em "trocar a chave", e quem usa o serviço da escola
    não tem chave nenhuma.
    """

    def __init__(self, mensagem: str, tipo: str = "outro"):
        super().__init__(mensagem)
        self.tipo = tipo


def _explicar_erro_http(erro: urllib.error.HTTPError) -> tuple:
    """(tipo, mensagem em português para quem usa a PRÓPRIA chave)."""
    try:
        corpo = json.loads(erro.read().decode("utf-8"))
        mensagem = str((corpo.get("error") or {}).get("message") or "")
    except Exception:
        mensagem = ""
    # O Gemini responde 400 (e não 401) para uma chave inválida.
    if erro.code == 401 or (erro.code == 400 and "api key" in mensagem.lower()):
        return "chave", (
            "A chave da API não foi aceita. Confira se ela foi copiada "
            "inteira e use \"Trocar chave da API\" para colar de novo."
        )
    if erro.code == 403:
        return "permissao", (
            "Esta chave não tem permissão para usar a API (pode ter sido "
            f"bloqueada ou restringida). Crie outra em {URL_CHAVES}."
        )
    if erro.code == 404:
        return "modelo", (
            "O modelo de IA configurado não foi encontrado — pode ter sido "
            "aposentado. Confira a linha MODELO_IA, se existir no .env."
        )
    if erro.code == 429:
        return "limite", (
            "Muitos pedidos seguidos, ou o limite do dia da chave gratuita "
            "acabou. Espere um pouco e tente de novo."
        )
    if erro.code >= 500:
        return "indisponivel", (
            "O serviço da IA está sobrecarregado ou fora do ar agora. "
            "Tente de novo em instantes."
        )
    return "recusado", f"O serviço da IA recusou o pedido (erro {erro.code}). {mensagem}".strip()


def pedir_texto(chave: str, contexto: dict, conversa: list, modelo: str = "") -> str:
    """
    Manda a conversa inteira (lista de {"role", "content"}, terminando
    numa fala do professor) e devolve o texto novo, já limpo.

    A conversa vai inteira a cada pedido porque a API não guarda nada
    entre um pedido e outro: é assim que "foi o professor de ARTES" faz
    sentido para ela — ela lê o texto anterior junto.
    """
    modelo = modelo or (os.environ.get("MODELO_IA") or "").strip() or MODELO_PADRAO
    corpo = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": montar_instrucoes(contexto)}]},
            # No Gemini a fala da IA tem o papel "model", não "assistant".
            "contents": [
                {
                    "role": "model" if fala["role"] == "assistant" else "user",
                    "parts": [{"text": fala["content"]}],
                }
                for fala in conversa
            ],
            # Folga de sobra para o parágrafo: se alguém trocar para um
            # modelo que "pensa" antes de responder, esse pensamento
            # também conta neste limite — com 500 a resposta vinha cortada.
            # Sem "temperature" de propósito: o padrão de cada modelo é o
            # recomendado, e MODELO_IA existe para trocar de modelo sem
            # mexer no código.
            "generationConfig": {"maxOutputTokens": 1500},
        }
    ).encode("utf-8")
    requisicao = urllib.request.Request(
        URL_API.format(modelo=urllib.parse.quote(modelo, safe="")),
        data=corpo,
        method="POST",
        headers={
            # A chave vai no cabeçalho, nunca no endereço: endereço aparece
            # em mensagens de erro e registros, cabeçalho não.
            "x-goog-api-key": chave,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        tipo, mensagem = _explicar_erro_http(erro)
        raise ErroDaIA(mensagem, tipo) from None
    except (urllib.error.URLError, OSError) as erro:
        raise ErroDaIA(
            "Não consegui falar com o serviço da IA — parece internet. "
            f"Confira a conexão e tente de novo.\n(detalhe técnico: {erro})",
            "rede",
        ) from None
    except ValueError:
        raise ErroDaIA(
            "O serviço da IA mandou uma resposta que não consegui ler. Tente de novo.",
            "resposta",
        ) from None

    candidatos = dados.get("candidates") or []
    if not candidatos:
        # Sem candidato = o filtro de segurança do serviço barrou o pedido.
        if (dados.get("promptFeedback") or {}).get("blockReason"):
            raise ErroDaIA(
                "O serviço da IA não aceitou escrever sobre isso (filtro de "
                "segurança). Reescreva a descrição da aula e tente de novo.",
                "bloqueado",
            )
        raise ErroDaIA("A IA respondeu em branco. Tente de novo.", "vazio")
    partes = (candidatos[0].get("content") or {}).get("parts") or []
    texto = "".join(
        parte.get("text", "")
        for parte in partes
        if isinstance(parte, dict) and not parte.get("thought")
    )
    texto = limpar_texto(texto)
    if not texto:
        raise ErroDaIA("A IA respondeu em branco. Tente de novo.", "vazio")
    return texto
