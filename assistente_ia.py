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

OPCIONAL, E PAGO POR QUEM USA
-----------------------------
Usa a API do Claude (Anthropic) com a chave do PRÓPRIO professor — que
é separada da assinatura do Claude e cobrada por uso (cada texto custa
uma fração de centavo de dólar no modelo usado aqui). Sem chave, a
janela só explica como conseguir uma; o resto do programa não muda.

A CHAVE FICA POR USUÁRIO DO WINDOWS, NÃO NA PASTA DE DADOS
----------------------------------------------------------
Diferente do resto dos dados — que são do computador, compartilhados
por todo mundo que usa o laboratório (ver caminhos.pasta_de_dados) — a
chave é pessoal e paga. Por isso fica em %APPDATA%\\RegistroSED, que
outro usuário do Windows não consegue ler. Também pode vir da variável
ANTHROPIC_API_KEY (inclusive escrita no .env), para quem preferir.

O QUE É ENVIADO PARA A IA
-------------------------
Só o necessário para escrever o texto: disciplina, turma, etapa, nº de
aulas, recursos marcados, o assunto anotado na agenda e o que o
professor digitar na conversa. NOMES de professores não são enviados.
O texto livre da conversa o programa não consegue filtrar — por isso a
janela avisa para não digitar nomes de estudantes (alunos são menores
de idade), e a instrução pede à IA para não repeti-los.

SEM DEPENDÊNCIA NOVA
--------------------
A chamada é feita com urllib (biblioteca padrão), como a do atualizador
— nada a mais para empacotar no .exe.
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

URL_API = "https://api.anthropic.com/v1/messages"
VERSAO_API = "2023-06-01"
URL_CHAVES = "https://platform.claude.com/settings/keys"

# O modelo mais barato e rápido da Anthropic — de sobra para um parágrafo
# de duas frases. Dá para trocar sem mexer no código, com a linha
# MODELO_IA=... no .env (por exemplo, para um modelo maior).
MODELO_PADRAO = "claude-haiku-4-5-20251001"

TEMPO_LIMITE = 60  # segundos
ARQUIVO_CHAVE = "chave_ia.txt"


# ---------------------------------------------------------------------------
# Chave da API
# ---------------------------------------------------------------------------
def _pasta_da_chave() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "RegistroSED"
    return Path.home() / ".config" / "RegistroSED"  # fora do Windows (desenvolvimento)


def carregar_chave() -> str:
    """
    A chave salva pela tela tem preferência — é a última coisa que o
    professor fez de propósito. A variável ANTHROPIC_API_KEY (ou a mesma
    linha no .env) fica como alternativa.
    """
    try:
        salva = (_pasta_da_chave() / ARQUIVO_CHAVE).read_text(encoding="utf-8").strip()
    except OSError:
        salva = ""
    return salva or (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def salvar_chave(chave: str) -> None:
    pasta = _pasta_da_chave()
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / ARQUIVO_CHAVE).write_text(chave.strip(), encoding="utf-8")


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
    """Erro já explicado em português, pronto para aparecer na janela."""


def _explicar_erro_http(erro: urllib.error.HTTPError) -> str:
    try:
        corpo = json.loads(erro.read().decode("utf-8"))
        mensagem = str((corpo.get("error") or {}).get("message") or "")
    except Exception:
        mensagem = ""
    if erro.code == 401:
        return (
            "A chave da API não foi aceita. Confira se ela foi copiada "
            "inteira e use \"Trocar chave da API\" para colar de novo."
        )
    if erro.code == 403:
        return "Esta chave não tem permissão para usar a API. Crie outra em platform.claude.com."
    if "credit" in mensagem.lower() or "billing" in mensagem.lower():
        return (
            "A conta da API está sem créditos. Adicione créditos em "
            "platform.claude.com (Billing) e tente de novo."
        )
    if erro.code == 429:
        return "Muitos pedidos seguidos. Espere alguns segundos e tente de novo."
    if erro.code >= 500:
        return "O serviço da IA está sobrecarregado ou fora do ar agora. Tente de novo em instantes."
    return f"O serviço da IA recusou o pedido (erro {erro.code}). {mensagem}".strip()


