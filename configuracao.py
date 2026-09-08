# -*- coding: utf-8 -*-
"""
Configuração pela tela, em vez de pelo Bloco de Notas.

POR QUE ISTO EXISTE
-------------------
Até aqui, configurar o programa era abrir um arquivo .env no Bloco de
Notas e preencher linhas na mão. Isso já custou caro mais de uma vez:

  * um professor copiou o modelo, preencheu só CPF e senha, e o programa
    abriu com o nome e a escola em branco;
  * o nome da escola digitado à mão não batia com o texto exato que a SED
    espera, e o registro ia para a escola errada;
  * quem tinha dois professores no mesmo computador precisava entender um
    formato numerado (ORIENTADOR_1_, ORIENTADOR_2_) para revezar.

Uma tela resolve os três: os campos são nomeados, a escola vem de lista
(as 46 da CRE Blumenau, escritas como a SED escreve) e cada professor se
cadastra sozinho.

O QUE FICA GUARDADO — E O QUE NÃO FICA
--------------------------------------
Fica guardado em configuracao.json: escola, regional e, para cada
professor, nome, CPF, tipo de atuação e turnos.

A SENHA NÃO É GUARDADA EM LUGAR NENHUM. Ela é digitada quando o professor
entra e vive só na memória, enquanto o programa está aberto; ao sair da
conta, some. Numa máquina que dois professores dividem, é isso que impede
que um registre aula no nome do outro — de propósito ou sem querer.

O arquivo .env continua funcionando para quem já o tem. Quando ele traz
uma senha salva, ela é usada e o programa não pergunta nada: ninguém que
já estava trabalhando perde o que tinha.
"""

from __future__ import annotations

import ctypes
import json
import math
import re
import tkinter as tk
from tkinter import messagebox, ttk

import tema
from caminhos import caminho_de_dados

ARQUIVO = "configuracao.json"

TIPOS = [("tecnologias", "Tecnologias Educacionais"), ("maker", "Laboratório Maker")]
TURNOS = ["Matutino", "Vespertino", "Noturno"]

# Texto que aparece no campo Escola quando ainda não foi escolhido nada
# — de propósito, em vez de vir pré-preenchida com a escola de outro
# professor (ou em branco, fácil de não notar): força a pessoa a
# reparar e escolher a dela de verdade antes de salvar.
PLACEHOLDER_ESCOLA = "Selecione uma escola"


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
def escolas_conhecidas() -> list:
    """
    As escolas da CRE Blumenau, exatamente como aparecem no formulário.

    Se por algum motivo a lista não puder ser lida, devolve vazio e o
    campo passa a aceitar digitação livre — melhor um campo aberto do que
    um programa que não abre.
    """
    try:
        from escolas import ESCOLAS_CRE_BLUMENAU

        return list(ESCOLAS_CRE_BLUMENAU)
    except Exception:
        return []


