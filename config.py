# -*- coding: utf-8 -*-
"""
Configuração fixa do preenchimento automático.
Ajuste os valores abaixo (ou use o .env — veja .env.example) conforme a
realidade da sua escola / orientação.
"""

import json
import os
import re
import unicodedata

from caminhos import caminho

# ---------------------------------------------------------------------------
# Dados do professor orientador (repetidos em todo preenchimento)
# ---------------------------------------------------------------------------
PLACEHOLDER = "!! PREENCHA"


# ---------------------------------------------------------------------------
# Configuração feita PELA TELA (configuracao.json)
# ---------------------------------------------------------------------------
# A partir da versão 1.3, quem instala o programa configura tudo numa tela
# na primeira execução, e os dados ficam aqui. O .env continua sendo lido
# para quem já o tinha: o arquivo novo apenas tem preferência quando
# existe. Assim ninguém que já estava trabalhando precisa refazer nada.
#
# A SENHA NÃO ESTÁ NESTE ARQUIVO, de propósito — ela é digitada na hora de
# entrar e vive só na memória. Ver configuracao.py.
def _da_tela() -> dict:
    try:
        with open(caminho("configuracao.json"), encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


CONFIG_DA_TELA = _da_tela()
_PROFESSORES_DA_TELA = [
    p for p in (CONFIG_DA_TELA.get("professores") or []) if (p.get("nome") or "").strip()
]


def _config(nome: str, padrao: str = "") -> str:
    """
    Lê uma configuração do .env tratando VAZIO como se não existisse.

    os.environ.get("X", padrao) só usa o padrão quando a chave NÃO existe.
    Se o .env tem a linha "ESCOLA=" (chave presente, valor vazio), ele
    devolve texto em branco e o padrão nunca entra. Foi exatamente isso
    que aconteceu na primeira instalação em outro computador: o professor
    copiou o modelo de .env, preencheu só CPF e senha, e o programa abriu
    com o nome e a escola EM BRANCO no alto da janela — sem nenhum aviso
    de que faltava configurar.
    """
    return (os.environ.get(nome) or "").strip() or padrao


ORIENTADOR_NOME = (
    _PROFESSORES_DA_TELA[0]["nome"]
    if _PROFESSORES_DA_TELA
    else _config("ORIENTADOR_NOME", PLACEHOLDER + " ORIENTADOR_NOME NO .env !!")
)

# "tecnologias" ou "maker"
ORIENTADOR_TIPO = (
    _PROFESSORES_DA_TELA[0].get("tipo", "tecnologias")
    if _PROFESSORES_DA_TELA
    else _config("ORIENTADOR_TIPO", "tecnologias")
)

REGIONAL = CONFIG_DA_TELA.get("regional") or _config("REGIONAL", "BLUMENAU")
ESCOLA = CONFIG_DA_TELA.get("escola") or _config("ESCOLA", PLACEHOLDER + " ESCOLA NO .env !!")


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


TODOS_TURNOS = ["Matutino", "Vespertino", "Noturno"]

# Faixas de horário de cada turno, usadas SÓ para adivinhar qual professor
# está de plantão quando o programa abre. As aulas em si não dependem
# disto: cada aula já vem da agenda sabendo o turno dela.
FAIXAS_TURNO = {
    "Matutino": (7, 12),
    "Vespertino": (12, 18),
    "Noturno": (18, 24),
}


def _turnos_do_config(chave: str) -> list:
    """
    Lê algo como "matutino,vespertino" e devolve ["Matutino", "Vespertino"].

    Em branco = todos os turnos, que é o certo para quem trabalha sozinho
    na escola e atende o dia inteiro.
    """
    bruto = _config(chave)
    if not bruto:
        return list(TODOS_TURNOS)
    escolhidos = []
    for pedaco in bruto.replace(";", ",").split(","):
        pedaco = _sem_acento(pedaco.strip().lower())
        for oficial in TODOS_TURNOS:
            if pedaco and pedaco == _sem_acento(oficial.lower()):
                escolhidos.append(oficial)
    return escolhidos or list(TODOS_TURNOS)


def turno_do_horario(momento) -> str:
    """Qual turno corresponde a este horário (para escolher o plantonista)."""
    hora = momento.hour
    for turno, (inicio, fim) in FAIXAS_TURNO.items():
        if inicio <= hora < fim:
            return turno
    return ""


def _ler_orientadores() -> list:
    """
    Lista de professores orientadores que usam ESTA instalação.

    Existem escolas com dois orientadores dividindo o mesmo computador —
    um no diurno, outro no noturno — e cada um tem CPF e senha próprios
    no site de agendamento. Por isso cada professor traz o seu login
    junto: ao trocar de professor na tela, o programa relê a agenda com
    as credenciais certas.

    Formato no .env (numerado, quantos professores quiser):

        ORIENTADOR_1_NOME=Fulano de Tal
        ORIENTADOR_1_CPF=00000000000
        ORIENTADOR_1_SENHA=...
        ORIENTADOR_2_NOME=Sicrana de Tal
        ORIENTADOR_2_CPF=11111111111
        ORIENTADOR_2_SENHA=...

    Quem tem um professor só continua usando o formato antigo
    (ORIENTADOR_NOME + AGENDA_CPF + AGENDA_SENHA) — ele segue valendo,
    e é o que acontece quando nenhum ORIENTADOR_1_* é encontrado.
    """
    # cadastrados pela tela: sem senha guardada (ela é pedida ao entrar)
    if _PROFESSORES_DA_TELA:
        return [
            {
                "nome": p.get("nome", ""),
                "cpf": p.get("cpf", ""),
                "senha": "",
                "tipo": p.get("tipo", "tecnologias"),
                "turnos": p.get("turnos") or list(TODOS_TURNOS),
            }
            for p in _PROFESSORES_DA_TELA
        ]

    lista = []
    numero = 1
    while True:
        nome = _config(f"ORIENTADOR_{numero}_NOME")
        if not nome:
            break
        lista.append(
            {
                "nome": nome,
                "cpf": _config(f"ORIENTADOR_{numero}_CPF"),
                "senha": _config(f"ORIENTADOR_{numero}_SENHA"),
                "tipo": _config(f"ORIENTADOR_{numero}_TIPO", "tecnologias"),
                "turnos": _turnos_do_config(f"ORIENTADOR_{numero}_TURNOS"),
            }
        )
        numero += 1

    if lista:
        return lista

    # formato de sempre: um professor só, atendendo todos os turnos
    return [
        {
            "nome": ORIENTADOR_NOME,
            "cpf": _config("AGENDA_CPF"),
            "senha": _config("AGENDA_SENHA"),
            "tipo": ORIENTADOR_TIPO,
            "turnos": list(TODOS_TURNOS),
        }
    ]


def orientador_de_plantao(momento):
    """
    Qual orientador está de plantão neste horário, ou None.

    Serve para escolas onde os dois orientadores nunca se cruzam — um no
    matutino/vespertino, outro só no noturno. Abrindo o programa à noite,
    já vem selecionado o professor da noite, sem ninguém precisar lembrar
    de trocar (que é justamente como um registro sairia no nome errado).
    """
    turno = turno_do_horario(momento)
    if not turno or len(ORIENTADORES) < 2:
        return None
    candidatos = [o for o in ORIENTADORES if turno in o.get("turnos", [])]
    # só decide sozinho quando a resposta é única; havendo empate, é mais
    # honesto deixar a escolha com a pessoa
    return candidatos[0] if len(candidatos) == 1 else None


ORIENTADORES = _ler_orientadores()

# Há senha guardada em arquivo? Só no formato antigo (.env) existe. Quando
# não há, o programa pede a senha na entrada — e é isso que permite dois
# professores dividirem o mesmo computador sem um usar a conta do outro.
SENHAS_SALVAS = any((o.get("senha") or "").strip() for o in ORIENTADORES)
CONFIGURADO_PELA_TELA = bool(_PROFESSORES_DA_TELA)


def configuracao_incompleta() -> list:
    """
    Lista os dados obrigatórios que ainda não foram configurados.

    Vazio = está tudo certo. Serve para o programa avisar logo ao abrir,
    em vez de deixar a pessoa descobrir só quando o formulário for
    enviado com o campo errado (ou com o nome de outra pessoa).
    """
    faltando = []
    # com vários orientadores, o nome vem da lista — não do ORIENTADOR_NOME
    nome_ok = ORIENTADORES[0]["nome"] if ORIENTADORES else ""
    for rotulo, valor in (
        ("Nome do orientador (ORIENTADOR_NOME)", nome_ok),
        ("Escola (ESCOLA)", ESCOLA),
        ("Regional (REGIONAL)", REGIONAL),
    ):
        if not valor.strip() or valor.strip().startswith(PLACEHOLDER):
            faltando.append(rotulo)
    return faltando

# Nome do professor(a) responsável pelas reservas que você quer processar
# (como aparece no site de agendamento). Deixe em branco/None para processar
# TODOS os professores que usam o laboratório — foi assim que decidimos usar
# na prática: o orientador registra a aula de quem quer que tenha
# usado o laboratório naquele horário, não só as aulas dele mesmo.
PROFESSOR_FILTRO = _config("PROFESSOR_FILTRO") or None

# Recursos utilizados por padrão em toda aula (a regra de ouro combinada:
# só pergunta recurso diferente se você pedir explicitamente com
# --perguntar-recursos).
# Como cada recurso aparece NA TELA. O texto enviado à SED continua sendo o
# nome completo (RECURSOS_DISPONIVEIS) — isto aqui é só para caber.
#
# O motivo é concreto: com os nomes por extenso, os oito recursos só cabiam
# em duas colunas de quatro linhas, e essas quatro linhas empurravam a lista
# para fora da parte visível numa tela de 1366x768. Foi o que fez um
# professor relatar que "sumiram as opções de materiais". Encurtando o
# rótulo, cabem três colunas de três linhas — e a lista inteira aparece sem
# rolar.
RECURSO_CURTO = {
    "Computadores/notebooks (pesquisa) no laboratório": "Notebooks — pesquisa",
    "Computadores/notebooks (software/programa) no laboratório": "Notebooks — software",
    "Computadores/notebooks (edição de imagens/vídeos) no laboratório": "Notebooks — imagens/vídeos",
    "Computadores/notebooks (sites educacionais) no laboratório": "Notebooks — sites educacionais",
    "Notebooks (recurso móvel para sala de aula)": "Notebooks na sala de aula",
}


def rotulo_curto(recurso: str) -> str:
    return RECURSO_CURTO.get(recurso, recurso)


RECURSOS_PADRAO = [
    "Lousa Digital",
    "Computadores/notebooks (pesquisa) no laboratório",
    "Computadores/notebooks (sites educacionais) no laboratório",
]

# ---------------------------------------------------------------------------
# Atualização automática
#
# Endereço onde ficam os arquivos da versão mais recente.
#
# ISTO TEM UM PADRÃO DE PROPÓSITO. Antes o endereço só existia se a
# pessoa tivesse escrito a linha URL_ATUALIZACAO no .env — e quem
# instalasse sem essa linha (ou copiasse um .env antigo por cima)
# simplesmente nunca era avisado de versão nova. O programa não dava erro
# nenhum: ele calava. Uma correção publicada não chegava em ninguém, e o
# jeito de descobrir era alguém reclamar de um defeito já resolvido.
#
# Continua configurável: escrever URL_ATUALIZACAO no .env manda por cima
# deste padrão. É o caminho para o dia em que o NTE/SED hospedar os
# arquivos no servidor deles — troca-se uma linha, sem reinstalar nada
# em escola nenhuma. E deixar a linha escrita como "desligado" desliga a
# atualização de vez.
# ---------------------------------------------------------------------------
CASA_DO_PROGRAMA = "https://raw.githubusercontent.com/ArnoNeto1/registro-sed-automatizado/main"

URL_ATUALIZACAO = _config("URL_ATUALIZACAO", CASA_DO_PROGRAMA)
if URL_ATUALIZACAO.strip().lower() in ("desligado", "nao", "não", "off", "0"):
    URL_ATUALIZACAO = ""

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
AGENDA_LOGIN_URL = "https://nteblumenau.com.br/escolas/login.php"
AGENDA_URL = "https://nteblumenau.com.br/escolas/agenda.php"
SED_FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSdpCK7OQtOsBxTAOXeGhTRq6EHocp1Om6vAm5UR4IMGa-a20Q/viewform"
)

