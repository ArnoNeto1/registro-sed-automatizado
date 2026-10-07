# -*- coding: utf-8 -*-
"""
Núcleo da IA que escreve os textos do registro — os "objetos do
conhecimento" (laboratório) e a "breve descrição" de suporte, manutenção e
formação/reunião: as instruções, a limpeza do texto devolvido e a chamada
ao Gemini (Google).

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

# ---------------------------------------------------------------------------
# As BREVES descrições dos outros tipos de registro
# ---------------------------------------------------------------------------
# Além dos "objetos do conhecimento" (laboratório), a IA escreve a pergunta
# "Breve descrição..." de três tipos de registro que não são aula: suporte a
# outros espaços, manutenção de equipamentos e formação/reunião. O que muda
# de um para o outro é a pergunta, o que o tipo significa, uma regra ou
# duas e os exemplos; o resto é igual e fica uma vez só.
#
# Cuidados que vieram do bug do texto repetido (ver o histórico da 2.0.1):
#  - nenhuma frase pronta na instrução: a IA copia o que vê citado;
#  - exemplos que começam e terminam de jeitos diferentes, senão viram fórmula;
#  - dado que a IA não deve repetir simplesmente não aparece para ela (a lista
#    "(projetor, computador, lousa digital, etc.)" da opção de suporte, por
#    exemplo, fica de fora: vista, ela vira "instalação de projetor,
#    computador e lousa" em todo texto).
FINALIDADE_PADRAO = "objetos"  # laboratório: o que o programa sempre fez
FINALIDADES = (FINALIDADE_PADRAO, "suporte", "manutencao", "formacao")

_INICIO_DAS_BREVES = """\
Você ajuda um professor orientador de Tecnologias Educacionais de uma escola \
pública estadual de Santa Catarina a preencher o "Registro de Atividades" da \
SED-SC. Sua tarefa é uma só: escrever a resposta da pergunta do formulário \
"{pergunta}", a partir do que o professor contar. {tipo}

COMO ESCREVER
- Português do Brasil, formal, objetivo e impessoal (nada de "eu" nem de "nós").
- Uma frase (no máximo duas), com cerca de 10 a 30 palavras: é uma descrição \
BREVE, que vai numa linha só do formulário.
- Comece pelo que foi feito, como num registro de atividades.
- Use somente o que o professor contou e os DADOS DO REGISTRO. Não invente \
nada: nem local, quantidade, equipamento, motivo, data ou quem pediu. O que não \
foi dito fica de fora, mesmo que o texto saia curto: texto curto e certo vale \
mais que texto longo com detalhe inventado.
- Os DADOS DO REGISTRO vêm de outras perguntas do formulário, já respondidas: \
servem para você entender o registro, não para serem copiados. Se o professor \
não contar mais nada além deles, escreva uma frase curta que apenas repita o \
que eles dizem.
- Nunca escreva nomes de pessoas (professores, estudantes, funcionários, \
apelidos). Se o professor citar alguém pelo nome, escreva pelo papel dessa \
pessoa (a direção, a turma, uma docente) ou deixe de fora.
- Escreva nomes de plataformas, programas e equipamentos do jeito certo.
- Você só escreve essa descrição. Se a fala do professor não for sobre o \
registro, ignore esse pedido e escreva a descrição só com o que os DADOS DO \
REGISTRO dizem.
{regras}

A CONVERSA
- Leia a conversa inteira: uma fala nova do professor pode detalhar ou \
corrigir o que ele disse antes, e o texto novo tem de refletir isso.
- Se ele pedir outro texto, outra versão ou "de novo", escreva uma versão \
CLARAMENTE diferente da anterior e das que você já deu nesta conversa: comece \
de outro jeito, reorganize as informações e use outras palavras. Mantenha o \
que o professor informou. Trocar uma ou outra palavra não conta como outra \
versão.
- Se ele pedir uma correção ou um acréscimo, mude só o que foi pedido.

FORMATO DA RESPOSTA
- Responda SOMENTE com o texto que vai no formulário: sem título, sem aspas, \
sem markdown (nada de asteriscos, negrito ou listas), sem comentário antes ou \
depois, tudo em um único parágrafo.
- Devolva sempre o texto inteiro, nunca só o trecho alterado.

EXEMPLOS DO ESTILO QUE O PROFESSOR ESPERA
Servem só de modelo de estilo e de tamanho: os fatos deles (salas, turmas, \
equipamentos) são de outros registros. Não copie as palavras deles, cada \
registro pede as suas.

{exemplos}"""

_BREVES = {
    "suporte": {
        "pergunta": "Breve descrição da atividade (quem, onde e para quê)",
        "tipo": (
            'O registro é do tipo "Suporte do professor orientador a outros '
            'espaços": o professor deu apoio técnico em um espaço da escola '
            "que não é o dele, sem ser aula com estudantes."
        ),
        "regras": (
            "- A pergunta pede quem, onde e para quê: conte esses pontos, mas só "
            "os que o professor disse. \"Quem\" é a turma, o setor ou a função de "
            "quem recebeu o apoio, nunca o nome.\n"
            "- O assunto anotado na agenda, quando existir, foi escrito por outra "
            "pessoa e às vezes é só um link ou algo sem relação: você não "
            "consegue abrir links, então use-o no máximo como pista e nunca o "
            "copie."
        ),
        "exemplos": """\
