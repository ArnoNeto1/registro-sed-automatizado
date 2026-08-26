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

Como abrir: dê dois cliques em "Registro SED.bat" (na Área de Trabalho),
ou rode `python app.py` na pasta do projeto.

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
    caminho,
    empacotado,
    garantir_env,
    limpar_sobras,
    pasta_do_programa,
)

# Quem baixa o .exe baixa um arquivo só: o modelo de configuração precisa
# aparecer ao lado dele na primeira execução, senão não há o que preencher.
garantir_env()

load_dotenv(pasta_do_programa() / ".env")

from agenda_scraper import TURNOS, filtrar_e_agrupar, login, scrape_week  # noqa: E402
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
    RECURSOS_PADRAO,
    SED_FORM_URL,
    configuracao_incompleta,
    curso_sugerido,
    etapa_para_turma,
    resolver_componente,
    rotulo_curto,
    subetapa_sugerida,
    SENHAS_SALVAS,
    TODOS_TURNOS,
    turno_do_horario,
)
import configuracao  # noqa: E402
from main import (  # noqa: E402
    ESTADO_FILE,  # noqa: F401  (mantido pra deixar claro de onde vem o estado)
    PROFILE_DIR,
    RECURSOS_DISPONIVEIS,
    agora_sc,
    carregar_enviados,
    chave_grupo,
    ja_comecou,
    marcar_enviado,
    monday_of,
)
from sed_form_filler import (  # noqa: E402
    enviar,
    preencher_atividade_com_estudantes,
    preencher_dados_fixos,
)

# O iniciar.py olha esta marca para não repetir um aviso que a pessoa já viu.
ERRO_JA_MOSTRADO = False


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

# Ritmo do verde piscando na linha "Sugerida agora". 700ms chama atenção
# sem virar aquele pisca-pisca que cansa a vista em poucos minutos.
INTERVALO_PISCA_MS = 700
VERDE_PISCA = ("#dff3e7", "#7fd4a8")

# Cor da linha selecionada. Cinza-ardósia de propósito: azul, laranja e
# verde já significam coisas na coluna Situação, e mais uma cor com
# significado atrapalharia a leitura.
SELECAO_BG = "#4a5568"
SELECAO_FG = "#ffffff"

COR_FUNDO = "#f4f6f8"
COR_CARTAO = "#ffffff"
COR_TEXTO = "#1f2933"
COR_SUAVE = "#6b7280"
COR_DESTAQUE = "#2f6f4e"


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
NAO_REALIZADAS_FILE = caminho("aulas_nao_realizadas.json")

