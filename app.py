# -*- coding: utf-8 -*-
"""
Janela (interface gráfica) para o registro de atividades na SED-SC.

É a mesma automação do main.py, só que com tela em vez de perguntas no
terminal. O que ela faz sozinha ao abrir:

  1. Lê a agenda do laboratório da semana atual;
  2. Identifica pelo HORÁRIO qual aula está acontecendo agora (ou qual
     acabou de acontecer) e já deixa ela selecionada;
  3. Só espera você digitar o número de estudantes — a única informação
     que não existe na agenda — e clicar em "Preencher formulário";
  4. Preenche o formulário inteiro e PARA na última página, mostrando o
     resumo. Nada é enviado até você clicar em "Enviar para a SED".

Regra de ouro mantida: o envio nunca acontece sozinho, e uma confirmação
não vale para o próximo registro.

Como abrir: baixe o `.exe`/instalador da página de Releases do GitHub, ou
rode `python app.py` na pasta do projeto (quem for mexer no código).

DETALHE TÉCNICO IMPORTANTE (pra quem for mexer): o Playwright roda numa
thread separada da janela. Isso é obrigatório — se ele rodasse na mesma
thread, a janela congelaria ("Não Respondendo") toda vez que o navegador
fosse fazer qualquer coisa. As duas conversam por filas: a janela manda
comandos, a thread devolve eventos, e só a janela mexe na tela.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import queue
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox, ttk

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# ATENÇÃO À ORDEM: o .env PRECISA ser carregado aqui, antes de importar
# config (e antes de agenda_scraper, que também importa config).
#
# O config lê os dados do ambiente na hora em que é importado. Antes, o
# load_dotenv() só acontecia mais tarde, dentro da thread do navegador —
# ou seja, DEPOIS que o config já tinha lido tudo. Resultado: o arquivo
# .env era simplesmente ignorado para nome, escola e regional.
#
# No computador de quem escreveu o programa isso passou despercebido por
# semanas, porque os valores padrão do config eram justamente os dados
# dele. Só apareceu quando outro professor instalou: .env preenchido
# corretamente e mesmo assim a janela insistia em "Configuração
# pendente".
#
# O caminho é montado a partir da pasta deste arquivo (e não da pasta
# atual do terminal) para funcionar mesmo se o programa for aberto de
# outro lugar.
# ---------------------------------------------------------------------------
from caminhos import (  # noqa: E402
    abrir_contexto,
    abrir_navegador,
    caminho_de_dados,
    empacotado,
    limpar_sobras,
    migrar_dados_antigos,
    pasta_de_dados,
)

# Quem já usava uma versão anterior à 1.5 tinha .env, login do navegador e
# histórico do lado do .exe; migra tudo para a pasta de dados antes de
# qualquer leitura abaixo.
migrar_dados_antigos()

load_dotenv(pasta_de_dados() / ".env")

from agenda_scraper import (  # noqa: E402
    TURNOS,
    categoria_do_recurso,
    filtrar_e_agrupar,
    login,
    scrape_semana_completa,
)
import atualizador  # noqa: E402
from config import (  # noqa: E402
    ESCOLA,
    ETAPA_AEE,
    ETAPA_PROFISSIONAL,
    URL_ATUALIZACAO,
    ORIENTADOR_NOME,
    ORIENTADORES,
    opcoes_subetapa,
    orientador_de_plantao,
    SED_FORM_URL,
    configuracao_incompleta,
    curso_sugerido,
    etapa_para_turma,
    resolver_componente,
    subetapa_sugerida,
    SENHAS_SALVAS,
    TODOS_TURNOS,
    turno_do_horario,
)
import configuracao  # noqa: E402
import tema  # noqa: E402
from main import (  # noqa: E402
    ESTADO_FILE,  # noqa: F401  (mantido pra deixar claro de onde vem o estado)
    pasta_do_perfil,
    RECURSOS_DISPONIVEIS,
    agora_sc,
    carregar_enviados,
    chave_grupo,
    estado_corrompido,
    ja_comecou,
    marcar_enviado,
    purgar_antigas,
    monday_of,
)
from sed_form_filler import (  # noqa: E402
    abrir_formulario,
    enviar,
    estado_da_conta_google,
    iniciar_conferencia,
    pegar_conferencia,
    preencher_atividade_com_estudantes,
    preencher_dados_fixos,
    preencher_formacao_reuniao,
    preencher_manutencao_equipamentos,
    preencher_suporte_outros_espacos,
    ORGANIZADORES_DE_FORMACAO,
    OPCOES_MANUTENCAO,
    TIPOS_DE_SUPORTE,
)

# O iniciar.py olha esta marca para não repetir um aviso que a pessoa já viu.
ERRO_JA_MOSTRADO = False


def _categoria_da_atividade(g) -> str:
    """
    Em qual aba esta aula aparece na tabela: "Laboratório" (o padrão —
    Lab. Tecs, ou qualquer recurso que `categoria_do_recurso` não
    reconheça) ou uma das categorias extras (Projetores, Tablets/Celular)
    que a escola tiver.
    """
    return categoria_do_recurso(g.recurso) or "Laboratório"


CATEGORIAS_RECURSO_EM_ORDEM = ("Laboratório", "Tablets/Celular", "Projetores")

# Três abas que NÃO vêm de agendamento nenhum — "Suporte a outros
# espaços", "Manutenção de equipamentos" e "Formação/Reunião" no
# formulário da SED não têm hora marcada na agenda do NTE, então ficam
# sempre visíveis (diferente das de cima, que só aparecem se a agenda
# de verdade trouxer aula daquele recurso). Ver _atualizar_abas_recurso
# e _atualizar_area_dados_registro.
#
# "Suporte a outros espaços" também é preenchível vindo da agenda (uma
# aula de Projetor/Tablets pode ser marcada como suporte em vez de aula
# — ver cartao_suporte, var_tipo_suporte), mas ATÉ aqui só existia esse
# caminho: um suporte que não veio de reserva nenhuma na agenda não
# tinha como ser registrado. Esta aba é pra esse caso — mesmo
# mecanismo de preenchimento (preencher_suporte_outros_espacos), só
# sem precisar de uma aula selecionada primeiro (ver
# _coletar_dados_suporte_avulso). A ordem aqui é a ordem visual da
# esquerda pra direita (ver o pack() em _atualizar_abas_recurso) — bate
# com a ordem das opções no formulário da SED.
CATEGORIAS_INDEPENDENTES = ("Suporte a outros espaços", "Manutenção", "Formação/Reunião")


class _RegistroSemAgenda:
    """
    Ocupa o lugar de "grupo" para os registros que não vêm de agendamento
    nenhum (ver CATEGORIAS_INDEPENDENTES, e "Aula sem agendamento" em
    _abrir_aula_sem_agendamento) — só para reaproveitar toda a
    infraestrutura de conferência/envio já pronta (chave_grupo,
    marcar_enviado, o resumo "CONFIRA ANTES DE ENVIAR" na tela) sem
    duplicar código para eles.

    `disciplina` carrega o nome do tipo de registro (Manutenção/
    Formação) OU a disciplina/atividade digitada à mão (Aula sem
    agendamento) — aparece no resumo. Para Manutenção/Formação, os
    demais campos ficam vazios/"hoje" (não fazem sentido ali). Para Aula
    sem agendamento, quem chama preenche `turma`/`numero_aulas` de
    verdade (a pessoa digitou) e ajusta `professor`/`inicio`/`fim` na
    mão logo depois de construir (ver _abrir_aula_sem_agendamento) —
    não dá pra passar tudo pelo construtor sem quebrar as duas chamadas
    antigas (só `titulo`) já espalhadas pelo código.

    `rastrear_como_enviado` decide se um envio bem-sucedido entra no
    histórico de "já enviados" (ver NavegadorWorker, ação "enviar").
    Falso por padrão — o padrão de Manutenção/Formação, que podem se
    repetir de verdade no mesmo dia (duas manutenções, duas reuniões) e
    por isso nunca tiveram esse controle. "Aula sem agendamento" muda
    isso pra True explicitamente (ver _abrir_aula_sem_agendamento) —
    sem isso, mandar a MESMA aula avulsa duas vezes por engano nunca
    seria pego pelo aviso de "já registrada" (achado numa revisão
    adversarial, antes de ir para o professor testar).
    """

    def __init__(
        self, titulo: str, turma: str = "", numero_aulas: int = 0,
        rastrear_como_enviado: bool = False,
    ):
        self.data = dt.date.today().isoformat()
        self.inicio = ""
        self.fim = ""
        self.professor = ""
        self.disciplina = titulo
        self.turma = turma
        self.numero_aulas = numero_aulas
        self.recurso = ""
        self.rastrear_como_enviado = rastrear_como_enviado


def _texto_conferencia(itens) -> str:
    """
    O que o formulário respondeu, lido de volta da própria página.

    Com o navegador em segundo plano, esta é a evidência de que o
    preenchimento aconteceu de verdade — e não a intenção do programa.
    Cada linha aqui foi lida DEPOIS de escrita: caixa marcada conferida
    com is_checked(), texto conferido com input_value(), item de lista
    conferido pelo aria-selected.
    """
    if not itens:
        return ""
    linhas = ["", "CONFERIDO NA PÁGINA (lido de volta do formulário):"]
    for campo, valor in itens:
        valor = str(valor).strip().replace("\n", " ")
        if len(valor) > 70:
            valor = valor[:70] + "..."
        linhas.append(f"  · {campo}: {valor}")
    return "\n".join(linhas)


def _mensagem_amigavel_de_erro(detalhe: str) -> str:
    """
    Traduz erro de CONEXÃO (site fora do ar, wifi caiu, internet lenta)
    pra uma frase que qualquer professor entende, em vez do texto cru do
    Playwright ("net::ERR_CONNECTION_TIMED_OUT at https://...").

    "net::ERR_" é a marca específica que o Chromium usa pra falha de
    REDE — não aparece em erro de lógica do programa (ex: "não achei tal
    botão na página"), então dá pra trocar a mensagem aqui sem risco de
    confundir um tipo de erro com outro. O texto técnico continua indo
    junto, só que como detalhe menor, não como a frase principal.
    """
    if "net::err_" in detalhe.lower():
        return (
            "Não consegui acessar o site — parece internet, não o "
            "programa. Confira a conexão e tente de novo (clique em "
            '"Atualizar agenda", ou tente preencher/enviar outra vez).\n\n'
            f"Detalhe técnico: {detalhe.strip()}"
        )
    return detalhe


def _notas_para_dialogo(texto: str) -> str:
    """
    Prepara o texto de NOVIDADES.md pra aparecer na caixa de "nova versão
    disponível" — que é uma caixa NATIVA do Windows, não desenhada pelo
    programa: ela não entende Markdown (mostraria **negrito** do jeito
    que está escrito, asteriscos e tudo) e também não sabe juntar de
    volta uma frase que o .md quebrou em várias linhas só pra ficar
    legível dentro do arquivo — sem isso, cada item de lista aparecia
    picado em pedacinhos curtos e difíceis de acompanhar.
    """
    paragrafos = []
    atual = []
    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha:
            if atual:
                paragrafos.append(" ".join(atual))
                atual = []
            continue
        if linha.startswith("- ") and atual:
            paragrafos.append(" ".join(atual))
            atual = [linha]
        else:
            atual.append(linha)
    if atual:
        paragrafos.append(" ".join(atual))
    # Uma linha em branco entre cada item — pedido explícito depois de ver
    # a caixa de verdade: sem isso, os itens ficavam colados um no outro.
    return "\n\n".join(paragrafos).replace("**", "")


def _texto_componente(comp) -> str:
    """
    Deixa o componente legível no resumo de conferência.

    Antes esta linha mostrava a tupla crua do Python — ("OUTRO", 'História')
    — que não diz nada para quem só quer conferir o que vai para a SED.
    """
    if isinstance(comp, tuple) and len(comp) == 2:
        marca, valor = comp
        if marca == "OUTRO":
            return f"Outro: {valor}"
        if marca == "CURSO":
            return f"Curso: {valor}"
        if marca == "AEE":
            return f"AEE · {valor}"
        return str(valor)
    if isinstance(comp, (list, tuple)):
        return ", ".join(str(c) for c in comp)
    return str(comp)


ETAPAS = [
    "Ensino Fundamental - Anos Iniciais",
    "Ensino Fundamental - Anos Finais",
    "Ensino Médio",
    "Ensino Profissional",
    "Educação de Jovens e Adultos",
    "Educação Especial (AEE)",
]

# De quanto em quanto tempo o relógio interno confere se alguma aula
# começou. 30s é bem mais curto que a menor aula (45min), então nenhuma
# passa batido, e é leve o bastante para não pesar em nada.
INTERVALO_CHECAGEM_MS = 30_000

# Só avisa se a aula começou há no máximo isso. Sem essa janela, abrir o
# programa às 15h faria ele piscar de uma vez por todas as aulas da manhã.
JANELA_AVISO_MIN = 5

# De quanto em quanto tempo relê a agenda sozinho, para pegar aulas
# agendadas depois que o programa foi aberto.
INTERVALO_RECONSULTA_MS = 30 * 60 * 1000

# De quanto em quanto tempo procura versão nova com o programa aberto.
#
# Ao abrir, ele já procura uma vez — e para quem fecha o programa todo dia
# isso basta. Mas em laboratório é comum a máquina ficar dias ligada com o
# programa aberto: sem este relógio, quem faz isso nunca receberia
# correção nenhuma. Uma vez por dia é frequência de sobra para um programa
# que muda algumas vezes por mês.
INTERVALO_ATUALIZACAO_MS = 24 * 60 * 60 * 1000

# Ritmo do verde piscando na linha "Sugerida agora". 700ms chama atenção
# sem virar aquele pisca-pisca que cansa a vista em poucos minutos.
INTERVALO_PISCA_MS = 700

# Paleta atual (Claro/Escuro/Igual ao sistema — escolhido em "Meus
# dados", guardado em configuracao.json). Lida uma vez aqui, na
# abertura do programa; trocar de tema pede reabrir, pelo mesmo caminho
# já usado para qualquer outra mudança em "Meus dados" (ver tema.py).
_PALETA = tema.resolver_paleta(configuracao.carregar().get("tema", tema.SISTEMA))

VERDE_PISCA = _PALETA["verde_pisca"]

# Cor da linha selecionada. Cinza-ardósia de propósito: azul, laranja e
# verde já significam coisas na coluna Situação, e mais uma cor com
# significado atrapalharia a leitura.
SELECAO_BG = _PALETA["selecao_bg"]
SELECAO_FG = _PALETA["selecao_fg"]

COR_FUNDO = _PALETA["fundo"]
COR_CARTAO = _PALETA["cartao"]
COR_CAMPO = _PALETA["campo"]
COR_TEXTO = _PALETA["texto"]
COR_SUAVE = _PALETA["suave"]
COR_DESTAQUE = _PALETA["destaque"]
COR_AZUL = _PALETA["azul"]
COR_LARANJA = _PALETA["laranja"]
COR_CINZA = _PALETA["cinza"]
COR_SUGERIDA_FG = _PALETA["sugerida_fg"]
COR_SUGERIDA_FG_SELECIONADA = _PALETA["sugerida_fg_selecionada"]


# ---------------------------------------------------------------------------
# Aulas agendadas que não aconteceram
#
# O professor reservou o laboratório mas não apareceu / não usou. Essas
# aulas NÃO devem ir para a SED (não houve atividade), mas também não
# podem ficar aparecendo como "pendente" para sempre, senão a lista nunca
# fica limpa e a sugestão automática insiste nelas.
#
# Ficam num arquivo separado do registros_enviados.json de propósito: uma
# coisa é "já registrei", outra bem diferente é "não houve aula". Misturar
# as duas faria parecer que foram enviadas à SED.
# ---------------------------------------------------------------------------
NAO_REALIZADAS_FILE = caminho_de_dados("aulas_nao_realizadas.json")

# Guarda qual professor foi escolhido da última vez. Em escola com dois
# orientadores dividindo o computador, ninguém quer reescolher o próprio
# nome toda vez que abre o programa.
ULTIMO_PROF_FILE = caminho_de_dados("ultimo_professor.txt")


def carregar_ultimo_professor() -> str:
    try:
        with open(ULTIMO_PROF_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def salvar_ultimo_professor(nome: str) -> None:
    try:
        with open(ULTIMO_PROF_FILE, "w", encoding="utf-8") as f:
            f.write(nome)
    except Exception:
        pass  # não poder lembrar não é motivo para atrapalhar o uso


def carregar_nao_realizadas() -> set:
    if not os.path.exists(NAO_REALIZADAS_FILE):
        return set()
    try:
        with open(NAO_REALIZADAS_FILE, "r", encoding="utf-8") as f:
            marcadas = set(json.load(f))
    except Exception:
        # arquivo corrompido não pode derrubar o programa inteiro
        return set()
    # Mesma limpeza de registros_enviados.json (main.purgar_antigas): sem
    # isto, este arquivo também cresceria para sempre.
    atuais = purgar_antigas(marcadas)
    if len(atuais) != len(marcadas):
        _salvar_nao_realizadas(atuais)
    return atuais


def _salvar_nao_realizadas(chaves: set) -> None:
    # Atômico pelo mesmo motivo de _escrever_estado() em main.py: uma
    # escrita comum interrompida no meio deixaria o .json pela metade.
    tmp = NAO_REALIZADAS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(chaves), f, ensure_ascii=False, indent=2)
    os.replace(tmp, NAO_REALIZADAS_FILE)


def marcar_nao_realizada(chave: str) -> None:
    atuais = carregar_nao_realizadas()
    atuais.add(chave)
    _salvar_nao_realizadas(atuais)


def desmarcar_nao_realizada(chave: str) -> None:
    atuais = carregar_nao_realizadas()
    atuais.discard(chave)
    _salvar_nao_realizadas(atuais)


# ---------------------------------------------------------------------------
# Escolha automática da aula pelo horário
# ---------------------------------------------------------------------------
def _hora(texto: str) -> dt.time:
    return dt.datetime.strptime(texto, "%H:%M").time()


def escolher_aula_automatica(grupos: list, ignorar: set, agora: dt.datetime, turnos=None):
    """
    Devolve a aula que faz mais sentido registrar agora, ou None.

    Prioridade:
      1. Uma aula acontecendo NESTE momento (agora entre início e fim);
      2. Senão, a aula mais recente que já começou e ainda não foi enviada.

    Nunca devolve aula futura (regra de ouro: só registra depois que
    aconteceu). `ignorar` traz as aulas que já foram enviadas em execuções
    anteriores e as marcadas como não realizadas — nenhuma das duas deve
    ser sugerida de novo.
    """
    # `turnos` limita a sugestão às aulas do turno de quem está usando o
    # programa: o professor da noite não deve ser puxado para uma aula da
    # manhã, que é do colega. As aulas do outro turno continuam visíveis
    # na lista (marcadas como tal), só não são sugeridas nem alertadas.
    candidatas = [
        g
        for g in grupos
        if ja_comecou(g, agora)
        and chave_grupo(g) not in ignorar
        and (not turnos or not getattr(g, "turno", "") or g.turno in turnos)
    ]
    if not candidatas:
        return None

    hoje = agora.date().isoformat()
    agora_h = agora.time()
    for g in candidatas:
        if g.data == hoje and _hora(g.inicio) <= agora_h <= _hora(g.fim):
            return g

    # nenhuma acontecendo agora — pega a que começou mais recentemente
    return max(candidatas, key=lambda g: (g.data, g.inicio))


# ---------------------------------------------------------------------------
# Thread do navegador (Playwright)
# ---------------------------------------------------------------------------
class NavegadorWorker(threading.Thread):
    """
    Roda o Playwright numa thread só dele, recebendo comandos por fila.

    Comandos aceitos (colocados em comandos):
        ("carregar", quieto, cpf, senha, escola)
        ("preencher", "aula", grupo, n_estudantes, recursos, etapa, conteudos,
         prof_nome, prof_tipo, prof_escola, subetapa, curso, mostrar)
        ("preencher", "suporte", grupo, tipo_atendimento, descricao,
         quantidade_aulas, prof_nome, prof_tipo, prof_escola, mostrar)
        ("conta_google", escola)
        ("enviar", grupo)
        ("sair_google", escola)
        ("reiniciar",)
        ("sair",)

    Eventos devolvidos (lidos pela janela em eventos):
        ("status", texto)
        ("aulas", lista_de_grupos)
        ("preenchido", grupo, resumo_dict)
        ("enviado", grupo)
        ("erro", mensagem, acao_que_falhou)
    """

    def __init__(self, comandos: queue.Queue, eventos: queue.Queue):
        super().__init__(daemon=True)
        self.comandos = comandos
        self.eventos = eventos
        self._page = None
        self._context = None
        self._visivel = None
        self._escola_atual = None

    # -- utilidades ---------------------------------------------------------
    def _status(self, texto: str) -> None:
        self.eventos.put(("status", texto))

    def _garantir_navegador(self, p, visivel: bool = False, escola: str = ""):
        """
        O navegador que preenche o formulário da SED.

        Por padrão ele roda em SEGUNDO PLANO: preencher oito páginas de
        formulário com a janela pulando na frente do professor era a parte
        mais incômoda do programa — a cada registro o Chrome roubava o
        foco e a pessoa ficava olhando o preenchimento acontecer sem poder
        fazer mais nada. O que ela precisa conferir está no resumo, e esse
        resumo é lido de volta da própria página (ver sed_form_filler).

        Visível continua sendo possível, e é obrigatório em dois momentos:
        para entrar na conta Google da escola e quando o professor pede
        para acompanhar.

        Usa o perfil salvo em disco de CADA escola (`pasta_do_perfil`,
        uma pasta por escola) — é ele que guarda o login do Google entre
        uma execução e outra, nos dois modos. Trocar de escola (quem dá
        aula em mais de uma, no mesmo computador — ver
        configuracao.pedir_escola) força reabrir o navegador com o
        perfil certo: reaproveitar o perfil de OUTRA escola faria o
        programa preencher o formulário logado na conta Google errada,
        sem avisar ninguém.

        Antes de reaproveitar a página guardada, confere se ela ainda
        está viva. Se a pessoa fechou a janela do Chrome na mão (ou ela
        travou/foi fechada por fora), `self._page` continuava apontando
        para uma página morta, e a AÇÃO SEGUINTE (preencher, enviar)
        batia direto nela e explodia com um erro cru do Playwright
        ("TargetClosedError: Target page, context or browser has been
        closed") em vez de simplesmente abrir o navegador de novo.
        """
        if self._page is not None and self._visivel == visivel and self._escola_atual == escola:
            try:
                ainda_aberta = not self._page.is_closed()
            except Exception:
                ainda_aberta = False
            if ainda_aberta:
                return self._page
            self._status("A janela do Chrome tinha fechado — abrindo de novo...")
            self._fechar_navegador()
        if self._page is not None:
            # trocar de modo (ou de escola) exige reabrir: um navegador
            # já aberto não muda de invisível para visível no meio do
            # caminho, nem troca sozinho o perfil/login de uma escola
            # para o de outra.
            self._fechar_navegador()

        self._status("Abrindo o navegador..." if visivel else "Preparando em segundo plano...")
        extras = {"args": ["--start-maximized"], "no_viewport": True} if visivel else {}
        self._context, nome = abrir_contexto(
            p, pasta_do_perfil(escola), headless=not visivel, **extras
        )
        self._visivel = visivel
        self._escola_atual = escola
        self._status(f"Navegador pronto ({nome}).")
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self._page

    def _fechar_navegador(self) -> None:
        for alvo in (self._context,):
            try:
                if alvo is not None:
                    alvo.close()
            except Exception:
                pass
        self._context = None
        self._page = None
        self._visivel = None
        self._escola_atual = None

    def _raspar_agenda(self, p, cpf: str, senha: str, escola: str, invisivel: bool, quieto: bool = False):
        """
        Abre a agenda, lê a semana e FECHA o navegador ao terminar.

        `quieto` serve para a reconsulta automática de 30 em 30 minutos:
        sem isso, ela sobrescreveria a mensagem da barra de status bem na
        hora em que ela diz "Formulário pronto — confira e clique em
        Enviar", o que confundiria mais do que informa.
        """
        navegador = abrir_navegador(p, headless=invisivel)
        try:
            pagina = navegador.new_page()
            if not quieto:
                self._status("Entrando no site da agenda...")
            login(pagina, cpf, senha, escola or ESCOLA)
            if not quieto:
                self._status("Lendo os agendamentos da semana...")
            agendamentos = scrape_semana_completa(pagina, monday_of(dt.date.today()), list(TURNOS))
            return filtrar_e_agrupar(agendamentos, None)
        finally:
            navegador.close()

    def _ler_agenda(self, p, cpf: str, senha: str, escola: str = "", quieto: bool = False):
        """
        Lê a agenda num navegador SEM JANELA (segundo plano).

        Antes a agenda era lida no mesmo navegador visível do formulário:
        ao abrir o programa, a janela do Chrome pulava na frente, ficava
        parada na tela da agenda e tapava o aplicativo. Agora essa leitura
        acontece invisível e o navegador é fechado no fim — a janela do
        Chrome só aparece na hora de preencher o formulário, que é quando
        faz sentido você ver.

        Também é um navegador separado do outro de propósito: a agenda
        entra com CPF e senha toda vez (não precisa de sessão salva), e
        dois navegadores não podem usar o mesmo perfil ao mesmo tempo.
        """
        try:
            return self._raspar_agenda(p, cpf, senha, escola, invisivel=True, quieto=quieto)
        except Exception:
            # Alguns sites se comportam diferente sem janela. Se a leitura
            # em segundo plano falhar, tenta de novo com janela visível
            # antes de desistir — melhor uma janela aparecendo do que o
            # programa sem a lista de aulas.
            self._status("Não deu para ler em segundo plano; tentando com janela...")
            return self._raspar_agenda(p, cpf, senha, escola, invisivel=False)

    # -- laço principal -----------------------------------------------------
    def run(self) -> None:
        # importado aqui dentro de propósito: o Playwright síncrono precisa
        # ser criado e usado na MESMA thread, senão ele reclama.
        from playwright.sync_api import sync_playwright

        # o .env já foi carregado lá no topo do arquivo, antes dos imports
        # As credenciais chegam JUNTO com cada comando, em vez de serem
        # lidas uma vez só aqui: numa escola com dois orientadores, trocar
        # de professor na tela precisa trocar também o login usado para
        # ler a agenda.

        with sync_playwright() as p:
            while True:
                comando = self.comandos.get()
                acao = comando[0]
                if acao == "sair":
                    # Fecha explicitamente aqui, em vez de confiar só na
                    # saída do "with sync_playwright()": esta é uma thread
                    # daemon — se o processo principal encerrar antes dela
                    # terminar de rodar, ela é interrompida na hora, sem
                    # garantia de que o Chrome da sessão persistente
                    # (browser_profile) chegou a fechar de verdade. Ver
                    # Janela._encerrar_worker(), que ESPERA esta thread
                    # terminar antes de deixar o processo ir embora.
                    self._fechar_navegador()
                    break
                try:
                    if acao == "carregar":
                        # ("carregar", quieto, cpf, senha, escola)
                        quieto = bool(comando[1]) if len(comando) > 1 else False
                        cpf = comando[2] if len(comando) > 2 else ""
                        senha = comando[3] if len(comando) > 3 else ""
                        escola = comando[4] if len(comando) > 4 else ""
                        grupos = self._ler_agenda(p, cpf, senha, escola, quieto=quieto)
                        self.eventos.put(("aulas", grupos, quieto))
                        if not quieto:
                            self._status("Agenda carregada.")

                    elif acao == "preencher" and comando[1] == "suporte":
                        (_, _, grupo, tipo_atendimento, descricao, quantidade_aulas,
                         prof_nome, prof_tipo, prof_escola, mostrar) = comando
                        page = self._garantir_navegador(p, visivel=bool(mostrar), escola=prof_escola)
                        iniciar_conferencia()
                        self._status("Abrindo o formulário e preenchendo (suporte)...")
                        preencher_dados_fixos(page, prof_nome, prof_tipo, prof_escola)
                        preencher_suporte_outros_espacos(
                            page,
                            tipo_atendimento=tipo_atendimento,
                            descricao=descricao,
                            quantidade_aulas=quantidade_aulas,
                        )
                        self.eventos.put(
                            (
                                "preenchido",
                                grupo,
                                {
                                    "tipo_registro": "suporte",
                                    "tipo_atendimento": tipo_atendimento,
                                    "descricao": descricao,
                                    "aulas": quantidade_aulas,
                                    "conferencia": pegar_conferencia(),
                                },
                            )
                        )
                        self._status("Formulário pronto — confira e clique em Enviar.")

                    elif acao == "preencher" and comando[1] == "manutencao":
                        (_, _, grupo, itens, outro_texto, descricao, quantidade_aulas,
                         prof_nome, prof_tipo, prof_escola, mostrar) = comando
                        page = self._garantir_navegador(p, visivel=bool(mostrar), escola=prof_escola)
                        iniciar_conferencia()
                        self._status("Abrindo o formulário e preenchendo (manutenção)...")
                        preencher_dados_fixos(page, prof_nome, prof_tipo, prof_escola)
                        preencher_manutencao_equipamentos(
                            page,
                            itens_manutencao=itens,
                            outro_texto=outro_texto,
                            descricao=descricao,
                            quantidade_aulas=quantidade_aulas,
                        )
                        self.eventos.put(
                            (
                                "preenchido",
                                grupo,
                                {
                                    "tipo_registro": "manutencao",
                                    "itens": itens,
                                    "outro_texto": outro_texto,
                                    "descricao": descricao,
                                    "aulas": quantidade_aulas,
                                    "conferencia": pegar_conferencia(),
                                },
                            )
                        )
                        self._status("Formulário pronto — confira e clique em Enviar.")

                    elif acao == "preencher" and comando[1] == "formacao":
                        (_, _, grupo, organizador, outro_texto, descricao, quantidade_aulas,
                         prof_nome, prof_tipo, prof_escola, mostrar) = comando
                        page = self._garantir_navegador(p, visivel=bool(mostrar), escola=prof_escola)
                        iniciar_conferencia()
                        self._status("Abrindo o formulário e preenchendo (formação/reunião)...")
                        preencher_dados_fixos(page, prof_nome, prof_tipo, prof_escola)
                        preencher_formacao_reuniao(
                            page,
                            organizador=organizador,
                            outro_texto=outro_texto,
                            descricao=descricao,
                            quantidade_aulas=quantidade_aulas,
                        )
                        self.eventos.put(
                            (
                                "preenchido",
                                grupo,
                                {
                                    "tipo_registro": "formacao",
                                    "organizador": organizador,
                                    "outro_texto": outro_texto,
                                    "descricao": descricao,
                                    "aulas": quantidade_aulas,
                                    "conferencia": pegar_conferencia(),
                                },
                            )
                        )
                        self._status("Formulário pronto — confira e clique em Enviar.")

                    elif acao == "preencher":
                        (_, _, grupo, n_estudantes, recursos, etapa, conteudos,
                         prof_nome, prof_tipo, prof_escola, subetapa, curso,
                         disciplina, professor, numero_aulas, mostrar) = comando
                        # Nunca grupo.disciplina/professor/numero_aulas direto
                        # daqui pra baixo: os três vêm dos campos editáveis da
                        # tela (ver Janela._coletar_dados_para_preencher) —
                        # pré-preenchidos com os valores da agenda, mas podem
                        # ter sido corrigidos (ex.: a agenda trouxe disciplina
                        # "_OUTROS", sem correspondência conhecida). O que vale
                        # pra SED é o que está escrito ali, não o valor cru da
                        # agenda — que nunca é alterada.
                        page = self._garantir_navegador(p, visivel=bool(mostrar), escola=prof_escola)
                        iniciar_conferencia()
                        self._status("Abrindo o formulário e preenchendo...")
                        preencher_dados_fixos(page, prof_nome, prof_tipo, prof_escola)
                        # "Turma" fica vazia numa aula sem agendamento (ver
                        # Janela._abrir_aula_sem_agendamento); "professor"
                        # também pode ficar vazio ali de propósito — quem está
                        # registrando já aparece na página 1 do formulário,
                        # repetir aqui é redundante e confunde se um dia outra
                        # pessoa reenviar por essa mesma máquina — sem estes
                        # dois "if", o resumo saía com um "()" pendurado ou um
                        # "Prof(a). " sem nome.
                        turma_texto = f" ({grupo.turma})" if grupo.turma else ""
                        professor_texto = f"Prof(a). {professor} - " if professor else ""
                        resumo = (
                            f"{disciplina}{turma_texto} - "
                            f"{professor_texto}{grupo.inicio}-{grupo.fim}"
                        )
                        preencher_atividade_com_estudantes(
                            page,
                            disciplina_agendamento=disciplina,
                            etapa=etapa,
                            resumo_projeto=resumo,
                            numero_aulas=numero_aulas,
                            numero_estudantes=n_estudantes,
                            conteudos_abordados=conteudos,
                            recursos_utilizados=recursos,
                            orientador_tipo=prof_tipo,
                            subetapa=subetapa,
                            curso=curso,
                        )
                        if etapa == ETAPA_PROFISSIONAL:
                            componente = ("CURSO", f"{curso} · {disciplina}")
                        elif etapa == ETAPA_AEE:
                            componente = ("AEE", subetapa)
                        else:
                            componente = resolver_componente(disciplina, etapa)
                            if componente is None:
                                componente = ("OUTRO", disciplina)
                        self.eventos.put(
                            (
                                "preenchido",
                                grupo,
                                {
                                    "tipo_registro": "aula",
                                    "etapa": etapa,
                                    "subetapa": subetapa,
                                    "componente": componente,
                                    "disciplina": disciplina,
                                    "resumo": resumo,
                                    "aulas": numero_aulas,
                                    "estudantes": n_estudantes,
                                    "conteudos": conteudos,
                                    "recursos": recursos,
                                    "conferencia": pegar_conferencia(),
                                },
                            )
                        )
                        self._status("Formulário pronto — confira e clique em Enviar.")

                    elif acao == "conta_google":
                        # ("conta_google", escola)
                        escola_conta = comando[1] if len(comando) > 1 else ""
                        # Abre o formulário SÓ para ver (e resolver) o estado
                        # da conta Google da escola. Nada é preenchido aqui.
                        # Sempre VISÍVEL: é impossível fazer login numa janela
                        # que não aparece.
                        page = self._garantir_navegador(p, visivel=True, escola=escola_conta)
                        self._status("Abrindo o formulário da SED...")
                        estado = abrir_formulario(page)
                        if not estado.get("conectado"):
                            # Avisa AGORA (antes de esperar) que precisa
                            # entrar — só depois disso espera a pessoa
                            # terminar de digitar a senha na janela do
                            # Chrome. A espera é em pedaços curtos (não um
                            # timeout único de minutos): se a pessoa
                            # desistir e clicar "Sair da conta" (ou
                            # fechar o programa) no meio disso, o comando
                            # "sair" cai na fila e este laço solta o
                            # navegador rápido, em vez de segurar a
                            # thread presa aqui e travar o fechamento.
                            self.eventos.put(("conta_google", estado))
                            prazo = time.monotonic() + 300  # 5 min de paciência
                            while time.monotonic() < prazo and self.comandos.empty():
                                try:
                                    page.wait_for_url(
                                        lambda url: "accounts.google.com" not in url
                                        and "signin" not in url.lower(),
                                        timeout=2000,
                                    )
                                    break
                                except Exception:
                                    continue
                            estado = estado_da_conta_google(page)
                        if estado.get("conectado"):
                            # Login resolvido (ou já estava): a janela do
                            # Chrome não precisa mais ficar na tela —
                            # fecha sozinha e o programa volta pra frente.
                            self._fechar_navegador()
                            self.eventos.put(("conta_google_pronta", estado))

                    elif acao == "enviar":
                        _, grupo = comando
                        # Reaproveita o que já está aberto (não abre nada
                        # novo aqui) — mas precisa dizer a MESMA escola de
                        # antes, senão _garantir_navegador acha que trocou
                        # de escola e fecha o formulário preenchido bem na
                        # hora de enviar.
                        page = self._garantir_navegador(
                            p, visivel=self._visivel or False, escola=self._escola_atual or ""
                        )
                        self._status("Enviando para a SED...")
                        enviar(page)
                        # Manutenção/Formação não vêm de agendamento e podem
                        # se repetir de verdade no mesmo dia — não faz
                        # sentido guardar no histórico de "já enviados" (que
                        # existe pra evitar duplicar o registro de uma MESMA
                        # aula). "Aula sem agendamento" É rastreada (ver
                        # rastrear_como_enviado em _RegistroSemAgenda) — sem
                        # isso, o aviso de "já registrada" daquela tela nunca
                        # disparava de verdade (achado em revisão adversarial).
                        if not isinstance(grupo, _RegistroSemAgenda) or grupo.rastrear_como_enviado:
                            marcar_enviado(chave_grupo(grupo))
                        self.eventos.put(("enviado", grupo))
                        self._status("Enviado com sucesso.")

                    elif acao == "sair_google":
                        # ("sair_google", escola)
                        #
                        # Chamado ao clicar "Sair da conta": quem saiu do
                        # programa provavelmente encerrou o uso do
                        # laboratório, e o próximo a usar o computador pode
                        # ser outro professor, de outra escola. Por
                        # segurança, a conta Google institucional não fica
                        # logada esperando o próximo — desloga de verdade
                        # (não só esquece localmente), acessando a página de
                        # logout do Google no perfil desta escola.
                        #
                        # Roda em segundo plano (sem abrir janela visível) e
                        # nunca deixa isto impedir o fechamento do programa:
                        # sem internet, ou se o Google mudar essa página, o
                        # login local só continua guardado até a próxima vez
                        # — não trava nem avisa com erro.
                        escola_sair = comando[1] if len(comando) > 1 else ""
                        try:
                            self._status("Saindo da conta Google da escola...")
                            page = self._garantir_navegador(p, visivel=False, escola=escola_sair)
                            page.goto(
                                "https://accounts.google.com/Logout",
                                wait_until="domcontentloaded",
                                timeout=8000,
                            )
                        except Exception:
                            pass

                    elif acao == "reiniciar":
                        # Só reabre o formulário em branco. Não é preciso
                        # "desfazer" nada: enquanto não se clica em Enviar,
                        # nada chegou na SED.
                        if self._page is not None:
                            try:
                                pagina_fechada = self._page.is_closed()
                            except Exception:
                                pagina_fechada = True
                            if pagina_fechada:
                                # a janela já não existe mais (fechada na
                                # mão, ou travou) — não há o que "limpar",
                                # só descarta a referência morta
                                self._fechar_navegador()
                            else:
                                self._status("Cancelando e limpando o formulário...")
                                self._page.goto(
                                    SED_FORM_URL, wait_until="domcontentloaded", timeout=60000
                                )
                        self._status("Cancelado — nada foi enviado.")

                except Exception as exc:  # noqa: BLE001 - queremos mostrar qualquer erro na tela
                    detalhe = "".join(
                        traceback.format_exception_only(type(exc), exc)
                    ).strip()
                    self.eventos.put(("erro", detalhe, acao))
                    self._status("Deu erro — veja a mensagem abaixo.")

        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Janela
# ---------------------------------------------------------------------------
class Janela(tk.Tk):
    def __init__(self, orientador=None, senha=""):
        super().__init__()
        # quando a pessoa entrou pela tela de login, o professor já vem
        # escolhido e com a senha na mão; sem ela (formato .env antigo), a
        # escolha é feita aqui embaixo como sempre foi
        self._orientador_da_entrada = orientador
        self._senha_da_entrada = senha
        self.sair_da_conta = False
        self.title("Registro de Atividades — SED-SC")
        # A janela se ajusta à tela em vez de ter um tamanho fixo. Num
        # monitor de 1366x768 (comum em escola), ou com o Windows em 125%
        # / 150% de escala, a altura fixa de antes deixava a parte de
        # baixo — justamente o resumo do que foi preenchido — fora da
        # tela, sem jeito de ver.
        #
        # Só o tamanho não resolvia: por isso os botões, o resumo e o
        # rodapé são ancorados no fim da janela e a parte de cima (lista
        # de aulas + dados) rola quando não couber. Ver _montar().
        self.configure(bg=COR_FUNDO)
        self.minsize(880, 520)

        self.comandos: queue.Queue = queue.Queue()
        self.eventos: queue.Queue = queue.Queue()
        self.worker = NavegadorWorker(self.comandos, self.eventos)
        self.worker.start()

        self.grupos: list = []
        self.enviados: set = carregar_enviados()
        self.nao_realizadas: set = carregar_nao_realizadas()
        self.grupo_atual = None
        self.preenchido_para = None
        # Dados do último preenchimento feito por _abrir_aula_sem_agendamento
        # (ver o método). Guardados aqui porque aquela tela é um Toplevel
        # PRÓPRIO que já foi destruído quando "Ver no navegador" tenta
        # preencher de novo — sem isso, o reenvio lia (por engano) os
        # campos da TELA PRINCIPAL, que não têm nada a ver com aquele
        # registro (achado em revisão adversarial, antes de ir pro
        # professor testar).
        self._dados_aula_avulsa = None
        # Resumo do último "preenchido" (ver NavegadorWorker) — guardado à
        # parte porque _enviar() precisa saber se foi "aula" ou "suporte"
        # para montar a mensagem de confirmação certa.
        self._ultimo_resumo_preenchido: dict | None = None
        # Qual cartão de dados está visível agora embaixo da lista de aulas
        # (cartao_dados, cartao_suporte ou cartao_tipo_registro) — usado só
        # por _mostrar_dados_do_registro para rolar a tela até ele.
        self._cartao_ativo = None
        # True do instante em que "enviar" é mandado pra fila até o evento
        # "enviado"/"erro" voltar. Ver `_fechar()`: fechar o programa no
        # meio disso pode deixar um envio que DEU CERTO do lado da SED sem
        # marcar a aula como enviada aqui — risco de duplicar depois.
        self._envio_em_andamento = False
        self._ja_avisadas: set = set()
        # Controla o convite automático pra conferir a conta Google da
        # escola: só faz sentido uma vez por sessão, na primeira agenda
        # carregada — não a cada releitura silenciosa. Ver _processar_evento.
        self._conta_google_verificada = False

        # Professor ativo. Numa escola com dois orientadores dividindo o
        # computador, é ele que define o nome no registro E o login usado
        # para ler a agenda.
        # Quem abre o programa às 19h é, quase certamente, o professor da
        # noite. Então o turno atual decide primeiro; o último escolhido
        # entra como segunda opção (e vale sozinho quando os dois cobrem
        # o mesmo turno, ou quando há um professor só).
        if self._orientador_da_entrada is not None:
            self.orientador = dict(self._orientador_da_entrada)
            self.orientador["senha"] = self._senha_da_entrada
        elif orientador_de_plantao(agora_sc()) is not None:
            self.orientador = orientador_de_plantao(agora_sc())
        else:
            lembrado = carregar_ultimo_professor()
            self.orientador = next(
                (o for o in ORIENTADORES if o["nome"] == lembrado), ORIENTADORES[0]
            )

        # sobra de uma atualização anterior (o .exe antigo), se houver
        limpar_sobras()

        # Job ids dos relógios que se re-agendam sozinhos enquanto o
        # programa está aberto (_ler_eventos, _verificar_inicio_de_aula,
        # _recarregar_silencioso, _procurar_atualizacao_diaria e
        # _piscar_sugerida — ver cada um mais abaixo). Guardados aqui para
        # poder cancelar todos de uma vez no <Destroy>, ligado logo a
        # seguir: sem isto, um after() já agendado tenta rodar depois que
        # a janela (e o interpretador Tcl inteiro, se for a raiz) já foi
        # destruída, e dá "invalid command name" — um erro que nem passa
        # pelo try/except de dentro do relógio, porque o Tcl nem chega a
        # achar o comando pra chamar. Mesmo problema, mesmo remédio, do
        # Caps Lock em configuracao.TelaDeEntrada._checar_caps_lock.
        self._after_ids: dict[str, str] = {}
        self.bind("<Destroy>", self._cancelar_relogios_pendentes, add="+")

        self._montar()
        self._dimensionar()
        # Abre maximizada — pedido do professor. "zoomed" é o estado do
        # Windows (mantém a barra de título com minimizar/fechar, não é
        # um fullscreen sem moldura); mesmo maximizada, _dimensionar()
        # continua valendo por baixo — se algum dia a pessoa restaurar
        # a janela (clicar no meio-quadrado do título), ela volta pro
        # tamanho calculado a partir do conteúdo, não pra um tamanho
        # cravado no código.
        self.state("zoomed")
        # Uma segunda medição, um instante depois de a janela já estar de
        # verdade na tela: com a grade de recursos em 5 colunas, o texto
        # do último grupo ("Notebooks (recurso móvel..." / "Outros
        # recursos") saía cortado, mesmo com as 3 passadas de
        # update_idletasks() dentro de _dimensionar() — a largura real de
        # alguns widgets ttk só fica certa depois que a janela é
        # efetivamente desenhada na tela (mapeada), o que só acontece
        # quando o laço de eventos de verdade roda, não antes. Achado
        # testando a mudança pra 5 colunas — com 2 ou 3 colunas o erro
        # era pequeno o bastante (a folga de _dimensionar) pra não cortar
        # nada, por isso nunca tinha aparecido antes.
        self._after_ids["dimensionar_de_novo"] = self.after(150, self._dimensionar)
        self._after_ids["ler_eventos"] = self.after(100, self._ler_eventos)
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        # Procura versão nova em segundo plano. Numa thread separada
        # porque uma internet lenta não pode segurar a janela fechada.
        threading.Thread(target=self._procurar_atualizacao, daemon=True).start()

        # Antes de qualquer coisa: os dados obrigatórios estão
        # configurados? Se não, avisar AGORA — de nada adianta carregar a
        # agenda se o registro vai sair com o nome ou a escola errados.
        # Mesmo sendo só uma vez (não um relógio que se reagenda), entra
        # no mesmo _after_ids: fechar o programa antes dos 300ms passarem
        # deixa este after() pendente do mesmo jeito, e dá o mesmo
        # "invalid command name" se não for cancelado — visto testando de
        # verdade.
        self._after_ids["checar_configuracao"] = self.after(300, self._checar_configuracao)

        # carrega a agenda sozinho ao abrir
        self._definir_status("Carregando a agenda da semana...")
        self.comandos.put((
            "carregar", False, self.orientador["cpf"], self.orientador["senha"],
            self.orientador.get("escola", ""),
        ))

        # relógio do aviso de início de aula + reconsulta periódica
        self._after_ids["verificar_inicio_de_aula"] = self.after(
            INTERVALO_CHECAGEM_MS, self._verificar_inicio_de_aula
        )
        self._after_ids["recarregar_silencioso"] = self.after(
            INTERVALO_RECONSULTA_MS, self._recarregar_silencioso
        )
        self._after_ids["procurar_atualizacao_diaria"] = self.after(
            INTERVALO_ATUALIZACAO_MS, self._procurar_atualizacao_diaria
        )

    # -- construção da tela -------------------------------------------------
    def _montar(self) -> None:
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("TFrame", background=COR_FUNDO)
        estilo.configure("Cartao.TFrame", background=COR_CARTAO, relief="flat")
        estilo.configure("TLabel", background=COR_FUNDO, foreground=COR_TEXTO)
        estilo.configure("Cartao.TLabel", background=COR_CARTAO, foreground=COR_TEXTO)
        estilo.configure("Suave.TLabel", background=COR_CARTAO, foreground=COR_SUAVE)
        estilo.configure("Titulo.TLabel", background=COR_FUNDO, font=("Segoe UI", 14, "bold"))
        estilo.configure("Sub.TLabel", background=COR_FUNDO, foreground=COR_SUAVE, font=("Segoe UI", 10))
        estilo.configure(
            "Rodape.TLabel", background=COR_FUNDO, foreground=COR_CINZA, font=("Segoe UI", 8)
        )
        estilo.configure("Rodape.TButton", font=("Segoe UI", 8), padding=(6, 2))
        estilo.configure(
            "SubAviso.TLabel",
            background=COR_FUNDO,
            foreground=COR_LARANJA,
            font=("Segoe UI", 10, "bold"),
        )
        estilo.configure("Secao.TLabel", background=COR_CARTAO, font=("Segoe UI", 11, "bold"))
        # Sem cor nenhuma aqui, todo botão (Salvar, Cancelar, Preencher
        # formulário, as próprias abas...) ficava no cinza-claro padrão do
        # tema "clam" com letra preta — um retângulo claro em cima da tela
        # escura, e o "Principal" nem se destacava direito no claro.
        estilo.configure(
            "TButton", font=("Segoe UI", 10), padding=8, background=COR_CARTAO, foreground=COR_TEXTO
        )
        estilo.map(
            "TButton",
            background=[("pressed", COR_CAMPO), ("active", COR_CAMPO)],
            foreground=[("disabled", COR_SUAVE)],
        )
        estilo.configure(
            "Principal.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=10,
            background=COR_DESTAQUE,
            foreground="#ffffff",
        )
        estilo.map(
            "Principal.TButton",
            background=[("pressed", COR_DESTAQUE), ("active", COR_DESTAQUE)],
            foreground=[("disabled", COR_SUAVE)],
        )
        # Aba de recurso (Laboratório/Projetores/Tablets-Celular) que TEM
        # aula acontecendo agora mas não é a aba aberta na tela — mesma cor
        # de aviso usada em "SubAviso.TLabel". Sem isto, duas aulas
        # simultâneas em recursos diferentes só mostrariam a mais recente:
        # trocar para a aba dela escondia a outra sem nenhum sinal de que
        # também precisava de atenção.
        estilo.configure(
            "AvisoAba.TButton",
            font=("Segoe UI", 10, "bold"),
            foreground=COR_LARANJA,
            background=COR_CARTAO,
            padding=8,
        )
        # Link discreto ("Registrar aula sem agendamento", embaixo da
        # tabela) — parece texto sublinhado, não um botão de verdade, para
        # não competir visualmente com "Atualizar agenda"/os outros botões
        # da tela. Precisa do próprio "active" (senão herdava a pílula
        # clara do TButton comum de novo — mesmo bug já corrigido acima).
        estilo.configure(
            "Link.TButton",
            font=("Segoe UI", 9, "underline"),
            foreground=COR_SUAVE,
            background=COR_FUNDO,
            padding=2,
            relief="flat",
            borderwidth=0,
        )
        estilo.map(
            "Link.TButton",
            background=[("active", COR_FUNDO)],
            foreground=[("active", COR_TEXTO)],
        )
        # Sem "foreground" aqui, o texto de QUALQUER Checkbutton/Radiobutton
        # (turnos, tipo de atuação, tipo de registro, recursos utilizados,
        # aparência...) ficava preto por padrão do tema "clam" — ilegível
        # em cima de um cartão escuro. Achado testando o tema escuro de
        # verdade (revisão adversarial confirmou com teste isolado).
        estilo.configure("TCheckbutton", background=COR_CARTAO, foreground=COR_TEXTO)
        estilo.configure("Acoes.TCheckbutton", background=COR_FUNDO, foreground=COR_TEXTO)
        # Faltava esta linha pros Radiobutton (Tipo de registro, Suporte,
        # Formação/Reunião) — sem ela o fundo deles ficava diferente do
        # cartão, dando a impressão de um retângulo cinza atrás do texto
        # ("como se estivesse sublinhado").
        estilo.configure("TRadiobutton", background=COR_CARTAO, foreground=COR_TEXTO)
        # Passar o mouse por cima (estado "active") usa um fundo claro
        # PRÓPRIO do tema "clam", que nunca foi sobrescrito acima — ficava
        # uma pílula branca cobrindo todo o texto no tema escuro, tornando
        # o item ilegível enquanto o mouse estava em cima dele. Achado
        # testando o programa de verdade (bug relatado com prints).
        estilo.map("TCheckbutton", background=[("active", COR_CARTAO)])
        estilo.map("Acoes.TCheckbutton", background=[("active", COR_FUNDO)])
        estilo.map("TRadiobutton", background=[("active", COR_CARTAO)])
        # Campos de digitar (Entry/Combobox) e a tabela de aulas (Treeview)
        # não seguiam o tema — no escuro, ficavam brancos por dentro de um
        # tema escuro por fora, e a tabela nem tinha fundo/letra próprios,
        # sempre a cor padrão do "clam" (branco). Sem isto, trocar pra
        # escuro deixava metade da tela ainda clara.
        estilo.configure(
            "TEntry", fieldbackground=COR_CAMPO, foreground=COR_TEXTO, insertcolor=COR_TEXTO
        )
        estilo.configure("TCombobox", fieldbackground=COR_CAMPO, foreground=COR_TEXTO)
        estilo.map(
            "TCombobox",
            fieldbackground=[("readonly", COR_CAMPO)],
            foreground=[("readonly", COR_TEXTO)],
            selectbackground=[("readonly", COR_CAMPO)],
            selectforeground=[("readonly", COR_TEXTO)],
        )
        estilo.configure(
            "Treeview", background=COR_CARTAO, fieldbackground=COR_CARTAO, foreground=COR_TEXTO
        )
        # "flat" (sem relief nenhum) deixava as colunas do cabeçalho
        # ("Dia e horário", "Professor(a)"...) todas coladas, sem nenhuma
        # linha separando uma da outra — dava pra ler, mas não pra ver
        # onde uma coluna terminava e a próxima começava. Relatado com
        # print de tela, marcando exatamente essa falta de separação.
        estilo.configure(
            "Treeview.Heading", background=COR_FUNDO, foreground=COR_TEXTO, relief="solid",
            borderwidth=1, bordercolor=COR_CINZA,
        )
        estilo.map("Treeview.Heading", background=[("active", COR_FUNDO)])
        # Barra de rolagem: sem isto ficava sempre no cinza-claro padrão
        # do tema "clam", um retângulo claro em cima de um fundo escuro.
        estilo.configure(
            "TScrollbar",
            background=COR_CARTAO,
            troughcolor=COR_FUNDO,
            bordercolor=COR_FUNDO,
            arrowcolor=COR_TEXTO,
        )
        estilo.map(
            "Treeview",
            background=[("selected", SELECAO_BG)],
            foreground=[("selected", SELECAO_FG)],
        )
        self._estilo = estilo  # guardado para o piscar mexer na seleção

        topo = ttk.Frame(self, padding=(20, 8, 20, 4))
        topo.pack(fill="x")
        ttk.Label(topo, text="Registro de Atividades — SED-SC", style="Titulo.TLabel").pack(anchor="w")
        # Escola e nome vêm da configuração, não fixos no código — mas essa
        # linha morou aqui embaixo do título só até este ponto: pedido do
        # próprio professor foi mover pro RODAPÉ ("Registrando como: ..."),
        # junto da barra de conta (Sair da conta/Meus dados), que é onde já
        # se olha pra conferir quem está logado. Ver mais abaixo, perto do
        # rodapé, onde self._identidade_rodape é de fato exibida.
        # ESCOLA é mostrada exatamente como está configurada, sem .title():
        # os nomes do formulário da SED são cheios de siglas (EEB, EEF,
        # CEDUP, CEJA) e o .title() as estragava — "EEB" virava "Eeb".
        #
        # A ÚNICA coisa que continua aqui no topo é o aviso de configuração
        # pendente — esse precisa saltar aos olhos na hora que a janela
        # abre, não esperar a pessoa rolar até o rodapé. Antes ele exibia o
        # texto interno de aviso ("!! PREENCHA ORIENTADOR_NOME NO .env !!"),
        # que parecia defeito do programa em vez de instrução para a pessoa.
        self._identidade_rodape = None
        if configuracao_incompleta():
            ttk.Label(
                topo,
                text="Configuração pendente — abra o arquivo .env e preencha seus dados",
                style="SubAviso.TLabel",
            ).pack(anchor="w", pady=(0, 0))
        else:
            escola_exibida = self.orientador.get("escola") or ESCOLA
            self._identidade_rodape = (
                f"Registrando como: {escola_exibida} · "
                f"{self.orientador.get('nome', ORIENTADOR_NOME)} · Tecnologias Educacionais"
            )

        # Seletor de professor — só aparece quando a escola tem mais de um
        # orientador configurado. Com um professor só, um seletor de uma
        # opção é ruído puro.
        # Com a configuração pela tela, quem troca de professor é a tela de
        # entrada (que pede a senha) — um seletor aqui deixaria qualquer um
        # registrar no nome do outro. Então: seletor no formato antigo,
        # botão de sair no formato novo.
        self.combo_professor = None
        if not SENHAS_SALVAS:
            pass          # a barra de conta fica no rodapé, junto da versão
        elif len(ORIENTADORES) > 1:
            linha_prof = ttk.Frame(topo)
            linha_prof.pack(anchor="w", pady=(10, 0))
            ttk.Label(linha_prof, text="Quem está registrando:").pack(side="left")
            self.combo_professor = ttk.Combobox(
                linha_prof,
                values=[o["nome"] for o in ORIENTADORES],
                width=34,
                state="readonly",
                font=("Segoe UI", 10, "bold"),
            )
            self.combo_professor.set(self.orientador["nome"])
            self.combo_professor.pack(side="left", padx=(8, 0))
            self.combo_professor.bind("<<ComboboxSelected>>", self._trocar_professor)

        # --- área que rola (lista de aulas + dados do registro) ---
        # O que fica FORA dela — botões, resumo e rodapé — é ancorado no
        # fim da janela e nunca sai da tela. O que fica DENTRO rola, se
        # precisar. Assim o resumo do que foi preenchido está sempre à
        # vista, em qualquer tela e em qualquer escala do Windows.
        # (Esta moldura só é empacotada no fim de _montar, depois dos
        # elementos do rodapé — a ordem é o que garante a prioridade.)
        self.area = ttk.Frame(self)
        self._tela = tk.Canvas(
            self.area, background=COR_FUNDO, highlightthickness=0, height=260
        )
        self._barra_area = ttk.Scrollbar(
            self.area, orient="vertical", command=self._tela.yview
        )
        self._tela.configure(yscrollcommand=self._barra_area.set)
        self._tela.pack(side="left", fill="both", expand=True)
        self._barra_visivel = False

        self.conteudo = ttk.Frame(self._tela, style="TFrame")
        self._item_conteudo = self._tela.create_window(
            (0, 0), window=self.conteudo, anchor="nw"
        )
        self.conteudo.bind("<Configure>", lambda _e: self._ajustar_area())
        self._tela.bind("<Configure>", self._tela_redimensionou)
        # roda do mouse (Windows/Mac usam <MouseWheel>; X11 usa Button-4/5)
        self.bind_all("<MouseWheel>", self._rolar_area)
        self.bind_all("<Button-4>", self._rolar_area)
        self.bind_all("<Button-5>", self._rolar_area)

        # --- lista de aulas ---
        cartao_lista = ttk.Frame(self.conteudo, style="Cartao.TFrame", padding=14)
        cartao_lista.pack(fill="x", expand=False, padx=20, pady=(8, 8))

        cabecalho = ttk.Frame(cartao_lista, style="Cartao.TFrame")
        cabecalho.pack(fill="x")
        ttk.Label(cabecalho, text="Aulas da semana", style="Secao.TLabel").pack(side="left")

        # Abas por recurso (Laboratório / Projetores / Tablets-Celular) —
        # só a maioria das escolas tem só o laboratório mesmo, então essa
        # linha começa ESCONDIDA e só aparece se a agenda de verdade trouxer
        # aula de mais de uma categoria (ver _atualizar_abas_recurso). Os 3
        # botões já nascem aqui, prontos, só entrando/saindo da tela com
        # pack/pack_forget — não recriados a cada atualização de agenda.
        self._linha_abas_recurso = ttk.Frame(cartao_lista, style="Cartao.TFrame")
        self._linha_abas_recurso.pack(fill="x", pady=(8, 0))
        self.categoria_atual = "Laboratório"
        self.botoes_categoria = {}
        for cat in CATEGORIAS_RECURSO_EM_ORDEM:
            botao = ttk.Button(
                self._linha_abas_recurso, text=cat, command=lambda c=cat: self._selecionar_categoria(c)
            )
            self.botoes_categoria[cat] = botao
        # "Manutenção" e "Formação/Reunião" não dependem da agenda (ver
        # CATEGORIAS_INDEPENDENTES) — ficam SEMPRE visíveis, ao contrário
        # das de cima.
        for cat in CATEGORIAS_INDEPENDENTES:
            botao = ttk.Button(
                self._linha_abas_recurso, text=cat, command=lambda c=cat: self._selecionar_categoria(c)
            )
            self.botoes_categoria[cat] = botao

        corpo_lista = ttk.Frame(cartao_lista, style="Cartao.TFrame")
        corpo_lista.pack(fill="both", expand=True, pady=(10, 0))
        self.corpo_lista = corpo_lista

        colunas = ("quando", "professor", "disciplina", "turma", "situacao")
        self.tabela = ttk.Treeview(
            corpo_lista, columns=colunas, show="headings", height=5, selectmode="browse"
        )
        # larguras somando pouco menos que a janela, senão a última coluna
        # ("Situação") fica cortada fora da tela.
        for col, titulo, largura, estica in (
            # "DD/MM  HH:MM-HH:MM" é sempre do mesmo tamanho — a coluna
            # acompanha exatamente esse texto, sem sobra de espaço vazio.
            ("quando", "Dia e horário", 125, False),
            ("professor", "Professor(a)", 200, True),
            ("disciplina", "Disciplina", 195, True),
            # BEM mais larga: a agenda do NTE nomeia a turma de um jeito
            # verboso e repetitivo ("Anos Iniciais - 3º ano - Anos
            # Iniciais"), quase 40 caracteres — 230px ainda cortava no
            # meio da palavra. Testado contra texto real (print de tela),
            # não só estimado.
            ("turma", "Turma", 360, True),
            # larga o bastante para "○ Ainda não ocorreu" caber inteiro —
            # antes esse texto aparecia cortado
            ("situacao", "Situação", 158, False),
        ):
            self.tabela.heading(col, text=titulo)
            self.tabela.column(col, width=largura, anchor="w", stretch=estica)
        barra = ttk.Scrollbar(corpo_lista, orient="vertical", command=self.tabela.yview)
        self.tabela.configure(yscrollcommand=barra.set)
        self.tabela.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.tabela.bind("<<TreeviewSelect>>", self._ao_selecionar)
        # Uma cor por situação. Antes "Já enviada" e "Ainda não ocorreu"
        # dividiam o mesmo cinza, então não dava para distinguir de relance
        # o que já foi resolvido do que ainda nem aconteceu.
        self.tabela.tag_configure("enviada", foreground=COR_AZUL)
        self.tabela.tag_configure("nao_realizada", foreground=COR_LARANJA)
        self.tabela.tag_configure("futura", foreground=COR_CINZA)
        self.tabela.tag_configure("pendente", foreground=COR_TEXTO)
        self.tabela.tag_configure(
            "sugerida", background=VERDE_PISCA[0], foreground=COR_SUGERIDA_FG
        )
        self._after_ids["piscar_sugerida"] = self.after(INTERVALO_PISCA_MS, self._piscar_sugerida)

        # --- "não agendou? registra assim mesmo" -------------------------
        # Às vezes o laboratório/tablet/projetor é usado sem reserva na
        # agenda do NTE — a aula precisa ir pra SED do mesmo jeito.
        # Discreto de propósito (link, não um botão chamativo): é o caso
        # raro, não o comum, e não pode competir visualmente com
        # "Atualizar agenda" ou com a tabela em si. Some junto da tabela
        # nas abas Manutenção/Formação (ver _atualizar_abas_recurso) — lá
        # já existe o próprio jeito de registrar sem agenda.
        self.rodape_aula_avulsa = ttk.Frame(cartao_lista, style="Cartao.TFrame")
        self.rodape_aula_avulsa.pack(fill="x", pady=(8, 0))
        ttk.Label(
            self.rodape_aula_avulsa,
            text="Não achou a sua aula na lista acima?",
            style="Suave.TLabel",
        ).pack(side="left")
        ttk.Button(
            self.rodape_aula_avulsa,
            text="Registrar aula sem agendamento",
            style="Link.TButton",
            command=self._abrir_aula_sem_agendamento,
        ).pack(side="left", padx=(6, 0))

        # --- tipo de registro (só aparece para Projetores/Tablets-Celular) ---
        # Um agendamento de Laboratório sempre foi só uma coisa: aula com
        # estudantes. Mas um de Projetor/Tablets pode ser isso OU o
        # professor orientador só foi instalar/dar suporte a um
        # equipamento levado para outra sala — fluxo BEM mais simples no
        # formulário da SED (ver preencher_suporte_outros_espacos). Como
        # os dois usam o mesmo agendamento, pergunta explicitamente toda
        # vez em vez de adivinhar: nenhuma opção vem pré-marcada.
        self.cartao_tipo_registro = ttk.Frame(self.conteudo, style="Cartao.TFrame", padding=14)
        ttk.Label(
            self.cartao_tipo_registro, text="Tipo de registro", style="Secao.TLabel"
        ).pack(anchor="w")
        self.var_tipo_registro = tk.StringVar(value="")
        linha_tipo_registro = ttk.Frame(self.cartao_tipo_registro, style="Cartao.TFrame")
        linha_tipo_registro.pack(fill="x", pady=(6, 0))
        ttk.Radiobutton(
            linha_tipo_registro,
            text="Aula com estudantes",
            value="aula",
            variable=self.var_tipo_registro,
            command=self._ao_escolher_tipo_registro,
        ).pack(side="left", padx=(0, 24))
        ttk.Radiobutton(
            linha_tipo_registro,
            text="Suporte/instalação de equipamento",
            value="suporte",
            variable=self.var_tipo_registro,
            command=self._ao_escolher_tipo_registro,
        ).pack(side="left")

        # --- dados da aula ---
        # Não empacota ainda: fica em branco até uma aula ser selecionada
        # (ver _atualizar_area_dados_registro) — antes disso não há nada
        # pra mostrar, então nem aparece.
        cartao_dados = ttk.Frame(self.conteudo, style="Cartao.TFrame", padding=14)
        self.cartao_dados = cartao_dados
        self._cartao_ativo = None

        ttk.Label(cartao_dados, text="Dados do registro", style="Secao.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        self.rotulo_aula = ttk.Label(
            cartao_dados, text="Nenhuma aula selecionada.", style="Suave.TLabel"
        )
        self.rotulo_aula.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 10))

        # Disciplina, professor(a), nº de aulas, nº de estudantes e etapa —
        # tudo numa barra só, lado a lado (não uma linha embaixo da outra).
        # Os três primeiros vêm da agenda (grupo.*), mas editáveis: quando
        # a agenda traz algo errado ou sem correspondência (ex.: disciplina
        # "_OUTROS"), esse texto ia LITERALMENTE assim pro formulário da
        # SED. Mesma filosofia do "Conteúdo aplicado" logo abaixo —
        # pré-preenchido, editável, e o que vale pra SED é o que está
        # escrito aqui, não o valor cru da agenda (que nunca é alterada
        # por isto — ver resposta ao professor sobre esse pedido).
        ttk.Label(
            cartao_dados,
            text=(
                "Disciplina, professor(a), nº de aulas, nº de estudantes e etapa "
                "(os 3 primeiros vêm da agenda — edite se precisar corrigir):"
            ),
            style="Cartao.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 4))
        linha_disciplina = ttk.Frame(cartao_dados, style="Cartao.TFrame")
        linha_disciplina.grid(row=3, column=0, columnspan=4, sticky="ew")

        ttk.Label(linha_disciplina, text="Disciplina:", style="Cartao.TLabel").pack(side="left")
        # width=20 cortava nomes reais da agenda ("Língua Estrangeira -
        # Inglês" virava "Língua Estrangeira - Ing", relatado com print) —
        # a janela larga o que precisar pra caber (ver _dimensionar), então
        # não tem por que economizar largura aqui.
        self.campo_disciplina = ttk.Entry(linha_disciplina, width=32, font=("Segoe UI", 10))
        self.campo_disciplina.pack(side="left", padx=(6, 14))

        ttk.Label(linha_disciplina, text="Professor(a):", style="Cartao.TLabel").pack(side="left")
        # Mesmo motivo: nomes completos ("Cristhine Fabiola De Ramos",
        # "Edina Silvia Netto Wilhelm") passavam de 23 e cortavam.
        self.campo_professor = ttk.Entry(linha_disciplina, width=30, font=("Segoe UI", 10))
        self.campo_professor.pack(side="left", padx=(6, 14))

        ttk.Label(linha_disciplina, text="Nº de aulas:", style="Cartao.TLabel").pack(side="left")
        self.campo_numero_aulas = ttk.Entry(linha_disciplina, width=4, font=("Segoe UI", 10))
        self.campo_numero_aulas.pack(side="left", padx=(6, 14))

        ttk.Label(linha_disciplina, text="Nº de estudantes:", style="Cartao.TLabel").pack(side="left")
        self.campo_estudantes = ttk.Entry(linha_disciplina, width=5, font=("Segoe UI", 11))
        self.campo_estudantes.pack(side="left", padx=(6, 14))
        self.campo_estudantes.bind("<Return>", lambda _e: self._preencher())

        ttk.Label(linha_disciplina, text="Etapa:", style="Cartao.TLabel").pack(side="left")
        # width=42 (não menor): "Ensino Fundamental - Anos Iniciais" sozinho
        # já tem 35 caracteres — um combobox mais estreito cortaria o texto.
        self.combo_etapa = ttk.Combobox(linha_disciplina, values=ETAPAS, width=42, state="readonly")
        self.combo_etapa.pack(side="left", padx=(6, 0))
        self.combo_etapa.bind("<<ComboboxSelected>>", lambda _e: self._ajustar_campo_extra())

        ttk.Label(
            cartao_dados,
            text="Disciplina/professor(a)/nº de aulas não alteram a agenda do NTE — vale só para este envio à SED.",
            style="Suave.TLabel",
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(3, 10))

        # Linha que só existe para as etapas com página própria no
        # formulário: AEE e EJA perguntam "Qual etapa?" antes de seguir, e
        # o Ensino Profissional pergunta o curso. Fica escondida no resto
        # do tempo (grid_remove) para não poluir a tela de todo dia.
        self.linha_extra = ttk.Frame(cartao_dados, style="Cartao.TFrame")
        self.linha_extra.grid(row=6, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.rotulo_extra = ttk.Label(self.linha_extra, text="", style="Cartao.TLabel")
        self.rotulo_extra.pack(side="left")
        self.combo_extra = ttk.Combobox(self.linha_extra, values=[], width=36, state="readonly")
        self.campo_curso = ttk.Entry(self.linha_extra, width=40, font=("Segoe UI", 10))
        self.dica_extra = ttk.Label(self.linha_extra, text="", style="Suave.TLabel")
        self.linha_extra.grid_remove()

        ttk.Label(
            cartao_dados,
            text="Conteúdo aplicado (é o que vai no campo de conteúdos da SED):",
            style="Cartao.TLabel",
        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(12, 4))
        self.campo_conteudo = tk.Text(
            cartao_dados,
            height=2,
            wrap="word",
            font=("Segoe UI", 10),
            relief="solid",
            borderwidth=1,
            background=COR_CAMPO,
            foreground=COR_TEXTO,
            insertbackground=COR_TEXTO,
        )
        self.campo_conteudo.grid(row=8, column=0, columnspan=4, sticky="ew")
        cartao_dados.columnconfigure(3, weight=1)
        ttk.Label(
            cartao_dados,
            text="Vem preenchido com o assunto lançado na agenda — edite à vontade.",
            style="Suave.TLabel",
        ).grid(row=9, column=0, columnspan=4, sticky="w", pady=(3, 0))

        ttk.Label(cartao_dados, text="Recursos utilizados:", style="Cartao.TLabel").grid(
            row=10, column=0, columnspan=4, sticky="w", pady=(12, 4)
        )
        caixa_recursos = ttk.Frame(cartao_dados, style="Cartao.TFrame")
        caixa_recursos.grid(row=11, column=0, columnspan=4, sticky="w")
        self.vars_recursos: dict = {}
        # Colunas preenchidas de cima para baixo, DUAS linhas cada (e não
        # em ziguezague): pedido do professor pra ocupar toda a largura
        # que sobrava à direita das três colunas de antes — com só 2 por
        # coluna, 9 recursos viram 5 colunas em vez de 3, esticando o
        # grupo pela tela toda. A última coluna fica com um item sozinho
        # (9 não é múltiplo de 2) — é esperado, não um bug de contagem.
        # Nome COMPLETO na tela, igual ao do formulário da SED — nunca
        # encurtado. "no laboratório" e "recurso móvel para sala de aula"
        # são justamente o que distingue um recurso do outro na hora de
        # marcar; um "Notebooks — software" abreviado já foi tentado e o
        # professor sentiu falta dessa informação.
        # A largura da janela é calculada a partir do que precisa caber
        # dentro dela (ver _dimensionar), não o contrário — então mais
        # colunas só fazem a janela ficar mais larga, sem cortar nada.
        por_coluna = 2
        for i, recurso in enumerate(RECURSOS_DISPONIVEIS):
            # Nenhum vem pré-marcado: quem registra escolhe cada vez, na
            # mão, o que realmente foi usado naquela aula (RECURSOS_PADRAO
            # é só o padrão do modo linha de comando, em main.py — a tela
            # não usa mais isso pra pré-marcar nada).
            var = tk.BooleanVar(value=False)
            self.vars_recursos[recurso] = var
            ttk.Checkbutton(caixa_recursos, text=recurso, variable=var).grid(
                row=i % por_coluna, column=i // por_coluna, sticky="w",
                padx=(0, 18), pady=1
            )

        # --- suporte/instalação de equipamento (Projetor, Tablets/Celular) ---
        # Fluxo BEM mais simples que o de cima: uma página só no formulário,
        # 3 perguntas — nada de nº de estudantes, etapa ou "Recursos
        # utilizados" (ver preencher_suporte_outros_espacos). Escondido por
        # padrão; _atualizar_area_dados_registro mostra este OU cartao_dados,
        # nunca os dois.
        cartao_suporte = ttk.Frame(self.conteudo, style="Cartao.TFrame", padding=14)
        self.cartao_suporte = cartao_suporte

        ttk.Label(cartao_suporte, text="Dados do suporte", style="Secao.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self.rotulo_aula_suporte = ttk.Label(cartao_suporte, text="", style="Suave.TLabel")
        self.rotulo_aula_suporte.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 10))

        ttk.Label(
            cartao_suporte,
            text="Qual foi o atendimento/suporte realizado?",
            style="Cartao.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.var_tipo_suporte = tk.StringVar(value="")
        for i, texto in enumerate(TIPOS_DE_SUPORTE):
            ttk.Radiobutton(
                cartao_suporte, text=texto, value=texto, variable=self.var_tipo_suporte,
            ).grid(row=3 + i, column=0, columnspan=2, sticky="w", pady=1)
        linha_base = 3 + len(TIPOS_DE_SUPORTE)

        ttk.Label(
            cartao_suporte,
            text="Breve descrição da atividade (quem, onde e para quê):",
            style="Cartao.TLabel",
        ).grid(row=linha_base, column=0, columnspan=2, sticky="w", pady=(12, 4))
        self.campo_descricao_suporte = ttk.Entry(cartao_suporte, width=70, font=("Segoe UI", 10))
        self.campo_descricao_suporte.grid(row=linha_base + 1, column=0, columnspan=2, sticky="ew")
        cartao_suporte.columnconfigure(1, weight=1)

        ttk.Label(cartao_suporte, text="Quantidade de aulas:", style="Cartao.TLabel").grid(
            row=linha_base + 2, column=0, sticky="w", pady=(12, 0)
        )
        self.campo_aulas_suporte = ttk.Entry(cartao_suporte, width=8, font=("Segoe UI", 11))
        self.campo_aulas_suporte.grid(
            row=linha_base + 2, column=1, sticky="w", padx=(8, 0), pady=(12, 0)
        )
        self.campo_aulas_suporte.bind("<Return>", lambda _e: self._preencher())

        # --- suporte a outros espaços (aba independente, sem agenda) ---
        # Mesmos 3 campos do cartao_suporte acima (o vindo da agenda) — mas
        # com widgets PRÓPRIOS, não reaproveitados: os dois ficam visíveis
        # em momentos diferentes (nunca ao mesmo tempo), só que se
        # compartilhassem variável, "Ver no navegador" correria o risco de
        # reler o suporte errado — a mesma classe de bug já encontrada e
        # corrigida para "Aula sem agendamento" (ver _dados_aula_avulsa).
        cartao_suporte_avulso = ttk.Frame(self.conteudo, style="Cartao.TFrame", padding=14)
        self.cartao_suporte_avulso = cartao_suporte_avulso

        ttk.Label(
            cartao_suporte_avulso, text="Suporte a outros espaços", style="Secao.TLabel"
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            cartao_suporte_avulso,
            text="Qual foi o atendimento/suporte realizado?",
            style="Cartao.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 4))
        self.var_suporte_avulso_tipo = tk.StringVar(value="")
        for i, texto in enumerate(TIPOS_DE_SUPORTE):
            ttk.Radiobutton(
                cartao_suporte_avulso, text=texto, value=texto,
                variable=self.var_suporte_avulso_tipo,
            ).grid(row=2 + i, column=0, columnspan=2, sticky="w", pady=1)
        linha_base_s = 2 + len(TIPOS_DE_SUPORTE)

        ttk.Label(
            cartao_suporte_avulso,
            text="Breve descrição da atividade (quem, onde e para quê):",
            style="Cartao.TLabel",
        ).grid(row=linha_base_s, column=0, columnspan=2, sticky="w", pady=(12, 4))
        self.campo_suporte_avulso_descricao = ttk.Entry(
            cartao_suporte_avulso, width=70, font=("Segoe UI", 10)
        )
        self.campo_suporte_avulso_descricao.grid(
            row=linha_base_s + 1, column=0, columnspan=2, sticky="ew"
        )
        cartao_suporte_avulso.columnconfigure(1, weight=1)

        ttk.Label(
            cartao_suporte_avulso, text="Quantidade de aulas:", style="Cartao.TLabel"
        ).grid(row=linha_base_s + 2, column=0, sticky="w", pady=(12, 0))
        self.campo_suporte_avulso_aulas = ttk.Entry(
            cartao_suporte_avulso, width=8, font=("Segoe UI", 11)
        )
        self.campo_suporte_avulso_aulas.grid(
            row=linha_base_s + 2, column=1, sticky="w", padx=(8, 0), pady=(12, 0)
        )
        self.campo_suporte_avulso_aulas.bind("<Return>", lambda _e: self._preencher())

        # --- manutenção de equipamentos (aba independente, sem agenda) ---
        cartao_manutencao = ttk.Frame(self.conteudo, style="Cartao.TFrame", padding=14)
        self.cartao_manutencao = cartao_manutencao

        ttk.Label(
            cartao_manutencao, text="Manutenção de equipamentos", style="Secao.TLabel"
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            cartao_manutencao,
            text="O que recebeu manutenção? (marque quantos precisar)",
            style="Cartao.TLabel",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 4))
        self.vars_manutencao: dict = {}
        caixa_manutencao = ttk.Frame(cartao_manutencao, style="Cartao.TFrame")
        caixa_manutencao.grid(row=2, column=0, columnspan=4, sticky="w")
        colunas_manutencao = 2
        por_coluna_m = -(-len(OPCOES_MANUTENCAO) // colunas_manutencao)
        for i, item in enumerate(OPCOES_MANUTENCAO):
            var = tk.BooleanVar(value=False)
            self.vars_manutencao[item] = var
            ttk.Checkbutton(caixa_manutencao, text=item, variable=var).grid(
                row=i % por_coluna_m, column=i // por_coluna_m, sticky="w",
                padx=(0, 18), pady=1
            )
        linha_outro_m = ttk.Frame(cartao_manutencao, style="Cartao.TFrame")
        linha_outro_m.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.var_manutencao_outro = tk.BooleanVar(value=False)
        ttk.Checkbutton(linha_outro_m, text="Outro:", variable=self.var_manutencao_outro).pack(
            side="left"
        )
        # registrado também no dicionário — quem coleta os dados (ver
        # _coletar_dados_manutencao) trata "Outro:" igual aos outros itens.
        self.vars_manutencao["Outro:"] = self.var_manutencao_outro
        self.campo_manutencao_outro = ttk.Entry(linha_outro_m, width=40, font=("Segoe UI", 10))
        self.campo_manutencao_outro.pack(side="left", padx=(8, 0))

        ttk.Label(
            cartao_manutencao, text="Breve descrição da manutenção:", style="Cartao.TLabel"
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(12, 4))
        self.campo_manutencao_descricao = ttk.Entry(
            cartao_manutencao, width=70, font=("Segoe UI", 10)
        )
        self.campo_manutencao_descricao.grid(row=5, column=0, columnspan=4, sticky="ew")
        cartao_manutencao.columnconfigure(3, weight=1)

        ttk.Label(cartao_manutencao, text="Quantidade de aulas:", style="Cartao.TLabel").grid(
            row=6, column=0, sticky="w", pady=(12, 0)
        )
        self.campo_manutencao_aulas = ttk.Entry(cartao_manutencao, width=8, font=("Segoe UI", 11))
        self.campo_manutencao_aulas.grid(row=6, column=1, sticky="w", padx=(8, 0), pady=(12, 0))
        self.campo_manutencao_aulas.bind("<Return>", lambda _e: self._preencher())

        # --- formação/reunião (aba independente, sem agenda) ---
        cartao_formacao = ttk.Frame(self.conteudo, style="Cartao.TFrame", padding=14)
        self.cartao_formacao = cartao_formacao

        ttk.Label(cartao_formacao, text="Formação/Reunião", style="Secao.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        ttk.Label(
            cartao_formacao, text="Quem organizou a reunião/formação?", style="Cartao.TLabel"
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 4))
        self.var_formacao_organizador = tk.StringVar(value="")
        for i, texto in enumerate(ORGANIZADORES_DE_FORMACAO):
            ttk.Radiobutton(
                cartao_formacao, text=texto, value=texto, variable=self.var_formacao_organizador,
            ).grid(row=2 + i, column=0, columnspan=4, sticky="w", pady=1)
        linha_base_f = 2 + len(ORGANIZADORES_DE_FORMACAO)
        linha_outro_f = ttk.Frame(cartao_formacao, style="Cartao.TFrame")
        linha_outro_f.grid(row=linha_base_f, column=0, columnspan=4, sticky="w", pady=(1, 0))
        ttk.Radiobutton(
            linha_outro_f, text="Outro:", value="Outro:", variable=self.var_formacao_organizador,
        ).pack(side="left")
        self.campo_formacao_outro = ttk.Entry(linha_outro_f, width=40, font=("Segoe UI", 10))
        self.campo_formacao_outro.pack(side="left", padx=(8, 0))

        ttk.Label(
            cartao_formacao, text="Breve descrição do encontro:", style="Cartao.TLabel"
        ).grid(row=linha_base_f + 1, column=0, columnspan=4, sticky="w", pady=(12, 4))
        self.campo_formacao_descricao = ttk.Entry(cartao_formacao, width=70, font=("Segoe UI", 10))
        self.campo_formacao_descricao.grid(row=linha_base_f + 2, column=0, columnspan=4, sticky="ew")
        cartao_formacao.columnconfigure(3, weight=1)

        ttk.Label(cartao_formacao, text="Quantidade de aulas:", style="Cartao.TLabel").grid(
            row=linha_base_f + 3, column=0, sticky="w", pady=(12, 0)
        )
        self.campo_formacao_aulas = ttk.Entry(cartao_formacao, width=8, font=("Segoe UI", 11))
        self.campo_formacao_aulas.grid(
            row=linha_base_f + 3, column=1, sticky="w", padx=(8, 0), pady=(12, 0)
        )
        self.campo_formacao_aulas.bind("<Return>", lambda _e: self._preencher())

        # --- ações ---
        # (empacotadas no fim do método, ancoradas na base da janela)
        acoes = ttk.Frame(self, padding=(20, 6, 20, 6))
        self.botao_preencher = ttk.Button(
            acoes, text="Preencher formulário", style="Principal.TButton", command=self._preencher
        )
        self.botao_preencher.pack(side="left")
        self.botao_enviar = ttk.Button(
            acoes,
            text="Enviar para a SED",
            style="Principal.TButton",
            command=self._enviar,
            state="disabled",
        )
        self.botao_enviar.pack(side="left", padx=(10, 0))
        # Preencher acontece em segundo plano (headless) por padrão — sem
        # isto não havia como conferir o formulário já preenchido com os
        # próprios olhos antes de mandar. A tentação, sem este botão, é
        # usar "Conta Google da escola" pra abrir uma janela — só que
        # aquilo abre outra janela, DESCARTANDO o preenchimento em
        # segundo plano sem avisar (ver aviso em _conferir_conta_google).
        self.botao_ver_no_navegador = ttk.Button(
            acoes,
            text="Ver no navegador",
            command=self._ver_no_navegador,
            state="disabled",
        )
        self.botao_ver_no_navegador.pack(side="left", padx=(10, 0))
        self.botao_cancelar = ttk.Button(
            acoes, text="Cancelar e voltar ao início", command=self._cancelar
        )
        self.botao_cancelar.pack(side="left", padx=(10, 0))
        self.botao_nao_realizada = ttk.Button(
            acoes, text="Aula não realizada", command=self._alternar_nao_realizada
        )
        self.botao_nao_realizada.pack(side="right")

        # O preenchimento acontece em segundo plano. Quem quiser assistir —
        # para conferir com os próprios olhos, ou porque algo saiu errado e
        # é preciso ver onde — marca aqui e o navegador aparece.
        self.mostrar_navegador = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            acoes,
            text="Ver o formulário sendo preenchido",
            variable=self.mostrar_navegador,
            style="Acoes.TCheckbutton",
        ).pack(side="right", padx=(0, 16))

        # --- status e resumo ---
        cartao_status = ttk.Frame(self, style="Cartao.TFrame", padding=14)
        self.rotulo_status = ttk.Label(
            cartao_status, text="Iniciando...", style="Cartao.TLabel", font=("Segoe UI", 10, "bold")
        )
        self.rotulo_status.pack(anchor="w")
        corpo_resumo = ttk.Frame(cartao_status, style="Cartao.TFrame")
        corpo_resumo.pack(fill="both", expand=True, pady=(8, 0))
        self.texto_resumo = tk.Text(
            corpo_resumo,
            height=4,
            wrap="word",
            relief="flat",
            background=COR_CAMPO,
            foreground=COR_TEXTO,
            insertbackground=COR_TEXTO,
            font=("Consolas", 10),
        )
        self._barra_resumo = ttk.Scrollbar(
            corpo_resumo, orient="vertical", command=self.texto_resumo.yview
        )
        self.texto_resumo.configure(yscrollcommand=self._barra_resumo.set)
        self.texto_resumo.pack(side="left", fill="both", expand=True)
        self._barra_resumo_visivel = False
        self.texto_resumo.configure(state="disabled")
        self.texto_resumo.bind("<Configure>", lambda _e: self._ajustar_barra_resumo())

        # --- rodapé: versão instalada ---
        # Discreto, mas presente: quando um professor relata um problema,
        # a primeira pergunta é sempre "qual versão você está usando?" —
        # e ninguém vai abrir arquivo nenhum para descobrir.
        rodape = ttk.Frame(self, padding=(20, 0, 20, 6))
        ttk.Label(
            rodape,
            text=f"Versão {atualizador.versao_atual()}",
            style="Rodape.TLabel",
        ).pack(side="right")
        ttk.Label(
            rodape,
            text="Desenvolvido por ArnoNeto1",
            style="Rodape.TLabel",
        ).pack(side="right", padx=(0, 16))
        ttk.Button(
            rodape, text="Procurar atualização", style="Rodape.TButton",
            command=self._procurar_atualizacao_agora,
        ).pack(side="right", padx=(0, 10))
        ttk.Button(
            rodape, text="Conta Google da escola", style="Rodape.TButton",
            command=self._conferir_conta_google,
        ).pack(side="right", padx=(0, 10))
        # Testando ao lado de "Conta Google da escola" — outra opção de
        # lugar pra "Atualizar agenda" (já esteve no cabeçalho da lista de
        # aulas, depois do lado de "Formação/Reunião").
        ttk.Button(
            rodape, text="Atualizar agenda", style="Rodape.TButton",
            command=self._recarregar,
        ).pack(side="right", padx=(0, 10))

        # Barra de conta no rodapé, e não no alto: ali ela não disputa
        # altura com a lista de aulas e com os campos do registro, que é
        # o que a pessoa precisa ver numa tela pequena. E fica ao lado da
        # versão, que é o outro dado "sobre o programa", não sobre a aula.
        #
        # "Registrando como: escola · nome · cargo" (self._identidade_rodape,
        # calculada lá no topo) mora aqui agora — antes ficava embaixo do
        # título "Registro de Atividades", pedido do próprio professor pra
        # descer pro rodapé, junto de Sair da conta/Meus dados.
        if self._identidade_rodape:
            ttk.Label(
                rodape,
                text=self._identidade_rodape,
                style="Rodape.TLabel",
            ).pack(side="left")
        if not SENHAS_SALVAS:
            ttk.Button(
                rodape, text="Sair da conta", style="Rodape.TButton",
                command=self._sair_da_conta,
            ).pack(side="left", padx=(10, 0))
            ttk.Button(
                rodape, text="Meus dados", style="Rodape.TButton",
                command=self._editar_cadastro,
            ).pack(side="left", padx=(6, 0))

        # --- ordem de empacotamento (é ela que decide quem some) ---------
        # O Tk atende os widgets na ordem em que são empacotados. Os de
        # baixo entram PRIMEIRO, então recebem a altura de que precisam
        # antes de tudo; a área rolável entra por último e fica com o que
        # sobrou — encolhendo (e mostrando a barra) em vez de empurrar o
        # resumo para fora da tela, como acontecia antes.
        rodape.pack(side="bottom", fill="x")
        cartao_status.pack(side="bottom", fill="both", expand=True, padx=20, pady=(6, 4))
        acoes.pack(side="bottom", fill="x")
        self.area.pack(side="top", fill="both", expand=False)

    # -- campo extra por etapa ----------------------------------------------
    def _ajustar_campo_extra(self, sugerir_de: str = "") -> None:
        """
        Mostra (ou esconde) o campo que só algumas etapas exigem.

        No formulário da SED, três etapas fogem do caminho comum:

          AEE .................. pergunta "Qual etapa?" (3 opções) e NÃO tem
                                 opção "Outro:" — era exatamente aqui que o
                                 programa quebrava com
                                 "Não encontrei o checkbox 'Outro:'".
          EJA .................. pergunta "Qual etapa?" (Fundamental/Médio)
                                 antes da lista de componentes.
          Ensino Profissional .. pergunta o curso, em texto livre.

        `sugerir_de` é o texto da turma, usado só para já deixar a resposta
        provável preenchida.
        """
        etapa = self.combo_etapa.get().strip()
        self.combo_extra.pack_forget()
        self.campo_curso.pack_forget()
        self.dica_extra.pack_forget()

        opcoes = opcoes_subetapa(etapa)
        if opcoes:
            self.rotulo_extra.configure(text="Qual etapa? (exigido pela SED):")
            self.combo_extra.configure(values=opcoes)
            if sugerir_de:
                self.combo_extra.set(subetapa_sugerida(sugerir_de, etapa))
            elif self.combo_extra.get() not in opcoes:
                self.combo_extra.set("")
            self.combo_extra.pack(side="left", padx=(8, 0))
            self.dica_extra.configure(
                text="confira — esta etapa pede essa resposta no formulário"
            )
            self.dica_extra.pack(side="left", padx=(10, 0))
            self.linha_extra.grid()
        elif etapa == ETAPA_PROFISSIONAL:
            self.rotulo_extra.configure(text="Qual o curso?")
            if sugerir_de:
                self.campo_curso.delete(0, "end")
                self.campo_curso.insert(0, curso_sugerido(sugerir_de))
            self.campo_curso.pack(side="left", padx=(8, 0))
            self.dica_extra.configure(text="vem da turma da agenda — corrija se precisar")
            self.dica_extra.pack(side="left", padx=(10, 0))
            self.linha_extra.grid()
        else:
            self.linha_extra.grid_remove()

    # -- tamanho da janela --------------------------------------------------
    def _dimensionar(self) -> None:
        """
        Abre a janela do tamanho que o conteúdo pede — sem passar da tela.

        Nada de altura fixa: com o Windows em 125%/150% de escala, ou num
        monitor de 1366x768, um número cravado no código deixava a parte
        de baixo (o resumo do que foi preenchido) fora da tela. Aqui o
        próprio Tk informa de quanto precisa; se não couber, a janela para
        no limite da tela e a área de cima passa a rolar.
        """
        # Duas passadas: a primeira ajusta a área rolável (que pode fazer a
        # barra de rolagem aparecer), a segunda mede a janela JÁ com ela.
        # Medindo só uma vez, a largura saía 14 px curta e o texto do
        # último recurso ficava cortado.
        for _ in range(3):
            self.update_idletasks()
            self._ajustar_area()
        self.update_idletasks()
        # Maximizada (self.state("zoomed") no __init__, chamado ANTES da
        # segunda passada agendada por after() — ver ali) um geometry()
        # aqui tiraria a janela do maximizado. As _ajustar_area() de cima
        # já bastam pra acertar a área rolável/barra por dentro dela.
        if self.state() == "zoomed":
            return
        # Reserva a largura da barra de rolagem mesmo quando ela ainda não
        # apareceu: com a janela aberta no tamanho da tela ela quase sempre
        # aparece, e aí comeria justamente o fim do texto dos recursos.
        reserva = max(self._barra_area.winfo_reqwidth(), 14)
        larg = min(
            max(self.winfo_reqwidth() + reserva, 1000), self.winfo_screenwidth() - 60
        )
        alt = min(self.winfo_reqheight(), self.winfo_screenheight() - 90)
        self.geometry(f"{larg}x{alt}")

    # -- área rolável -------------------------------------------------------
    def _ajustar_area(self) -> None:
        """Acerta a região de rolagem e mostra a barra só quando precisa."""
        if not self.winfo_exists():
            return
        preciso = self.conteudo.winfo_reqheight()
        largura = max(self._tela.winfo_width(), 1)
        self._tela.configure(scrollregion=(0, 0, largura, preciso))

        # A moldura pede a altura do conteúdo (com um teto, senão ela
        # engoliria a janela inteira em telas grandes). Quando não couber,
        # o empacotamento acima corta o que sobra e a barra aparece.
        desejada = min(preciso, 640)
        if abs(self._tela.winfo_reqheight() - desejada) > 1:
            self._tela.configure(height=desejada)

        # A moldura também pede a largura do conteúdo. Sem isto ela pediria
        # a largura padrão de um Canvas (378 px) e a janela abriria estreita
        # demais, cortando o texto dos recursos.
        larg_nec = self.conteudo.winfo_reqwidth()
        if abs(self._tela.winfo_reqwidth() - larg_nec) > 1:
            self._tela.configure(width=larg_nec)

        disponivel = self._tela.winfo_height()
        precisa_barra = preciso > disponivel + 2
        if precisa_barra and not self._barra_visivel:
            # before=self._tela é essencial: a moldura pede a largura toda
            # do conteúdo, então quem for empacotado DEPOIS dela fica com
            # zero pixel de largura. Sem isto a barra existia mas ficava
            # invisível — e ninguém adivinha que a tela rola.
            self._barra_area.pack(side="right", fill="y", before=self._tela)
            self._barra_visivel = True
        elif not precisa_barra and self._barra_visivel:
            self._barra_area.pack_forget()
            self._barra_visivel = False
            self._tela.yview_moveto(0)

    def _tela_redimensionou(self, evento) -> None:
        # o conteúdo acompanha a largura da moldura
        self._tela.itemconfigure(self._item_conteudo, width=evento.width)
        self._ajustar_area()

    def _rolar_area(self, evento):
        """Roda do mouse rola a área de cima."""
        if not self._barra_visivel:
            return
        # Treeview tem rolagem própria — nunca rouba dela.
        if isinstance(evento.widget, ttk.Treeview):
            return
        # Text também tem rolagem própria — mas só faz sentido deixar com
        # ele quando há alguma coisa pra rolar LÁ DENTRO. Um campo pequeno
        # (ex.: "Conteúdo aplicado", só 2 linhas de altura) raramente tem
        # texto demais pra caber — sem este "if", o mouse em cima dele
        # virava um ponto morto: nem rolava por dentro (nada pra rolar)
        # nem deixava a página de baixo rolar. Relatado ao vivo, testando
        # de verdade.
        if isinstance(evento.widget, tk.Text):
            topo, fim = evento.widget.yview()
            if topo > 0.0 or fim < 1.0:
                return
        if getattr(evento, "num", None) == 4:
            passos = -1
        elif getattr(evento, "num", None) == 5:
            passos = 1
        else:
            passos = -1 if evento.delta > 0 else 1
        self._tela.yview_scroll(passos, "units")

    def _mostrar_dados_do_registro(self) -> None:
        """
        Rola a área de cima até os campos do registro.

        Em tela pequena, o fim do cartão — que é onde ficam os "Recursos
        utilizados" — cai abaixo da dobra. Depois de escolher a aula é
        justamente ali que se trabalha, então a tela desce o suficiente
        para o cartão inteiro aparecer.

        Rola o MÍNIMO necessário e nunca passa do topo do cartão: se ele
        for mais alto que o espaço visível, é o começo dele que fica à
        vista, não o meio.
        """
        if not self._barra_visivel:
            return
        cartao = self._cartao_ativo or self.cartao_dados
        try:
            topo_atual = self._tela.canvasy(0)
            topo_cartao = cartao.winfo_rooty() - self.conteudo.winfo_rooty()
            base_cartao = topo_cartao + cartao.winfo_height() + 8
            falta = base_cartao - (topo_atual + self._tela.winfo_height())
            if falta <= 0:
                return
            novo_topo = min(topo_atual + falta, topo_cartao)
            total = max(self.conteudo.winfo_reqheight(), 1)
            self._tela.yview_moveto(max(0.0, min(novo_topo / total, 1.0)))
        except tk.TclError:
            pass

    # -- helpers de tela ----------------------------------------------------
    def _definir_status(self, texto: str) -> None:
        self.rotulo_status.configure(text=texto)

    def _trazer_para_frente(self) -> None:
        """
        Traz a janela do programa de volta para a frente.

        Necessário porque o Chrome que o programa abre rouba o foco: sem
        isto, você ficava olhando a janela do navegador sem perceber que o
        aplicativo já tinha terminado e estava esperando você atrás dela.
        O "-topmost" é ligado e desligado logo em seguida só para forçar a
        vinda para frente — deixá-lo ligado prenderia a janela por cima de
        tudo, o que seria pior.
        """
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self._after_ids["topmost"] = self.after(
                400, lambda: self.attributes("-topmost", False)
            )
            self.focus_force()
        except Exception:
            pass  # se o gerenciador de janelas não deixar, segue a vida

    def _procurar_atualizacao(self, manual: bool = False) -> None:
        """
        Consulta se há versão nova (roda fora da janela, em segundo plano).

        Ao abrir o programa, o silêncio é proposital: sem internet ou com
        o servidor fora do ar, não é hora de incomodar ninguém. Mas quando
        a pessoa PEDE para procurar (manual=True), calar é o pior que
        pode acontecer — ela fica sem saber se está atualizada, se a
        internet falhou ou se o programa está quebrado. Então, no pedido
        manual, toda saída tem resposta.
        """
        if not URL_ATUALIZACAO:
            if manual:
                self.eventos.put((
                    "aviso_atualizacao",
                    "A atualização automática está desligada neste computador "
                    "(a linha URL_ATUALIZACAO do arquivo .env está marcada "
                    "como desligada).",
                ))
            return
        try:
            info = atualizador.consultar(URL_ATUALIZACAO)
        except Exception as erro:
            if manual:
                self.eventos.put((
                    "aviso_atualizacao",
                    "Não consegui consultar se há versão nova agora. "
                    f"Tente de novo mais tarde.\n\n({erro})",
                ))
            return  # sem internet, servidor fora do ar: hoje não deu, e tudo bem
        if info:
            self.eventos.put(("atualizacao", info))
        elif manual:
            self.eventos.put((
                "aviso_atualizacao",
                f"Você já está na versão mais nova ({atualizador.versao_atual()}).",
            ))

    def _conferir_conta_google(self) -> None:
        """
        Abre o formulário para conferir (ou fazer) o login da conta da escola.

        O login do Google acontece UMA vez por computador e fica guardado
        na pasta do programa. O problema é que, sem este botão, a pessoa só
        descobre que a sessão caiu no meio de um registro — com a aula já
        acontecendo e o relógio correndo. Aqui ela resolve isso na hora que
        quiser, de propósito.

        Isto abre um navegador PRÓPRIO, separado do preenchimento em
        segundo plano — e trocar de um pro outro fecha o que estava
        aberto (ver `_garantir_navegador`). Clicar aqui com um
        preenchimento pendente descartaria ele sem avisar — e a pessoa só
        percebia ao tentar enviar depois, com um erro sem explicação.
        Avisa e sugere o botão certo para conferir o preenchimento:
        "Ver no navegador".
        """
        if self.preenchido_para is not None:
            if not messagebox.askyesno(
                "Formulário preenchido esperando envio",
                "Existe um formulário preenchido esperando envio.\n\n"
                "Conferir a conta Google agora fecha essa janela e descarta "
                "o preenchimento — vai ser preciso preencher de novo depois.\n\n"
                'Se você quer só CONFERIR o que já foi preenchido, cancele e '
                'use o botão "Ver no navegador" em vez deste.\n\n'
                "Continuar mesmo assim?",
            ):
                return
            # Confirmado o descarte: reflete na tela — senão "Enviar" e
            # "Ver no navegador" continuariam habilitados apontando para
            # um preenchimento que está prestes a deixar de existir.
            self.preenchido_para = None
            self.botao_enviar.configure(state="disabled")
            self.botao_ver_no_navegador.configure(state="disabled")
        self._definir_status("Conferindo a conta Google da escola...")
        self.comandos.put(("conta_google", self.orientador.get("escola", "")))

    def _procurar_atualizacao_diaria(self) -> None:
        """
        Procura versão nova uma vez por dia, com o programa aberto.

        Adia se houver formulário preenchido esperando envio: aceitar a
        atualização fecha e reabre o programa, e isso jogaria fora um
        preenchimento pronto — bem na hora em que a pessoa está conferindo
        para mandar. Nesse caso ele tenta de novo em meia hora.
        """
        ocupado = self.preenchido_para is not None
        proximo = INTERVALO_RECONSULTA_MS if ocupado else INTERVALO_ATUALIZACAO_MS
        if not ocupado:
            threading.Thread(target=self._procurar_atualizacao, daemon=True).start()
        self._after_ids["procurar_atualizacao_diaria"] = self.after(
            proximo, self._procurar_atualizacao_diaria
        )

    def _procurar_atualizacao_agora(self) -> None:
        """Botão 'Procurar atualização' — a consulta vai para outra thread."""
        self._definir_status("Procurando versão nova...")
        threading.Thread(
            target=self._procurar_atualizacao, kwargs={"manual": True}, daemon=True
        ).start()

    def _oferecer_atualizacao(self, info: dict) -> None:
        """Avisa que saiu versão nova e, se a pessoa quiser, atualiza."""
        # As notas vêm do NOVIDADES.md publicado junto com a versão. Um
        # texto muito longo estouraria a caixinha do Windows e sairia
        # cortado sem aviso, então ele é limitado aqui — o texto inteiro
        # continua na página da versão, no GitHub.
        texto_notas = _notas_para_dialogo((info.get("notas") or "").strip())
        if len(texto_notas) > 1200:
            texto_notas = texto_notas[:1200].rsplit("\n\n", 1)[0] + "\n\n(...)"
        notas = (
            f"\n\nO que mudou nesta versão:\n\n{texto_notas}" if texto_notas else ""
        )
        if not messagebox.askyesno(
            "Nova versão disponível",
            f"Saiu a versão {info['versao']} do programa "
            f"(você está na {atualizador.versao_atual()}).{notas}\n\n"
            "Atualizar agora? Leva alguns segundos.\n\n"
            "Seus dados não são afetados: senha, login do Google e o "
            "histórico de registros continuam como estão.",
        ):
            return
        try:
            arquivos = atualizador.aplicar(info)
        except Exception as exc:
            messagebox.showerror(
                "Não deu para atualizar",
                f"A atualização não foi aplicada e nada mudou no programa.\n\n{exc}",
            )
            return
        # NÃO reabre mais sozinho (nem como .exe): reabrir rápido demais —
        # o processo antigo morrendo quase no mesmo instante em que o novo
        # nasce — já deu pelo menos três erros diferentes, vistos ao vivo
        # com print de tela, nenhum consertável por dentro do programa
        # porque acontecem ANTES ou DURANTE a inicialização do Python/Tcl
        # (antes de qualquer código nosso rodar): "Security validation
        # failure" do Chromium, "Can't find a usable init.tcl" e até
        # "Failed to start embedded python interpreter" — este nem chega a
        # ser uma exceção Python, é o PRÓPRIO INTERPRETADOR que não
        # nasceu. Pedir para a pessoa fechar e abrir na mão é mais chato,
        # mas sempre funcionou, porque dá um tempo natural entre o
        # processo antigo sumir de vez e o novo começar.
        if empacotado():
            # Fecha o Chrome da sessão persistente ANTES de avisar: sem
            # isto, uma reabertura rápida da pessoa podia esbarrar na
            # trava (SingletonLock) que ele deixa no browser_profile até
            # terminar de fechar de verdade.
            self._encerrar_worker()
        messagebox.showinfo(
            "Atualizado",
            f"Pronto — agora na versão {info['versao']}.\n\n"
            "FECHE o programa e abra de novo para usar a versão nova.",
        )
        if empacotado():
            # Não usa _fechar() aqui: já fechamos o navegador acima, à
            # mão — chamar de novo só mandaria um "sair" redundante para
            # uma thread que já terminou.
            self.destroy()
            return
        self._definir_status(
            f"Atualizado para a versão {info['versao']} — feche e abra o programa."
        )

    def _checar_configuracao(self) -> None:
        """Avisa, logo ao abrir, se faltou preencher o arquivo .env — ou se
        o histórico de envios não pôde ser lido."""
        if estado_corrompido():
            self._escrever(
                "NÃO CONSEGUI LER O HISTÓRICO DE ENVIOS\n\n"
                f"O arquivo {os.path.basename(ESTADO_FILE)} existe, mas está "
                "corrompido — o programa está tratando como se nada tivesse "
                "sido enviado ainda.\n\n"
                "IMPORTANTE: confira com cuidado, antes de reenviar, se "
                "cada aula já não foi registrada de verdade na SED — pode "
                "estar em duplicidade."
            )
            messagebox.showwarning(
                "Histórico de envios corrompido",
                f"O arquivo {os.path.basename(ESTADO_FILE)} (o que já foi "
                "enviado à SED) existe, mas não pôde ser lido — o programa "
                "vai tratar tudo como pendente.\n\n"
                "Antes de reenviar qualquer aula, confira na própria SED se "
                "ela já não foi registrada — para não duplicar.",
            )
        faltando = configuracao_incompleta()
        if not faltando:
            return
        lista = "\n".join(f"   • {item}" for item in faltando)
        pasta_env = str(pasta_de_dados())
        self._escrever(
            "FALTA CONFIGURAR O ARQUIVO .env\n\n"
            "Estes dados ainda não foram preenchidos:\n"
            f"{lista}\n\n"
            f"Abra o arquivo .env (em {pasta_env}) com o Bloco de "
            "Notas, preencha os campos, salve e abra o programa de novo."
        )
        self._definir_status("Falta configurar o arquivo .env — veja abaixo.")
        messagebox.showwarning(
            "Falta configurar",
            "O programa ainda não sabe quem você é.\n\n"
            "Estes dados não foram preenchidos:\n\n"
            f"{lista}\n\n"
            f"Abra o arquivo .env (em {pasta_env}) com o Bloco de Notas, "
            "preencha esses campos, salve e abra o programa de novo.\n\n"
            "Sem isso, o registro iria para a SED com os dados errados.",
        )

    def _piscar_sugerida(self) -> None:
        """
        Faz a linha "Sugerida agora" piscar em verde.

        Alterna só o fundo da etiqueta, entre um verde claro e um mais
        forte. Como a cor é da etiqueta (e não da linha), isso funciona
        sozinho para qualquer linha que seja a sugerida no momento — não
        precisa saber qual é, nem refazer nada quando a sugestão muda.
        """
        try:
            if self.winfo_exists():
                self._pisca_ligado = not getattr(self, "_pisca_ligado", False)
                cor = VERDE_PISCA[1 if self._pisca_ligado else 0]
                self.tag_sugerida_cor = cor
                self.tabela.tag_configure(
                    "sugerida", background=cor, foreground=COR_SUGERIDA_FG
                )

                # A linha selecionada é pintada pela cor de seleção, que
                # cobre a cor da etiqueta — sem isto, a aula sugerida
                # pararia de piscar justamente quando estivesse
                # selecionada, que é o caso mais comum (ela vem
                # selecionada sozinha). Então, quando a selecionada É a
                # sugerida, o próprio destaque da seleção pisca.
                selecao = self.tabela.selection()
                sugerida_selecionada = (
                    bool(selecao)
                    and getattr(self, "_iid_sugerida", None) == selecao[0]
                )
                if sugerida_selecionada:
                    self._estilo.map(
                        "Treeview",
                        background=[("selected", cor)],
                        foreground=[("selected", COR_SUGERIDA_FG_SELECIONADA)],
                    )
                else:
                    self._estilo.map(
                        "Treeview",
                        background=[("selected", SELECAO_BG)],
                        foreground=[("selected", SELECAO_FG)],
                    )
        except Exception:
            return  # janela fechando — para o ciclo
        self._after_ids["piscar_sugerida"] = self.after(INTERVALO_PISCA_MS, self._piscar_sugerida)

    def _piscar_na_barra(self) -> None:
        """
        Faz o botão do programa piscar na barra de tarefas do Windows.

        Usa o recurso nativo do Windows (FlashWindowEx) de propósito, em
        vez de trazer a janela para a frente: se você estiver atendendo um
        professor ou digitando outra coisa, uma janela pulando na frente
        atrapalha. Piscando, o aviso espera você olhar.

        O piscar continua até você clicar no programa (é o que a opção
        "até vir para a frente" faz), então não tem como perder o aviso
        por estar de costas para a tela.
        """
        try:
            import ctypes
            from ctypes import wintypes

            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("hwnd", wintypes.HWND),
                    ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT),
                    ("dwTimeout", wintypes.DWORD),
                ]

            user32 = ctypes.windll.user32
            # o botão da barra de tarefas pertence à janela "pai" do widget
            hwnd = user32.GetParent(self.winfo_id()) or self.winfo_id()
            FLASHW_TRAY = 0x02          # pisca só o botão da barra
            FLASHW_TIMERNOFG = 0x0C     # até a janela vir para a frente
            info = FLASHWINFO(
                ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_TRAY | FLASHW_TIMERNOFG, 0, 0
            )
            user32.FlashWindowEx(ctypes.byref(info))
        except Exception:
            # fora do Windows (ou se a API não estiver disponível) o
            # programa segue funcionando normalmente, só sem o piscar
            pass

    def _turno_e_meu(self, grupo) -> bool:
        """A aula pertence ao turno do professor que está usando o programa?"""
        turnos = self.orientador.get("turnos") or []
        turno_da_aula = getattr(grupo, "turno", "")
        if not turnos or not turno_da_aula:
            return True  # sem informação de turno, não restringe nada
        return turno_da_aula in turnos

    def _momento_inicio(self, grupo, agora: dt.datetime) -> dt.datetime:
        return dt.datetime.combine(
            dt.date.fromisoformat(grupo.data), _hora(grupo.inicio), tzinfo=agora.tzinfo
        )

    def _verificar_inicio_de_aula(self) -> None:
        """Relógio interno: avisa quando uma aula agendada acaba de começar."""
        try:
            agora = agora_sc()

            # A coluna "Situação" é um retrato do momento em que a lista
            # foi desenhada. Sem redesenhar, uma aula que começou agora
            # continua escrita como "Ainda não ocorreu" — foi exatamente
            # isso que aconteceu: o alerta piscou na barra, mas a linha
            # não virou "Sugerida agora" nem começou a piscar em verde.
            # Se a sugestão de QUALQUER aba mudou, a lista está velha:
            # redesenha (a aba aberta agora — sem trocar sozinho de aba
            # aqui; só o aviso de "começou agora", logo abaixo, faz isso).
            sugeridas_novas = self._sugerida_por_categoria()
            if (
                sugeridas_novas != getattr(self, "_sugeridas_por_categoria_anterior", None)
                and self.preenchido_para is None
            ):
                self._preencher_tabela()
            self._sugeridas_por_categoria_anterior = sugeridas_novas

            # Sem "break": se duas aulas começaram juntas em recursos
            # diferentes (um laboratório, outro Tablets ao mesmo tempo),
            # as DUAS precisam do aviso — cada uma pisca a barra de
            # tarefas na hora certa, e a aba de quem não ficou selecionada
            # por último continua marcada (ver _atualizar_abas_recurso).
            for g in self.grupos:
                chave = chave_grupo(g)
                if chave in self._ja_avisadas:
                    continue
                if chave in self.enviados or chave in self.nao_realizadas:
                    continue
                if not self._turno_e_meu(g):
                    continue  # aula do outro turno não é minha para registrar
                atraso = (agora - self._momento_inicio(g, agora)).total_seconds()
                if 0 <= atraso <= JANELA_AVISO_MIN * 60:
                    self._ja_avisadas.add(chave)
                    self._avisar_aula_comecou(g)
        except Exception:
            pass  # nunca deixar o relógio morrer por causa de um erro pontual
        finally:
            self._after_ids["verificar_inicio_de_aula"] = self.after(
                INTERVALO_CHECAGEM_MS, self._verificar_inicio_de_aula
            )

    def _avisar_aula_comecou(self, grupo) -> None:
        self._piscar_na_barra()
        quando = f"{grupo.inicio}-{grupo.fim}"

        # Se a aula que acabou de começar é de outra aba (ex: Tablets, com
        # o Laboratório aberto na tela), troca pra aba certa sozinho — senão
        # a linha "Sugerida agora" fica escrita e piscando numa aba que
        # ninguém está olhando, e a seleção automática logo abaixo nem acha
        # a linha (ela não existe na tabela enquanto a aba errada estiver
        # selecionada).
        categoria_da_aula = _categoria_da_atividade(grupo)
        if self.categoria_atual != categoria_da_aula:
            self.categoria_atual = categoria_da_aula

        # Garante que a linha desta aula já esteja escrita como "Sugerida
        # agora" (e piscando) no momento em que o aviso aparece.
        if self.preenchido_para is None and self._grupo_sugerido is not grupo:
            self._preencher_tabela()

        # Se um formulário já está preenchido e esperando envio, NÃO troca
        # a seleção: isso apagaria o preenchimento em andamento. Nesse caso
        # só avisa e deixa a pessoa decidir.
        if self.preenchido_para is not None:
            self._definir_status(
                f"Começou agora: {grupo.disciplina} · {quando} — "
                "termine o registro atual antes de trocar de aula."
            )
            return

        try:
            indice = next(i for i, x in enumerate(self.grupos) if x is grupo)
            self.tabela.selection_set(str(indice))
            self.tabela.see(str(indice))
            self._ao_selecionar()
            self.campo_estudantes.focus_set()
        except Exception:
            pass
        self._definir_status(
            f"Começou agora: {grupo.disciplina} · {grupo.turma} · {quando}"
        )

    def _recarregar_silencioso(self) -> None:
        """Relê a agenda de tempos em tempos, sem chamar atenção."""
        self.comandos.put((
            "carregar", True, self.orientador["cpf"], self.orientador["senha"],
            self.orientador.get("escola", ""),
        ))
        self._after_ids["recarregar_silencioso"] = self.after(
            INTERVALO_RECONSULTA_MS, self._recarregar_silencioso
        )

    def _escrever(self, texto: str) -> None:
        self.texto_resumo.configure(state="normal")
        self.texto_resumo.delete("1.0", "end")
        self.texto_resumo.insert("1.0", texto)
        self.texto_resumo.configure(state="disabled")
        self.after_idle(self._ajustar_altura_resumo)
        self.after_idle(self._ajustar_barra_resumo)

    def _ajustar_altura_resumo(self) -> None:
        """
        O resumo cresce conforme o que tem para mostrar.

        Enquanto ele guarda só um aviso de uma linha, ocupar nove linhas
        da tela é desperdício — e era esse desperdício que empurrava os
        "Recursos utilizados" para fora da área visível em telas menores.
        Quando chega a conferência do registro, ele cresce de novo.
        """
        try:
            self.texto_resumo.update_idletasks()
            medida = self.texto_resumo.count("1.0", "end", "displaylines")
            linhas = int(medida[0] if isinstance(medida, (list, tuple)) else medida)
        except Exception:
            try:
                linhas = int(self.texto_resumo.index("end-1c").split(".")[0])
            except tk.TclError:
                return
        alvo = max(4, min(10, linhas))
        try:
            if int(self.texto_resumo.cget("height")) != alvo:
                self.texto_resumo.configure(height=alvo)
        except tk.TclError:
            pass

    def _ajustar_barra_resumo(self) -> None:
        """
        Barra de rolagem do resumo — só aparece quando sobra texto.

        O resumo é a conferência do que vai para a SED: se a última linha
        (os recursos, geralmente) ficar escondida, a pessoa não tem como
        saber que ela existe. A barra é o aviso de que há mais para ver.
        """
        try:
            inicio, fim = self.texto_resumo.yview()
        except tk.TclError:
            return
        sobra = (fim - inicio) < 0.999
        if sobra and not self._barra_resumo_visivel:
            self._barra_resumo.pack(side="right", fill="y")
            self._barra_resumo_visivel = True
        elif not sobra and self._barra_resumo_visivel:
            self._barra_resumo.pack_forget()
            self._barra_resumo_visivel = False

    def _selecionar_categoria(self, categoria: str) -> None:
        self.categoria_atual = categoria
        self._preencher_tabela()

    def _sugerida_por_categoria(self) -> dict:
        """
        A "sugerida agora" de CADA aba, calculada separadamente — não uma
        só pra tudo. Necessário porque, com mais de um recurso, pode
        acontecer aula em duas abas ao mesmo tempo (um laboratório, outro
        Tablets): uma sugestão global esconderia uma das duas ao trocar de
        aba pra mostrar a outra.
        """
        agora = agora_sc()
        ignorar = self.enviados | self.nao_realizadas
        turnos = self.orientador.get("turnos")
        resultado = {}
        for cat in CATEGORIAS_RECURSO_EM_ORDEM:
            grupos_da_aba = [g for g in self.grupos if _categoria_da_atividade(g) == cat]
            resultado[cat] = escolher_aula_automatica(grupos_da_aba, ignorar, agora, turnos)
        return resultado

    def _atualizar_abas_recurso(self) -> None:
        """
        Mostra as abas de recurso (Laboratório/Projetores/Tablets-Celular)
        só quando a agenda de verdade tiver aula de mais de uma categoria —
        a grande maioria das escolas só tem o laboratório, e 3 abas para
        escolher entre uma coisa só seria só confusão.

        "Suporte a outros espaços", "Manutenção" e "Formação/Reunião" não
        seguem essa regra: elas não vêm de agendamento nenhum (ver
        CATEGORIAS_INDEPENDENTES), então ficam SEMPRE visíveis — mas
        encostadas na ponta DIREITA da linha, separadas das de cima, que
        ficam à esquerda.

        Uma aba que não é a selecionada, mas tem uma "sugerida agora" dela
        mesma, ganha destaque de aviso (cor de "SubAviso") — é o sinal de
        que tem aula acontecendo ali que a pessoa ainda não olhou.

        EXCEÇÃO IMPORTANTE: numa escola de só um recurso (o caso comum,
        onde as abas de cima ficam sempre escondidas), clicar em
        "Manutenção"/"Formação/Reunião" não pode ser um beco sem saída —
        sem NENHUM botão de recurso visível, não havia como voltar pra
        "Laboratório" a não ser fechando e abrindo o programa de novo.
        Por isso, estando numa categoria independente, a aba do recurso
        único aparece mesmo sozinha, só como porta de saída.
        """
        presentes = {"Laboratório"} | {_categoria_da_atividade(g) for g in self.grupos}
        sugeridas = self._sugerida_por_categoria()
        # Desempacota TUDO primeiro e reempacota na ordem certa — pack()
        # sem pack_forget() antes não reordena um botão já visível, só
        # atualiza as opções dele; sem isto, uma aba que sumiu e voltou
        # (ex: Projetores, que só aparece quando a agenda tem aula lá)
        # ficava fora de ordem em relação às outras.
        for botao in self.botoes_categoria.values():
            botao.pack_forget()
        if len(presentes) > 1 or self.categoria_atual in CATEGORIAS_INDEPENDENTES:
            for cat in CATEGORIAS_RECURSO_EM_ORDEM:
                if cat not in presentes:
                    continue
                if cat == self.categoria_atual:
                    estilo = "Principal.TButton"
                elif sugeridas.get(cat) is not None:
                    estilo = "AvisoAba.TButton"
                else:
                    estilo = "TButton"
                self.botoes_categoria[cat].configure(style=estilo)
                self.botoes_categoria[cat].pack(side="left", padx=(0, 6))
        # Empacotadas da direita pra esquerda: a ÚLTIMA da lista fica mais
        # à esquerda das duas, então percorre a lista ao contrário pra
        # "Manutenção" aparecer antes de "Formação/Reunião" na leitura.
        for cat in reversed(CATEGORIAS_INDEPENDENTES):
            estilo = "Principal.TButton" if cat == self.categoria_atual else "TButton"
            self.botoes_categoria[cat].configure(style=estilo)
            self.botoes_categoria[cat].pack(side="right", padx=(6, 0))
        if self.categoria_atual not in presentes and self.categoria_atual not in CATEGORIAS_INDEPENDENTES:
            self.categoria_atual = "Laboratório"
        # "Manutenção" e "Formação/Reunião" não têm aula nenhuma pra listar
        # — some a tabela inteira e sobra só o formulário daquele tipo
        # (ver _atualizar_area_dados_registro, chamada no fim de
        # _preencher_tabela, depois que self.grupo_atual está resolvido).
        if self.categoria_atual in CATEGORIAS_INDEPENDENTES:
            self.corpo_lista.pack_forget()
            self.rodape_aula_avulsa.pack_forget()
        else:
            self.corpo_lista.pack(fill="both", expand=True, pady=(10, 0))
            self.rodape_aula_avulsa.pack(fill="x", pady=(8, 0))

    def _preencher_tabela(self) -> None:
        self._atualizar_abas_recurso()
        self.tabela.delete(*self.tabela.get_children())
        agora = agora_sc()
        self.nao_realizadas = carregar_nao_realizadas()
        # Sugestão só dentro da aba aberta agora — não da agenda inteira —
        # pelo mesmo motivo do aviso acima: cada aba mostra a aula dela.
        grupos_da_aba = [g for g in self.grupos if _categoria_da_atividade(g) == self.categoria_atual]
        sugerida = escolher_aula_automatica(
            grupos_da_aba, self.enviados | self.nao_realizadas, agora,
            self.orientador.get("turnos"),
        )
        self.grupo_atual = None
        self._iid_sugerida = None
        # guardado para o relógio saber se a lista desenhada ainda
        # corresponde à realidade (ver _verificar_inicio_de_aula)
        self._grupo_sugerido = sugerida
        for indice, g in enumerate(self.grupos):
            # Só desenha a linha se ela for da aba (categoria de recurso)
            # selecionada agora — o índice usado no iid continua sendo a
            # posição REAL em self.grupos (não recalculado), porque é por
            # ele que _ao_selecionar acha o grupo certo ao clicar na linha.
            if _categoria_da_atividade(g) != self.categoria_atual:
                continue
            # A bolinha antes do texto ajuda a bater o olho e achar a linha
            # pela cor, sem precisar ler a coluna inteira.
            if chave_grupo(g) in self.enviados:
                situacao, tags = "● Já enviada", ("enviada",)
            elif chave_grupo(g) in self.nao_realizadas:
                situacao, tags = "● Não realizada", ("nao_realizada",)
            elif not self._turno_e_meu(g):
                # aula do colega do outro turno: aparece na lista (para
                # dar visão do laboratório), mas em cinza e sem sugestão
                situacao, tags = f"· {g.turno} (outro turno)", ("futura",)
            elif not ja_comecou(g, agora):
                situacao, tags = "○ Ainda não ocorreu", ("futura",)
            elif sugerida is not None and g is sugerida:
                situacao, tags = "▶ Sugerida agora", ("sugerida",)
                self._iid_sugerida = str(indice)
            else:
                situacao, tags = "● Pendente", ("pendente",)
            dia = dt.date.fromisoformat(g.data).strftime("%d/%m")
            self.tabela.insert(
                "",
                "end",
                iid=str(indice),
                values=(
                    f"{dia}  {g.inicio}-{g.fim}",
                    g.professor.title(),
                    g.disciplina,
                    g.turma,
                    situacao,
                ),
                tags=tags,
            )
        # Sem isto, a barra de rolagem da tabela (à direita) às vezes não
        # aparecia depois de inserir as linhas — só surgia depois de
        # qualquer coisa que forçasse um redesenho, como arrastar a borda
        # de uma coluna. O yscrollcommand já avisa a barra sozinho quando
        # a tabela muda, mas nem sempre a pintura da tela acompanha —
        # forçar aqui garante que a barra sempre reflita a lista atual.
        # Relatado com print de tela, marcando a barra "sumida".
        self.tabela.update_idletasks()
        # Atualiza os cartões de baixo (Dados do registro / Suporte /
        # Manutenção / Formação) pra bater com a categoria atual — feito
        # AQUI, e não em _atualizar_abas_recurso, porque self.grupo_atual
        # só está no valor final (None, acabou de ser resetado acima)
        # depois deste ponto. Roda mesmo se o formulário atual redesenhar
        # a tabela por baixo de um preenchimento pendente (ver abaixo).
        self._atualizar_area_dados_registro()
        # IMPORTANTE: se há um formulário preenchido esperando envio, a
        # seleção NÃO pode mudar. Trocar a seleção dispara a limpeza dos
        # campos, e a reconsulta automática (de 30 em 30 min) apagaria o
        # trabalho em andamento bem na hora de clicar em Enviar.
        if self.preenchido_para is not None:
            # Por CHAVE, não por identidade (`is`): toda recarga da agenda
            # — inclusive a silenciosa, de 30 em 30 min — cria objetos
            # novos a partir de um scrape novo. Comparar por identidade
            # nunca reencontra a aula depois disso, e a linha ficava sem
            # seleção visual (cosmético — o envio usa self.preenchido_para
            # direto, não esta busca — mas confuso: parecia que a aula
            # tinha sumido no meio do preenchimento).
            chave_pendente = chave_grupo(self.preenchido_para)
            try:
                indice = next(
                    i for i, x in enumerate(self.grupos) if chave_grupo(x) == chave_pendente
                )
                self.tabela.selection_set(str(indice))
                self.grupo_atual = self.preenchido_para
            except StopIteration:
                pass
            return

        if sugerida is not None:
            indice = next(i for i, x in enumerate(self.grupos) if x is sugerida)
            self.tabela.selection_set(str(indice))
            self._rolar_ate(indice)
            self.campo_estudantes.focus_set()
        else:
            # Sem sugestão (tudo resolvido, ou ainda nem começou o dia) a
            # lista ficava parada na segunda-feira e era preciso rolar até
            # achar o dia de hoje. Rola sozinha até o "agora".
            self._rolar_ate(self._indice_do_agora(agora))

    def _indice_do_agora(self, agora: dt.datetime):
        """
        Índice da linha que representa "este momento" na lista da semana.

        A primeira aula que ainda não terminou — ou seja, a que está
        acontecendo agora ou a próxima a acontecer. Se a semana inteira já
        passou, devolve a última linha.
        """
        if not self.grupos:
            return None
        for i, g in enumerate(self.grupos):
            fim = dt.datetime.combine(
                dt.date.fromisoformat(g.data), _hora(g.fim), tzinfo=agora.tzinfo
            )
            if fim >= agora:
                return i
        return len(self.grupos) - 1

    def _rolar_ate(self, indice) -> None:
        """Rola a lista até deixar aquela linha visível."""
        if indice is None:
            return
        try:
            self.tabela.update_idletasks()
            self.tabela.see(str(indice))
        except Exception:
            pass

    def _ao_selecionar(self, _evento=None) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            return
        grupo = self.grupos[int(selecao[0])]

        # Se a aula selecionada é justamente a que já está preenchida e
        # esperando envio, não mexe em nada. Sem isto, qualquer coisa que
        # reposicione a seleção — a reconsulta automática, por exemplo —
        # dispararia este evento e limparia o preenchimento em andamento,
        # inclusive o texto do conteúdo que você acabou de escrever.
        if grupo is self.preenchido_para:
            self.grupo_atual = grupo
            return

        self.grupo_atual = grupo
        self.preenchido_para = None
        self.botao_enviar.configure(state="disabled")
        self.botao_ver_no_navegador.configure(state="disabled")
        dia = dt.date.fromisoformat(grupo.data).strftime("%d/%m/%Y")
        texto_aula = (
            f"{dia} · {grupo.inicio}-{grupo.fim} · {grupo.professor.title()} · "
            f"{grupo.disciplina} · {grupo.turma} · {grupo.numero_aulas} aula(s)"
        )
        self.rotulo_aula.configure(text=texto_aula)
        self.rotulo_aula_suporte.configure(text=texto_aula)
        self.campo_disciplina.delete(0, "end")
        self.campo_disciplina.insert(0, grupo.disciplina)
        self.campo_professor.delete(0, "end")
        self.campo_professor.insert(0, grupo.professor)
        self.campo_numero_aulas.delete(0, "end")
        self.campo_numero_aulas.insert(0, str(grupo.numero_aulas))
        etapa = etapa_para_turma(grupo.turma)
        self.combo_etapa.set(etapa or "")
        self._ajustar_campo_extra(sugerir_de=grupo.turma)
        # Traz o assunto lançado na agenda como ponto de partida — o
        # professor ajusta/reescreve antes de registrar.
        self.campo_conteudo.delete("1.0", "end")
        self.campo_conteudo.insert("1.0", grupo.conteudo or "")

        # Projetor/Tablets-Celular: pergunta de novo a cada aula
        # selecionada — nunca assume "foi aula com estudantes" só porque
        # foi a última escolha (ver _atualizar_area_dados_registro).
        # Laboratório continua exatamente como sempre foi.
        categoria = _categoria_da_atividade(grupo)
        self.var_tipo_registro.set("aula" if categoria == "Laboratório" else "")
        self.var_tipo_suporte.set("")
        self.campo_descricao_suporte.delete(0, "end")
        self.campo_aulas_suporte.delete(0, "end")
        self.campo_aulas_suporte.insert(0, str(grupo.numero_aulas))
        self._atualizar_area_dados_registro()

        # o mesmo botão marca e desmarca, conforme a aula selecionada
        marcada = chave_grupo(grupo) in self.nao_realizadas
        self.botao_nao_realizada.configure(
            text="Desfazer 'não realizada'" if marcada else "Aula não realizada"
        )
        # em tela pequena, leva os campos do registro para a vista
        self.after_idle(self._mostrar_dados_do_registro)

        if chave_grupo(grupo) in self.enviados:
            self._escrever(
                "Esta aula já foi registrada numa execução anterior.\n"
                "Se registrar de novo, vai duplicar na SED."
            )
        elif marcada:
            self._escrever(
                "Marcada como NÃO REALIZADA — o(a) professor(a) agendou mas não usou "
                "o laboratório.\n"
                "Ela não vai para a SED e não aparece mais como pendente.\n\n"
                "Se foi engano, use o botão 'Desfazer não realizada'."
            )
        else:
            self._escrever("")

    def _limpar_dados_do_registro(self) -> None:
        """
        Volta o cartão "Dados do registro" para o estado de "nada
        selecionado" — mesmo texto/campos vazios de quando a janela abre.

        Chamado quando self.grupo_atual vira None sem uma aula nova ter
        sido selecionada (ex: trocar de aba). Sem isto, os campos ficavam
        com os dados da ÚLTIMA aula selecionada, mesmo depois de trocar
        de aba — parecia que uma aula da aba nova estava selecionada, sem
        estar.
        """
        self.rotulo_aula.configure(text="Nenhuma aula selecionada.")
        self.campo_disciplina.delete(0, "end")
        self.campo_professor.delete(0, "end")
        self.campo_numero_aulas.delete(0, "end")
        self.campo_estudantes.delete(0, "end")
        self.combo_etapa.set("")
        self._ajustar_campo_extra()
        self.campo_conteudo.delete("1.0", "end")
        for var in self.vars_recursos.values():
            var.set(False)

    def _atualizar_area_dados_registro(self) -> None:
        """
        Mostra o(s) cartão(ões) certo(s) abaixo da lista de aulas, conforme
        a aba/categoria atual:

        - Laboratório: sempre o cartão de sempre (cartao_dados).
        - Projetores/Tablets-Celular: pergunta o tipo de registro (aula com
          estudantes ou suporte/instalação, ver
          preencher_suporte_outros_espacos em sed_form_filler.py).
        - Suporte a outros espaços / Manutenção / Formação-Reunião
          (CATEGORIAS_INDEPENDENTES): não dependem de aula nenhuma
          selecionada — mostram direto o cartão daquele tipo.

        Esconde todos primeiro e reempacota só o que faz sentido, NA ORDEM
        CERTA: pack() sem "before"/"after" reaparece no FIM de quem já
        estiver visível, então reempacotar por cima do que já estava lá
        bagunçaria a ordem dependendo de qual cartão apareceu por último.
        """
        self.cartao_tipo_registro.pack_forget()
        self.cartao_dados.pack_forget()
        self.cartao_suporte.pack_forget()
        self.cartao_suporte_avulso.pack_forget()
        self.cartao_manutencao.pack_forget()
        self.cartao_formacao.pack_forget()

        if self.categoria_atual == "Suporte a outros espaços":
            self.cartao_suporte_avulso.pack(fill="x", padx=20, pady=(0, 8))
            self._cartao_ativo = self.cartao_suporte_avulso
            return
        if self.categoria_atual == "Manutenção":
            self.cartao_manutencao.pack(fill="x", padx=20, pady=(0, 8))
            self._cartao_ativo = self.cartao_manutencao
            return
        if self.categoria_atual == "Formação/Reunião":
            self.cartao_formacao.pack(fill="x", padx=20, pady=(0, 8))
            self._cartao_ativo = self.cartao_formacao
            return

        grupo = self.grupo_atual
        if grupo is None:
            # Nenhuma aula selecionada ainda (agenda carregando, trocou
            # de aba, ou ninguém clicou em nada) — fica em branco de
            # propósito, sem nenhum cartão. Só aparece quando o professor
            # escolhe uma aula na lista.
            #
            # IMPORTANTE limpar os campos aqui mesmo assim: se voltar a
            # aparecer (ex: por causa de algum outro caminho de código),
            # não pode trazer dado da aula ANTERIOR junto — bug real
            # encontrado testando a tela, dava a entender que uma aula
            # estava selecionada quando não estava.
            self._limpar_dados_do_registro()
            self._cartao_ativo = None
            return
        if _categoria_da_atividade(grupo) == "Laboratório":
            self.cartao_dados.pack(fill="x", padx=20, pady=(0, 8))
            self._cartao_ativo = self.cartao_dados
            return

        self.cartao_tipo_registro.pack(fill="x", padx=20, pady=(0, 8))
        tipo = self.var_tipo_registro.get()
        if tipo == "aula":
            self.cartao_dados.pack(fill="x", padx=20, pady=(0, 8))
            self._cartao_ativo = self.cartao_dados
        elif tipo == "suporte":
            self.cartao_suporte.pack(fill="x", padx=20, pady=(0, 8))
            self._cartao_ativo = self.cartao_suporte
        else:
            # ainda não escolheu: não mostra nenhum dos dois, força a
            # pessoa a escolher em vez de assumir "aula" por padrão.
            self._cartao_ativo = self.cartao_tipo_registro

    def _ao_escolher_tipo_registro(self) -> None:
        self._atualizar_area_dados_registro()
        # em tela pequena, leva o cartão que acabou de aparecer para a vista
        self.after_idle(self._mostrar_dados_do_registro)

    # -- ações --------------------------------------------------------------
    def _sair_da_conta(self) -> None:
        """
        Fecha a sessão deste professor e volta para a tela de entrada.

        A senha vive só na memória; ao sair, ela some junto com a janela.
        É assim que o professor do noturno assume a máquina sem herdar a
        conta de quem usou de manhã.

        Isto também desloga a conta Google DESTA escola — sair do
        programa é o sinal de que o uso acabou, e o próximo a mexer no
        computador pode ser outro professor, de outra escola. Não faria
        sentido a conta institucional continuar logada esperando por ele.
        """
        if self.preenchido_para is not None:
            if not messagebox.askyesno(
                "Sair da conta",
                "Tem um formulário preenchido esperando envio.\n\n"
                "Sair agora descarta esse preenchimento. Continuar?",
            ):
                return
        self.sair_da_conta = True
        self.comandos.put(("sair_google", self.orientador.get("escola", "")))
        self._fechar()

    def _editar_cadastro(self) -> None:
        """Abre o cadastro deste professor (nome, CPF, turnos, escola(s))."""
        atual = next(
            (
                p
                for p in (configuracao.carregar().get("professores") or [])
                if p.get("cpf") == self.orientador.get("cpf")
            ),
            None,
        )
        tela = configuracao.TelaDeCadastro(mestre=self, professor=atual)
        if tela.mostrar():
            messagebox.showinfo(
                "Dados salvos",
                "Pronto. Feche o programa e abra de novo para os dados novos "
                "valerem.",
            )
            self._fechar()
            _reabrir_e_sair()

    def _trocar_professor(self, _evento=None) -> None:
        """
        Troca o professor que está registrando.

        Como cada orientador tem CPF e senha próprios no site de
        agendamento, trocar de professor exige reler a agenda com o login
        dele — não basta trocar o nome que vai no formulário.
        """
        escolhido = self.combo_professor.get()
        novo = next((o for o in ORIENTADORES if o["nome"] == escolhido), None)
        if novo is None or novo is self.orientador:
            return

        # Um formulário já preenchido pertence ao professor anterior:
        # enviá-lo com o nome do outro seria registro errado na SED.
        if self.preenchido_para is not None:
            if not messagebox.askyesno(
                "Trocar de professor(a)",
                "Existe um formulário preenchido esperando envio, no nome de\n"
                f"{self.orientador['nome']}.\n\n"
                "Trocar de professor(a) agora descarta esse preenchimento.\n"
                "Quer trocar mesmo assim?",
            ):
                self.combo_professor.set(self.orientador["nome"])
                return
            self.preenchido_para = None
            self.botao_enviar.configure(state="disabled")
            self.botao_ver_no_navegador.configure(state="disabled")
            self.comandos.put(("reiniciar",))

        self.orientador = novo
        salvar_ultimo_professor(novo["nome"])
        self._ja_avisadas.clear()  # os avisos valem para a agenda do novo login
        # Troca de professor pode ser troca de escola também — confere de
        # novo a conta Google assim que a agenda deste voltar.
        self._conta_google_verificada = False

        # A aula selecionada na tabela é da agenda do professor ANTERIOR —
        # ela só é substituída quando o evento "aulas" do novo login
        # voltar (é assíncrono, a leitura da agenda leva um tempo). Sem
        # isto, clicar "Preencher formulário" nesse intervalo registraria
        # a aula de um professor com o nome do outro: dado errado na SED,
        # sem nenhum aviso. `_preencher()` recusa a agir sem uma aula
        # selecionada — não precisa desabilitar o botão pra isso, e
        # desabilitar aqui deixaria ele travado até o próximo preenchimento
        # de verdade, já que nada mais o reabilita.
        self.grupo_atual = None

        self._definir_status(f"Professor(a): {novo['nome']} — relendo a agenda...")
        self.comandos.put((
            "carregar", False, novo["cpf"], novo["senha"], novo.get("escola", ""),
        ))

    def _recarregar(self) -> None:
        self.enviados = carregar_enviados()
        self._definir_status("Atualizando a agenda...")
        self.comandos.put((
            "carregar", False, self.orientador["cpf"], self.orientador["senha"],
            self.orientador.get("escola", ""),
        ))

    def _abrir_aula_sem_agendamento(self) -> None:
        """
        Janela separada para registrar uma aula que aconteceu SEM
        agendamento na agenda do NTE — o professor usou o laboratório (ou
        tablet/projetor) sem reservar, mas a SED ainda precisa do
        registro. Pedida depois de conferir, direto no formulário da SED,
        que os únicos dados que realmente faltam (o resto já é fixo por
        professor/escola, ou são os MESMOS campos de qualquer aula com
        estudantes) são: disciplina/atividade, turma, e quantidade de
        aulas — que numa aula agendada vêm prontos da agenda.

        Um LINK discreto embaixo da tabela abre isto (ver _montar) em vez
        de uma 4ª aba fixa — é o caso raro, não o comum, e não devia
        competir com Laboratório/Manutenção/Formação na tela principal o
        tempo todo.
        """
        dlg = tk.Toplevel(self)
        dlg.title("Registro SED — aula sem agendamento")
        dlg.configure(bg=COR_FUNDO)
        dlg.transient(self)
        dlg.resizable(False, False)

        cartao = ttk.Frame(dlg, style="Cartao.TFrame", padding=18)
        cartao.pack(fill="both", expand=True, padx=14, pady=14)

        ttk.Label(cartao, text="Aula sem agendamento", style="Secao.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        ttk.Label(
            cartao,
            text="Para quando o laboratório (ou tablet/projetor) foi usado sem "
            "reserva na agenda do NTE.",
            style="Suave.TLabel",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 14))

        ttk.Label(cartao, text="Disciplina/atividade:", style="Cartao.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        campo_disciplina = ttk.Entry(cartao, width=28, font=("Segoe UI", 10))
        campo_disciplina.grid(row=2, column=1, sticky="w", padx=(8, 20))
        ttk.Label(cartao, text="Turma (opcional):", style="Cartao.TLabel").grid(
            row=2, column=2, sticky="w"
        )
        campo_turma = ttk.Entry(cartao, width=18, font=("Segoe UI", 10))
        campo_turma.grid(row=2, column=3, sticky="w", padx=(8, 0))

        ttk.Label(cartao, text="Nº de estudantes:", style="Cartao.TLabel").grid(
            row=3, column=0, sticky="w", pady=(14, 0)
        )
        campo_estudantes = ttk.Entry(cartao, width=8, font=("Segoe UI", 11))
        campo_estudantes.grid(row=3, column=1, sticky="w", padx=(8, 20), pady=(14, 0))
        ttk.Label(cartao, text="Quantidade de aulas:", style="Cartao.TLabel").grid(
            row=3, column=2, sticky="w", pady=(14, 0)
        )
        campo_aulas = ttk.Entry(cartao, width=8, font=("Segoe UI", 11))
        campo_aulas.grid(row=3, column=3, sticky="w", padx=(8, 0), pady=(14, 0))

        ttk.Label(cartao, text="Etapa:", style="Cartao.TLabel").grid(
            row=4, column=0, sticky="w", pady=(14, 0)
        )
        combo_etapa = ttk.Combobox(cartao, values=ETAPAS, width=42, state="readonly")
        combo_etapa.grid(row=4, column=1, columnspan=3, sticky="w", padx=(8, 0), pady=(14, 0))

        # Linha que só aparece para AEE/EJA/Ensino Profissional — mesma
        # regra e mesmos textos de _ajustar_campo_extra, só que numa
        # janela separada (widgets próprios, não dá pra reaproveitar os
        # da tela principal).
        linha_extra = ttk.Frame(cartao, style="Cartao.TFrame")
        rotulo_extra = ttk.Label(linha_extra, text="", style="Cartao.TLabel")
        rotulo_extra.pack(side="left")
        combo_extra = ttk.Combobox(linha_extra, values=[], width=30, state="readonly")
        campo_curso = ttk.Entry(linha_extra, width=30, font=("Segoe UI", 10))
        dica_extra = ttk.Label(linha_extra, text="", style="Suave.TLabel")
        dica_extra.pack(side="left", padx=(10, 0))

        def _ajustar_extra(_evento=None) -> None:
            etapa = combo_etapa.get().strip()
            combo_extra.pack_forget()
            campo_curso.pack_forget()
            opcoes = opcoes_subetapa(etapa)
            if opcoes:
                rotulo_extra.configure(text="Qual etapa? (exigido pela SED):")
                combo_extra.configure(values=opcoes)
                if combo_extra.get() not in opcoes:
                    combo_extra.set("")
                combo_extra.pack(side="left", padx=(8, 0), before=dica_extra)
                dica_extra.configure(
                    text="confira — esta etapa pede essa resposta no formulário"
                )
                linha_extra.grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
            elif etapa == ETAPA_PROFISSIONAL:
                rotulo_extra.configure(text="Qual o curso?")
                campo_curso.pack(side="left", padx=(8, 0), before=dica_extra)
                dica_extra.configure(text="")
                linha_extra.grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
            else:
                linha_extra.grid_remove()

        combo_etapa.bind("<<ComboboxSelected>>", _ajustar_extra)

        ttk.Label(cartao, text="Conteúdo aplicado:", style="Cartao.TLabel").grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(14, 4)
        )
        campo_conteudo = tk.Text(
            cartao, height=2, width=60, wrap="word", font=("Segoe UI", 10),
            relief="solid", borderwidth=1, background=COR_CAMPO, foreground=COR_TEXTO,
            insertbackground=COR_TEXTO,
        )
        campo_conteudo.grid(row=7, column=0, columnspan=4, sticky="ew")
        cartao.columnconfigure(3, weight=1)

        ttk.Label(cartao, text="Recursos utilizados:", style="Cartao.TLabel").grid(
            row=8, column=0, columnspan=4, sticky="w", pady=(14, 4)
        )
        caixa_recursos = ttk.Frame(cartao, style="Cartao.TFrame")
        caixa_recursos.grid(row=9, column=0, columnspan=4, sticky="w")
        vars_recursos: dict = {}
        # Mesmo layout do formulário principal (2 por coluna) — ver o
        # comentário em _montar, na criação de self.vars_recursos.
        por_coluna = 2
        for i, recurso in enumerate(RECURSOS_DISPONIVEIS):
            var = tk.BooleanVar(value=False)
            vars_recursos[recurso] = var
            ttk.Checkbutton(caixa_recursos, text=recurso, variable=var).grid(
                row=i % por_coluna, column=i // por_coluna, sticky="w", padx=(0, 18), pady=1
            )

        acoes = ttk.Frame(cartao, style="Cartao.TFrame")
        acoes.grid(row=10, column=0, columnspan=4, sticky="w", pady=(18, 0))
        botao_ok = ttk.Button(acoes, text="Preencher formulário", style="Principal.TButton")
        botao_ok.pack(side="left")
        ttk.Button(acoes, text="Cancelar", style="TButton", command=dlg.destroy).pack(
            side="left", padx=(10, 0)
        )

        def _confirmar() -> None:
            disciplina = campo_disciplina.get().strip()
            if not disciplina:
                messagebox.showinfo(
                    "Disciplina/atividade",
                    "Escreva a disciplina ou atividade trabalhada — esse texto "
                    "é usado para encontrar o componente curricular certo no "
                    "formulário da SED.",
                )
                campo_disciplina.focus_set()
                return
            bruto_aulas = campo_aulas.get().strip()
            if not bruto_aulas.isdigit() or int(bruto_aulas) <= 0:
                messagebox.showinfo(
                    "Quantidade de aulas",
                    "Digite quantas aulas (blocos de 45 min) foram usadas — só "
                    "números.",
                )
                campo_aulas.focus_set()
                return
            bruto_estudantes = campo_estudantes.get().strip()
            if not bruto_estudantes.isdigit() or int(bruto_estudantes) <= 0:
                messagebox.showinfo(
                    "Número de estudantes",
                    "Digite quantos estudantes foram atendidos (só números).",
                )
                campo_estudantes.focus_set()
                return
            etapa = combo_etapa.get().strip()
            if not etapa:
                messagebox.showinfo("Etapa", "Escolha a etapa na lista.")
                return
            subetapa = ""
            curso = ""
            if opcoes_subetapa(etapa):
                subetapa = combo_extra.get().strip()
                if not subetapa:
                    messagebox.showinfo(
                        "Qual etapa?",
                        f"A etapa \"{etapa}\" tem uma pergunta a mais no "
                        "formulário da SED: \"Qual etapa?\".\n\nEscolha a "
                        "resposta ao lado da etapa e tente de novo.",
                    )
                    combo_extra.focus_set()
                    return
            elif etapa == ETAPA_PROFISSIONAL:
                curso = campo_curso.get().strip()
                if not curso:
                    messagebox.showinfo(
                        "Qual o curso?",
                        "O Ensino Profissional pede o nome do curso no "
                        "formulário da SED. Preencha o campo \"Qual o curso?\" "
                        "e tente de novo.",
                    )
                    campo_curso.focus_set()
                    return
            recursos = [r for r, v in vars_recursos.items() if v.get()]
            if not recursos:
                messagebox.showinfo("Recursos", "Marque pelo menos um recurso utilizado.")
                return
            conteudo = campo_conteudo.get("1.0", "end").strip()
            if not conteudo:
                messagebox.showinfo(
                    "Conteúdo aplicado",
                    "Escreva o que foi trabalhado na aula — esse texto vai "
                    "para o campo de conteúdos da SED.",
                )
                campo_conteudo.focus_set()
                return

            turma = campo_turma.get().strip()
            grupo = _RegistroSemAgenda(
                disciplina, turma=turma, numero_aulas=int(bruto_aulas),
                rastrear_como_enviado=True,
            )
            # Sem professor (fica "" — o padrão de _RegistroSemAgenda): quem
            # está registrando já vai numa pergunta própria, na página 1 do
            # formulário da SED — repetir "Prof(a). Fulano" dentro do
            # resumo do projeto é redundante (pedido explícito depois de
            # testar de verdade). A composição do resumo, em
            # NavegadorWorker, já trata professor vazio como turma vazia —
            # só entra "Prof(a). ..." quando há um nome pra mostrar.
            #
            # Sem horário de agenda pra usar (ver _RegistroSemAgenda): a
            # data entra no lugar de "início" e a hora no lugar de "fim",
            # pra chave_grupo (dedup) e o resumo ficarem com algo que
            # identifica ESTE preenchimento, não um "-" pendurado sozinho.
            agora = dt.datetime.now()
            grupo.inicio = agora.strftime("%d/%m/%Y")
            grupo.fim = agora.strftime("%H:%M")
            if chave_grupo(grupo) in self.enviados:
                messagebox.showinfo(
                    "Aula já registrada",
                    "Este exato registro (mesma disciplina/turma, hoje, neste "
                    "minuto) já foi enviado. Espere um minuto e tente de novo "
                    "se realmente for um registro diferente.",
                )
                return

            # Guardado para "Ver no navegador" poder preencher de novo (com
            # a janela do Chrome visível desta vez) sem precisar reabrir
            # este diálogo, que está prestes a ser destruído — ver
            # _coletar_dados_para_preencher, que confere isto ANTES de
            # tentar ler os campos da tela principal.
            self._dados_aula_avulsa = {
                "grupo": grupo,
                "n_estudantes": int(bruto_estudantes),
                "recursos": recursos,
                "etapa": etapa,
                "conteudo": conteudo,
                "subetapa": subetapa,
                "curso": curso,
            }
            comando = (
                "preencher", "aula", grupo, int(bruto_estudantes), recursos, etapa,
                conteudo, self.orientador["nome"], self.orientador["tipo"],
                self.orientador.get("escola", ""), subetapa, curso,
                bool(self.mostrar_navegador.get()),
            )
            self.botao_preencher.configure(state="disabled")
            self.botao_enviar.configure(state="disabled")
            self.botao_ver_no_navegador.configure(state="disabled")
            self._definir_status("Abrindo o formulário e preenchendo (aula sem agendamento)...")
            self.comandos.put(comando)
            dlg.destroy()

        botao_ok.configure(command=_confirmar)
        campo_disciplina.focus_set()
        dlg.grab_set()
        # Centralizada sobre a janela principal — sem isto, o Windows abre
        # este Toplevel num canto meio arbitrário, longe de onde os olhos
        # já estão.
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.wait_window(dlg)

    def _coletar_dados_para_preencher(self, grupo, mostrar: bool):
        """
        Lê e valida os campos da tela para `grupo`, conforme o tipo de
        registro escolhido (aula com estudantes ou suporte/instalação —
        só existe essa escolha para Projetores/Tablets-Celular; Laboratório
        continua sendo sempre "aula"). Devolve o comando pronto para o
        NavegadorWorker, ou None se faltar algo — já tendo avisado a
        pessoa, então quem chama só precisa checar o retorno.

        Compartilhado entre "Preencher formulário" e "Ver no navegador":
        os dois preenchem os MESMOS dados, só muda se a janela do Chrome
        aparece ou não.

        "Suporte a outros espaços", "Manutenção" e "Formação/Reunião" não
        têm `grupo` nenhum (não vêm de agendamento) — desvia pros
        coletores próprios deles, que montam um _RegistroSemAgenda do
        zero.

        "Aula sem agendamento" (ver _abrir_aula_sem_agendamento) também
        desvia — mas por IDENTIDADE do grupo, não por self.categoria_atual
        (o link que abre aquela tela fica dentro das abas de recurso
        normais, então categoria_atual nunca é "Manutenção"/"Formação"
        para ela). Sem este desvio, "Ver no navegador" tentava reler os
        campos da TELA PRINCIPAL — que não têm nada a ver com aquele
        registro, já digitado e destruído junto com o diálogo (achado em
        revisão adversarial, antes de ir pro professor testar).

        Para "aula", disciplina/professor(a)/nº de aulas que vão pro
        NavegadorWorker são os de `self.campo_disciplina` /
        `self.campo_professor` / `self.campo_numero_aulas` (pré-preenchidos
        com grupo.disciplina/professor/numero_aulas, mas editáveis — ver
        _montar) — NUNCA os atributos de `grupo` direto, porque um valor
        errado ou sem correspondência conhecida na agenda (ex.: disciplina
        "_OUTROS") iria assim mesmo pro formulário da SED sem essa
        correção. A agenda do NTE em si nunca é alterada por isso — é só
        o que este envio específico manda pra SED.
        """
        if self._dados_aula_avulsa is not None and grupo is self._dados_aula_avulsa["grupo"]:
            d = self._dados_aula_avulsa
            # "Aula sem agendamento" já tem os próprios campos de
            # disciplina/professor/nº de aulas naquele diálogo (não passa
            # pela barra de "Dados do registro") — grupo.disciplina e
            # grupo.numero_aulas já são o que a pessoa digitou lá, e
            # grupo.professor fica vazio de propósito (ver NavegadorWorker).
            return (
                "preencher", "aula", grupo, d["n_estudantes"], d["recursos"], d["etapa"],
                d["conteudo"], self.orientador["nome"], self.orientador["tipo"],
                self.orientador.get("escola", ""), d["subetapa"], d["curso"],
                grupo.disciplina, grupo.professor, grupo.numero_aulas, mostrar,
            )
        if self.categoria_atual == "Suporte a outros espaços":
            return self._coletar_dados_suporte_avulso(mostrar)
        if self.categoria_atual == "Manutenção":
            return self._coletar_dados_manutencao(mostrar)
        if self.categoria_atual == "Formação/Reunião":
            return self._coletar_dados_formacao(mostrar)

        categoria = _categoria_da_atividade(grupo)
        tipo_registro = self.var_tipo_registro.get() if categoria != "Laboratório" else "aula"
        if categoria != "Laboratório" and not tipo_registro:
            messagebox.showinfo(
                "Tipo de registro",
                "Escolha se foi uma aula com estudantes ou um "
                "suporte/instalação de equipamento antes de preencher.",
            )
            return None

        if tipo_registro == "suporte":
            tipo_atendimento = self.var_tipo_suporte.get().strip()
            if not tipo_atendimento:
                messagebox.showinfo(
                    "Qual foi o atendimento/suporte realizado?",
                    "Escolha uma das opções antes de preencher.",
                )
                return None
            descricao = self.campo_descricao_suporte.get().strip()
            if not descricao:
                messagebox.showinfo(
                    "Breve descrição da atividade",
                    "Descreva rapidamente quem, onde e para quê — esse "
                    "texto vai para o formulário da SED.",
                )
                self.campo_descricao_suporte.focus_set()
                return None
            bruto_aulas = self.campo_aulas_suporte.get().strip()
            if not bruto_aulas.isdigit() or int(bruto_aulas) <= 0:
                messagebox.showinfo(
                    "Quantidade de aulas",
                    "Digite quantas aulas (blocos de 45 min) você levou "
                    "para o suporte/instalação — só números.",
                )
                self.campo_aulas_suporte.focus_set()
                return None
            return (
                "preencher", "suporte", grupo, tipo_atendimento, descricao, int(bruto_aulas),
                self.orientador["nome"], self.orientador["tipo"], self.orientador.get("escola", ""),
                mostrar,
            )

        # tipo_registro == "aula" (Laboratório sempre, ou Projetor/Tablets
        # quando a pessoa escolheu "Aula com estudantes")
        bruto = self.campo_estudantes.get().strip()
        if not bruto.isdigit() or int(bruto) <= 0:
            messagebox.showinfo(
                "Número de estudantes",
                "Digite quantos estudantes foram atendidos (só números).",
            )
            self.campo_estudantes.focus_set()
            return None
        etapa = self.combo_etapa.get().strip()
        if not etapa:
            messagebox.showinfo(
                "Etapa", "Não consegui deduzir a etapa pela turma — escolha na lista."
            )
            return None
        # Etapas com página própria no formulário pedem uma resposta a mais.
        subetapa = ""
        curso = ""
        if opcoes_subetapa(etapa):
            subetapa = self.combo_extra.get().strip()
            if not subetapa:
                messagebox.showinfo(
                    "Qual etapa?",
                    f"A etapa \"{etapa}\" tem uma pergunta a mais no formulário "
                    "da SED: \"Qual etapa?\".\n\nEscolha a resposta ao lado da "
                    "etapa e tente de novo.",
                )
                self.combo_extra.focus_set()
                return None
        elif etapa == ETAPA_PROFISSIONAL:
            curso = self.campo_curso.get().strip()
            if not curso:
                messagebox.showinfo(
                    "Qual o curso?",
                    "O Ensino Profissional pede o nome do curso no formulário "
                    "da SED. Preencha o campo \"Qual o curso?\" e tente de novo.",
                )
                self.campo_curso.focus_set()
                return None

        disciplina = self.campo_disciplina.get().strip()
        if not disciplina:
            messagebox.showinfo(
                "Disciplina/Componente curricular",
                "Escreva a disciplina ou componente curricular — esse texto "
                "decide o campo \"Componente curricular\" no formulário da SED.",
            )
            self.campo_disciplina.focus_set()
            return None
        # Professor(a) pode ficar em branco de propósito (mesma regra de
        # "Aula sem agendamento" — ver comentário em NavegadorWorker) —
        # por isso sem messagebox aqui, só lê e segue.
        professor = self.campo_professor.get().strip()
        bruto_aulas = self.campo_numero_aulas.get().strip()
        if not bruto_aulas.isdigit() or int(bruto_aulas) <= 0:
            messagebox.showinfo(
                "Nº de aulas",
                "Digite quantas aulas (blocos de 45 min) — só números.",
            )
            self.campo_numero_aulas.focus_set()
            return None
        recursos = [r for r, v in self.vars_recursos.items() if v.get()]
        if not recursos:
            messagebox.showinfo("Recursos", "Marque pelo menos um recurso utilizado.")
            return None
        conteudo = self.campo_conteudo.get("1.0", "end").strip()
        if not conteudo:
            messagebox.showinfo(
                "Conteúdo aplicado",
                "Escreva o que foi trabalhado na aula — esse texto vai para o "
                "campo de conteúdos da SED.",
            )
            self.campo_conteudo.focus_set()
            return None
        return (
            "preencher", "aula", grupo, int(bruto), recursos, etapa, conteudo,
            self.orientador["nome"], self.orientador["tipo"], self.orientador.get("escola", ""),
            subetapa, curso, disciplina, professor, int(bruto_aulas), mostrar,
        )

    def _coletar_dados_suporte_avulso(self, mostrar: bool):
        """
        Lê e valida os campos do cartão "Suporte a outros espaços" (aba
        independente, sem agenda) — chamado por _coletar_dados_para_preencher
        quando essa é a aba atual. Devolve o comando pronto, ou None se
        faltar algo (já tendo avisado a pessoa).

        Mesmo formato de comando que o suporte vindo da agenda (ver o
        ramo "suporte" logo abaixo) — o NavegadorWorker não faz distinção
        nenhuma entre os dois, só usa `grupo` como identificador.
        """
        tipo_atendimento = self.var_suporte_avulso_tipo.get().strip()
        if not tipo_atendimento:
            messagebox.showinfo(
                "Qual foi o atendimento/suporte realizado?",
                "Escolha uma das opções antes de preencher.",
            )
            return None
        descricao = self.campo_suporte_avulso_descricao.get().strip()
        if not descricao:
            messagebox.showinfo(
                "Breve descrição da atividade",
                "Descreva rapidamente quem, onde e para quê — esse texto "
                "vai para o formulário da SED.",
            )
            self.campo_suporte_avulso_descricao.focus_set()
            return None
        bruto = self.campo_suporte_avulso_aulas.get().strip()
        if not bruto.isdigit() or int(bruto) <= 0:
            messagebox.showinfo(
                "Quantidade de aulas",
                "Digite quantas aulas (blocos de 45 min) você levou para "
                "o suporte/instalação — só números.",
            )
            self.campo_suporte_avulso_aulas.focus_set()
            return None
        grupo = _RegistroSemAgenda("Suporte a outros espaços")
        return (
            "preencher", "suporte", grupo, tipo_atendimento, descricao, int(bruto),
            self.orientador["nome"], self.orientador["tipo"], self.orientador.get("escola", ""),
            mostrar,
        )

    def _coletar_dados_manutencao(self, mostrar: bool):
        """
        Lê e valida os campos do cartão "Manutenção de equipamentos" —
        chamado por _coletar_dados_para_preencher quando essa é a aba
        atual. Devolve o comando pronto, ou None se faltar algo (já
        tendo avisado a pessoa).
        """
        itens = [item for item, v in self.vars_manutencao.items() if v.get()]
        if not itens:
            messagebox.showinfo(
                "O que recebeu manutenção?",
                "Marque pelo menos um item antes de preencher.",
            )
            return None
        outro_texto = self.campo_manutencao_outro.get().strip()
        if "Outro:" in itens and not outro_texto:
            messagebox.showinfo(
                "O que recebeu manutenção?",
                "Você marcou \"Outro\" — escreva o que foi no campo ao lado.",
            )
            self.campo_manutencao_outro.focus_set()
            return None
        descricao = self.campo_manutencao_descricao.get().strip()
        if not descricao:
            messagebox.showinfo(
                "Breve descrição da manutenção",
                "Descreva rapidamente o que foi feito — esse texto vai para "
                "o formulário da SED.",
            )
            self.campo_manutencao_descricao.focus_set()
            return None
        bruto = self.campo_manutencao_aulas.get().strip()
        if not bruto.isdigit() or int(bruto) <= 0:
            messagebox.showinfo(
                "Quantidade de aulas",
                "Digite quantas aulas (blocos de 45 min) essa manutenção "
                "levou — só números.",
            )
            self.campo_manutencao_aulas.focus_set()
            return None
        grupo = _RegistroSemAgenda("Manutenção de equipamentos")
        return (
            "preencher", "manutencao", grupo, itens, outro_texto, descricao, int(bruto),
            self.orientador["nome"], self.orientador["tipo"], self.orientador.get("escola", ""),
            mostrar,
        )

    def _coletar_dados_formacao(self, mostrar: bool):
        """
        Lê e valida os campos do cartão "Formação/Reunião" — chamado por
        _coletar_dados_para_preencher quando essa é a aba atual. Devolve
        o comando pronto, ou None se faltar algo (já tendo avisado a
        pessoa).
        """
        organizador = self.var_formacao_organizador.get().strip()
        if not organizador:
            messagebox.showinfo(
                "Quem organizou a reunião/formação?",
                "Escolha uma das opções antes de preencher.",
            )
            return None
        outro_texto = self.campo_formacao_outro.get().strip()
        if organizador == "Outro:" and not outro_texto:
            messagebox.showinfo(
                "Quem organizou a reunião/formação?",
                "Você marcou \"Outro\" — escreva quem organizou no campo ao "
                "lado.",
            )
            self.campo_formacao_outro.focus_set()
            return None
        descricao = self.campo_formacao_descricao.get().strip()
        if not descricao:
            messagebox.showinfo(
                "Breve descrição do encontro",
                "Descreva rapidamente do que se tratou — esse texto vai "
                "para o formulário da SED.",
            )
            self.campo_formacao_descricao.focus_set()
            return None
        bruto = self.campo_formacao_aulas.get().strip()
        if not bruto.isdigit() or int(bruto) <= 0:
            messagebox.showinfo(
                "Quantidade de aulas",
                "Digite quantas aulas (blocos de 45 min) esse encontro "
                "levou — só números.",
            )
            self.campo_formacao_aulas.focus_set()
            return None
        grupo = _RegistroSemAgenda("Formação/Reunião")
        return (
            "preencher", "formacao", grupo, organizador, outro_texto, descricao, int(bruto),
            self.orientador["nome"], self.orientador["tipo"], self.orientador.get("escola", ""),
            mostrar,
        )

    def _preencher(self) -> None:
        if str(self.botao_preencher.cget("state")) == "disabled":
            # O botão já reflete "preenchimento em andamento" — mas o
            # atalho <Return> no campo de estudantes chama esta função
            # direto, sem passar pelo botão. Sem esta checagem, um Enter
            # a mais (ou Enter logo depois de um clique) enfileira um
            # segundo "preencher" pro mesmo formulário.
            return
        # "Manutenção" e "Formação/Reunião" não pedem aula selecionada —
        # não vêm de agendamento nenhum (ver CATEGORIAS_INDEPENDENTES).
        independente = self.categoria_atual in CATEGORIAS_INDEPENDENTES
        if not independente and self.grupo_atual is None:
            messagebox.showinfo("Escolha uma aula", "Selecione uma aula na lista primeiro.")
            return
        comando = self._coletar_dados_para_preencher(
            self.grupo_atual, mostrar=bool(self.mostrar_navegador.get())
        )
        if comando is None:
            return
        if not independente:
            if chave_grupo(self.grupo_atual) in self.nao_realizadas:
                if not messagebox.askyesno(
                    "Aula marcada como não realizada",
                    "Esta aula está marcada como NÃO REALIZADA.\n\n"
                    "Quer registrá-la mesmo assim? (a marca será removida)",
                ):
                    return
                desmarcar_nao_realizada(chave_grupo(self.grupo_atual))
                self.nao_realizadas = carregar_nao_realizadas()
            if chave_grupo(self.grupo_atual) in self.enviados:
                if not messagebox.askyesno(
                    "Aula já registrada",
                    "Esta aula já foi enviada antes. Registrar de novo vai duplicar na SED.\n\n"
                    "Quer continuar mesmo assim?",
                ):
                    return
        self.botao_preencher.configure(state="disabled")
        self.botao_enviar.configure(state="disabled")
        self.botao_ver_no_navegador.configure(state="disabled")
        self._definir_status("Preenchendo o formulário...")
        self.comandos.put(comando)

    def _ver_no_navegador(self) -> None:
        """
        Reabre o formulário com a janela do Chrome VISÍVEL, com os mesmos
        dados já preenchidos — para conferir pessoalmente antes de
        enviar.

        Não existe "mostrar a página que já foi preenchida escondida": um
        Chrome headless não vira visível no meio do caminho, é outro
        processo por dentro (ver `_garantir_navegador`, que fecha e
        reabre quando o modo visível/invisível muda). A saída é preencher
        de novo, do zero, mas desta vez com a janela aparecendo — como
        cada campo já foi lido de volta e conferido na primeira vez (é o
        "CONFIRA ANTES DE ENVIAR" do resumo), reescrever os mesmos dados
        não muda nada nem arrisca nada.

        Existe por causa de um erro real: sem esse botão, a saída era
        clicar em "Conta Google da escola" para ver alguma janela do
        Chrome — só que aquele botão abre OUTRO navegador, e trocar de
        modo (headless -> visível) DESCARTA o preenchimento em segundo
        plano sem avisar ninguém. A pessoa fechava aquela janela sem achar
        o formulário preenchido, clicava em Enviar, e o programa quebrava
        tentando usar uma página que já não existia mais.
        """
        if self.preenchido_para is None:
            return
        grupo = self.preenchido_para
        # sempre visível (True) — é o propósito deste botão
        comando = self._coletar_dados_para_preencher(grupo, mostrar=True)
        if comando is None:
            return  # não deveria acontecer: já foi validado ao preencher

        self.botao_preencher.configure(state="disabled")
        self.botao_enviar.configure(state="disabled")
        self.botao_ver_no_navegador.configure(state="disabled")
        self._definir_status("Abrindo o formulário no Chrome para você conferir...")
        self.comandos.put(comando)

    def _enviar(self) -> None:
        if self.preenchido_para is None:
            return
        grupo = self.preenchido_para
        resumo = self._ultimo_resumo_preenchido or {}
        tipo_registro = resumo.get("tipo_registro")
        if tipo_registro == "suporte":
            detalhe = f"{resumo.get('aulas', '?')} aula(s) de suporte/instalação"
        elif tipo_registro in ("manutencao", "formacao"):
            detalhe = f"{resumo.get('aulas', '?')} aula(s)"
        else:
            # resumo['estudantes'] (o número já preenchido de VERDADE no
            # formulário — ver o "preenchido" que guarda este resumo) em
            # vez do campo da tela principal: "Aula sem agendamento" nunca
            # escreve nele (tem seu próprio campo, num diálogo à parte, já
            # destruído a essa altura), então lia lixo de outra aula ou
            # campo vazio — achado em revisão adversarial.
            detalhe = f"{resumo.get('estudantes', self.campo_estudantes.get())} estudantes"
        # Manutenção/Formação não têm turma nem horário (não vêm de
        # agendamento — ver _RegistroSemAgenda), então a segunda linha
        # ficaria vazia/estranha; mostra só disciplina + detalhe pra eles.
        # Aula sem agendamento fica no meio-termo: tem "horário" (data e
        # hora do preenchimento — ver _abrir_aula_sem_agendamento), mas
        # pode não ter turma (campo opcional) — daí as duas partes serem
        # somadas em vez de uma string só fixa, sem linha vazia sobrando.
        # resumo['disciplina'] (o texto que foi de verdade pro formulário —
        # ver o "preenchido" que guarda este resumo), não grupo.disciplina
        # direto: se a pessoa corrigiu o campo (ex.: agenda trouxe
        # "_OUTROS"), a confirmação tem que mostrar o que foi corrigido,
        # senão parece que a correção não valeu — mesma lógica do
        # 'estudantes' logo acima.
        disciplina_confirmacao = resumo.get("disciplina", grupo.disciplina)
        if grupo.turma or grupo.inicio:
            partes = [disciplina_confirmacao]
            if grupo.turma:
                partes.append(grupo.turma)
            partes.append(f"{grupo.inicio}-{grupo.fim} · {detalhe}")
            linha_aula = "\n".join(partes)
        else:
            linha_aula = f"{disciplina_confirmacao}\n{detalhe}"
        if not messagebox.askyesno(
            "Confirmar envio",
            f"Enviar este registro para a SED?\n\n"
            f"{linha_aula}\n\n"
            f"Registrando como: {self.orientador['nome']}",
        ):
            return
        self.botao_enviar.configure(state="disabled")
        self.botao_ver_no_navegador.configure(state="disabled")
        self._definir_status("Enviando...")
        self._envio_em_andamento = True
        self.comandos.put(("enviar", grupo))

    def _alternar_nao_realizada(self) -> None:
        """
        Marca (ou desmarca) a aula selecionada como não realizada.

        Nada é enviado para a SED aqui — não houve atividade, então não há
        o que registrar. A marca serve só para essa aula sumir da fila de
        pendentes e parar de ser sugerida.
        """
        if self.grupo_atual is None:
            messagebox.showinfo("Escolha uma aula", "Selecione uma aula na lista primeiro.")
            return
        grupo = self.grupo_atual
        chave = chave_grupo(grupo)
        dia = dt.date.fromisoformat(grupo.data).strftime("%d/%m")
        descricao = f"{dia} · {grupo.inicio}-{grupo.fim} · {grupo.disciplina} · {grupo.turma}"

        if chave in self.nao_realizadas:
            if not messagebox.askyesno(
                "Desfazer",
                f"Voltar esta aula para a fila de pendentes?\n\n{descricao}",
            ):
                return
            desmarcar_nao_realizada(chave)
        else:
            if chave in self.enviados:
                messagebox.showinfo(
                    "Aula já registrada",
                    "Esta aula já foi enviada para a SED, então não dá para "
                    "marcá-la como não realizada.\n\nSe o registro foi indevido, "
                    "é preciso resolver isso direto com a SED.",
                )
                return
            if not messagebox.askyesno(
                "Aula não realizada",
                "Marcar esta aula como NÃO REALIZADA?\n\n"
                f"{descricao}\n\n"
                "Ela não será registrada na SED e sai da lista de pendentes.",
            ):
                return
            marcar_nao_realizada(chave)
            # se o formulário já estava preenchido para essa aula, o
            # preenchimento perde o sentido — descarta antes que alguém
            # clique em Enviar sem querer
            if self.preenchido_para is grupo:
                self.preenchido_para = None
                self.botao_enviar.configure(state="disabled")
                self.botao_ver_no_navegador.configure(state="disabled")
                self.comandos.put(("reiniciar",))

        self.nao_realizadas = carregar_nao_realizadas()
        self._preencher_tabela()
        self._definir_status(
            "Aula marcada como não realizada."
            if chave in self.nao_realizadas
            else "Aula devolvida para a fila de pendentes."
        )

    def _cancelar(self) -> None:
        self.preenchido_para = None
        self.botao_enviar.configure(state="disabled")
        self.botao_ver_no_navegador.configure(state="disabled")
        self.botao_preencher.configure(state="normal")
        self.campo_disciplina.delete(0, "end")
        self.campo_professor.delete(0, "end")
        self.campo_numero_aulas.delete(0, "end")
        self.campo_estudantes.delete(0, "end")
        for var in self.vars_recursos.values():
            var.set(False)
        self.campo_conteudo.delete("1.0", "end")
        self._escrever("")
        self._definir_status("Cancelado — nada foi enviado. Escolha uma aula.")
        self.comandos.put(("reiniciar",))
        self._preencher_tabela()

    def _cancelar_relogios_pendentes(self, evento) -> None:
        """
        Cancela todo after() ainda pendente assim que a janela é
        destruída — de QUALQUER jeito que isso aconteça (X, _fechar(), ou
        um destroy() direto, como num script de teste).

        Ligada em <Destroy> (ver __init__) em vez de só confiar em
        winfo_exists() dentro de cada relógio: uma checagem dessas não
        ajuda aqui, porque o Tcl falha ao tentar CHAMAR o callback (não
        dentro dele) depois que o interpretador/janela já sumiu — daí o
        "invalid command name ..._ler_eventos" visto testando de verdade.
        Cancelando o job aqui, o Tcl nem chega a tentar. Mesmo problema,
        mesmo remédio, do Caps Lock em
        configuracao.TelaDeEntrada._checar_caps_lock.
        """
        if evento.widget is not self:
            return  # <Destroy> também dispara para cada widget filho
        for job_id in self._after_ids.values():
            try:
                self.after_cancel(job_id)
            except Exception:
                pass
        self._after_ids.clear()

    def _fechar(self) -> None:
        # Fechar no meio de um envio é o pior momento possível: se o
        # clique em "Enviar" já tiver dado certo do lado da SED e o
        # programa for embora antes do evento "enviado" voltar, a aula
        # nunca é marcada como enviada aqui — e reaparece como pendente,
        # arriscando um registro duplicado na próxima vez que abrir.
        if self._envio_em_andamento and not messagebox.askyesno(
            "Envio em andamento",
            "Ainda estou enviando este registro para a SED — feche só depois "
            'de ver a mensagem "Registro enviado para a SED".\n\n'
            "Se fechar agora, o envio pode terminar do lado da SED sem que o "
            "programa saiba disso aqui, e a aula voltaria a aparecer como "
            "pendente (risco de duplicar o registro).\n\n"
            "Fechar mesmo assim?",
        ):
            return
        self._encerrar_worker()
        self.destroy()

    def _encerrar_worker(self) -> None:
        """
        Manda a thread do navegador sair e ESPERA (até 8s) ela terminar
        antes de continuar.

        Sem esperar, o processo pode ir embora (ou, na atualização
        automática, a versão NOVA pode abrir) antes do Chrome da sessão
        persistente (browser_profile) ter soltado o perfil de verdade — a
        thread do navegador é "daemon" e é interrompida na hora se o
        processo principal encerrar primeiro, sem chance de fechar o
        Chrome direito. Um Chrome que não fechou por completo deixa uma
        trava (SingletonLock) na pasta do perfil, e a próxima tentativa de
        abrir esse MESMO perfil esbarra nela e falha — foi exatamente
        esse o "erro que precisa fechar e abrir de novo" visto depois de
        uma atualização automática (ver `_oferecer_atualizacao`, que
        chama isto ANTES de abrir a versão nova, não depois).

        O timeout é rede de segurança, não o caminho esperado: se o
        Chrome estiver mesmo travado, é melhor o programa fechar do jeito
        antigo (arriscando a trava) do que travar para sempre esperando.
        """
        self.comandos.put(("sair",))
        # 15s, não 8: "Sair da conta" agora enfileira um "sair_google" antes
        # deste "sair" (ver _sair_da_conta), que faz uma ida de verdade até
        # o site do Google para deslogar a conta da escola — precisa de
        # folga além do simples fechar do Chrome.
        self.worker.join(timeout=15)

    # -- eventos vindos da thread do navegador ------------------------------
    def _ler_eventos(self) -> None:
        """
        Lê os eventos que a thread do navegador colocou na fila e atualiza
        a tela.

        Reagendada em `finally`, não no fim do corpo: um erro inesperado
        ao processar UM evento (um KeyError num campo que faltou, um
        TclError num widget) não pode fazer esta função nunca mais ser
        chamada — foi exatamente isso que já aconteceu aqui, e o efeito é
        silencioso e grave: a tela para de reagir a QUALQUER coisa (status,
        botões, "enviado com sucesso") pelo resto da sessão, sem avisar.
        Cada evento é processado no seu próprio try/except por causa
        disso: um evento com problema não pode impedir os próximos, já
        enfileirados, de serem lidos.
        """
        try:
            while True:
                try:
                    evento = self.eventos.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._processar_evento(evento)
                except Exception:
                    traceback.print_exc()
        finally:
            self._after_ids["ler_eventos"] = self.after(100, self._ler_eventos)

    def _processar_evento(self, evento) -> None:
        tipo = evento[0]
        if tipo == "status":
            self._definir_status(evento[1])
        elif tipo == "aulas":
            self.grupos = evento[1]
            quieto = bool(evento[2]) if len(evento) > 2 else False
            self.enviados = carregar_enviados()
            # Aulas que já começaram há mais tempo que a janela de
            # aviso entram como "já avisadas": abrir o programa às
            # 15h não deve piscar de uma vez pela manhã inteira.
            agora = agora_sc()
            for g in self.grupos:
                if (agora - self._momento_inicio(g, agora)).total_seconds() > JANELA_AVISO_MIN * 60:
                    self._ja_avisadas.add(chave_grupo(g))
            self._preencher_tabela()
            if self.grupo_atual is None and not self.grupos:
                self._escrever("Nenhuma aula encontrada nesta semana.")
            if not quieto:
                self._trazer_para_frente()
                # Primeira agenda carregada nesta sessão (não as
                # releituras silenciosas de 30 em 30 min): aproveita para
                # já conferir a conta Google da escola, em vez de esperar
                # a pessoa lembrar de clicar em "Conta Google da escola"
                # e só descobrir no meio do preenchimento que precisa
                # logar. Faz sentido logo aqui porque "Sair da conta"
                # agora desloga o Google da escola — toda sessão nova
                # começa deslogada de propósito.
                if not self._conta_google_verificada:
                    self._conta_google_verificada = True
                    self.comandos.put(
                        ("conta_google", self.orientador.get("escola", ""))
                    )
        elif tipo == "preenchido":
            _, grupo, resumo = evento
            self.preenchido_para = grupo
            self._ultimo_resumo_preenchido = resumo
            self.botao_preencher.configure(state="normal")
            self.botao_enviar.configure(state="normal")
            self.botao_ver_no_navegador.configure(state="normal")
            if resumo.get("tipo_registro") == "suporte":
                self._escrever(
                    "CONFIRA ANTES DE ENVIAR\n"
                    f"  Atendimento .... {resumo['tipo_atendimento']}\n"
                    f"  Descrição ...... {resumo['descricao']}\n"
                    f"  Nº de aulas .... {resumo['aulas']}"
                    + _texto_conferencia(resumo.get("conferencia"))
                )
            elif resumo.get("tipo_registro") == "manutencao":
                linha_outro = ""
                if resumo.get("outro_texto"):
                    linha_outro = f"  Outro .......... {resumo['outro_texto']}\n"
                self._escrever(
                    "CONFIRA ANTES DE ENVIAR\n"
                    f"  Recebeu manutenção .... {', '.join(resumo['itens'])}\n"
                    + linha_outro
                    + f"  Descrição ...... {resumo['descricao']}\n"
                    f"  Nº de aulas .... {resumo['aulas']}"
                    + _texto_conferencia(resumo.get("conferencia"))
                )
            elif resumo.get("tipo_registro") == "formacao":
                linha_outro = ""
                if resumo.get("outro_texto"):
                    linha_outro = f"  Outro .......... {resumo['outro_texto']}\n"
                self._escrever(
                    "CONFIRA ANTES DE ENVIAR\n"
                    f"  Organizado por.. {resumo['organizador']}\n"
                    + linha_outro
                    + f"  Descrição ...... {resumo['descricao']}\n"
                    f"  Nº de aulas .... {resumo['aulas']}"
                    + _texto_conferencia(resumo.get("conferencia"))
                )
            else:
                linha_sub = ""
                if resumo.get("subetapa"):
                    linha_sub = f"  Qual etapa? .... {resumo['subetapa']}\n"
                self._escrever(
                    "CONFIRA ANTES DE ENVIAR\n"
                    f"  Etapa .......... {resumo['etapa']}\n"
                    + linha_sub
                    + f"  Componente ..... {_texto_componente(resumo['componente'])}\n"
                    f"  Resumo ......... {resumo['resumo']}\n"
                    f"  Nº de aulas .... {resumo['aulas']}\n"
                    f"  Estudantes ..... {resumo['estudantes']}\n"
                    f"  Conteúdos ...... {resumo['conteudos']}\n"
                    f"  Recursos ....... {', '.join(resumo['recursos'])}"
                    + _texto_conferencia(resumo.get("conferencia"))
                )
            # o Chrome está na frente depois de preencher — traz o
            # programa de volta, que é onde fica o botão de enviar
            self._trazer_para_frente()
        elif tipo == "enviado":
            _, grupo = evento
            self._envio_em_andamento = False
            self.enviados = carregar_enviados()
            self.preenchido_para = None
            self.botao_enviar.configure(state="disabled")
            self.botao_ver_no_navegador.configure(state="disabled")
            self.botao_preencher.configure(state="normal")
            self.campo_disciplina.delete(0, "end")
            self.campo_professor.delete(0, "end")
            self.campo_numero_aulas.delete(0, "end")
            self.campo_estudantes.delete(0, "end")
            self.var_tipo_suporte.set("")
            self.campo_descricao_suporte.delete(0, "end")
            self.campo_aulas_suporte.delete(0, "end")
            self.var_suporte_avulso_tipo.set("")
            self.campo_suporte_avulso_descricao.delete(0, "end")
            self.campo_suporte_avulso_aulas.delete(0, "end")
            for var in self.vars_manutencao.values():
                var.set(False)
            self.campo_manutencao_outro.delete(0, "end")
            self.campo_manutencao_descricao.delete(0, "end")
            self.campo_manutencao_aulas.delete(0, "end")
            self.var_formacao_organizador.set("")
            self.campo_formacao_outro.delete(0, "end")
            self.campo_formacao_descricao.delete(0, "end")
            self.campo_formacao_aulas.delete(0, "end")
            self._ultimo_resumo_preenchido = None
            self._escrever("Registro enviado para a SED.")
            self._preencher_tabela()
        elif tipo == "atualizacao":
            self._oferecer_atualizacao(evento[1])
        elif tipo == "aviso_atualizacao":
            messagebox.showinfo("Atualização", evento[1])
        elif tipo == "conta_google":
            # Só chega aqui quando NÃO está conectado (ver NavegadorWorker)
            # — pede pra entrar. O caso já-conectado nem passa por cá; ele
            # some direto pra "conta_google_pronta", sem interromper a
            # pessoa com uma mensagem à toa.
            self._definir_status("Entre com a conta da escola na janela do Chrome.")
            messagebox.showinfo(
                "Entrar na conta da escola",
                "Abri o formulário numa janela do Chrome e ele parou "
                "na tela de entrada do Google.\n\n"
                "Entre ali com o e-mail institucional da escola (o "
                "mesmo que responde o formulário da SED). Assim que "
                "você terminar, o programa fecha essa janela sozinho "
                "e volta pra tela principal.",
            )
        elif tipo == "conta_google_pronta":
            estado = evento[1]
            conta = estado.get("conta") or ""
            self._definir_status(
                "Conta Google da escola conectada" + (f" ({conta})" if conta else "") + "."
            )
            self._trazer_para_frente()
        elif tipo == "erro":
            self.botao_preencher.configure(state="normal")
            # Erro ao ENVIAR: o formulário preenchido continua lá na
            # janela do Chrome, então reabilita "Enviar" também —
            # senão a única saída seria preencher tudo de novo por
            # causa de, por exemplo, uma internet lenta.
            if len(evento) > 2 and evento[2] == "enviar":
                self.botao_enviar.configure(state="normal")
                self.botao_ver_no_navegador.configure(state="normal")
                self._envio_em_andamento = False
            self._escrever("DEU ERRO\n\n" + _mensagem_amigavel_de_erro(evento[1]))


def _reabrir_e_sair() -> None:
    """
    Sai do programa — quem chamou já avisou a pessoa pra abrir de novo NA
    MÃO (ver o messagebox logo antes de cada chamada daqui).

    Necessário depois de mexer no cadastro: escola, regional e nome são
    lidos UMA vez, quando o programa abre, e distribuídos para os módulos
    que preenchem o formulário. Continuar rodando depois de mudá-los
    daria o pior dos mundos — a tela mostrando o dado novo e o registro
    saindo com o antigo.

    NÃO reabre sozinho como .exe (mudou depois de visto ao vivo, com
    print de tela: reabrir rápido demais — o processo antigo morrendo
    quase no mesmo instante em que o novo nasce — deu no MÍNIMO três
    erros diferentes, nenhum consertável por dentro do programa porque
    acontecem ANTES ou DURANTE a inicialização do Python/Tcl, antes de
    qualquer código nosso rodar: "Security validation failure" do
    Chromium, "Can't find a usable init.tcl" e até "Failed to start
    embedded python interpreter" — este último nem chega a ser uma
    exceção Python, é o PRÓPRIO INTERPRETADOR que não conseguiu
    nascer. Reabrir na mão sempre funcionou, porque dá um tempo natural
    — nem que sejam só alguns segundos — entre o processo antigo sumir
    de vez e o novo começar. Rodando do código-fonte (não empacotado)
    continua reabrindo sozinho: é ambiente de desenvolvimento, sem
    esse risco.
    """
    try:
        if not empacotado():
            subprocess.Popen([sys.executable] + sys.argv, close_fds=True)
    except Exception:
        pass
    raise SystemExit(0)


def _professores_cadastrados() -> list:
    """
    Lê os professores direto do arquivo, e não da configuração carregada
    na abertura: assim um cadastro feito agora aparece na tela de entrada
    sem precisar reabrir nada.
    """
    dados = configuracao.carregar()
    escola_global = dados.get("escola") or ESCOLA
    return [
        {
            "nome": p.get("nome", ""),
            "cpf": p.get("cpf", ""),
            "senha": "",
            "tipo": p.get("tipo", "tecnologias"),
            "turnos": p.get("turnos") or list(TODOS_TURNOS),
            # turno POR escola (pode ser diferente de uma pra outra) —
            # repassado adiante pra TelaDeEntrada resolver qual vale assim
            # que a escola da sessão é escolhida (ver configuracao.
            # turnos_da_escola). Sem isto aqui, a distinção se perdia e
            # toda escola usava o turno "geral" (a união de todas).
            "turnos_por_escola": p.get("turnos_por_escola") or {},
            # sempre em lista — pode ter mais de uma. `configuracao.
            # pedir_escola()` decide se pergunta ou não (só pergunta
            # havendo mais de uma).
            "escolas": configuracao.escolas_do_professor(p) or [escola_global],
        }
        for p in (dados.get("professores") or [])
        if (p.get("nome") or "").strip()
    ]


def _quem_provavelmente_esta_usando(professores: list) -> str:
    """Palpite para já vir escolhido na tela de entrada: turno, depois hábito."""
    turno = turno_do_horario(agora_sc())
    candidatos = [p for p in professores if turno in (p.get("turnos") or [])]
    if len(candidatos) == 1:
        return candidatos[0]["nome"]
    lembrado = carregar_ultimo_professor()
    nomes = [p["nome"] for p in professores]
    if lembrado in nomes:
        return lembrado
    return nomes[0] if nomes else ""


def _entrar_no_programa():
    """
    Quem vai usar o programa agora — e com qual senha.

    Devolve (professor, senha) para a janela, ou None quando a pessoa
    desiste (fecha a tela de entrada).

    No formato antigo (.env com a senha salva) não há o que perguntar: o
    programa abre direto, como sempre abriu.
    """
    if SENHAS_SALVAS:
        return (None, "")

    professores = _professores_cadastrados()
    if not professores:
        # sem ninguém cadastrado não há como entrar: cadastra e reabre
        if configuracao.pedir_configuracao_inicial() is None:
            return None
        messagebox.showinfo(
            "Cadastro feito",
            "Pronto. Feche o programa e abra de novo pelo atalho de sempre.",
        )
        _reabrir_e_sair()

    resposta = configuracao.pedir_entrada(
        professores, sugerido=_quem_provavelmente_esta_usando(professores)
    )
    if resposta is None:
        return None
    if resposta[0] == "CADASTRAR":
        if configuracao.pedir_configuracao_inicial() is not None:
            messagebox.showinfo(
                "Cadastro feito",
                "Pronto. Feche o programa e abra de novo pelo atalho de sempre.",
            )
            _reabrir_e_sair()
        return _entrar_no_programa()
    professor, senha = resposta
    professor["senha"] = senha
    return (professor, senha)


def main() -> None:
    # Rede de segurança: aberta pelo atalho, a janela roda SEM terminal
    # atrás. Se algo estourar antes dela aparecer (ex: falta uma
    # dependência), sem isto o programa morreria em silêncio e daria a
    # impressão de que "não abre". Assim, o erro aparece numa caixinha.
    global ERRO_JA_MOSTRADO
    try:
        # Laço de conta: entra -> usa -> sai -> entra de novo. É ele que
        # permite o revezamento numa máquina compartilhada sem fechar e
        # abrir o programa a cada troca de turno.
        while True:
            entrada = _entrar_no_programa()
            if entrada is None:
                return
            janela = Janela(*entrada)
            janela.mainloop()
            if not getattr(janela, "sair_da_conta", False):
                return
    except Exception:
        detalhe = traceback.format_exc()
        try:
            raiz = tk.Tk()
            raiz.withdraw()
            messagebox.showerror("Erro ao abrir o programa", detalhe)
            raiz.destroy()
            # avisa o iniciar.py de que a pessoa JÁ viu a mensagem, para
            # não aparecerem duas caixinhas dizendo a mesma coisa
            ERRO_JA_MOSTRADO = True
        except Exception:
            print(detalhe)
        raise


if __name__ == "__main__":
    main()
