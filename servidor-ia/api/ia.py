# -*- coding: utf-8 -*-
"""
Servidor intermediário da IA do Registro SED (função da Vercel, em Python).

POR QUE EXISTE: o professor não precisa criar chave nenhuma. A chave do
Gemini da escola mora SÓ aqui, numa variável de ambiente do servidor —
nunca no programa (que é distribuído e fácil de abrir) nem no repositório
(que é público). O programa manda os dados da aula e a conversa; o
servidor monta a instrução, chama o Gemini e devolve o texto.

O QUE ELE FAZ PARA SE DEFENDER (qualquer segredo guardado no programa
pode ser extraído por alguém determinado, então o servidor não confia em
ninguém):
  - só aceita POST com o cabeçalho x-app-token certo (APP_TOKEN);
  - a instrução é FIXA e vive aqui: ninguém consegue usar este endereço
    como uma IA genérica de graça, só para escrever "objetos do
    conhecimento";
  - só passam os campos da aula combinados (ia.CHAVES_DO_CONTEXTO), com
    tamanho limitado — nunca nome de professor;
  - tamanho do pedido, da conversa e de cada fala têm teto;
  - recusa texto que pareça ter CPF, e-mail ou telefone (o escape mais
    comum; nome de pessoa não dá para detectar, fica com o aviso);
  - nunca devolve o erro cru da Google (poderia vazar detalhe da chave) e
    nunca registra o conteúdo dos pedidos, só o motivo da recusa.
O que falta para ser à prova de abuso é um teto de gasto na própria Google
(orçamento/cota do projeto) e, se for preciso, um limite por IP — ver o
README desta pasta.

VARIÁVEIS DE AMBIENTE (configuradas no painel da Vercel, como "sensíveis"):
  GEMINI_API_KEY  chave do Gemini com FATURAMENTO ligado (plano pago): na
                  chave gratuita a Google usa o conteúdo dos professores
                  para melhorar os produtos dela;
  APP_TOKEN       segredo longo e aleatório, igual ao que vai no programa;
  MODELO_IA       (opcional) outro modelo no lugar da lista padrão. Vários,
                  separados por vírgula, são tentados na ordem; um só usa
                  esse modelo e nenhum outro (desliga a troca automática).
"""

from __future__ import annotations

import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ia_gemini as ia  # noqa: E402  (cópia exata de ia_gemini.py, na raiz do repositório)

LIMITE_CORPO = 24_000  # bytes do pedido inteiro
MAX_FALAS = 20
MAX_TEXTO_FALA = 4_000
MAX_TEXTO_CAMPO = 600
MAX_TOTAL_CONVERSA = 12_000

MSG_CONFIGURACAO = (
    "O serviço de IA da escola está com um problema de configuração. "
    "Avise quem mantém o programa."
)
MSG_FORA_DO_AR = "O serviço de IA está fora do ar agora. Tente de novo em instantes."
RESPOSTAS_DE_ERRO = {
    # (status HTTP, mensagem para o professor) por tipo de ErroDaIA
    "chave": (503, MSG_CONFIGURACAO),
    "permissao": (503, MSG_CONFIGURACAO),
    "modelo": (503, MSG_CONFIGURACAO),
    "limite": (
        429,
        "O serviço de IA está muito ocupado agora (limite de uso). "
        "Tente de novo em alguns minutos.",
    ),
    "indisponivel": (503, MSG_FORA_DO_AR),
    "rede": (502, MSG_FORA_DO_AR),
    "bloqueado": (
        422,
        "O serviço da IA não aceitou escrever sobre isso (filtro de segurança). "
        "Reescreva a descrição da aula e tente de novo.",
    ),
    "vazio": (502, "A IA respondeu em branco. Tente de novo."),
    "resposta": (502, MSG_FORA_DO_AR),
    "recusado": (502, MSG_FORA_DO_AR),
}


class PedidoInvalido(ValueError):
    """Pedido fora do combinado — a mensagem já é para o professor."""


def _registrar(motivo: str) -> None:
    # Só o motivo, nunca o conteúdo: o que o professor escreve não pode
    # parar em registro de servidor.
    print(f"[ia] {motivo}", file=sys.stderr)