# ---------------------------------------------------------------------------
# Mapeamento: disciplina do site de agendamento -> Componente Curricular do
# formulário da SED.
#
# Cada valor pode ser:
#   - uma lista de nomes de checkbox a marcar (quando corresponde direto a
#     um ou mais componentes do formulário);
#   - ("OUTRO", "texto") quando deve marcar a opção "Outro:" e digitar esse
#     texto no campo ao lado;
#   - ("ETAPA_DEPENDENTE", {etapa: lista_ou_outro}) quando a opção certa no
#     formulário muda de nome dependendo da etapa (isso acontece só com
#     "Educação Digital", que no formulário aparece como "Educação Digital"
#     nos Anos Iniciais e "Educação Digital (ETI)" nos Anos Finais —
#     confirmado inspecionando as duas páginas reais do formulário).
#
# As chaves já passam por normalização (ver normalizar_disciplina) antes da
# busca, então não é preciso duplicar entradas só por causa de travessão
# "–" vs hífen "-" ou espaços a mais/a menos.
# ---------------------------------------------------------------------------
DISCIPLINA_PARA_COMPONENTE = {
    "Arte": ["Arte"],
    "Ciências": ["Ciências"],
    "Educação Física": ["Educação Física"],
    "Ensino Religioso": ["Ensino Religioso"],
    "Geografia": ["Geografia"],
    "História": ["História"],
    "Língua Estrangeira - Inglês": ["Língua Estrangeira (Inglês)"],
    "Língua Estrangeira - Espanhol": ["Língua Estrangeira (Espanhol)"],
    "Espanhol": ["Língua Estrangeira (Espanhol)"],
    "Inglês": ["Língua Estrangeira (Inglês)"],
    "Língua Portuguesa": ["Língua Portuguesa"],
    "Matemática": ["Matemática"],
    # --- componentes que só existem no ENSINO MÉDIO ---
    # (conferido na estrutura real do formulário: a página de componentes
    # do Ensino Médio é outra, e traz estas matérias que não aparecem no
    # Fundamental.)
    "Biologia": ["Biologia"],
    "Física": ["Física"],
    "Química": ["Química"],
    "Filosofia": ["Filosofia"],
    "Sociologia": ["Sociologia"],
    # no Fundamental a opção existe só na versão "(ETI)"; no Médio, sem
    "Segunda Língua Estrangeira": (
        "ETAPA_DEPENDENTE",
        {
            "Ensino Fundamental - Anos Iniciais": ["Segunda Língua Estrangeira  (ETI)"],
            "Ensino Fundamental - Anos Finais": ["Segunda Língua Estrangeira  (ETI)"],
            "Ensino Médio": ["Segunda Língua Estrangeira"],
        },
    ),
    "Componente Curricular Eletivo": ["Componente Curricular Eletivo"],
    "ETI - Arte e Musicalização": ["Artes Visuais (ETI)", "Musicalização  (ETI)"],
    "ETI - Educação Financeira": ["Educação Financeira  (ETI)"],
    "ETI - Esportes": ["Esporte  (ETI)"],
    "ETI - Esporte": ["Esporte  (ETI)"],
    "ETI - LEIA": ["LEIA  (ETI)"],
    "ETI - Segunda Língua Estrangeira": ["Segunda Língua Estrangeira  (ETI)"],
    "ETI - Dança": ["Dança  (ETI)"],
    "ETI - Teatro": ["Teatro  (ETI)"],
    "ETI - Iniciação à pesquisa": ("OUTRO", "Iniciação à pesquisa"),
    "ETI - Educação Em Sustentabilidade": ("OUTRO", "Educação Em Sustentabilidade"),
    # "Educação Digital" muda de nome conforme a etapa — conferido na
    # estrutura real do formulário:
    #   Anos Iniciais e Ensino Médio -> "Educação Digital"
    #   Anos Finais                  -> "Educação Digital (ETI)"
    "ETI - Educação Digital": (
        "ETAPA_DEPENDENTE",
        {
            "Ensino Fundamental - Anos Iniciais": ["Educação Digital"],
            "Ensino Fundamental - Anos Finais": ["Educação Digital (ETI)"],
            "Ensino Médio": ["Educação Digital"],
        },
    ),
    "Educação Digital": (
        "ETAPA_DEPENDENTE",
        {
            "Ensino Fundamental - Anos Iniciais": ["Educação Digital"],
            "Ensino Fundamental - Anos Finais": ["Educação Digital (ETI)"],
            "Ensino Médio": ["Educação Digital"],
        },
    ),
    # Orientadora de Convivência (Daiana) — aula avulsa que não aparece na
    # agenda, tratada à parte pelo fluxo "--daiana" do main.py.
    "Orientadora de Convivência": ("OUTRO", "Interação"),
}