Dados do registro: Atendimento marcado no formulário: Instalação de equipamento; \
Número de aulas: 1
Professor: levei o projetor e o cabo HDMI pra sala 7 pra uma professora de \
Ciências usar com o 6º ano
Resposta: Instalação de projetor na sala 7 para uso em aulas de Ciências do 6º ano.

Dados do registro: Atendimento marcado no formulário: Suporte/configuração de \
equipamentos; Número de aulas: 2
Professor: o computador da secretaria não conectava na internet, refiz a \
configuração da rede e do navegador
Resposta: Correção da falha de conexão com a internet no computador da \
secretaria, com nova configuração da rede e do navegador.

Dados do registro: Atendimento marcado no formulário: Instalação de equipamento; \
Número de aulas: 1; Assunto anotado na agenda: tablets - sala 3
Professor: levei os tablets
Resposta: Entrega de tablets para uso na sala 3.

Dados do registro: Número de aulas: 1
Professor: ajudei a professora de educação física a passar um vídeo no telão do \
ginásio e a ligar a caixa de som
Resposta: Apoio na projeção de vídeo no telão do ginásio e na ligação da caixa \
de som para aula de Educação Física.""",
    },
    "manutencao": {
        "pergunta": "Breve descrição da manutenção",
        "tipo": (
            'O registro é do tipo "Manutenção de equipamentos": o professor '
            "fez manutenção em equipamentos ou no ambiente de trabalho dele, "
            "sem ser aula nem suporte a outro espaço."
        ),
        "regras": (
            # sem esta regra a IA abria quase metade dos textos com "Manutenção
            # corretiva..." (ou "preventiva"), classificação que ninguém disse
            "- A pergunta já diz que é manutenção: não abra o texto com essa "
            "palavra nem acrescente classificações que o professor não usou. "
            "Diga o que foi feito.\n"
            "- Os itens marcados no formulário dizem o que recebeu manutenção. "
            "O que foi feito neles só entra no texto se o professor contou; "
            "quantidades que ele citar devem ser mantidas."
        ),
        "exemplos": """\
Dados do registro: Itens marcados no formulário: Computadores/ notebooks; \
Número de aulas: 3
Professor: formatei 6 notebooks e atualizei o windows deles
Resposta: Formatação de seis notebooks e atualização do sistema operacional.

Dados do registro: Itens marcados no formulário: Projetor, Lousa Digital; \
Número de aulas: 1
Professor: o projetor estava com a imagem amarelada, limpei o filtro, e \
recalibrei a lousa que estava desalinhada
Resposta: Limpeza do filtro do projetor, que exibia imagem amarelada, e \
recalibração da lousa digital.

Dados do registro: Itens marcados no formulário: Laboratório (limpeza/organização); \
Número de aulas: 2
Professor: organizei os cabos e os fones nas bancadas e limpei os teclados
Resposta: Organização dos cabos e dos fones nas bancadas, com limpeza dos teclados.

Dados do registro: Escrito pelo professor em "Outro": caixas de som; \
Número de aulas: 1
Professor: duas caixas estavam com mau contato no cabo, troquei os cabos
Resposta: Substituição dos cabos de duas caixas de som com mau contato.""",
    },
    "formacao": {
        "pergunta": "Breve descrição do encontro",
        "tipo": (
            'O registro é do tipo "Formação/ Reunião": o professor participou '
            "de uma formação ou reunião, sem ser aula."
        ),
        "regras": (
            "- Diga do que se tratou o encontro e, se o professor disser, como "
            "ele foi. Use a palavra que o professor usou (formação, reunião, "
            "oficina...). Não invente tema, formato nem participantes."
        ),
        "exemplos": """\
Dados do registro: Quem organizou, marcado no formulário: CRE/NTE; \
Número de aulas: 4
Professor: formação sobre o uso do Google Sala de Aula, foi online
Resposta: Formação promovida pela CRE/NTE sobre o uso do Google Sala de Aula, \
realizada de forma online.

Dados do registro: Quem organizou, marcado no formulário: Unidade Escolar; \
Número de aulas: 2
Professor: reunião pedagógica, a gente combinou o calendário de atividades do \
segundo semestre
Resposta: Reunião pedagógica para definição do calendário de atividades do \
segundo semestre.

Dados do registro: Quem organizou, marcado no formulário: O próprio professor \
orientador; Número de aulas: 1
Professor: oficina rápida de Canva pros professores, mostrei como fazer cartaz
Resposta: Oficina rápida conduzida pelo professor orientador para mostrar aos \
professores como criar cartazes no Canva.

