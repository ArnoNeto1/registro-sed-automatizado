# -*- coding: utf-8 -*-
"""
Assistente de IA para a pergunta "Quais os objetos do conhecimento
(conteúdos temáticos) abordados?" do formulário da SED — o campo
"Conteúdo aplicado" da tela.

COMO É USADO
------------
O botão "Escrever com IA", ao lado do campo, abre uma janelinha de
conversa. O professor descreve a aula do jeito dele ("o professor de
artes projetou no datashow e mostrou o Estudante Online..."), a IA
devolve o texto no formato que a SED espera, e ele pode pedir correções
na mesma conversa ("foi o professor de ARTES, não matemática") até
clicar em "Usar este texto" — que só troca o texto do campo. Nada vai
para a SED sem passar pelo mesmo "Preencher formulário" → conferir →
"Enviar para a SED" de sempre.

DOIS JEITOS DE FALAR COM A IA
-----------------------------
1. SERVIÇO DA ESCOLA (quando o programa vem configurado com um): o
   programa chama o servidor intermediário (pasta `servidor-ia/`), que
   guarda a chave do Gemini e a instrução. O professor não precisa de
   nada — é só clicar em "Escrever com IA". O endereço e o segredo vêm
   das variáveis SERVIDOR_IA_URL e SERVIDOR_IA_TOKEN (inclusive no .env)
   ou de um `servidor_ia.json` embutido no .exe na hora de montá-lo.
2. CHAVE PRÓPRIA: o professor cola uma chave do Gemini criada por ele no
   Google AI Studio e o programa fala direto com a Google. Se existe uma
   chave própria, ela tem preferência — é a última coisa que o professor
   fez de propósito. Sem servidor configurado, é o único jeito.

A CHAVE PRÓPRIA FICA POR USUÁRIO DO WINDOWS, NÃO NA PASTA DE DADOS
------------------------------------------------------------------
Diferente do resto dos dados — que são do computador, compartilhados
por todo mundo que usa o laboratório (ver caminhos.pasta_de_dados) — a
chave é pessoal. Por isso fica em %APPDATA%\\RegistroSED, que outro
usuário do Windows não consegue ler. Também pode vir da variável
GEMINI_API_KEY (inclusive escrita no .env), para quem preferir.

O QUE É ENVIADO PARA A IA
-------------------------
Só o necessário para escrever o texto: disciplina, turma, etapa, nº de
aulas, recursos marcados, o assunto anotado na agenda e o que o
professor digitar na conversa. NOMES de professores não são enviados.
O texto livre da conversa o programa não consegue filtrar — por isso a
janela avisa para não digitar nomes de estudantes (alunos são menores
de idade), e a instrução pede à IA para não repeti-los.

PRIVACIDADE DO PLANO GRATUITO DA GOOGLE
---------------------------------------
Nos termos da Google, o que passa por uma chave GRATUITA pode ser usado
para melhorar os produtos deles, e pessoas podem ler esse conteúdo; eles
pedem para não enviar dados pessoais por ali. Com o faturamento ligado
(plano pago) isso não acontece. Uma assinatura do Gemini NÃO liga a
chave ao plano pago. O serviço da escola deve usar uma chave PAGA.

SEM DEPENDÊNCIA NOVA
--------------------
As chamadas usam urllib (biblioteca padrão), como a do atualizador —
nada a mais para empacotar no .exe.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import ttk

import caminhos
from ia_gemini import (  # noqa: F401  (a janela e os testes buscam daqui)
    CHAVES_DO_CONTEXTO,
    INSTRUCOES,
    MODELO_PADRAO,
    TEMPO_LIMITE,
    URL_CHAVES,
    ErroDaIA,
    limpar_texto,
    montar_instrucoes,
)
from ia_gemini import pedir_texto as pedir_com_chave_propria

ARQUIVO_CHAVE = "chave_ia.txt"
ARQUIVO_SERVIDOR = "servidor_ia.json"

# Texto do painel da chave: um quando é o ÚNICO caminho (sem serviço da
# escola) e outro quando a chave própria é só uma alternativa.
TEXTO_CHAVE_PROPRIA = (
    "Para escrever com IA, o programa usa o Gemini (Google) com uma chave "
    "sua, criada de graça no Google AI Studio. A chave fica guardada só "
    "neste usuário do Windows.\n"
    "O que você escrever na conversa, junto com os dados da aula, é "
    "enviado à Google para gerar o texto — não digite nomes de "
    "estudantes nem outros dados pessoais. Numa chave gratuita, a Google "
    "pode usar esse conteúdo para melhorar os produtos dela; para que "
    "isso não aconteça, ligue o faturamento da chave no AI Studio."
)
TEXTO_CHAVE_COM_SERVIDOR = (
    "Este programa já usa o serviço de IA da escola: você não precisa de "
    "chave nenhuma. Só cole uma chave sua se preferir usar a sua própria "
    "conta do Google AI Studio — aí o que você escrever passa por essa "
    "conta e, numa chave gratuita, a Google pode usar esse conteúdo para "
    "melhorar os produtos dela. Em qualquer caso, não digite nomes de "
    "estudantes nem outros dados pessoais."
)


# ---------------------------------------------------------------------------
# Chave própria da API
# ---------------------------------------------------------------------------
def _pasta_da_chave() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "RegistroSED"
    return Path.home() / ".config" / "RegistroSED"  # fora do Windows (desenvolvimento)


def carregar_chave() -> str:
    """
    A chave salva pela tela tem preferência — é a última coisa que o
    professor fez de propósito. A variável GEMINI_API_KEY (ou a mesma
    linha no .env) fica como alternativa.
    """
    try:
        salva = (_pasta_da_chave() / ARQUIVO_CHAVE).read_text(encoding="utf-8").strip()
    except OSError:
        salva = ""
    return salva or (os.environ.get("GEMINI_API_KEY") or "").strip()


def salvar_chave(chave: str) -> None:
    pasta = _pasta_da_chave()
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / ARQUIVO_CHAVE).write_text(chave.strip(), encoding="utf-8")


def apagar_chave() -> None:
    """Esquece a chave salva pela tela (para voltar a usar o serviço da escola)."""
    try:
        (_pasta_da_chave() / ARQUIVO_CHAVE).unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Serviço da escola (servidor intermediário)
# ---------------------------------------------------------------------------
def configuracao_do_servidor():
    """
    (endereço, segredo) do serviço da escola, ou None se este programa não
    foi configurado com um.

    Só aceita https — o segredo viaja no cabeçalho, e em http puro
    qualquer um na rede da escola o leria — com a exceção de localhost,
    que existe para testar o servidor no próprio computador.
    """
    url = (os.environ.get("SERVIDOR_IA_URL") or "").strip()
    token = (os.environ.get("SERVIDOR_IA_TOKEN") or "").strip()
    if not (url and token):
        try:
            dados = json.loads(caminhos.recurso(ARQUIVO_SERVIDOR).read_text(encoding="utf-8"))
            url = str(dados.get("url") or "").strip()
            token = str(dados.get("token") or "").strip()
        except (OSError, ValueError, AttributeError):
            return None
    seguro = url.lower().startswith(("https://", "http://127.0.0.1", "http://localhost"))
    return (url, token) if (seguro and token) else None


def contexto_para_enviar(contexto: dict) -> dict:
    """Só os campos da aula que podem sair do computador (nunca nome de professor)."""
    contexto = contexto or {}
    return {chave: contexto[chave] for chave in CHAVES_DO_CONTEXTO if contexto.get(chave)}


def _mensagem_do_servidor(erro: urllib.error.HTTPError) -> str:
    try:
        corpo = json.loads(erro.read().decode("utf-8"))
        mensagem = str(corpo.get("erro") or "").strip()
    except Exception:
        mensagem = ""
    return mensagem or (
        f"O serviço de IA da escola não respondeu direito (erro {erro.code}). "
        "Tente de novo mais tarde."
    )


def pedir_ao_servidor(url: str, token: str, contexto: dict, conversa: list) -> str:
    """Pede o texto ao serviço da escola e devolve o texto já limpo."""
    corpo = json.dumps(
        {"contexto": contexto_para_enviar(contexto), "conversa": conversa}
    ).encode("utf-8")
    requisicao = urllib.request.Request(
        url,
        data=corpo,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-app-token": token,
            "user-agent": "RegistroSED-IA",
        },
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        raise ErroDaIA(_mensagem_do_servidor(erro), "servidor") from None
    except (urllib.error.URLError, OSError) as erro:
        raise ErroDaIA(
            "Não consegui falar com o serviço de IA da escola — parece internet. "
            f"Confira a conexão e tente de novo.\n(detalhe técnico: {erro})",
            "rede",
        ) from None
    except ValueError:
        raise ErroDaIA(
            "O serviço de IA da escola mandou uma resposta que não consegui ler. "
            "Tente de novo.",
            "resposta",
        ) from None
    texto = limpar_texto(str(dados.get("texto") or "")) if isinstance(dados, dict) else ""
    if not texto:
        raise ErroDaIA("A IA respondeu em branco. Tente de novo.", "vazio")
    return texto


# ---------------------------------------------------------------------------
# Qual caminho usar
# ---------------------------------------------------------------------------
def modo_disponivel() -> str:
    """"chave" (a própria do professor), "servidor" (da escola) ou "" (nenhum)."""
    if carregar_chave():
        return "chave"
    if configuracao_do_servidor():
        return "servidor"
    return ""


def pedir(contexto: dict, conversa: list) -> str:
    """Pede o texto pelo caminho disponível (ver `modo_disponivel`)."""
    chave = carregar_chave()
    if chave:
        return pedir_com_chave_propria(chave, contexto, conversa)
    servidor = configuracao_do_servidor()
    if servidor:
        return pedir_ao_servidor(*servidor, contexto, conversa)
    raise ErroDaIA("A IA ainda não está configurada neste computador.", "chave")


# ---------------------------------------------------------------------------
# A janela de conversa
# ---------------------------------------------------------------------------
class JanelaAssistente:
    """
    Modal, de propósito: com ela aberta não dá para trocar de aula na
    tela de trás — senão "Usar este texto" poderia cair no campo de OUTRA
    aula, diferente daquela sobre a qual se estava conversando.
    """

    def __init__(self, mestre, contexto: dict, texto_inicial: str, cores: dict, ao_usar):
        self.mestre = mestre
        self.contexto = dict(contexto or {})
        self.cores = cores
        self.ao_usar = ao_usar
        self.conversa: list = []
        self.ultimo_texto = ""
        self._fila: queue.Queue = queue.Queue()
        self._trabalho = None  # id do after() que confere a resposta
        self._trabalho_inicial = None  # id do after() do pedido automático
        self._ocupado = False
        self._enviado_por_ultimo = ""
        # a janela de "aula sem agendamento" também é modal: ao fechar
        # esta, a trava volta para ela (ver _fechar). grab_current() pode
        # estourar quando quem tem a trava é uma janela interna do próprio
        # Tk (uma caixa de aviso aberta, por exemplo) — aí não há o que
        # devolver depois.
        try:
            self._grab_anterior = mestre.grab_current()
        except (KeyError, tk.TclError):
            self._grab_anterior = None

        j = tk.Toplevel(mestre)
        self.janela = j
        j.title("Registro SED — objetos do conhecimento com IA")
        j.configure(bg=cores["fundo"])
        j.transient(mestre.winfo_toplevel())
        j.minsize(560, 460)
        j.protocol("WM_DELETE_WINDOW", self._fechar)
        self._estilos()
        self._montar()

        if modo_disponivel():
            self._mostrar_painel_conversa()
        else:
            self._mostrar_painel_chave(primeira_vez=True)

        self.entrada.insert("1.0", (texto_inicial or "").strip())
        self._centralizar()
        try:
            # a trava (grab) só pega numa janela já visível na tela
            j.wait_visibility()
            j.grab_set()
        except tk.TclError:
            pass  # sem trava, a janela continua funcionando normalmente

        # Veio só o assunto da agenda, do jeito que o professor que agendou
        # escreveu ("atividade de geografia - mercantilismo")? Já pede o
        # texto na hora: é exatamente o caso que fica genérico demais
        # copiado ao pé da letra. Se o campo já foi editado — ou é um texto
        # da própria IA, reaberto para ajustar —, só espera o professor.
        if modo_disponivel():
            self._pedir_sozinho_se_for_so_o_assunto()

    def _pedir_sozinho_se_for_so_o_assunto(self) -> None:
        assunto = " ".join(str(self.contexto.get("assunto") or "").split())
        escrito = " ".join(self.entrada.get("1.0", "end").split())
        if escrito and escrito == assunto and not self.conversa:
            self._trabalho_inicial = self.janela.after(200, self._enviar)

    # -- montagem -------------------------------------------------------------
    def _estilos(self) -> None:
        c = self.cores
        estilo = ttk.Style(self.janela)
        # link discreto em cima do cartão (o Link.TButton do app tem o
        # fundo da janela, que destoa dentro de um cartão)
        estilo.configure(
            "IALink.TButton", font=("Segoe UI", 9, "underline"), foreground=c["suave"],
            background=c["cartao"], padding=2, relief="flat", borderwidth=0,
        )
        estilo.map("IALink.TButton", background=[("active", c["cartao"])],
                   foreground=[("active", c["texto"])])

    def _texto(self, pai, altura: int, **extras) -> tk.Text:
        c = self.cores
        return tk.Text(
            pai, height=altura, wrap="word", font=("Segoe UI", 10), relief="solid",
            borderwidth=1, background=c["campo"], foreground=c["texto"],
            insertbackground=c["texto"], **extras,
        )

    def _montar(self) -> None:
        c = self.cores
        cartao = ttk.Frame(self.janela, style="Cartao.TFrame", padding=16)
        cartao.pack(fill="both", expand=True, padx=12, pady=12)
        self.cartao = cartao

        ttk.Label(
            cartao, text="Objetos do conhecimento com IA", style="Secao.TLabel"
        ).pack(anchor="w")
        resumo = " · ".join(
            str(self.contexto.get(k) or "").strip()
            for k in ("disciplina", "turma")
            if str(self.contexto.get(k) or "").strip()
        )
        aulas = str(self.contexto.get("numero_aulas") or "").strip()
        if aulas:
            resumo = f"{resumo} · {aulas} aula(s)" if resumo else f"{aulas} aula(s)"
        ttk.Label(
            cartao,
            text=(resumo or "Aula sem dados da agenda") + "  —  a IA já recebe esses dados.",
            style="Suave.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        # histórico da conversa
        quadro = ttk.Frame(cartao, style="Cartao.TFrame")
        quadro.pack(fill="both", expand=True)
        self.historico = self._texto(quadro, 12, width=70, padx=10, pady=8, cursor="arrow")
        barra = ttk.Scrollbar(quadro, orient="vertical", command=self.historico.yview)
        self.historico.configure(yscrollcommand=barra.set)
        self.historico.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        h = self.historico
        h.tag_configure("rotulo_voce", font=("Segoe UI", 9, "bold"), foreground=c["suave"], spacing1=10)
        h.tag_configure("rotulo_ia", font=("Segoe UI", 9, "bold"), foreground=c["destaque"], spacing1=10)
        h.tag_configure("fala", spacing1=2, spacing3=2)
        h.tag_configure("erro", foreground=c["laranja"], spacing1=10)
        h.tag_configure("dica", foreground=c["suave"], font=("Segoe UI", 9, "italic"))
        self._escrever(
            "Descreva o que foi feito na aula, do seu jeito — ou mande o assunto "
            "da agenda como está. Eu escrevo o texto dos objetos do conhecimento "
            "no formato da SED, e você pode pedir correções aqui mesmo (\"foi o "
            "professor de Arte, não de Matemática\").\n"
            "Atenção: o que você escrever aqui é enviado ao serviço de IA — "
            "não digite nomes de estudantes.",
            "dica",
        )

        # painel de conversa: entrada + Enviar
        self.painel_conversa = ttk.Frame(cartao, style="Cartao.TFrame")
        ttk.Label(
            self.painel_conversa,
            text="Sua mensagem (Enter envia · Shift+Enter pula linha):",
            style="Cartao.TLabel",
        ).pack(anchor="w", pady=(10, 4))
        linha = ttk.Frame(self.painel_conversa, style="Cartao.TFrame")
        linha.pack(fill="x")
        # o botão entra ANTES (pela direita): empacotada primeiro, a caixa
        # de texto pedia a largura inteira e espremia o "Enviar" num risco
        self.botao_enviar = ttk.Button(
            linha, text="Enviar", style="Principal.TButton", command=self._enviar
        )
        self.botao_enviar.pack(side="right", padx=(8, 0), anchor="n")
        self.entrada = self._texto(linha, 3, width=40)
        self.entrada.pack(side="left", fill="x", expand=True)
        self.entrada.bind("<Return>", self._enviar)
        self.entrada.bind("<Shift-Return>", self._pular_linha)

        # painel da chave (primeiro uso, ou "Trocar chave")
        self.painel_chave = ttk.Frame(cartao, style="Cartao.TFrame")
        self.texto_painel_chave = ttk.Label(
            self.painel_chave,
            text=TEXTO_CHAVE_PROPRIA,
            style="Cartao.TLabel",
            wraplength=560,
            justify="left",
        )
        self.texto_painel_chave.pack(anchor="w", pady=(10, 4))
        ttk.Button(
            self.painel_chave, text="Criar uma chave no Google AI Studio",
            style="IALink.TButton", command=lambda: webbrowser.open(URL_CHAVES),
        ).pack(anchor="w")
        linha_chave = ttk.Frame(self.painel_chave, style="Cartao.TFrame")
        linha_chave.pack(fill="x", pady=(6, 0))
        ttk.Label(linha_chave, text="Chave da API:", style="Cartao.TLabel").pack(side="left")
        self.campo_chave = ttk.Entry(linha_chave, width=46, show="•", font=("Segoe UI", 10))
        self.campo_chave.pack(side="left", padx=(8, 8), fill="x", expand=True)
        self.campo_chave.bind("<Return>", lambda _e: self._salvar_chave())
        ttk.Button(
            linha_chave, text="Salvar chave", style="Principal.TButton",
            command=self._salvar_chave,
        ).pack(side="left")
        self.botao_voltar_da_chave = ttk.Button(
            self.painel_chave, text="Cancelar troca de chave", style="IALink.TButton",
            command=self._mostrar_painel_conversa,
        )
        self.botao_usar_servidor = ttk.Button(
            self.painel_chave, text="Usar o serviço de IA da escola (esquecer minha chave)",
            style="IALink.TButton", command=self._usar_servidor,
        )

        # rodapé — "acoes" empacotado ANTES do status, os dois por baixo:
        # assim o status ("A IA está escrevendo...") fica logo acima dos
        # botões, perto de onde o olho está
        acoes = ttk.Frame(cartao, style="Cartao.TFrame")
        acoes.pack(fill="x", side="bottom", pady=(8, 0))
        self.status = ttk.Label(cartao, text="", style="Suave.TLabel")
        self.status.pack(anchor="w", side="bottom", pady=(8, 0))
        self.botao_usar = ttk.Button(
            acoes, text="Usar este texto", style="Principal.TButton",
            command=self._usar, state="disabled",
        )
        self.botao_usar.pack(side="left")
        ttk.Button(acoes, text="Cancelar", style="TButton", command=self._fechar).pack(
            side="left", padx=(10, 0)
        )
        self.botao_trocar_chave = ttk.Button(
            acoes, text="Trocar chave da API", style="IALink.TButton",
            command=lambda: self._mostrar_painel_chave(primeira_vez=False),
        )
        self.botao_trocar_chave.pack(side="right")

    def _centralizar(self) -> None:
        j = self.janela
        j.update_idletasks()
        topo = self.mestre.winfo_toplevel()
        largura = max(j.winfo_reqwidth(), 640)
        altura = max(j.winfo_reqheight(), 520)
        x = topo.winfo_rootx() + (topo.winfo_width() - largura) // 2
        y = topo.winfo_rooty() + (topo.winfo_height() - altura) // 3
        j.geometry(f"{largura}x{altura}+{max(x, 0)}+{max(y, 0)}")

    # -- painéis ----------------------------------------------------------------
    def _mostrar_painel_conversa(self) -> None:
        self.painel_chave.pack_forget()
        self.painel_conversa.pack(fill="x", after=self.historico.master)
        # com o serviço da escola o professor não tem chave para "trocar":
        # o link vira o caminho para usar uma própria, se quiser
        self.botao_trocar_chave.configure(
            text="Usar minha própria chave" if modo_disponivel() == "servidor"
            else "Trocar chave da API"
        )
        self.botao_trocar_chave.pack(side="right")
        self.entrada.focus_set()
        self.entrada.mark_set("insert", "end")

    def _mostrar_painel_chave(self, primeira_vez: bool) -> None:
        self.painel_conversa.pack_forget()
        self.painel_chave.pack(fill="x", after=self.historico.master)
        self.campo_chave.delete(0, "end")
        com_servidor = configuracao_do_servidor() is not None
        self.texto_painel_chave.configure(
            text=TEXTO_CHAVE_COM_SERVIDOR if com_servidor else TEXTO_CHAVE_PROPRIA
        )
        self.botao_voltar_da_chave.pack_forget()
        self.botao_usar_servidor.pack_forget()
        if primeira_vez:
            self.botao_trocar_chave.pack_forget()
        else:
            self.botao_voltar_da_chave.pack(anchor="w", pady=(6, 0))
            if com_servidor and carregar_chave():
                self.botao_usar_servidor.pack(anchor="w", pady=(2, 0))
        self.campo_chave.focus_set()

    def _usar_servidor(self) -> None:
        apagar_chave()
        if carregar_chave():
            # sobrou uma chave na variável de ambiente: o programa não a apaga
            self.status.configure(
                text="Ainda há uma chave em GEMINI_API_KEY (variável ou .env); "
                "remova-a para usar o serviço da escola."
            )
        else:
            self.status.configure(text="Usando o serviço de IA da escola.")
        self._mostrar_painel_conversa()

    def _salvar_chave(self) -> None:
        chave = self.campo_chave.get().strip()
        if not chave:
            self.status.configure(text="Cole a chave no campo antes de salvar.")
            return
        try:
            salvar_chave(chave)
        except OSError as erro:
            self.status.configure(text=f"Não consegui guardar a chave: {erro}")
            return
        self.status.configure(text="Chave guardada. Agora é só descrever a aula.")
        self._mostrar_painel_conversa()
        self._pedir_sozinho_se_for_so_o_assunto()

    # -- conversa ---------------------------------------------------------------
    def _escrever(self, texto: str, *tags) -> None:
        h = self.historico
        h.configure(state="normal")
        if h.get("1.0", "end").strip():
            h.insert("end", "\n")
        h.insert("end", texto, tags)
        h.configure(state="disabled")
        h.see("end")

    def _fala(self, quem: str, texto: str) -> None:
        self._escrever("Você" if quem == "voce" else "IA", "rotulo_" + quem)
        self._escrever(texto, "fala")

    def _pular_linha(self, _evento=None):
        self.entrada.insert("insert", "\n")
        return "break"

    def _enviar(self, _evento=None):
        if self._ocupado:
            return "break"
        texto = self.entrada.get("1.0", "end").strip()
        if not texto:
            self.status.configure(text="Escreva algo sobre a aula antes de enviar.")
            return "break"
        if not modo_disponivel():
            self._mostrar_painel_chave(primeira_vez=True)
            return "break"
        self.entrada.delete("1.0", "end")
        self._fala("voce", texto)
        self.conversa.append({"role": "user", "content": texto})
        self._enviado_por_ultimo = texto
        self._ocupar(True)
        threading.Thread(
            target=self._pedir_em_segundo_plano, args=(list(self.conversa),), daemon=True
        ).start()
        self._trabalho = self.janela.after(150, self._conferir_resposta)
        return "break"

    def _pedir_em_segundo_plano(self, conversa: list) -> None:
        # Fora da thread da janela: o Tk não pode ser tocado daqui, então
        # a resposta volta por uma fila, lida por _conferir_resposta.
        try:
            self._fila.put(("ok", pedir(self.contexto, conversa)))
        except ErroDaIA as erro:
            self._fila.put(("erro", str(erro)))
        except Exception as erro:  # noqa: BLE001 - qualquer erro vira mensagem na janela
            self._fila.put(("erro", f"Erro inesperado: {erro}"))

    def _conferir_resposta(self) -> None:
        self._trabalho = None
        try:
            tipo, texto = self._fila.get_nowait()
        except queue.Empty:
            self._trabalho = self.janela.after(150, self._conferir_resposta)
            return
        self._ocupar(False)
        if tipo == "ok":
            self.conversa.append({"role": "assistant", "content": texto})
            self.ultimo_texto = texto
            self._fala("ia", texto)
            self.botao_usar.configure(state="normal")
            self.status.configure(
                text="Gostou? \"Usar este texto\". Senão, peça a correção aqui embaixo."
            )
        else:
            # A fala que falhou sai da conversa (a API não pode receber
            # duas falas seguidas do professor) e volta para a caixa de
            # digitar — é só clicar em Enviar de novo.
            if self.conversa and self.conversa[-1]["role"] == "user":
                self.conversa.pop()
            self._escrever(texto, "erro")
            if not self.entrada.get("1.0", "end").strip():
                self.entrada.insert("1.0", self._enviado_por_ultimo)
            # uma correção que falhou não apaga o texto bom de antes
            if self.ultimo_texto:
                self.botao_usar.configure(state="normal")
            self.status.configure(text="")
        self.entrada.focus_set()

    def _ocupar(self, ocupado: bool) -> None:
        self._ocupado = ocupado
        self.botao_enviar.configure(state="disabled" if ocupado else "normal")
        if ocupado:
            self.botao_usar.configure(state="disabled")
            self.status.configure(text="A IA está escrevendo...")

    def _usar(self) -> None:
        if not self.ultimo_texto:
            return
        texto = self.ultimo_texto
        self._fechar()
        self.ao_usar(texto)

    def _fechar(self) -> None:
        for nome in ("_trabalho", "_trabalho_inicial"):
            job = getattr(self, nome)
            if job is not None:
                try:
                    self.janela.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, nome, None)
        try:
            self.janela.grab_release()
        except tk.TclError:
            pass
        self.janela.destroy()
        anterior = self._grab_anterior
        if anterior is not None:
            try:
                if anterior.winfo_exists():
                    anterior.grab_set()
            except tk.TclError:
                pass


def abrir(mestre, contexto: dict, texto_inicial: str, cores: dict, ao_usar) -> JanelaAssistente:
    """Abre a janela de conversa. `ao_usar(texto)` recebe o texto escolhido."""
    return JanelaAssistente(mestre, contexto, texto_inicial, cores, ao_usar)