def carregar() -> dict:
    """Lê o configuracao.json. Devolve {} quando ainda não existe."""
    try:
        with open(caminho_de_dados(ARQUIVO), encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def salvar(dados: dict) -> None:
    with open(caminho_de_dados(ARQUIVO), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


# Paleta atual (Claro/Escuro/Igual ao sistema — escolhido em "Meus
# dados" da tela principal, guardado aqui no mesmo configuracao.json).
# Lida uma vez na abertura desta tela; ver tema.py.
_PALETA = tema.resolver_paleta(carregar().get("tema", tema.SISTEMA))

COR_FUNDO = _PALETA["fundo_dialogo"]
COR_CARTAO = _PALETA["cartao"]
COR_CAMPO = _PALETA["campo"]
COR_TEXTO = _PALETA["texto"]
COR_SUAVE = _PALETA["suave"]
COR_LARANJA = _PALETA["laranja"]
COR_DESTAQUE = _PALETA["destaque"]


def esta_configurado() -> bool:
    """Há escola e pelo menos um professor cadastrado?"""
    dados = carregar()
    return bool(dados.get("escola")) and bool(dados.get("professores"))


def limpar_cpf(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def validar_professor(dados: dict) -> str:
    """Devolve a primeira pendência encontrada, ou "" se está tudo certo."""
    if not (dados.get("nome") or "").strip():
        return "Escreva o nome do(a) professor(a) orientador(a)."
    if len(limpar_cpf(dados.get("cpf"))) != 11:
        return "O CPF precisa ter 11 números (só os números, sem ponto nem traço)."
    turnos_por_escola = dados.get("turnos_por_escola") or {}
    for escola in dados.get("escolas") or []:
        if not turnos_por_escola.get(escola):
            return f'Marque pelo menos um turno em que você atende em "{escola}".'
    return ""


def remover_professor(cpf: str) -> dict:
    dados = carregar()
    dados["professores"] = [
        p for p in (dados.get("professores") or []) if p.get("cpf") != limpar_cpf(cpf)
    ]
    salvar(dados)
    return dados


# ---------------------------------------------------------------------------
# Peças comuns das telas
# ---------------------------------------------------------------------------
def _estilizar(janela) -> None:
    janela.configure(bg=COR_FUNDO)
    estilo = ttk.Style(janela)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass
    estilo.configure("TFrame", background=COR_FUNDO)
    estilo.configure("Cartao.TFrame", background=COR_CARTAO)
    estilo.configure("TLabel", background=COR_FUNDO, foreground=COR_TEXTO)
    estilo.configure("Cartao.TLabel", background=COR_CARTAO, foreground=COR_TEXTO)
    estilo.configure("Suave.TLabel", background=COR_CARTAO, foreground=COR_SUAVE)
    estilo.configure("Titulo.TLabel", background=COR_FUNDO, font=("Segoe UI", 16, "bold"))
    estilo.configure(
        "Sub.TLabel", background=COR_FUNDO, foreground=COR_SUAVE, font=("Segoe UI", 10)
    )
    # Sem "foreground" aqui, o texto de todo Checkbutton/Radiobutton
    # (turnos, tipo de atuação, aparência...) ficava preto por padrão do
    # tema "clam" — ilegível em cima de um cartão escuro.
    estilo.configure("TCheckbutton", background=COR_CARTAO, foreground=COR_TEXTO)
    estilo.configure("TRadiobutton", background=COR_CARTAO, foreground=COR_TEXTO)
    # Passar o mouse por cima (estado "active") usa um fundo claro PRÓPRIO
    # do tema "clam", que nunca foi sobrescrito acima — ficava uma pílula
    # branca cobrindo todo o texto no tema escuro, tornando o item (ex.:
    # "Aparência", "Você é orientador de:") ilegível enquanto o mouse
    # estava em cima. Achado testando o programa de verdade (bug relatado
    # com prints).
    estilo.map("TCheckbutton", background=[("active", COR_CARTAO)])
    estilo.map("TRadiobutton", background=[("active", COR_CARTAO)])
    # Traço entre seções do formulário — sem isto usa a cor de linha fixa
    # do tema "clam", que não acompanha claro/escuro como o resto do cartão.
    estilo.configure("TSeparator", background=COR_SUAVE)
    # Campos de digitar (Entry/Combobox) não seguiam o tema — no escuro,
    # ficavam brancos por dentro de um tema escuro por fora (mesma
    # correção feita em app.py).
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
    # Cor do aviso "SELECIONE UMA ESCOLA" dentro do combobox — mesma cor
    # do texto de ajuda ("Suave.TLabel") logo abaixo, pra ficar claro que
    # é aviso e não um nome de escola de verdade já escolhido.
    estilo.configure("Placeholder.TCombobox", foreground=COR_SUAVE)
    estilo.map("Placeholder.TCombobox", foreground=[("readonly", COR_SUAVE)])
    # Sem cor nenhuma aqui, todo botão (Salvar, Cancelar, Entrar,
    # Cadastrar/Remover professor(a)...) ficava no cinza-claro padrão do
    # tema "clam" com letra preta — mesma correção feita em app.py.
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
    # Mesma cor de aviso usada no resto do programa (app.py: "Aula não
    # realizada", abas com sugestão pendente) — pra quem já usa o
    # programa reconhecer de cara que é um alerta, não um texto comum.
    estilo.configure(
        "Aviso.TLabel", background=COR_CARTAO, foreground=COR_LARANJA,
        font=("Segoe UI", 9, "bold"),
    )
    # Botão "fantasma": texto colorido sem caixa em volta, pra ações
    # secundárias que não devem competir visualmente com o botão
    # principal (ex.: "Cadastrar outro(a) professor(a)" na tela de
    # entrar) — mesmo espírito do "Rodape.TButton" em app.py.
    estilo.configure(
        "Fantasma.TButton", font=("Segoe UI", 9), padding=(0, 6),
        background=COR_FUNDO, foreground=COR_SUAVE, borderwidth=0,
    )
    estilo.map("Fantasma.TButton", foreground=[("active", COR_TEXTO)])


def _caps_lock_ativo() -> bool:
    """
    Confere se o Caps Lock está ligado AGORA — sem depender de nenhuma
    tecla ter sido apertada dentro de campo nenhum.

    GetKeyState(VK_CAPITAL) conta o estado de ALTERNÂNCIA da tecla (bit
    mais baixo do retorno), não se ela está pressionada neste instante —
    é a mesma informação que o LED do teclado mostra. Assim pega tanto o
    Caps Lock que já estava ligado ANTES de abrir a tela quanto o que a
    pessoa liga/desliga com o foco em outro campo, coisa que só escutar
    tecla apertada dentro do campo de senha não pegaria.

    Só existe de verdade no Windows — único sistema onde este programa
    roda (ver caminhos.py). Em qualquer outro, devolve False sem quebrar
    nada: a pessoa só não vê o aviso.

    restype/argtypes declarados à mão (em vez do "int" que o ctypes
    assume sozinho): GetKeyState devolve SHORT de verdade, não int — sem
    isto, o "& 1" que a gente lê aqui continua certo (é só o bit mais
    baixo, que sobra igual dos dois jeitos), mas se um dia este código
    crescer pra também conferir o bit mais alto (tecla fisicamente
    pressionada agora, 0x8000), aí sim precisaria do tipo certo pra não
    ler sinal errado. Declarar já deixa isso à prova de futuro.
    """
    try:
        VK_CAPITAL = 0x14
        get_key_state = ctypes.windll.user32.GetKeyState
        get_key_state.restype = ctypes.c_short
        get_key_state.argtypes = [ctypes.c_int]
        return bool(get_key_state(VK_CAPITAL) & 1)
    except Exception:
        return False


def _centralizar(janela) -> None:
    janela.update_idletasks()
    x = max((janela.winfo_screenwidth() - janela.winfo_width()) // 2, 0)
    y = max((janela.winfo_screenheight() - janela.winfo_height()) // 3, 0)
    janela.geometry(f"+{x}+{y}")


class _Dialogo:
    """
    Janela que funciona nos dois momentos da vida do programa.

    Sem janela principal ainda (primeira execução), ela é a janela raiz.
    Com o programa já aberto, é uma janela filha que bloqueia a de trás.
    Sem isso, a primeira execução não teria onde se apoiar e o cadastro
    feito depois criaria uma segunda raiz — que no Tkinter é caminho certo
    para tela congelada.
    """

    def __init__(self, mestre=None, titulo=""):
        self.mestre = mestre
        self.raiz_propria = mestre is None
        self.janela = tk.Tk() if self.raiz_propria else tk.Toplevel(mestre)
        self.janela.title(titulo)
        self.resultado = None
        _estilizar(self.janela)

    def mostrar(self):
        _centralizar(self.janela)
        self.janela.protocol("WM_DELETE_WINDOW", self._fechar)
        if self.raiz_propria:
            self.janela.mainloop()
        else:
            self.janela.transient(self.mestre)
            self.janela.grab_set()
            self.mestre.wait_window(self.janela)
        return self.resultado

    def _fechar(self):
        self.resultado = None
        self.janela.destroy()


# ---------------------------------------------------------------------------
# Tela de cadastro
# ---------------------------------------------------------------------------
class TelaDeCadastro(_Dialogo):
    """Cadastro da escola e de um professor (primeira execução ou novo)."""

    def __init__(self, mestre=None, professor=None):
        super().__init__(mestre, "Registro SED — configuração")
        self.dados = carregar()
        self.professor = professor or {}
        self._montar()

    def _montar(self) -> None:
        primeira_vez = not self.dados.get("professores")
        j = self.janela

        topo = ttk.Frame(j, padding=(24, 20, 24, 6))
        topo.pack(fill="x")
        ttk.Label(
            topo,
            text="Bem-vindo(a)" if primeira_vez else "Dados do(a) professor(a)",
            style="Titulo.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            topo,
            text=(
                "Só desta vez: preencha os dados abaixo e o programa fica pronto."
                if primeira_vez
                else "Preencha os dados de quem vai usar o programa neste computador."
            ),
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        cartao = ttk.Frame(j, style="Cartao.TFrame", padding=18)
        cartao.pack(fill="both", expand=True, padx=24, pady=12)
        cartao.columnconfigure(1, weight=1)
        linha = 0

        escolas_do_professor = self.professor.get("escolas") or (
            [self.professor["escola"]] if self.professor.get("escola") else []
        )
        turnos_por_escola_salvos = self.professor.get("turnos_por_escola") or {}
        # formato de antes de existir turno por escola: um turno só,
        # valendo pra escola única que o professor tinha
        turnos_formato_antigo = self.professor.get("turnos")
        # A escola "padrão do computador" (dados.get("escola")) só é um
        # bom palpite para quem está CADASTRANDO ALGUÉM NOVO (poupa
        # escolher de novo quem só tem uma mesmo) — nunca para editar
        # alguém que JÁ existe e não tem escola própria salva (cadastro
        # de antes desta função existir). Nesse segundo caso, usar o
        # padrão do computador deixaria o campo pré-preenchido com a
        # escola de QUALQUER outra pessoa cadastrada por último, e quem
        # só olhasse e confirmasse acabaria salvando a escola errada de
        # novo — foi exatamente assim que um cadastro antigo ficou preso
        # na escola errada mesmo depois de "corrigido" pela tela.
        eh_cadastro_novo = not self.professor

        # Até 3 escolas — o estado permite dar aula em até 3. Escola 2 e 3
        # são opcionais e ficam SEMPRE visíveis (nada de checkbox
        # escondendo campo); em branco é a mesma coisa que "não tenho essa
        # escola". Cada uma tem o PRÓPRIO turno: um professor pode atender
        # de manhã numa escola e só à noite noutra — o turno de cada uma
        # decide o que aparece em destaque (e o que aparece em cinza, "de
        # outro turno") na agenda DAQUELA escola. Toda vez que o programa
        # abre (ou troca de professor), ele pergunta em qual das escolas
        # cadastradas você está agora — ver configuracao.pedir_escola.
        self.combos_escola = []
        self.vars_turnos_por_escola = []
        for numero in (1, 2, 3):
            indice = numero - 1
            ttk.Label(
                cartao,
                text="Escola:" if numero == 1 else f"Escola {numero}:",
                style="Cartao.TLabel",
            ).grid(row=linha, column=0, sticky="w", pady=(0, 4))
            # readonly: só dá pra escolher da lista (rolando ou digitando
            # pra pular até o nome), nunca digitar/apagar livremente. Além
            # de evitar nome que não bate com o exato da SED, é o que
            # deixa o aviso "SELECIONE UMA ESCOLA" fixo — sem readonly,
            # dava pra apagar aquele texto sem escolher nada de verdade.
            combo = ttk.Combobox(
                cartao,
                values=escolas_conhecidas(),
                width=44,
                font=("Segoe UI", 10),
                state="readonly",
            )
            valor_salvo = (
                escolas_do_professor[indice] if len(escolas_do_professor) > indice else ""
            )
            # Só a Escola 1 (obrigatória) ganha o texto de aviso — 2 e 3
            # são opcionais, e em branco já deixa isso claro sozinho. Cor
            # de aviso (igual à do texto de ajuda) enquanto for só o
            # aviso; some sozinha assim que escolher uma escola de
            # verdade da lista.
            if valor_salvo or numero != 1:
                combo.set(valor_salvo)
            else:
                combo.set(PLACEHOLDER_ESCOLA)
                combo.configure(style="Placeholder.TCombobox")
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, c=combo: c.configure(style="TCombobox"),
            )
            combo.grid(row=linha, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))
            self.combos_escola.append(combo)
            linha += 1
            if numero == 1:
                ttk.Label(
                    cartao,
                    text="Escolha na lista — é o nome exato que a SED usa no formulário",
                    style="Suave.TLabel",
                ).grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 6))
                linha += 1

            ttk.Label(cartao, text="Atende em:", style="Cartao.TLabel").grid(
                row=linha, column=0, sticky="w", pady=(0, 12)
            )
            caixa_turnos = ttk.Frame(cartao, style="Cartao.TFrame")
            caixa_turnos.grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 12))
            turnos_salvos = turnos_por_escola_salvos.get(valor_salvo) if valor_salvo else None
            if turnos_salvos is None:
                # Nada pré-marcado por padrão: cadastro novo (ou escola
                # ainda sem turno salvo) começa com os 3 desmarcados —
                # a pessoa escolhe cada vez, em vez de precisar notar e
                # desmarcar o que não usa.
                turnos_salvos = turnos_formato_antigo if (indice == 0 and turnos_formato_antigo) else []
            vars_turno = {}
            for turno in TURNOS:
                var = tk.BooleanVar(value=turno in turnos_salvos)
                vars_turno[turno] = var
                ttk.Checkbutton(caixa_turnos, text=turno, variable=var).pack(
                    side="left", padx=(0, 16)
                )
            self.vars_turnos_por_escola.append(vars_turno)
            linha += 1

        ttk.Label(
            cartao,
            text=(
                "Deixe a escola em branco quem tem menos de 3 — o turno de cada\n"
                "escola decide o que aparece em destaque (ou em cinza, \"de outro\n"
                "turno\") na agenda dela, e quem já abre escolhido quando dois\n"
                "professores dividem o mesmo computador"
            ),
            style="Suave.TLabel",
            justify="left",
        ).grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 12))
        linha += 1

        ttk.Label(cartao, text="Regional:", style="Cartao.TLabel").grid(
            row=linha, column=0, sticky="w", pady=(0, 12)
        )
        self.campo_regional = ttk.Entry(cartao, width=22, font=("Segoe UI", 10))
        self.campo_regional.insert(0, self.dados.get("regional", "BLUMENAU"))
        self.campo_regional.grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 12))
        linha += 1

        ttk.Separator(cartao).grid(row=linha, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        linha += 1

        ttk.Label(cartao, text="Seu nome:", style="Cartao.TLabel").grid(
            row=linha, column=0, sticky="w", pady=(0, 4)
        )
        self.campo_nome = ttk.Entry(cartao, width=44, font=("Segoe UI", 10))
        self.campo_nome.insert(0, self.professor.get("nome", ""))
        self.campo_nome.grid(row=linha, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))
        linha += 1
        ttk.Label(
            cartao,
            text="Como deve aparecer no registro enviado à SED",
            style="Suave.TLabel",
        ).grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 12))
        linha += 1

        ttk.Label(cartao, text="Seu CPF:", style="Cartao.TLabel").grid(
            row=linha, column=0, sticky="w", pady=(0, 4)
        )
        self.campo_cpf = ttk.Entry(cartao, width=20, font=("Segoe UI", 10))
        self.campo_cpf.insert(0, self.professor.get("cpf", ""))
        self.campo_cpf.grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 4))
        linha += 1
        ttk.Label(
            cartao,
            text="É o mesmo login do site da agenda do NTE (só os números)",
            style="Suave.TLabel",
        ).grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 12))
        linha += 1

        ttk.Label(cartao, text="Você é orientador de:", style="Cartao.TLabel").grid(
            row=linha, column=0, sticky="w", pady=(0, 12)
        )
        caixa_tipo = ttk.Frame(cartao, style="Cartao.TFrame")
        caixa_tipo.grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 12))
        self.var_tipo = tk.StringVar(value=self.professor.get("tipo", "tecnologias"))
        for chave, rotulo in TIPOS:
            ttk.Radiobutton(caixa_tipo, text=rotulo, value=chave, variable=self.var_tipo).pack(
                side="left", padx=(0, 16)
            )
        linha += 1

        # Aparência: preferência do COMPUTADOR (ver tema.py), não deste
        # professor — por isso vem de self.dados (o configuracao.json
        # inteiro), não de self.professor. "Igual ao sistema" nunca vem
        # pré-marcado por padrão sozinho por acaso: é só o valor salvo,
        # ou "sistema" mesmo se nunca foi escolhido nada ainda.
        ttk.Label(cartao, text="Aparência:", style="Cartao.TLabel").grid(
            row=linha, column=0, sticky="w", pady=(0, 12)
        )
        caixa_tema = ttk.Frame(cartao, style="Cartao.TFrame")
        caixa_tema.grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(0, 12))
        tema_salvo = self.dados.get("tema")
        self.var_tema = tk.StringVar(
            value=tema_salvo if tema_salvo in tema.OPCOES else tema.SISTEMA
        )
        for valor in tema.OPCOES:
            ttk.Radiobutton(
                caixa_tema, text=tema.ROTULOS[valor], value=valor, variable=self.var_tema
            ).pack(side="left", padx=(0, 16))
        linha += 1

        rodape = ttk.Frame(j, padding=(24, 0, 24, 18))
        rodape.pack(fill="x")
        ttk.Button(rodape, text="Salvar", style="Principal.TButton", command=self._salvar).pack(
            side="left"
        )
        ttk.Button(rodape, text="Cancelar", command=self._fechar).pack(side="left", padx=(10, 0))
        ttk.Label(
            rodape,
            text="A senha da agenda não é pedida aqui — ela é digitada ao entrar",
            style="Sub.TLabel",
        ).pack(side="right")

        self.campo_nome.focus_set()

    def _salvar(self) -> None:
        escola = self.combos_escola[0].get().strip()
        if not escola or escola == PLACEHOLDER_ESCOLA:
            messagebox.showinfo("Escola", "Escolha a sua escola na lista.", parent=self.janela)
            return
        escolas = [escola]
        turnos_por_escola = {
            escola: [t for t, v in self.vars_turnos_por_escola[0].items() if v.get()]
        }
        for numero, combo, vars_turno in zip(
            (2, 3), self.combos_escola[1:], self.vars_turnos_por_escola[1:]
        ):
            extra = combo.get().strip()
            if not extra:
                continue
            if extra in escolas:
                messagebox.showinfo(
                    f"Escola {numero}",
                    f"A escola {numero} precisa ser diferente das outras já escolhidas.",
                    parent=self.janela,
                )
                return
            escolas.append(extra)
            turnos_por_escola[extra] = [t for t, v in vars_turno.items() if v.get()]
        professor = {
            "nome": self.campo_nome.get().strip(),
            "cpf": limpar_cpf(self.campo_cpf.get()),
            "tipo": self.var_tipo.get(),
            "escolas": escolas,
            "turnos_por_escola": turnos_por_escola,
            # "turnos" (achatado, sem separar por escola) fica só de eco:
            # é a união de todas — usado antes de qualquer escola ser
            # escolhida (ver app._quem_provavelmente_esta_usando), quando
            # ainda não dá pra saber qual delas vale.
            "turnos": [t for t in TURNOS if any(t in ts for ts in turnos_por_escola.values())],
        }
        pendencia = validar_professor(professor)
        if pendencia:
            messagebox.showinfo("Falta preencher", pendencia, parent=self.janela)
            return

        dados = carregar()
        # SÓ define o padrão do computador na primeira vez (setdefault, não
        # atribuição direta): esse campo é o que um cadastro ANTIGO (de
        # antes de existir escola por professor — sem "escolas" próprio)
        # usa como escola dele, em app._professores_cadastrados(). Se
        # atualizasse a cada Salvar, cadastrar ou editar um professor
        # QUALQUER (mesmo um com duas escolas, mesmo outra pessoa) mudava
        # silenciosamente a escola de todo mundo que ainda não tem a
        # própria — foi exatamente assim que um cadastro antigo "herdou"
        # a escola de outro professor testado por último.
        dados.setdefault("escola", escola)
        dados["regional"] = self.campo_regional.get().strip() or "BLUMENAU"
        dados["tema"] = self.var_tema.get()
        lista = list(dados.get("professores") or [])
        for i, p in enumerate(lista):          # mesmo CPF = edição, não cadastro novo
            if p.get("cpf") == professor["cpf"]:
                lista[i] = professor
                break
        else:
            lista.append(professor)
        dados["professores"] = lista
        salvar(dados)
        self.resultado = dados
        self.janela.destroy()