# Disciplinas do site de agendamento que NÃO são "Atividade/Aula com
# estudantes" (são reservas internas de formação/reunião/limpeza) — o script
# pula essas automaticamente, pois pertencem a outro fluxo do formulário
# ("Formação/Reunião") que ainda não foi mapeado (ver README, seção
# "Próximos passos").
DISCIPLINAS_IGNORADAS = {
    "Organização interna na Sala de Tecnologias\\Formação",
}


def normalizar_disciplina(texto: str) -> str:
    """
    Normaliza o texto da disciplina para buscar em DISCIPLINA_PARA_COMPONENTE
    sem se importar com travessão vs hífen ou espaços duplicados — o site do
    NTE não é 100% consistente nisso (ex: "ETI – Educação Digital" com
    travessão em algumas aulas e "ETI - Iniciação à pesquisa" com hífen
    normal em outras).
    """
    t = texto.strip()
    t = re.sub(r"[‐-―−]", "-", t)  # travessões/en-dash/em-dash -> hífen
    t = re.sub(r"\s*-\s*", " - ", t)  # espaçamento padrão ao redor do hífen
    t = re.sub(r"\s+", " ", t)  # colapsa espaços duplicados
    return t.strip()


def chave_comparacao(texto: str) -> str:
    """
    Reduz um texto à sua forma "crua" para comparar sem sustos: sem
    acento, tudo minúsculo, espaços colapsados.

    Isto existe porque a comparação literal falhava de um jeito
    traiçoeiro. Uma aula de História foi registrada como "Outro:
    História" mesmo existindo a opção "História" na lista — o texto
    parecia idêntico na tela, mas não era igual byte a byte.

    São três armadilhas diferentes, e qualquer uma derruba a busca:

      1. Acento composto x decomposto. "História" pode vir com o "ó"
         como um caractere só, ou como "o" + acento separado. Na tela
         são idênticos; para o computador, não.
      2. Maiúsculas. Sistemas escolares costumam gravar "HISTÓRIA".
      3. Acento ausente. Alguém cadastra "Historia" e pronto.

    Comparando pela forma crua, as três variantes casam com a opção
    certa do formulário.
    """
    t = normalizar_disciplina(texto)
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower().strip()


