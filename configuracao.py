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

import json
import re
import tkinter as tk
from tkinter import messagebox, ttk

from caminhos import caminho_de_dados

ARQUIVO = "configuracao.json"

TIPOS = [("tecnologias", "Tecnologias Educacionais"), ("maker", "Laboratório Maker")]
TURNOS = ["Matutino", "Vespertino", "Noturno"]

COR_FUNDO = "#eef1f5"
COR_CARTAO = "#ffffff"
COR_TEXTO = "#1f2933"
COR_SUAVE = "#6b7684"


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


def esta_configurado() -> bool:
    """Há escola e pelo menos um professor cadastrado?"""
    dados = carregar()
    return bool(dados.get("escola")) and bool(dados.get("professores"))


def limpar_cpf(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def validar_professor(dados: dict) -> str:
    """Devolve a primeira pendência encontrada, ou "" se está tudo certo."""
    if not (dados.get("nome") or "").strip():
        return "Escreva o nome do professor orientador."
    if len(limpar_cpf(dados.get("cpf"))) != 11:
        return "O CPF precisa ter 11 números (só os números, sem ponto nem traço)."
    if not dados.get("turnos"):
        return "Marque pelo menos um turno em que você atende."
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
    estilo.configure("TCheckbutton", background=COR_CARTAO)
    estilo.configure("TRadiobutton", background=COR_CARTAO)
    estilo.configure("TButton", font=("Segoe UI", 10), padding=8)
    estilo.configure("Principal.TButton", font=("Segoe UI", 11, "bold"), padding=10)


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
            text="Bem-vindo" if primeira_vez else "Dados do professor",
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

        ttk.Label(cartao, text="Escola:", style="Cartao.TLabel").grid(
            row=linha, column=0, sticky="w", pady=(0, 4)
        )
        self.combo_escola = ttk.Combobox(
            cartao, values=escolas_conhecidas(), width=44, font=("Segoe UI", 10)
        )
        self.combo_escola.set(self.dados.get("escola", ""))
        self.combo_escola.grid(row=linha, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))
        linha += 1
        ttk.Label(
            cartao,
            text="escolha na lista — é o nome exato que a SED usa no formulário",
            style="Suave.TLabel",
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
            text="como deve aparecer no registro enviado à SED",
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
            text="é o mesmo login do site da agenda do NTE (só os números)",
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

        ttk.Label(cartao, text="Você atende em:", style="Cartao.TLabel").grid(
            row=linha, column=0, sticky="w"
        )
        caixa_turnos = ttk.Frame(cartao, style="Cartao.TFrame")
        caixa_turnos.grid(row=linha, column=1, sticky="w", padx=(10, 0))
        salvos = self.professor.get("turnos") or list(TURNOS)
        self.vars_turnos = {}
        for turno in TURNOS:
            var = tk.BooleanVar(value=turno in salvos)
            self.vars_turnos[turno] = var
            ttk.Checkbutton(caixa_turnos, text=turno, variable=var).pack(side="left", padx=(0, 16))
        linha += 1
        ttk.Label(
            cartao,
            text=(
                "com dois professores no mesmo computador, o turno é o que faz o\n"
                "programa já abrir no nome de quem está de plantão"
            ),
            style="Suave.TLabel",
            justify="left",
        ).grid(row=linha, column=1, sticky="w", padx=(10, 0), pady=(4, 0))

        rodape = ttk.Frame(j, padding=(24, 0, 24, 18))
        rodape.pack(fill="x")
        ttk.Button(rodape, text="Salvar", style="Principal.TButton", command=self._salvar).pack(
            side="left"
        )
        ttk.Button(rodape, text="Cancelar", command=self._fechar).pack(side="left", padx=(10, 0))
        ttk.Label(
            rodape,
            text="a senha da agenda não é pedida aqui — ela é digitada ao entrar",
            style="Sub.TLabel",
        ).pack(side="right")

        self.campo_nome.focus_set()

    def _salvar(self) -> None:
        escola = self.combo_escola.get().strip()
        if not escola:
            messagebox.showinfo("Escola", "Escolha a sua escola na lista.", parent=self.janela)
            return
        professor = {
            "nome": self.campo_nome.get().strip(),
            "cpf": limpar_cpf(self.campo_cpf.get()),
            "tipo": self.var_tipo.get(),
            "turnos": [t for t, v in self.vars_turnos.items() if v.get()],
        }
        pendencia = validar_professor(professor)
        if pendencia:
            messagebox.showinfo("Falta preencher", pendencia, parent=self.janela)
            return

        dados = carregar()
        dados["escola"] = escola
        dados["regional"] = self.campo_regional.get().strip() or "BLUMENAU"
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
        topo = ttk.Frame(j, padding=(24, 20, 24, 6))
        topo.pack(fill="x")
        ttk.Label(topo, text="Quem está registrando?", style="Titulo.TLabel").pack(anchor="w")
        if self.aviso:
            ttk.Label(topo, text=self.aviso, style="Sub.TLabel").pack(anchor="w", pady=(4, 0))

        cartao = ttk.Frame(j, style="Cartao.TFrame", padding=18)
        cartao.pack(fill="both", expand=True, padx=24, pady=12)
        cartao.columnconfigure(1, weight=1)

        nomes = [p.get("nome", "") for p in self.professores]
        ttk.Label(cartao, text="Professor(a):", style="Cartao.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        self.combo_nome = ttk.Combobox(
            cartao, values=nomes, width=38, state="readonly", font=("Segoe UI", 10, "bold")
        )
        escolhido = self.sugerido if self.sugerido in nomes else (nomes[0] if nomes else "")
        self.combo_nome.set(escolhido)
        self.combo_nome.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 10))

        ttk.Label(cartao, text="Senha da agenda:", style="Cartao.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        self.campo_senha = ttk.Entry(cartao, width=28, show="•", font=("Segoe UI", 11))
        self.campo_senha.grid(row=1, column=1, sticky="w", padx=(10, 0))
        self.campo_senha.bind("<Return>", lambda _e: self._entrar())

        ttk.Label(
            cartao,
            text=(
                "a mesma senha que você usa no site da agenda do NTE.\n"
                "Ela não fica salva: é pedida de novo na próxima vez que abrir."
            ),
            style="Suave.TLabel",
            justify="left",
        ).grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(8, 0))

        rodape = ttk.Frame(j, padding=(24, 0, 24, 18))
        rodape.pack(fill="x")
        ttk.Button(rodape, text="Entrar", style="Principal.TButton", command=self._entrar).pack(
            side="left"
        )
        ttk.Button(rodape, text="Cadastrar outro professor", command=self._cadastrar).pack(
            side="left", padx=(10, 0)
        )
        self.campo_senha.focus_set()

    def _entrar(self) -> None:
        nome = self.combo_nome.get()
        senha = self.campo_senha.get()
        if not nome:
            messagebox.showinfo("Professor", "Escolha quem está registrando.", parent=self.janela)
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
        self.resultado = (dict(professor), senha)
        self.janela.destroy()

    def _cadastrar(self) -> None:
        tela = TelaDeCadastro(mestre=self.janela if not self.raiz_propria else None)
        # numa janela raiz própria não dá para abrir outra raiz: fecha esta
        # devolvendo o pedido de cadastro para quem chamou
        if self.raiz_propria:
            self.resultado = ("CADASTRAR", None)
            self.janela.destroy()
            return
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
