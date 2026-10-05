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
import re
import time
import urllib.error
import urllib.parse
import urllib.request

URL_API = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
URL_CHAVES = "https://aistudio.google.com/apikey"

# Os modelos, na ordem em que são tentados. O primeiro é o mais barato e
# rápido do Gemini, de sobra para um parágrafo de duas frases. No plano
# gratuito CADA MODELO TEM COTA PRÓPRIA (pedidos por minuto e por dia; o
# limite é do projeto, dividido com qualquer outra ferramenta que use as
# chaves dele): quando o primeiro atinge o limite ou está sobrecarregado,
# o seguinte atende, e as cotas se somam. Só entram modelos da mesma
# família, que se comportam parecido com a instrução abaixo.
# Dá para trocar sem mexer no código, com MODELO_IA=... (no .env do
# programa ou no painel do servidor): um nome só usa ESSE modelo e nenhum
# outro; vários, separados por vírgula, formam a lista.
MODELOS_PADRAO = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash")
MODELO_PADRAO = MODELOS_PADRAO[0]  # o principal

TEMPO_LIMITE = 60  # segundos de espera por UM modelo
# Teto de TODAS as tentativas juntas: o programa espera 60 s pelo servidor da
# escola, que precisa responder (nem que seja com o erro) antes disso. Um
# modelo sobrecarregado costuma levar de 30 a 50 s para falhar.
TEMPO_TOTAL = 55
# Com menos tempo que isso sobrando, nem vale começar outro modelo.
TEMPO_MINIMO_DE_UMA_TENTATIVA = 8


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
- Siga o modelo: primeiro os conteúdos ("Foram abordados conteúdos de...", \
"Foram trabalhados...", "Foram estudados..."); depois as habilidades \
("Também foram desenvolvidas habilidades de...").
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
que foi contado. Não invente atividades, ferramentas, quantidades, nomes de \
pessoas nem códigos da BNCC.
- Se a descrição for só o nome da disciplina ou algo muito amplo, escolha \
conteúdos característicos dela, na medida da etapa e da turma dos DADOS DA \
AULA (a idade muda o que faz sentido ensinar).
- As habilidades têm de ser as DESTE assunto: o que os estudantes aprendem a \
fazer, comparar, construir ou interpretar ao estudá-lo. Evite rótulos vagos \
que serviriam para qualquer aula; diga habilidades de quê, dentro do tema.
- Se o professor citar um recurso usado na aula, você pode mencioná-lo numa \
expressão curta. Não termine todo texto com um recurso por hábito.
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

A CONVERSA
- Leia a conversa inteira: uma fala nova do professor pode detalhar ou \
corrigir o que ele disse antes, e o texto novo tem de refletir isso.
- Se ele pedir outro texto, outra versão ou "de novo", escreva uma versão \
CLARAMENTE diferente da anterior e das que você já deu nesta conversa: abra \
de outro jeito, destaque outros aspectos do mesmo assunto e use outras \
palavras. Mantenha o que o professor informou. Trocar uma ou outra palavra \
não conta como outra versão.
- Se ele pedir uma correção ou um acréscimo, mude só o que foi pedido.

FORMATO DA RESPOSTA
- Responda SOMENTE com o texto que vai no formulário: sem título, sem \
aspas, sem markdown (nada de asteriscos, negrito ou listas), sem comentário \
antes ou depois.
- Devolva sempre o texto inteiro, nunca só o trecho alterado.

EXEMPLOS DO ESTILO QUE O PROFESSOR ESPERA
Servem só de modelo de estilo e de nível de detalhe: não copie as palavras \
deles, cada assunto pede as suas.

Dados da aula: Disciplina: Arte
Professor: Cálculo da média, acesso ao sistema Estudante Online e à \
plataforma Google Sala de Aula. O professor de artes projetou no datashow e \
mostrou aos alunos.
Resposta: Foram trabalhados pelo professor de Arte conteúdos relacionados ao \
cálculo da média e à utilização de ferramentas digitais para o acompanhamento \
das atividades escolares. Também foram apresentados aos alunos o Estudante \
Online e o Google Sala de Aula, com a projeção no datashow.