# monta um índice já normalizado (feito uma vez, na importação do módulo)
_INDICE_NORMALIZADO = {chave_comparacao(k): v for k, v in DISCIPLINA_PARA_COMPONENTE.items()}


def disciplina_tem_mapeamento(disciplina_agendamento: str) -> bool:
    """Verificação simples (sem etapa) usada só para o aviso de pré-visualização."""
    return chave_comparacao(disciplina_agendamento) in _INDICE_NORMALIZADO


def resolver_componente(disciplina_agendamento: str, etapa: str):
    """
    Retorna o valor de DISCIPLINA_PARA_COMPONENTE já resolvido para a etapa
    informada (lista de checkboxes a marcar, ou ("OUTRO", texto)), ou None se
    a disciplina não estiver mapeada.
    """
    chave = chave_comparacao(disciplina_agendamento)
    valor = _INDICE_NORMALIZADO.get(chave)
    if valor is None:
        return None
    if isinstance(valor, tuple) and valor[0] == "ETAPA_DEPENDENTE":
        por_etapa = valor[1]
        return por_etapa.get(etapa)
    return valor


# ---------------------------------------------------------------------------
# Mapeamento: prefixo da turma do site de agendamento -> etapa da Educação
# Básica no formulário da SED. Regra explícita combinada com o usuário:
# 1º ao 5º ano = Anos Iniciais / 6º ao 9º ano = Anos Finais.
# ---------------------------------------------------------------------------
def etapa_para_turma(turma_texto: str):
    """
    Deduz a etapa da Educação Básica a partir do texto da turma.

    A ORDEM AQUI É CRÍTICA: primeiro procuramos o nome da etapa escrito
    no próprio texto; só depois, se nada foi encontrado, entra a regra
    numérica (1º-5º = Anos Iniciais, 6º-9º = Anos Finais).

    Isso porque a regra numérica sozinha erra feio no Ensino Médio: uma
    turma "Ensino Médio - 3º ano 03" tem o número 3 e virava
    "Anos Iniciais" — sem erro nenhum na tela, só um registro errado
    indo para a SED. Foi encontrado quando o programa começou a ser
    usado numa escola com Ensino Médio.

    Por isso a regra numérica agora só vale quando o texto NÃO diz a
    etapa; e, na dúvida, devolvemos None para o programa perguntar em
    vez de chutar.
    """
    t = _sem_acento(turma_texto.strip().lower())

    # 1) etapa dita com todas as letras no texto da turma
    #
    # EJA, AEE e Profissional vêm ANTES de "Ensino Médio" de propósito:
    # uma turma escrita como "EJA - Ensino Médio" contém as duas coisas, e
    # o que vale é a modalidade — no formulário da SED ela tem página
    # própria. Com a ordem invertida, essa turma virava Ensino Médio comum
    # e o registro ia para a página errada.
    if "jovens e adultos" in t or "eja" in t.split():
        return "Educação de Jovens e Adultos"
    if "aee" in t.split() or "educacao especial" in t:
        return "Educação Especial (AEE)"
    if "profissional" in t or "tecnico" in t:
        return "Ensino Profissional"
    if "ensino medio" in t or t.startswith("em "):
        return "Ensino Médio"
    if t.startswith("anos iniciais"):
        return "Ensino Fundamental - Anos Iniciais"
    if t.startswith("anos finais"):
        return "Ensino Fundamental - Anos Finais"

    # 2) só agora a regra numérica, e só para o Ensino Fundamental
    m = re.search(r"(\d+)\s*º?\s*ano", t)
    if m:
        ano = int(m.group(1))
        if 1 <= ano <= 5:
            return "Ensino Fundamental - Anos Iniciais"
        if 6 <= ano <= 9:
            return "Ensino Fundamental - Anos Finais"
    return None  # não foi possível deduzir — o programa vai perguntar