# ---------------------------------------------------------------------------
# Tela de entrada (quem é você + senha)
# ---------------------------------------------------------------------------
def escolas_do_professor(p: dict) -> list:
    """
    As escolas de um professor, sempre em lista — cadastros antigos (de
    antes de existir a segunda escola) tinham só "escola" (texto); os
    novos têm "escolas" (lista, de 1 item pra quem só tem uma mesmo).
    """
    if p.get("escolas"):
        return list(p["escolas"])
    if p.get("escola"):
        return [p["escola"]]
    return []


def turnos_da_escola(p: dict, escola: str) -> list:
    """
    Os turnos deste professor NESTA escola — pode ser diferente de escola
    pra escola (de manhã/tarde numa, só à noite noutra).

    É o que decide, na agenda daquela escola, o que fica em destaque e o
    que aparece em cinza ("de outro turno") — ver app._turno_e_meu.
    """
    por_escola = p.get("turnos_por_escola") or {}
    if escola in por_escola:
        return list(por_escola[escola])
    # formato antigo (antes de turno valer por escola): usa o turno geral
    # do professor, que valia pra escola única que ele tinha
    if p.get("turnos"):
        return list(p["turnos"])
    return list(TURNOS)


def pedir_escola(escolas: list, mestre=None):
    """
    Pergunta qual das escolas do professor vale para esta sessão.

    Devolve a única escola direto, sem perguntar nada, quando só há uma —
    é o caso de quase todo mundo. Só abre a telinha quando há de verdade
    uma escolha a fazer.
    """
    if len(escolas) <= 1:
        return escolas[0] if escolas else None
    return TelaDeEscolha(escolas, mestre=mestre).mostrar()