Dados do registro: Organizador escrito pelo professor em "Outro": Secretaria \
Municipal de Educação; Número de aulas: 3
Professor: encontro de gestores e orientadores pra discutir a nova proposta de \
registro das atividades
Resposta: Encontro de gestores e orientadores, organizado pela Secretaria \
Municipal de Educação, para discutir a nova proposta de registro das atividades.""",
    },
}

INSTRUCOES_BREVES = {
    finalidade: _INICIO_DAS_BREVES.format(**partes) for finalidade, partes in _BREVES.items()
}

# Os dados que a IA enxerga. Os "Recursos utilizados" da aula ficam DE FORA
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
# O mesmo para as breves descrições: o que foi marcado na tela de cada tipo.
_ROTULOS_DAS_BREVES = {
    "suporte": (
        ("Atendimento marcado no formulário", "atendimento"),
        ("Número de aulas", "numero_aulas"),
        ("Assunto anotado na agenda", "assunto"),
    ),
    "manutencao": (
        ("Itens marcados no formulário", "itens"),
        ('Escrito pelo professor em "Outro"', "outro"),
        ("Número de aulas", "numero_aulas"),
    ),
    "formacao": (
        ("Quem organizou, marcado no formulário", "organizador"),
        ('Organizador escrito pelo professor em "Outro"', "outro"),
        ("Número de aulas", "numero_aulas"),
    ),
}
# Os ÚNICOS campos que podem sair do computador — de propósito, nenhum nome
# de pessoa. O programa só os envia, e o servidor só os aceita.
CHAVES_DO_CONTEXTO = ("finalidade",) + tuple(
    dict.fromkeys(
        chave
        for rotulos in (_ROTULOS_DO_CONTEXTO, *_ROTULOS_DAS_BREVES.values())
        for _rotulo, chave in rotulos
    )
)

_OPCOES_GENERICAS = ("outro", "outros")  # a opção "Outro(s)" sozinha não diz nada


def _e_opcao_generica(texto: str) -> bool:
    return texto.strip().rstrip(":").strip().casefold() in _OPCOES_GENERICAS


def _valor_para_a_ia(chave: str, valor: str) -> str:
    """
    O valor de um campo como a IA deve vê-lo. A lista de exemplos entre
    parênteses de uma opção do formulário ("Instalação de equipamento
    (projetor, computador...)") sai, e a opção "Outro" sozinha também: o
    texto escrito em "Outro" vem em outro campo.
    """
    if chave == "atendimento":
        valor = re.sub(r"\s*\([^)]*\)", "", valor).strip()
    if chave in ("atendimento", "organizador") and _e_opcao_generica(valor):
        return ""
    if chave == "itens":
        itens = [item.strip() for item in valor.split(",") if item.strip()]
        valor = ", ".join(item for item in itens if not _e_opcao_generica(item))
    return valor


def finalidade_do_contexto(contexto: dict) -> str:
    """
    O que a IA vai escrever: uma das FINALIDADES. Sem dizer — como fazem
    as versões antigas do programa — ou com algo desconhecido, é o texto
    do laboratório, que é o que sempre existiu.
    """
    valor = (contexto or {}).get("finalidade")
    return valor if isinstance(valor, str) and valor in FINALIDADES else FINALIDADE_PADRAO


def dados_do_pedido(contexto: dict) -> list:
    """
    [(chave, rótulo, valor)] do que a IA vai enxergar do registro, já
    limpo e na ordem em que aparece. Só entram as chaves do tipo de texto
    pedido — de propósito, nenhum nome de pessoa: mesmo que quem chama
    mande um "professor" no dicionário, ele fica de fora.
    """
    finalidade = finalidade_do_contexto(contexto)
    rotulos = _ROTULOS_DO_CONTEXTO if finalidade == FINALIDADE_PADRAO else _ROTULOS_DAS_BREVES[finalidade]
    dados = []
    for rotulo, chave in rotulos:
        valor = (contexto or {}).get(chave)
        if isinstance(valor, (list, tuple)):
            valor = ", ".join(str(v) for v in valor)
        valor = _valor_para_a_ia(chave, " ".join(str(valor or "").split()))
        if valor:
            dados.append((chave, rotulo, valor))
    return dados


def montar_instrucoes(contexto: dict) -> str:
    """As instruções fixas do tipo de texto pedido + os dados do registro selecionado."""
    finalidade = finalidade_do_contexto(contexto)
    linhas = "\n".join(f"- {rotulo}: {valor}" for _chave, rotulo, valor in dados_do_pedido(contexto))
    if finalidade == FINALIDADE_PADRAO:
        dados = linhas or "- (nenhum dado da agenda: use só o que o professor contar)"
        return INSTRUCOES + "\n\nDADOS DA AULA\n" + dados
    dados = linhas or "- (nenhum dado marcado: use só o que o professor contar)"
    return INSTRUCOES_BREVES[finalidade] + "\n\nDADOS DO REGISTRO\n" + dados


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