# ---------------------------------------------------------------------------
# Etapas que têm página própria no formulário
# ---------------------------------------------------------------------------
# Três etapas NÃO seguem o caminho comum "marque o componente curricular".
# Conferido ao vivo na estrutura do formulário da SED:
#
#   Ensino Profissional ....... duas caixas de texto: "Qual o curso?" e
#                               "Qual o componente curricular?".
#   Educação Especial (AEE) ... caixas de seleção "Qual etapa?" (três
#                               opções) + "Breve descrição da atividade:".
#                               NÃO existe opção "Outro:" nessa página.
#   EJA ....................... um "Qual etapa?" (Fundamental/Médio) ANTES
#                               da lista de componentes.
#
# Enquanto isso não estava no programa, escolher AEE ou Ensino Profissional
# terminava em "Não encontrei o checkbox 'Outro:' nesta página" — o programa
# procurava uma lista de componentes numa página que não tem lista nenhuma.
ETAPA_PROFISSIONAL = "Ensino Profissional"
ETAPA_AEE = "Educação Especial (AEE)"
ETAPA_EJA = "Educação de Jovens e Adultos"

SUBETAPAS_AEE = [
    "Ensino Fundamental - Anos Iniciais",
    "Ensino Fundamental - Anos Finais",
    "Ensino Médio",
]
SUBETAPAS_EJA = ["Ensino Fundamental", "Ensino Médio"]