class TelaDeEscolha(_Dialogo):
    """
    "Qual escola hoje?" — só aparece para quem tem mais de uma cadastrada.

    Não fica salva: é perguntada de novo toda vez que o programa abre (ou
    troca de professor), do mesmo jeito que a senha — evita que o
    registro vá para a escola errada por causa de uma escolha de ontem.
    """

    def __init__(self, escolas: list, mestre=None):
        super().__init__(mestre, "Registro SED — qual escola?")
        self.escolas = list(escolas)
        self._montar()

    def _montar(self) -> None:
        j = self.janela
        topo = ttk.Frame(j, padding=(24, 20, 24, 6))
        topo.pack(fill="x")
        ttk.Label(topo, text="Qual escola hoje?", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(
            topo,
            text="Você está cadastrado em mais de uma — escolha em qual vai registrar agora.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        cartao = ttk.Frame(j, style="Cartao.TFrame", padding=18)
        cartao.pack(fill="both", expand=True, padx=24, pady=12)
        self.combo_escola = ttk.Combobox(
            cartao, values=self.escolas, width=44, state="readonly", font=("Segoe UI", 10, "bold")
        )
        self.combo_escola.set(self.escolas[0])
        self.combo_escola.pack(fill="x")

        rodape = ttk.Frame(j, padding=(24, 0, 24, 18))
        rodape.pack(fill="x")
        ttk.Button(rodape, text="Continuar", style="Principal.TButton", command=self._ok).pack(
            side="left"
        )
        ttk.Button(rodape, text="Cancelar", command=self._fechar).pack(side="left", padx=(10, 0))

    def _ok(self) -> None:
        self.resultado = self.combo_escola.get()
        self.janela.destroy()


class TelaDeEntrada(_Dialogo):
    """
    Escolha do professor e senha da agenda.

    A senha fica só na memória do programa. Ao sair da conta, some — é o
    que permite dois professores dividirem a mesma máquina sem que um
    consiga registrar aula no nome do outro.
    """

    def __init__(self, professores, mestre=None, sugerido=None, aviso=""):
        super().__init__(mestre, "Registro SED — entrar")
        self.professores = list(professores)
        self.sugerido = sugerido
        self.aviso = aviso
        self._montar()

    def _montar(self) -> None:
        j = self.janela

        # --- anel de tracinhos girando em volta da tela de login TODA ---
        # Pedido do professor, com print: não é mais só atrás de um selo
        # pequeno — o anel precisa envolver o cartão inteiro (título,
        # campos, botão). Isso muda a estrutura: em vez de empilhar
        # [anel] em cima e [cartão] embaixo (como na primeira versão),
        # os dois agora ficam SOBREPOSTOS e concêntricos — o Canvas do
        # anel embaixo, o cartão por cima (via place(), que é o único
        # jeito do Tk empilhar dois widgets ocupando o MESMO espaço).
        #
        # Isso exige montar o cartão PRIMEIRO (sem exibir ainda) só pra
        # medir de quanto espaço ele precisa, e SÓ DEPOIS desenhar um
        # anel com raio grande o bastante pra cercar essa medida (o
        # raio de um círculo que envolve um retângulo é metade da
        # diagonal dele, com uma margem).
        moldura = tk.Frame(j, bg=COR_FUNDO)
        moldura.pack(fill="both", expand=True)

        # LARGURA_CARTAO fixa a largura pela CAIXA DE SENHA (mais abaixo)
        # e pelo wraplength dos textos — não no frame do cartão em si:
        # um pack_propagate(False) aqui travaria a ALTURA também (viraria
        # 1px, o padrão do Tk, em vez de crescer para caber os campos),
        # e é justamente essa altura que a conta do raio do anel, logo
        # adiante, precisa medir de verdade. Achado testando: a janela
        # abria pequena demais e cortava o anel.
        LARGURA_CARTAO = 320
        cartao = tk.Frame(moldura, bg=COR_FUNDO)

        ttk.Label(
            cartao, text="Quem está registrando?", style="Titulo.TLabel", background=COR_FUNDO,
        ).pack(pady=(0, 2))
        if self.aviso:
            ttk.Label(
                cartao, text=self.aviso, style="Sub.TLabel", wraplength=LARGURA_CARTAO,
                justify="center",
            ).pack(pady=(0, 4))

        ttk.Label(cartao, text="Professor(a)", style="Sub.TLabel").pack(anchor="w", pady=(4, 0))
        nomes = [p.get("nome", "") for p in self.professores]
        self.combo_nome = ttk.Combobox(
            cartao, values=nomes, state="readonly", font=("Segoe UI", 10, "bold")
        )
        escolhido = self.sugerido if self.sugerido in nomes else (nomes[0] if nomes else "")
        self.combo_nome.set(escolhido)
        self.combo_nome.pack(fill="x", pady=(3, 8))

        # --- senha, com rótulo "flutuante" ---
        # A ideia (rótulo começa centralizado dentro do campo vazio, feito
        # de placeholder, e sobe/encolhe assim que a pessoa clica ou
        # digita algo) é a mesma do site de referência — refeita do zero
        # aqui com place()/eventos de foco, já que Tkinter não tem um
        # equivalente do seletor CSS ":focus ~ label". Truque: os dois
        # widgets ocupam o MESMO espaço, empilhados (.lift() decide quem
        # fica visível por cima) — nada de CSS, é só geometria e eventos.
        ALTURA_CAIXA_SENHA = 48
        caixa_senha = tk.Frame(
            cartao, bg=COR_CAMPO, width=LARGURA_CARTAO, height=ALTURA_CAIXA_SENHA,
        )
        caixa_senha.pack(fill="x")
        caixa_senha.pack_propagate(False)

        self.campo_senha = tk.Entry(
            caixa_senha, show="•", bg=COR_CAMPO, fg=COR_TEXTO, insertbackground=COR_TEXTO,
            relief="flat", font=("Segoe UI", 11), borderwidth=0,
        )
        self.campo_senha.place(x=14, y=0, relwidth=1.0, width=-56, relheight=1.0)
        self.campo_senha.bind("<Return>", lambda _e: self._entrar())

        rotulo_senha = tk.Label(
            caixa_senha, text="Senha da agenda", bg=COR_CAMPO, fg=COR_SUAVE, font=("Segoe UI", 10),
        )

        def _posicionar_rotulo_senha(*_a) -> None:
            focado = j.focus_get() is self.campo_senha
            ativo = bool(self.campo_senha.get()) or focado
            if ativo:
                rotulo_senha.configure(font=("Segoe UI", 8), fg=COR_DESTAQUE)
                rotulo_senha.place(x=14, y=5, anchor="nw")
            else:
                rotulo_senha.configure(font=("Segoe UI", 10), fg=COR_SUAVE)
                rotulo_senha.place(x=14, y=ALTURA_CAIXA_SENHA // 2, anchor="w")
            rotulo_senha.lift()

        self.campo_senha.bind("<FocusIn>", _posicionar_rotulo_senha)
        self.campo_senha.bind("<FocusOut>", _posicionar_rotulo_senha)
        self.campo_senha.bind("<KeyRelease>", _posicionar_rotulo_senha)
        _posicionar_rotulo_senha()

        # Texto pequeno em vez de botão — mostrar/ocultar senha é uma
        # ação secundária, não precisa de uma caixa chamativa competindo
        # com o campo em si. Cursor de "mão" avisa que é clicável.
        def _alternar_visibilidade_senha(_evento=None) -> None:
            if campo_senha_visivel[0]:
                self.campo_senha.configure(show="•")
                rotulo_olho.configure(text="mostrar")
            else:
                self.campo_senha.configure(show="")
                rotulo_olho.configure(text="ocultar")
            campo_senha_visivel[0] = not campo_senha_visivel[0]

        campo_senha_visivel = [False]
        rotulo_olho = tk.Label(
            caixa_senha, text="mostrar", bg=COR_CAMPO, fg=COR_SUAVE, font=("Segoe UI", 8),
            cursor="hand2",
        )
        rotulo_olho.place(relx=1.0, x=-10, rely=0.5, anchor="e")
        rotulo_olho.bind("<Button-1>", _alternar_visibilidade_senha)

        # Aviso de Caps Lock — a senha vem escondida (show="•"), então é
        # o único jeito de perceber que vai sair tudo em maiúscula antes
        # de tentar entrar e levar um "senha incorreta" sem entender por
        # quê. Escondido por padrão; _checar_caps_lock (chamada no fim
        # deste método) decide se mostra, e continua conferindo sozinha
        # enquanto esta tela estiver aberta. "before=" garante que ele
        # sempre aparece ENTRE o campo de senha e o texto de ajuda,
        # mesmo depois de escondido/mostrado várias vezes (pack() não
        # lembra posição sozinho do jeito que grid() lembrava antes).
        self.aviso_caps = ttk.Label(cartao, text="⚠ Caps Lock ativado", style="Aviso.TLabel")

        texto_ajuda_senha = ttk.Label(
            cartao,
            text=(
                "A mesma senha que você usa no site da agenda do NTE.\n"
                "Ela não fica salva: é pedida de novo na próxima vez que abrir."
            ),
            style="Suave.TLabel",
            justify="left",
            wraplength=LARGURA_CARTAO,
        )
        texto_ajuda_senha.pack(anchor="w", pady=(4, 0))

        ttk.Button(cartao, text="Entrar", style="Principal.TButton", command=self._entrar).pack(
            fill="x", pady=(10, 0)
        )
        linha_secundaria = ttk.Frame(cartao)
        linha_secundaria.pack(fill="x", pady=(5, 0))
        ttk.Button(
            linha_secundaria, text="Cadastrar outro(a) professor(a)", style="Fantasma.TButton",
            command=self._cadastrar,
        ).pack(side="left")
        # À direita, separado do resto de propósito, e num botão "de
        # verdade" (não fantasma) — é uma ação destrutiva (tira o
        # professor da lista deste computador), não algo pra clicar sem
        # querer no meio do fluxo de sempre.
        ttk.Button(linha_secundaria, text="Remover professor(a)", command=self._remover).pack(
            side="right"
        )

        # --- mede o cartão pronto, desenha um anel grande o bastante
        # pra envolver ele todo, e sobrepõe os dois, concêntricos ---
        cartao.update_idletasks()
        altura_cartao = cartao.winfo_reqheight()
        raio_anel = math.hypot(LARGURA_CARTAO, altura_cartao) / 2 + 16
        tam_anel = int(raio_anel * 2) + 20
        centro_anel = tam_anel / 2
        # Voltou a ser um anel só (não dois) — pedido do professor. Mais
        # tracinhos e cada um mais comprido (14->17) do que a versão de
        # um anel só original, pra sobrar bem menos vão entre eles.
        FAIXAS_ANEL = (
            # (raio, quantos tracinhos, comprimento de cada um)
            (raio_anel, 90, 17),
        )

        moldura.configure(width=tam_anel, height=tam_anel)
        # moldura só tem filhos via place() (canvas do anel + o cartão) —
        # sem filho nenhum em pack()/grid(), o Tk não propaga esse
        # tamanho pra janela sozinho (o auto-ajuste de janela depende de
        # geometria pack/grid, não de place()). Sem isto, a janela ficava
        # menor que o anel e cortava tudo — achado testando de verdade.
        j.update_idletasks()
        j.geometry(f"{tam_anel}x{tam_anel}")

        self._anel_entrada = tk.Canvas(
            moldura, width=tam_anel, height=tam_anel, bg=COR_FUNDO, highlightthickness=0,
        )
        self._anel_entrada.place(x=0, y=0)

        def _cor_esmaecida_anel(fracao: float) -> str:
            """fracao 0..1 -> mistura entre o fundo (traço "apagado") e a
            cor de destaque (traço "aceso", na cabeça do giro)."""
            r1, g1, b1 = int(COR_FUNDO[1:3], 16), int(COR_FUNDO[3:5], 16), int(COR_FUNDO[5:7], 16)
            r2, g2, b2 = int(COR_DESTAQUE[1:3], 16), int(COR_DESTAQUE[3:5], 16), int(COR_DESTAQUE[5:7], 16)
            r = int(r1 + (r2 - r1) * fracao)
            g = int(g1 + (g2 - g1) * fracao)
            b = int(b1 + (b2 - b1) * fracao)
            return f"#{r:02x}{g:02x}{b:02x}"

        self._angulo_anel_entrada = 0.0

        def _desenhar_anel_entrada() -> None:
            self._anel_entrada.delete("traco")
            # Dois anéis concêntricos, girando em sentidos opostos (o de
            # dentro um pouco mais rápido) — mais cheio visualmente que
            # um anel só, e o contraste de sentido deixa bem claro que
            # são duas faixas, não uma coisa confusa.
            for indice_faixa, (raio, n_tracos, comprimento) in enumerate(FAIXAS_ANEL):
                sentido = 1 if indice_faixa == 0 else -1
                angulo_faixa = self._angulo_anel_entrada * sentido * (1 + 0.4 * indice_faixa)
                for i in range(n_tracos):
                    ang = angulo_faixa + (360 / n_tracos) * i
                    rad = math.radians(ang)
                    # Gradiente contínuo em volta do círculo INTEIRO (nunca
                    # apaga de vez) — só a "cabeça" fica bem mais acesa,
                    # andando junto com a rotação. Com um anel deste
                    # tamanho (cercando o cartão todo, não só um selo
                    # pequeno), apagar a maior parte dele deixava a
                    # imagem parada com metade do anel sumida — só fazia
                    # sentido girando ao vivo.
                    posicao_na_cauda = i / n_tracos
                    fracao = 0.16 + 0.84 * posicao_na_cauda
                    cor = _cor_esmaecida_anel(fracao)
                    largura = 3 + round(2 * fracao)
                    x1 = centro_anel + raio * math.cos(rad)
                    y1 = centro_anel + raio * math.sin(rad)
                    x2 = centro_anel + (raio - comprimento) * math.cos(rad)
                    y2 = centro_anel + (raio - comprimento) * math.sin(rad)
                    self._anel_entrada.create_line(
                        x1, y1, x2, y2, fill=cor, width=largura, capstyle="round", tags="traco"
                    )

        def _girar_anel_entrada() -> None:
            if not j.winfo_exists():
                return
            self._angulo_anel_entrada = (self._angulo_anel_entrada + 3) % 360
            _desenhar_anel_entrada()
            self._id_anel_entrada = j.after(35, _girar_anel_entrada)

        cartao.place(relx=0.5, rely=0.5, anchor="center")
        cartao.lift()
        self.campo_senha.focus_set()

        # Cancela os dois relógios (anel girando + checagem de Caps
        # Lock) assim que a tela fecha — de QUALQUER jeito que ela feche
        # (Entrar, Cancelar, Cadastrar outro professor, fechar pelo X).
        # Sem isto, achado testando de verdade: o after() já agendado
        # tenta rodar depois que a janela (e o interpretador Tcl
        # inteiro, se for a raiz) já foi destruída, e dá "invalid
        # command name" — um erro que nem passa pelo try/except de
        # dentro do relógio, porque o Tcl nem chega a achar o comando
        # pra chamar.
        self._id_anel_entrada = None
        self._id_caps_lock = None
        self._texto_ajuda_senha_widget = texto_ajuda_senha
        self.janela.bind("<Destroy>", self._parar_relogios_entrada, add="+")
        _girar_anel_entrada()
        self._checar_caps_lock()

    def _parar_relogios_entrada(self, evento) -> None:
        if evento.widget is not self.janela:
            return  # <Destroy> também dispara pra cada widget filho
        for atributo in ("_id_anel_entrada", "_id_caps_lock"):
            id_job = getattr(self, atributo, None)
            if id_job is not None:
                try:
                    self.janela.after_cancel(id_job)
                except Exception:
                    pass
                setattr(self, atributo, None)

    def _checar_caps_lock(self) -> None:
        """
        Mostra/esconde o aviso de Caps Lock, e se chama de novo em
        seguida — continua conferindo sozinha enquanto esta tela estiver
        aberta, pega o Caps Lock ligado/desligado a qualquer momento
        (não só quando aperta uma tecla dentro do campo de senha).

        Para sozinha quando a tela fecha — winfo_exists() cobre o caso
        comum, e _parar_relogios_entrada (ligada no <Destroy>) cobre a
        corrida de uma checagem que já tinha sido agendada bem na hora
        do fechamento.
        """
        if not self.janela.winfo_exists():
            return
        if _caps_lock_ativo():
            # before= garante a posição certa (entre o campo de senha e
            # o texto de ajuda) mesmo depois de escondido/mostrado várias
            # vezes — pack() não guarda lugar sozinho do jeito que
            # grid()/grid_remove() guardavam antes.
            self.aviso_caps.pack(anchor="w", pady=(6, 0), before=self._texto_ajuda_senha_widget)
        else:
            self.aviso_caps.pack_forget()
        self._id_caps_lock = self.janela.after(250, self._checar_caps_lock)

    def _remover(self) -> None:
        nome = self.combo_nome.get()
        if not nome:
            messagebox.showinfo(
                "Remover professor(a)", "Escolha quem remover na lista.", parent=self.janela
            )
            return
        professor = next((p for p in self.professores if p.get("nome") == nome), None)
        if professor is None:
            return
        if not messagebox.askyesno(
            "Remover professor(a)",
            f'Remover "{nome}" da lista de quem usa o programa neste computador?\n\n'
            "Isso não mexe em nada na SED nem no site da agenda — só tira o "
            "cadastro salvo aqui. Se precisar de novo, é só cadastrar outra vez.",
            parent=self.janela,
        ):
            return
        configuracao_atual = remover_professor(professor.get("cpf", ""))
        self.professores = list(configuracao_atual.get("professores") or [])
        nomes = [p.get("nome", "") for p in self.professores]
        self.combo_nome.configure(values=nomes)
        self.combo_nome.set(nomes[0] if nomes else "")
        self.campo_senha.delete(0, "end")

    def _entrar(self) -> None:
        nome = self.combo_nome.get()
        senha = self.campo_senha.get()
        if not nome:
            messagebox.showinfo("Professor(a)", "Escolha quem está registrando.", parent=self.janela)
            return
        if not senha:
            messagebox.showinfo(
                "Senha",
                "Digite a senha do site da agenda para entrar.",
                parent=self.janela,
            )
            self.campo_senha.focus_set()
            return
        professor = next((p for p in self.professores if p.get("nome") == nome), None)
        if professor is None:
            return

        escolas = escolas_do_professor(professor)
        if not escolas:
            messagebox.showinfo(
                "Escola",
                "Falta cadastrar a escola do(a) professor(a) — abra \"Meus dados\" depois de entrar.",
                parent=self.janela,
            )
        escola = pedir_escola(escolas, mestre=self.janela) if escolas else ""
        if escolas and escola is None:
            return  # cancelou a escolha da escola -- não entra

        professor = dict(professor)
        professor["escola"] = escola or ""
        # Substitui o turno "geral" (usado só pra sugerir o nome antes de
        # escolher escola — ver app._quem_provavelmente_esta_usando) pelo
        # turno DESTA escola especificamente: é ele que decide o que
        # aparece em destaque (e o que fica cinza, "de outro turno") na
        # agenda a partir daqui.
        if escola:
            professor["turnos"] = turnos_da_escola(professor, escola)
        self.resultado = (professor, senha)
        self.janela.destroy()

    def _cadastrar(self) -> None:
        # numa janela raiz própria não dá para abrir outra raiz: fecha esta
        # devolvendo o pedido de cadastro para quem chamou. ESSA CONFERÊNCIA
        # PRECISA VIR ANTES de construir TelaDeCadastro — não depois: criar
        # a tela e SÓ ENTÃO decidir não usá-la já deixava uma segunda janela
        # raiz nascida e abandonada (órfã, nunca destruída), sobrando em
        # branco atrás da tela de cadastro de verdade que vinha a seguir.
        # Exatamente o "tela congelada" que este comentário já avisava.
        if self.raiz_propria:
            self.resultado = ("CADASTRAR", None)
            self.janela.destroy()
            return
        tela = TelaDeCadastro(mestre=self.janela)
        dados = tela.mostrar()
        if dados:
            self.professores = list(dados.get("professores") or [])
            self.combo_nome.configure(values=[p.get("nome", "") for p in self.professores])
            if self.professores:
                self.combo_nome.set(self.professores[-1].get("nome", ""))


def pedir_configuracao_inicial():
    """Primeira execução: cadastra escola e professor. Devolve os dados ou None."""
    return TelaDeCadastro().mostrar()


def pedir_entrada(professores, mestre=None, sugerido=None, aviso=""):
    """Pergunta quem está usando e a senha. Devolve (professor, senha) ou None."""
    return TelaDeEntrada(professores, mestre=mestre, sugerido=sugerido, aviso=aviso).mostrar()