def pedir_texto(chave: str, contexto: dict, conversa: list, modelo: str = "") -> str:
    """
    Manda a conversa inteira (lista de {"role", "content"}, terminando
    numa fala do professor) e devolve o texto novo, já limpo.

    A conversa vai inteira a cada pedido porque a API não guarda nada
    entre um pedido e outro: é assim que "foi o professor de ARTES" faz
    sentido para ela — ela lê o texto anterior junto.
    """
    corpo = json.dumps(
        {
            "model": modelo or (os.environ.get("MODELO_IA") or "").strip() or MODELO_PADRAO,
            "max_tokens": 500,
            # Sem "temperature" de propósito: os modelos maiores atuais
            # recusam esse parâmetro (erro 400), e MODELO_IA existe
            # justamente para trocar de modelo sem mexer no código.
            "system": montar_instrucoes(contexto),
            "messages": conversa,
        }
    ).encode("utf-8")
    requisicao = urllib.request.Request(
        URL_API,
        data=corpo,
        method="POST",
        headers={
            "x-api-key": chave,
            "anthropic-version": VERSAO_API,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        raise ErroDaIA(_explicar_erro_http(erro)) from None
    except (urllib.error.URLError, OSError) as erro:
        raise ErroDaIA(
            "Não consegui falar com o serviço da IA — parece internet. "
            f"Confira a conexão e tente de novo.\n(detalhe técnico: {erro})"
        ) from None
    except ValueError:
        raise ErroDaIA("O serviço da IA mandou uma resposta que não consegui ler. Tente de novo.") from None

    texto = "".join(
        bloco.get("text", "")
        for bloco in (dados.get("content") or [])
        if isinstance(bloco, dict) and bloco.get("type") == "text"
    )
    texto = limpar_texto(texto)
    if not texto:
        raise ErroDaIA("A IA respondeu em branco. Tente de novo.")
    return texto


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

        if carregar_chave():
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
        if carregar_chave():
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
        ttk.Label(
            self.painel_chave,
            text=(
                "Para escrever com IA, o programa usa a API do Claude (Anthropic) com "
                "uma chave sua. Ela é separada da assinatura do Claude e é cobrada por "
                "uso — cada texto custa uma fração de centavo de dólar. A chave fica "
                "guardada só neste usuário do Windows.\n"
                "O que você escrever na conversa, junto com os dados da aula, é "
                "enviado à Anthropic para gerar o texto: não digite nomes de "
                "estudantes."
            ),
            style="Cartao.TLabel",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(10, 4))
        ttk.Button(
            self.painel_chave, text="Criar uma chave em platform.claude.com",
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
        self.botao_trocar_chave.pack(side="right")
        self.entrada.focus_set()
        self.entrada.mark_set("insert", "end")

    def _mostrar_painel_chave(self, primeira_vez: bool) -> None:
        self.painel_conversa.pack_forget()
        self.painel_chave.pack(fill="x", after=self.historico.master)
        self.campo_chave.delete(0, "end")
        if primeira_vez:
            self.botao_voltar_da_chave.pack_forget()
            self.botao_trocar_chave.pack_forget()
        else:
            self.botao_voltar_da_chave.pack(anchor="w", pady=(6, 0))
        self.campo_chave.focus_set()

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
        chave = carregar_chave()
        if not chave:
            self._mostrar_painel_chave(primeira_vez=True)
            return "break"
        self.entrada.delete("1.0", "end")
        self._fala("voce", texto)
        self.conversa.append({"role": "user", "content": texto})
        self._enviado_por_ultimo = texto
        self._ocupar(True)
        threading.Thread(
            target=self._pedir_em_segundo_plano, args=(chave, list(self.conversa)), daemon=True
        ).start()
        self._trabalho = self.janela.after(150, self._conferir_resposta)
        return "break"

    def _pedir_em_segundo_plano(self, chave: str, conversa: list) -> None:
        # Fora da thread da janela: o Tk não pode ser tocado daqui, então
        # a resposta volta por uma fila, lida por _conferir_resposta.
        try:
            self._fila.put(("ok", pedir_texto(chave, self.contexto, conversa)))
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