# Guarda qual professor foi escolhido da última vez. Em escola com dois
# orientadores dividindo o computador, ninguém quer reescolher o próprio
# nome toda vez que abre o programa.
ULTIMO_PROF_FILE = caminho("ultimo_professor.txt")


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
    if os.path.exists(NAO_REALIZADAS_FILE):
        try:
            with open(NAO_REALIZADAS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            # arquivo corrompido não pode derrubar o programa inteiro
            return set()
    return set()


def _salvar_nao_realizadas(chaves: set) -> None:
    with open(NAO_REALIZADAS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(chaves), f, ensure_ascii=False, indent=2)


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
        ("carregar",)
        ("preencher", grupo, n_estudantes, recursos, etapa)
        ("enviar", grupo)
        ("reiniciar",)
        ("sair",)

    Eventos devolvidos (lidos pela janela em eventos):
        ("status", texto)
        ("aulas", lista_de_grupos)
        ("preenchido", grupo, resumo_dict)
        ("enviado", grupo)
        ("erro", mensagem)
    """

    def __init__(self, comandos: queue.Queue, eventos: queue.Queue):
        super().__init__(daemon=True)
        self.comandos = comandos
        self.eventos = eventos
        self._page = None
        self._context = None

    # -- utilidades ---------------------------------------------------------
    def _status(self, texto: str) -> None:
        self.eventos.put(("status", texto))

    def _garantir_navegador(self, p):
        """
        Navegador VISÍVEL, usado só para preencher o formulário da SED.

        É visível de propósito: você acompanha o preenchimento acontecendo
        e, na primeira vez, faz o login da conta Google nele. Ele usa um
        perfil salvo em disco (PROFILE_DIR), que é o que guarda esse login
        entre uma execução e outra.
        """
        if self._page is not None:
            return self._page
        self._status("Abrindo o navegador...")
        self._context, nome = abrir_contexto(
            p,
            PROFILE_DIR,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        self._status(f"Navegador aberto ({nome}).")
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self._page

    def _raspar_agenda(self, p, cpf: str, senha: str, invisivel: bool, quieto: bool = False):
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
            login(pagina, cpf, senha)
            if not quieto:
                self._status("Lendo os agendamentos da semana...")
            agendamentos = scrape_week(pagina, monday_of(dt.date.today()), list(TURNOS))
            return filtrar_e_agrupar(agendamentos, None)
        finally:
            navegador.close()

    def _ler_agenda(self, p, cpf: str, senha: str, quieto: bool = False):
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
            return self._raspar_agenda(p, cpf, senha, invisivel=True, quieto=quieto)
        except Exception:
            # Alguns sites se comportam diferente sem janela. Se a leitura
            # em segundo plano falhar, tenta de novo com janela visível
            # antes de desistir — melhor uma janela aparecendo do que o
            # programa sem a lista de aulas.
            self._status("Não deu para ler em segundo plano; tentando com janela...")
            return self._raspar_agenda(p, cpf, senha, invisivel=False)

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
                    break
                try:
                    if acao == "carregar":
                        # ("carregar", quieto, cpf, senha)
                        quieto = bool(comando[1]) if len(comando) > 1 else False
                        cpf = comando[2] if len(comando) > 2 else ""
                        senha = comando[3] if len(comando) > 3 else ""
                        grupos = self._ler_agenda(p, cpf, senha, quieto=quieto)
                        self.eventos.put(("aulas", grupos, quieto))
                        if not quieto:
                            self._status("Agenda carregada.")

                    elif acao == "preencher":
                        (_, grupo, n_estudantes, recursos, etapa, conteudos,
                         prof_nome, prof_tipo, subetapa, curso) = comando
                        page = self._garantir_navegador(p)
                        self._status("Abrindo o formulário e preenchendo...")
                        preencher_dados_fixos(page, prof_nome, prof_tipo)
                        resumo = (
                            f"{grupo.disciplina} ({grupo.turma}) - "
                            f"Prof(a). {grupo.professor} - {grupo.inicio}-{grupo.fim}"
                        )
                        preencher_atividade_com_estudantes(
                            page,
                            disciplina_agendamento=grupo.disciplina,
                            etapa=etapa,
                            resumo_projeto=resumo,
                            numero_aulas=grupo.numero_aulas,
                            numero_estudantes=n_estudantes,
                            conteudos_abordados=conteudos,
                            recursos_utilizados=recursos,
                            orientador_tipo=prof_tipo,
                            subetapa=subetapa,
                            curso=curso,
                        )
                        if etapa == ETAPA_PROFISSIONAL:
                            componente = ("CURSO", f"{curso} · {grupo.disciplina}")
                        elif etapa == ETAPA_AEE:
                            componente = ("AEE", subetapa)
                        else:
                            componente = resolver_componente(grupo.disciplina, etapa)
                            if componente is None:
                                componente = ("OUTRO", grupo.disciplina)
                        self.eventos.put(
                            (
                                "preenchido",
                                grupo,
                                {
                                    "etapa": etapa,
                                    "subetapa": subetapa,
                                    "componente": componente,
                                    "resumo": resumo,
                                    "aulas": grupo.numero_aulas,
                                    "estudantes": n_estudantes,
                                    "conteudos": conteudos,
                                    "recursos": recursos,
                                },
                            )
                        )
                        self._status("Formulário pronto — confira e clique em Enviar.")

                    elif acao == "enviar":
                        _, grupo = comando
                        page = self._garantir_navegador(p)
                        self._status("Enviando para a SED...")
                        enviar(page)
                        marcar_enviado(chave_grupo(grupo))
                        self.eventos.put(("enviado", grupo))
                        self._status("Enviado com sucesso.")

                    elif acao == "reiniciar":
                        # Só reabre o formulário em branco. Não é preciso
                        # "desfazer" nada: enquanto não se clica em Enviar,
                        # nada chegou na SED.
                        if self._page is not None:
                            self._status("Cancelando e limpando o formulário...")
                            self._page.goto(
                                SED_FORM_URL, wait_until="domcontentloaded", timeout=60000
                            )
                        self._status("Cancelado — nada foi enviado.")

                except Exception as exc:  # noqa: BLE001 - queremos mostrar qualquer erro na tela
                    detalhe = "".join(
                        traceback.format_exception_only(type(exc), exc)
                    ).strip()
                    self.eventos.put(("erro", detalhe))
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
        self._ja_avisadas: set = set()

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

        self._montar()
        self._dimensionar()
        self.after(100, self._ler_eventos)
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        # Procura versão nova em segundo plano. Numa thread separada
        # porque uma internet lenta não pode segurar a janela fechada.
        threading.Thread(target=self._procurar_atualizacao, daemon=True).start()

        # Antes de qualquer coisa: os dados obrigatórios estão
        # configurados? Se não, avisar AGORA — de nada adianta carregar a
        # agenda se o registro vai sair com o nome ou a escola errados.
        self.after(300, self._checar_configuracao)

        # carrega a agenda sozinho ao abrir
        self._definir_status("Carregando a agenda da semana...")
        self.comandos.put(("carregar", False, self.orientador["cpf"], self.orientador["senha"]))

        # relógio do aviso de início de aula + reconsulta periódica
        self.after(INTERVALO_CHECAGEM_MS, self._verificar_inicio_de_aula)
        self.after(INTERVALO_RECONSULTA_MS, self._recarregar_silencioso)

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
        estilo.configure("Titulo.TLabel", background=COR_FUNDO, font=("Segoe UI", 17, "bold"))
        estilo.configure("Sub.TLabel", background=COR_FUNDO, foreground=COR_SUAVE, font=("Segoe UI", 10))
        estilo.configure(
            "Rodape.TLabel", background=COR_FUNDO, foreground="#9aa5b1", font=("Segoe UI", 8)
        )
        estilo.configure("Rodape.TButton", font=("Segoe UI", 8), padding=(6, 2))
        estilo.configure(
            "SubAviso.TLabel",
            background=COR_FUNDO,
            foreground="#a1663a",
            font=("Segoe UI", 10, "bold"),
        )
        estilo.configure("Secao.TLabel", background=COR_CARTAO, font=("Segoe UI", 11, "bold"))
        estilo.configure("TButton", font=("Segoe UI", 10), padding=8)
        estilo.configure("Principal.TButton", font=("Segoe UI", 11, "bold"), padding=10)
        estilo.configure("TCheckbutton", background=COR_CARTAO)
        estilo.map(
            "Treeview",
            background=[("selected", SELECAO_BG)],
            foreground=[("selected", SELECAO_FG)],
        )
        self._estilo = estilo  # guardado para o piscar mexer na seleção

        topo = ttk.Frame(self, padding=(20, 16, 20, 8))
        topo.pack(fill="x")
        ttk.Label(topo, text="Registro de Atividades — SED-SC", style="Titulo.TLabel").pack(anchor="w")
        # Escola e nome vêm da configuração, não fixos no código: assim,
        # quem receber uma cópia do programa vê os PRÓPRIOS dados aqui — e,
        # se esquecer de configurar, percebe na hora, porque vai aparecer o
        # nome de outra pessoa logo no alto da janela.
        # ESCOLA é mostrada exatamente como está configurada, sem .title():
        # os nomes do formulário da SED são cheios de siglas (EEB, EEF,
        # CEDUP, CEJA) e o .title() as estragava — "EEB" virava "Eeb".
        #
        # E, enquanto faltar configuração, o cabeçalho mostra uma frase
        # que diz O QUE FAZER. Antes ele exibia o texto interno de aviso
        # ("!! PREENCHA ORIENTADOR_NOME NO .env !!"), que parecia defeito
        # do programa em vez de instrução para a pessoa.
        if configuracao_incompleta():
            subtitulo = "Configuração pendente — abra o arquivo .env e preencha seus dados"
            estilo_sub = "SubAviso.TLabel"
        else:
            subtitulo = f"{ESCOLA} · {ORIENTADOR_NOME} · Tecnologias Educacionais"
            estilo_sub = "Sub.TLabel"
        ttk.Label(topo, text=subtitulo, style=estilo_sub).pack(anchor="w", pady=(2, 0))

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
        ttk.Button(cabecalho, text="Atualizar agenda", command=self._recarregar).pack(side="right")

        corpo_lista = ttk.Frame(cartao_lista, style="Cartao.TFrame")
        corpo_lista.pack(fill="both", expand=True, pady=(10, 0))

        colunas = ("quando", "professor", "disciplina", "turma", "situacao")
        self.tabela = ttk.Treeview(
            corpo_lista, columns=colunas, show="headings", height=5, selectmode="browse"
        )
        # larguras somando pouco menos que a janela, senão a última coluna
        # ("Situação") fica cortada fora da tela.
        for col, titulo, largura, estica in (
            ("quando", "Dia e horário", 140, False),
            ("professor", "Professor(a)", 200, True),
            ("disciplina", "Disciplina", 195, True),
            ("turma", "Turma", 150, True),
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
        self.tabela.tag_configure("enviada", foreground="#1d5fa8")        # azul
        self.tabela.tag_configure("nao_realizada", foreground="#a1663a")  # laranja
        self.tabela.tag_configure("futura", foreground="#9aa5b1")         # cinza
        self.tabela.tag_configure("pendente", foreground="#1f2933")       # escuro
        self.tabela.tag_configure("sugerida", background="#dff3e7", foreground="#14532d")
        self.after(INTERVALO_PISCA_MS, self._piscar_sugerida)

        # --- dados da aula ---
        cartao_dados = ttk.Frame(self.conteudo, style="Cartao.TFrame", padding=14)
        cartao_dados.pack(fill="x", padx=20, pady=(0, 8))
        self.cartao_dados = cartao_dados

        ttk.Label(cartao_dados, text="Dados do registro", style="Secao.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        self.rotulo_aula = ttk.Label(
            cartao_dados, text="Nenhuma aula selecionada.", style="Suave.TLabel"
        )
        self.rotulo_aula.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 10))

        ttk.Label(cartao_dados, text="Nº de estudantes:", style="Cartao.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        self.campo_estudantes = ttk.Entry(cartao_dados, width=8, font=("Segoe UI", 11))
        self.campo_estudantes.grid(row=2, column=1, sticky="w", padx=(8, 24))
        self.campo_estudantes.bind("<Return>", lambda _e: self._preencher())

        ttk.Label(cartao_dados, text="Etapa:", style="Cartao.TLabel").grid(row=2, column=2, sticky="w")
        self.combo_etapa = ttk.Combobox(cartao_dados, values=ETAPAS, width=42, state="readonly")
        self.combo_etapa.grid(row=2, column=3, sticky="w", padx=(8, 0))
        self.combo_etapa.bind("<<ComboboxSelected>>", lambda _e: self._ajustar_campo_extra())

        # Linha que só existe para as etapas com página própria no
        # formulário: AEE e EJA perguntam "Qual etapa?" antes de seguir, e
        # o Ensino Profissional pergunta o curso. Fica escondida no resto
        # do tempo (grid_remove) para não poluir a tela de todo dia.
        self.linha_extra = ttk.Frame(cartao_dados, style="Cartao.TFrame")
        self.linha_extra.grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))
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
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(12, 4))
        self.campo_conteudo = tk.Text(
            cartao_dados,
            height=2,
            wrap="word",
            font=("Segoe UI", 10),
            relief="solid",
            borderwidth=1,
            background="#ffffff",
            foreground=COR_TEXTO,
        )
        self.campo_conteudo.grid(row=5, column=0, columnspan=4, sticky="ew")
        cartao_dados.columnconfigure(3, weight=1)
        ttk.Label(
            cartao_dados,
            text="Vem preenchido com o assunto lançado na agenda — edite à vontade.",
            style="Suave.TLabel",
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(3, 0))

        ttk.Label(cartao_dados, text="Recursos utilizados:", style="Cartao.TLabel").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(12, 4)
        )
        caixa_recursos = ttk.Frame(cartao_dados, style="Cartao.TFrame")
        caixa_recursos.grid(row=8, column=0, columnspan=4, sticky="w")
        self.vars_recursos: dict = {}
        # Duas colunas preenchidas de cima para baixo (e não em ziguezague):
        # assim os quatro nomes longos de "Computadores/notebooks" ficam
        # juntos na primeira coluna e a segunda não estoura a largura da
        # janela. Antes o texto da direita saía cortado ("...no laborató"),
        # e a barra de rolagem da área de cima ainda comia alguns pixels.
        colunas_recursos = 3
        por_coluna = -(-len(RECURSOS_DISPONIVEIS) // colunas_recursos)
        for i, recurso in enumerate(RECURSOS_DISPONIVEIS):
            var = tk.BooleanVar(value=recurso in RECURSOS_PADRAO)
            self.vars_recursos[recurso] = var
            ttk.Checkbutton(
                caixa_recursos, text=rotulo_curto(recurso), variable=var
            ).grid(
                row=i % por_coluna, column=i // por_coluna, sticky="w",
                padx=(0, 18), pady=1
            )

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
        self.botao_cancelar = ttk.Button(
            acoes, text="Cancelar e voltar ao início", command=self._cancelar
        )
        self.botao_cancelar.pack(side="left", padx=(10, 0))
        self.botao_nao_realizada = ttk.Button(
            acoes, text="Aula não realizada", command=self._alternar_nao_realizada
        )
        self.botao_nao_realizada.pack(side="right")

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
            background="#fbfcfd",
            foreground=COR_TEXTO,
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
            text=f"versão {atualizador.versao_atual()}",
            style="Rodape.TLabel",
        ).pack(side="right")
        ttk.Button(
            rodape, text="Procurar atualização", style="Rodape.TButton",
            command=self._procurar_atualizacao_agora,
        ).pack(side="right", padx=(0, 10))

        # Barra de conta no rodapé, e não no alto: ali ela não disputa
        # altura com a lista de aulas e com os campos do registro, que é
        # o que a pessoa precisa ver numa tela pequena. E fica ao lado da
        # versão, que é o outro dado "sobre o programa", não sobre a aula.
        if not SENHAS_SALVAS:
            ttk.Label(
                rodape,
                text=f"registrando como {self.orientador['nome']}",
                style="Rodape.TLabel",
            ).pack(side="left")
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
        # Text e Treeview têm rolagem própria — não roubar a deles.
        if isinstance(evento.widget, (tk.Text, ttk.Treeview)):
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
        try:
            topo_atual = self._tela.canvasy(0)
            topo_cartao = self.cartao_dados.winfo_rooty() - self.conteudo.winfo_rooty()
            base_cartao = topo_cartao + self.cartao_dados.winfo_height() + 8
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
            self.after(400, lambda: self.attributes("-topmost", False))
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
        texto_notas = (info.get("notas") or "").strip()
        if len(texto_notas) > 1200:
            texto_notas = texto_notas[:1200].rsplit("\n", 1)[0] + "\n(...)"
        notas = f"\n\nO que mudou nesta versão:\n{texto_notas}" if texto_notas else ""
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
        # Como .exe, o programa se reabre sozinho na versão nova — não faz
        # sentido pedir para a pessoa fechar e abrir se ele pode fazer isso
        # melhor do que ela (e sem esquecer).
        if empacotado():
            messagebox.showinfo(
                "Atualizado",
                f"Pronto — agora na versão {info['versao']}.\n\n"
                "O programa vai fechar e abrir de novo sozinho.",
            )
            try:
                atualizador.reiniciar()
            except Exception:
                messagebox.showinfo(
                    "Quase lá",
                    "A atualização foi aplicada, mas não consegui reabrir o "
                    "programa sozinho. Abra de novo pelo atalho.",
                )
            self._fechar()
            return

        messagebox.showinfo(
            "Atualizado",
            f"Pronto — agora na versão {info['versao']}.\n"
            f"({len(arquivos)} arquivos atualizados)\n\n"
            "FECHE e abra o programa de novo para usar a versão nova.",
        )
        self._definir_status(
            f"Atualizado para a versão {info['versao']} — feche e abra o programa."
        )

    def _checar_configuracao(self) -> None:
        """Avisa, logo ao abrir, se faltou preencher o arquivo .env."""
        faltando = configuracao_incompleta()
        if not faltando:
            return
        lista = "\n".join(f"   • {item}" for item in faltando)
        self._escrever(
            "FALTA CONFIGURAR O ARQUIVO .env\n\n"
            "Estes dados ainda não foram preenchidos:\n"
            f"{lista}\n\n"
            "Abra o arquivo .env (na pasta do programa) com o Bloco de "
            "Notas, preencha os campos, salve e abra o programa de novo."
        )
        self._definir_status("Falta configurar o arquivo .env — veja abaixo.")
        messagebox.showwarning(
            "Falta configurar",
            "O programa ainda não sabe quem você é.\n\n"
            "Estes dados não foram preenchidos:\n\n"
            f"{lista}\n\n"
            "Abra o arquivo .env na pasta do programa com o Bloco de Notas, "
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
                    "sugerida", background=cor, foreground="#14532d"
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
                        foreground=[("selected", "#0b3d26")],
                    )
                else:
                    self._estilo.map(
                        "Treeview",
                        background=[("selected", SELECAO_BG)],
                        foreground=[("selected", SELECAO_FG)],
                    )
        except Exception:
            return  # janela fechando — para o ciclo
        self.after(INTERVALO_PISCA_MS, self._piscar_sugerida)

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
            # Se a aula sugerida mudou, a lista está velha: redesenha.
            sugerida = escolher_aula_automatica(
                self.grupos, self.enviados | self.nao_realizadas, agora,
                self.orientador.get("turnos"),
            )
            if (
                sugerida is not getattr(self, "_grupo_sugerido", None)
                and self.preenchido_para is None
            ):
                self._preencher_tabela()

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
                    break
        except Exception:
            pass  # nunca deixar o relógio morrer por causa de um erro pontual
        finally:
            self.after(INTERVALO_CHECAGEM_MS, self._verificar_inicio_de_aula)

    def _avisar_aula_comecou(self, grupo) -> None:
        self._piscar_na_barra()
        quando = f"{grupo.inicio}-{grupo.fim}"

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
        self.comandos.put(("carregar", True, self.orientador["cpf"], self.orientador["senha"]))
        self.after(INTERVALO_RECONSULTA_MS, self._recarregar_silencioso)

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

    def _preencher_tabela(self) -> None:
        self.tabela.delete(*self.tabela.get_children())
        agora = agora_sc()
        self.nao_realizadas = carregar_nao_realizadas()
        sugerida = escolher_aula_automatica(
            self.grupos, self.enviados | self.nao_realizadas, agora,
            self.orientador.get("turnos"),
        )
        self.grupo_atual = None
        self._iid_sugerida = None
        # guardado para o relógio saber se a lista desenhada ainda
        # corresponde à realidade (ver _verificar_inicio_de_aula)
        self._grupo_sugerido = sugerida
        for indice, g in enumerate(self.grupos):
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
        # IMPORTANTE: se há um formulário preenchido esperando envio, a
        # seleção NÃO pode mudar. Trocar a seleção dispara a limpeza dos
        # campos, e a reconsulta automática (de 30 em 30 min) apagaria o
        # trabalho em andamento bem na hora de clicar em Enviar.
        if self.preenchido_para is not None:
            try:
                indice = next(i for i, x in enumerate(self.grupos) if x is self.preenchido_para)
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
        dia = dt.date.fromisoformat(grupo.data).strftime("%d/%m/%Y")
        self.rotulo_aula.configure(
            text=(
                f"{dia} · {grupo.inicio}-{grupo.fim} · {grupo.professor.title()} · "
                f"{grupo.disciplina} · {grupo.turma} · {grupo.numero_aulas} aula(s)"
            )
        )
        etapa = etapa_para_turma(grupo.turma)
        self.combo_etapa.set(etapa or "")
        self._ajustar_campo_extra(sugerir_de=grupo.turma)
        # Traz o assunto lançado na agenda como ponto de partida — o
        # professor ajusta/reescreve antes de registrar.
        self.campo_conteudo.delete("1.0", "end")
        self.campo_conteudo.insert("1.0", grupo.conteudo or "")
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
                "Marcada como NÃO REALIZADA — o professor agendou mas não usou "
                "o laboratório.\n"
                "Ela não vai para a SED e não aparece mais como pendente.\n\n"
                "Se foi engano, use o botão 'Desfazer não realizada'."
            )
        else:
            self._escrever("")

    # -- ações --------------------------------------------------------------
    def _sair_da_conta(self) -> None:
        """
        Fecha a sessão deste professor e volta para a tela de entrada.

        A senha vive só na memória; ao sair, ela some junto com a janela.
        É assim que o professor do noturno assume a máquina sem herdar a
        conta de quem usou de manhã.
        """
        if self.preenchido_para is not None:
            if not messagebox.askyesno(
                "Sair da conta",
                "Tem um formulário preenchido esperando envio.\n\n"
                "Sair agora descarta esse preenchimento. Continuar?",
            ):
                return
        self.sair_da_conta = True
        self._fechar()

    def _editar_cadastro(self) -> None:
        """Abre o cadastro deste professor (nome, CPF, turnos, escola)."""
        atual = next(
            (
                p
                for p in (configuracao.carregar().get("professores") or [])
                if p.get("nome") == self.orientador["nome"]
            ),
            None,
        )
        tela = configuracao.TelaDeCadastro(mestre=self, professor=atual)
        if tela.mostrar():
            messagebox.showinfo(
                "Dados salvos",
                "Pronto. O programa vai fechar e abrir de novo para os dados "
                "novos valerem.",
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
                "Trocar de professor",
                "Existe um formulário preenchido esperando envio, no nome de\n"
                f"{self.orientador['nome']}.\n\n"
                "Trocar de professor agora descarta esse preenchimento.\n"
                "Quer trocar mesmo assim?",
            ):
                self.combo_professor.set(self.orientador["nome"])
                return
            self.preenchido_para = None
            self.botao_enviar.configure(state="disabled")
            self.comandos.put(("reiniciar",))

        self.orientador = novo
        salvar_ultimo_professor(novo["nome"])
        self._ja_avisadas.clear()  # os avisos valem para a agenda do novo login
        self._definir_status(f"Professor: {novo['nome']} — relendo a agenda...")
        self.comandos.put(("carregar", False, novo["cpf"], novo["senha"]))

    def _recarregar(self) -> None:
        self.enviados = carregar_enviados()
        self._definir_status("Atualizando a agenda...")
        self.comandos.put(("carregar", False, self.orientador["cpf"], self.orientador["senha"]))

    def _preencher(self) -> None:
        if self.grupo_atual is None:
            messagebox.showinfo("Escolha uma aula", "Selecione uma aula na lista primeiro.")
            return
        bruto = self.campo_estudantes.get().strip()
        if not bruto.isdigit() or int(bruto) <= 0:
            messagebox.showinfo(
                "Número de estudantes",
                "Digite quantos estudantes foram atendidos (só números).",
            )
            self.campo_estudantes.focus_set()
            return
        etapa = self.combo_etapa.get().strip()
        if not etapa:
            messagebox.showinfo(
                "Etapa", "Não consegui deduzir a etapa pela turma — escolha na lista."
            )
            return
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
                return
        elif etapa == ETAPA_PROFISSIONAL:
            curso = self.campo_curso.get().strip()
            if not curso:
                messagebox.showinfo(
                    "Qual o curso?",
                    "O Ensino Profissional pede o nome do curso no formulário "
                    "da SED. Preencha o campo \"Qual o curso?\" e tente de novo.",
                )
                self.campo_curso.focus_set()
                return

        recursos = [r for r, v in self.vars_recursos.items() if v.get()]
        if not recursos:
            messagebox.showinfo("Recursos", "Marque pelo menos um recurso utilizado.")
            return
        conteudo = self.campo_conteudo.get("1.0", "end").strip()
        if not conteudo:
            messagebox.showinfo(
                "Conteúdo aplicado",
                "Escreva o que foi trabalhado na aula — esse texto vai para o "
                "campo de conteúdos da SED.",
            )
            self.campo_conteudo.focus_set()
            return
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
        self._definir_status("Preenchendo o formulário...")
        self.comandos.put(
            ("preencher", self.grupo_atual, int(bruto), recursos, etapa, conteudo,
             self.orientador["nome"], self.orientador["tipo"], subetapa, curso)
        )

    def _enviar(self) -> None:
        if self.preenchido_para is None:
            return
        grupo = self.preenchido_para
        if not messagebox.askyesno(
            "Confirmar envio",
            f"Enviar este registro para a SED?\n\n"
            f"{grupo.disciplina}\n{grupo.turma}\n"
            f"{grupo.inicio}-{grupo.fim} · {self.campo_estudantes.get()} estudantes\n\n"
            f"Registrando como: {self.orientador['nome']}",
        ):
            return
        self.botao_enviar.configure(state="disabled")
        self._definir_status("Enviando...")
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
        self.botao_preencher.configure(state="normal")
        self.campo_estudantes.delete(0, "end")
        for recurso, var in self.vars_recursos.items():
            var.set(recurso in RECURSOS_PADRAO)
        self.campo_conteudo.delete("1.0", "end")
        self._escrever("")
        self._definir_status("Cancelado — nada foi enviado. Escolha uma aula.")
        self.comandos.put(("reiniciar",))
        self._preencher_tabela()

    def _fechar(self) -> None:
        self.comandos.put(("sair",))
        self.destroy()

    # -- eventos vindos da thread do navegador ------------------------------
    def _ler_eventos(self) -> None:
        try:
            while True:
                evento = self.eventos.get_nowait()
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
                elif tipo == "preenchido":
                    _, grupo, resumo = evento
                    self.preenchido_para = grupo
                    self.botao_preencher.configure(state="normal")
                    self.botao_enviar.configure(state="normal")
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
                    )
                    # o Chrome está na frente depois de preencher — traz o
                    # programa de volta, que é onde fica o botão de enviar
                    self._trazer_para_frente()
                elif tipo == "enviado":
                    _, grupo = evento
                    self.enviados = carregar_enviados()
                    self.preenchido_para = None
                    self.botao_enviar.configure(state="disabled")
                    self.botao_preencher.configure(state="normal")
                    self.campo_estudantes.delete(0, "end")
                    self._escrever("Registro enviado para a SED.")
                    self._preencher_tabela()
                elif tipo == "atualizacao":
                    self._oferecer_atualizacao(evento[1])
                elif tipo == "aviso_atualizacao":
                    messagebox.showinfo("Atualização", evento[1])
                elif tipo == "erro":
                    self.botao_preencher.configure(state="normal")
                    self._escrever("DEU ERRO\n\n" + evento[1])
        except queue.Empty:
            pass
        self.after(100, self._ler_eventos)


def _reabrir_e_sair() -> None:
    """
    Fecha e abre o programa de novo.

    Necessário depois de mexer no cadastro: escola, regional e nome são
    lidos UMA vez, quando o programa abre, e distribuídos para os módulos
    que preenchem o formulário. Continuar rodando depois de mudá-los
    daria o pior dos mundos — a tela mostrando o dado novo e o registro
    saindo com o antigo.
    """
    try:
        if empacotado():
            atualizador.reiniciar()
        else:
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
    return [
        {
            "nome": p.get("nome", ""),
            "cpf": p.get("cpf", ""),
            "senha": "",
            "tipo": p.get("tipo", "tecnologias"),
            "turnos": p.get("turnos") or list(TODOS_TURNOS),
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
        _reabrir_e_sair()

    resposta = configuracao.pedir_entrada(
        professores, sugerido=_quem_provavelmente_esta_usando(professores)
    )
    if resposta is None:
        return None
    if resposta[0] == "CADASTRAR":
        if configuracao.pedir_configuracao_inicial() is not None:
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
            # avisa o iniciar.py de que a pessoa JA viu a mensagem, para
            # não aparecerem duas caixinhas dizendo a mesma coisa
            ERRO_JA_MOSTRADO = True
        except Exception:
            print(detalhe)
        raise


if __name__ == "__main__":
    main()