def validar(dados) -> tuple:
    """(contexto, conversa) já limpos, ou levanta PedidoInvalido."""
    if not isinstance(dados, dict):
        raise PedidoInvalido("Pedido mal formado.")

    bruto = dados.get("contexto") or {}
    if not isinstance(bruto, dict):
        raise PedidoInvalido("Pedido mal formado (dados da aula).")
    contexto: dict = {}
    # Só os campos combinados; o resto é ignorado. Isso inclui o "recursos"
    # que a versão 2.0.0 do programa ainda manda: a IA deixou de recebê-lo.
    for chave in ia.CHAVES_DO_CONTEXTO:
        valor = bruto.get(chave)
        if valor in (None, "", []):
            continue
        if not isinstance(valor, (str, int)) or isinstance(valor, bool):
            raise PedidoInvalido(f"Pedido mal formado ({chave}).")
        texto = str(valor)
        if len(texto) > MAX_TEXTO_CAMPO:
            raise PedidoInvalido(f"O campo {chave} está grande demais.")
        contexto[chave] = texto

    falas = dados.get("conversa")
    if not isinstance(falas, list) or not falas or len(falas) > MAX_FALAS:
        raise PedidoInvalido("Pedido mal formado (conversa).")
    conversa = []
    total = 0
    for posicao, fala in enumerate(falas):
        if not isinstance(fala, dict):
            raise PedidoInvalido("Pedido mal formado (conversa).")
        papel = "user" if posicao % 2 == 0 else "assistant"  # sempre alternando, começando por quem escreve
        texto = fala.get("content")
        if fala.get("role") != papel or not isinstance(texto, str) or not texto.strip():
            raise PedidoInvalido("Pedido mal formado (conversa).")
        if len(texto) > MAX_TEXTO_FALA:
            raise PedidoInvalido("Uma mensagem está grande demais. Escreva um pouco menos.")
        total += len(texto)
        conversa.append({"role": papel, "content": texto})
    if conversa[-1]["role"] != "user":
        raise PedidoInvalido("Pedido mal formado (a conversa precisa terminar com você).")
    if total > MAX_TOTAL_CONVERSA:
        raise PedidoInvalido("A conversa ficou grande demais. Feche a janela e comece de novo.")
    return contexto, conversa


def responder(corpo: bytes, token_recebido: str) -> tuple:
    """(status HTTP, dicionário JSON) para um pedido. Sem nada de rede aqui dentro além da chamada ao Gemini."""
    # strip(): um espaço ou quebra de linha invisível colado junto com o
    # segredo no painel da Vercel faria o servidor recusar o programa para
    # sempre (ou a chave virar um cabeçalho inválido) — e seria um erro
    # muito difícil de enxergar.
    token = os.environ.get("APP_TOKEN", "").strip()
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not token or not chave:
        _registrar("servidor sem APP_TOKEN ou GEMINI_API_KEY configurados")
        return 503, {"erro": "O serviço de IA da escola ainda não está configurado."}

    if not hmac.compare_digest(token_recebido.encode("utf-8"), token.encode("utf-8")):
        _registrar("recusado: segredo do programa errado")
        return 401, {
            "erro": "O serviço de IA da escola não reconheceu este programa. "
            "Atualize o programa para a versão mais nova."
        }

    if len(corpo) > LIMITE_CORPO:
        return 413, {"erro": "O pedido ficou grande demais."}
    try:
        dados = json.loads(corpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return 400, {"erro": "Pedido mal formado."}
    try:
        contexto, conversa = validar(dados)
    except PedidoInvalido as erro:
        _registrar("recusado: pedido fora do combinado")
        return 400, {"erro": str(erro)}

    # CPF, e-mail ou telefone no texto: recusa antes de a Google ver. O
    # programa já avisa, mas o servidor não confia em ninguém. Só o TIPO
    # vai para o registro, nunca o texto.
    for texto_da_pessoa in ia.textos_do_pedido(contexto, conversa):
        tipo_de_dado = ia.achar_dado_pessoal(texto_da_pessoa)
        if tipo_de_dado:
            _registrar(f"recusado: parece haver {tipo_de_dado} no texto")
            return 422, {"erro": ia.aviso_de_dado_pessoal(tipo_de_dado)}

    try:
        # Se o modelo principal estiver no limite ou sobrecarregado, o núcleo
        # tenta o seguinte; cada troca vai para o registro só como tipo e modelo.
        texto = ia.pedir_texto(chave, contexto, conversa, registrar=_registrar)
    except ia.ErroDaIA as erro:
        _registrar(f"erro do Gemini: {erro.tipo}")
        status, mensagem = RESPOSTAS_DE_ERRO.get(erro.tipo, (502, MSG_FORA_DO_AR))
        return status, {"erro": mensagem}
    except Exception as erro:  # noqa: BLE001 - qualquer surpresa vira resposta limpa
        _registrar(f"erro inesperado: {type(erro).__name__}")
        return 500, {"erro": "O serviço de IA da escola teve um problema inesperado. Tente de novo."}
    return 200, {"texto": texto}


class handler(BaseHTTPRequestHandler):  # nome exigido pela Vercel
    def _enviar(self, status: int, dados: dict) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):  # noqa: N802 (nome exigido pelo http.server)
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            tamanho = -1
        if tamanho < 0 or tamanho > LIMITE_CORPO:
            self._enviar(413, {"erro": "O pedido ficou grande demais."})
            return
        corpo = self.rfile.read(tamanho)
        status, dados = responder(corpo, self.headers.get("x-app-token", ""))
        self._enviar(status, dados)

    def _so_post(self):
        self._enviar(405, {"erro": "Use POST."})

    do_GET = do_PUT = do_DELETE = do_PATCH = _so_post  # noqa: N815

    def log_message(self, *_args):
        pass  # o registro padrão imprimiria endereços; não queremos ruído