def opcoes_subetapa(etapa: str) -> list:
    """Opções da pergunta 'Qual etapa?' — lista vazia quando não existe."""
    if etapa == ETAPA_AEE:
        return list(SUBETAPAS_AEE)
    if etapa == ETAPA_EJA:
        return list(SUBETAPAS_EJA)
    return []


def curso_sugerido(turma_texto: str) -> str:
    """
    Tira o "Ensino Profissional -" da frente da turma para sobrar o curso.

    A agenda escreve "Ensino Profissional - Técnico em Informática"; o
    formulário quer só "Técnico em Informática" no campo "Qual o curso?".
    """
    t = (turma_texto or "").strip()
    cru = _sem_acento(t.lower())
    for prefixo in ("ensino profissional", "curso tecnico", "curso"):
        if cru.startswith(prefixo):
            t = t[len(prefixo):].strip(" -–—:")
            if prefixo == "curso tecnico" and t:
                t = f"Técnico {t}" if not t.lower().startswith("tecnico") else t
            break
    return t or (turma_texto or "").strip()


def subetapa_sugerida(turma_texto: str, etapa: str) -> str:
    """
    Deduz a sub-etapa (a pergunta "Qual etapa?") pelo texto da turma.

    Serve para deixar o campo já preenchido na tela — quem confirma é o
    professor, que vê o valor antes de mandar. Devolve "" quando não dá
    para deduzir, e aí o campo fica vazio de propósito, em vez de chutar.
    """
    opcoes = opcoes_subetapa(etapa)
    if not opcoes:
        return ""

    t = _sem_acento((turma_texto or "").lower())
    medio = "ensino medio" in t or "medio" in t.split()
    ano = None
    m = re.search(r"(\d+)\s*º?\s*ano", t)
    if m:
        ano = int(m.group(1))

    if etapa == ETAPA_EJA:
        if medio:
            return "Ensino Médio"
        if "fundamental" in t or (ano is not None and 1 <= ano <= 9):
            return "Ensino Fundamental"
        return ""

    if medio:
        return "Ensino Médio"
    if "anos iniciais" in t or (ano is not None and 1 <= ano <= 5):
        return "Ensino Fundamental - Anos Iniciais"
    if "anos finais" in t or (ano is not None and 6 <= ano <= 9):
        return "Ensino Fundamental - Anos Finais"
    return ""