Dados da aula: Disciplina: Geografia
Professor: atividade de geografia - mercantilismo
Resposta: Foram abordados conteúdos de Geografia relacionados ao \
mercantilismo, como o metalismo, a balança comercial favorável e o \
protecionismo. Também foram desenvolvidas habilidades de interpretar como \
essas práticas moldaram o comércio entre metrópoles e colônias.

Dados da aula: Clube de robótica
Professor: Os alunos do clube de robótica aprenderam os primeiros passos na \
configuração e montagem da lagarta pelo site do MakeCode.
Resposta: Foram abordados conteúdos de robótica educacional, com foco na \
configuração e montagem inicial do robô lagarta. Também foram desenvolvidas \
habilidades de programação e prototipagem a partir do MakeCode.

Dados da aula: Disciplina: ETI - Educação Digital; Turma: Anos Finais - 7º ano
Professor: Os alunos fizeram cartazes no Canva sobre o meio ambiente.
Resposta: Foram abordados conteúdos de Educação Digital relacionados ao \
design gráfico no Canva, como a escolha de modelos, a combinação de cores e \
fontes e a organização de textos e imagens no cartaz. Também foram \
desenvolvidas habilidades de comunicar uma mensagem de forma visual e de \
adaptar a linguagem ao público do tema ambiental."""

# Os dados da aula que a IA enxerga. Os "Recursos utilizados" ficam DE FORA
# de propósito: já vão em outro campo do formulário e, vistos pela IA, faziam
# todo texto fechar com "utilizando os computadores do laboratório" (ou algo
# parecido). Pedir na instrução para não repetir não bastou, em seis
# redações testadas; sem o dado, a IA não tem o que repetir.
_ROTULOS_DO_CONTEXTO = (
    ("Disciplina", "disciplina"),
    ("Turma", "turma"),
    ("Etapa", "etapa"),
    ("Número de aulas", "numero_aulas"),
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


# ---------------------------------------------------------------------------
# Dado pessoal no texto: CPF, e-mail e telefone
# ---------------------------------------------------------------------------
# O escape acidental mais comum num texto livre. Nome de pessoa não dá para
# detectar com segurança — esse risco fica com o aviso da janela.
#
# CUIDADO COM FALSO POSITIVO: aula de História/Geografia fala de "1500-1822"
# e "séculos XV a XVIII". Por isso o telefone sem DDD entre parênteses só
# vale se for celular (9 + 8 dígitos), e 11 dígitos soltos só contam como
# CPF se os dígitos verificadores baterem.
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RE_CPF_FORMATADO = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
_RE_ONZE_DIGITOS = re.compile(r"(?<!\d)\d{11}(?!\d)")
_RE_TELEFONES = (
    # +55 47 99999-8888
    re.compile(r"\+55[\s().-]*\d{2}[\s().-]*9?[\s.-]?\d{4}[\s.-]?\d{4}(?!\d)"),
    # (47) 99999-8888, 47 99999-8888, 99999-8888
    re.compile(r"(?<!\d)(?:\(?\d{2}\)?[\s.-]?)?9[\s.-]?\d{4}[\s.-]?\d{4}(?!\d)"),
    # (47) 3333-4444
    re.compile(r"\(\d{2}\)\s?\d{4}[\s.-]?\d{4}(?!\d)"),
)


def _cpf_valido(digitos: str) -> bool:
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * (tamanho + 1 - i) for i, d in enumerate(digitos[:tamanho]))
        if (soma * 10) % 11 % 10 != int(digitos[tamanho]):
            return False
    return True


def achar_dado_pessoal(texto: str) -> str:
    """Qual dado pessoal o texto parece ter (e-mail, CPF ou telefone), ou vazio se nenhum."""
    texto = texto or ""
    if _RE_EMAIL.search(texto):
        return "e-mail"
    if _RE_CPF_FORMATADO.search(texto):
        return "CPF"
    if any(_cpf_valido(m.group()) for m in _RE_ONZE_DIGITOS.finditer(texto)):
        return "CPF"
    if any(padrao.search(texto) for padrao in _RE_TELEFONES):
        return "telefone"
    return ""


def aviso_de_dado_pessoal(tipo: str) -> str:
    return f"Parece haver um {tipo} no texto. Tire esse dado pessoal e tente de novo."


def textos_do_pedido(contexto: dict, conversa: list) -> list:
    """Tudo o que a PESSOA escreveu e que vai sair: campos da aula e falas dela."""
    textos = []
    for valor in (contexto or {}).values():
        itens = valor if isinstance(valor, (list, tuple)) else [valor]
        textos.extend(str(item) for item in itens)
    textos.extend(fala["content"] for fala in conversa if fala.get("role") == "user")
    return textos


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


def _pedir_a_um_modelo(
    chave: str, contexto: dict, conversa: list, modelo: str, tempo_limite: float = TEMPO_LIMITE
) -> str:
    """
    Um pedido a UM modelo: manda a conversa inteira (lista de {"role",
    "content"}, terminando numa fala do professor) e devolve o texto novo,
    já limpo.

    A conversa vai inteira a cada pedido porque a API não guarda nada
    entre um pedido e outro: é assim que "foi o professor de ARTES" faz
    sentido para ela — ela lê o texto anterior junto.
    """
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
        with urllib.request.urlopen(requisicao, timeout=tempo_limite) as resposta:
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


# Erros que são do MODELO (cota, sobrecarga ou aposentadoria), não do pedido
# nem da chave: só neles vale tentar o modelo seguinte. Chave recusada,
# filtro de segurança, internet fora do ar... outro modelo não resolve.
_TROCAM_DE_MODELO = ("limite", "indisponivel", "modelo")


def _modelos_a_tentar(modelo: str = "") -> list:
    """
    Os modelos, na ordem. Um modelo escolhido (o argumento ou MODELO_IA no
    ambiente) vale SOZINHO: quem escolheu não quer que outro responda no
    lugar dele. Vários, separados por vírgula, formam a lista. Sem escolha,
    vale MODELOS_PADRAO.
    """
    escolhido = modelo or (os.environ.get("MODELO_IA") or "")
    lista = [nome.strip() for nome in escolhido.split(",") if nome.strip()]
    return lista or list(MODELOS_PADRAO)


def pedir_texto(chave: str, contexto: dict, conversa: list, modelo: str = "", registrar=None) -> str:
    """
    Pede o texto ao primeiro modelo da lista; se ele estiver no limite de
    uso, sobrecarregado ou aposentado, passa ao seguinte, sem o professor
    perceber. Se todos falharem, o erro é o do primeiro (o modelo
    principal, que melhor descreve a situação). Todas as tentativas juntas
    respeitam TEMPO_TOTAL. `registrar`, se vier, recebe uma frase curta a
    cada falha: só o tipo do erro e o nome do modelo, nunca o conteúdo do
    pedido.
    """
    modelos = _modelos_a_tentar(modelo)
    inicio = time.monotonic()
    primeiro_erro = None
    for posicao, nome in enumerate(modelos):
        restante = TEMPO_TOTAL - (time.monotonic() - inicio)
        if posicao > 0 and restante < TEMPO_MINIMO_DE_UMA_TENTATIVA:
            if registrar:
                registrar("sem tempo para tentar outro modelo")
            break
        try:
            return _pedir_a_um_modelo(chave, contexto, conversa, nome, min(TEMPO_LIMITE, restante))
        except ErroDaIA as erro:
            if posicao == 0 and erro.tipo not in _TROCAM_DE_MODELO:
                raise  # chave recusada, filtro de segurança...: outro modelo não resolve
            primeiro_erro = primeiro_erro or erro
            if registrar:
                proximo = " — tentando o próximo" if posicao + 1 < len(modelos) else ""
                registrar(f"{erro.tipo} no modelo {nome}{proximo}")
    raise primeiro_erro
