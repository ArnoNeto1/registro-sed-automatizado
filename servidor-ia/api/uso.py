# -*- coding: utf-8 -*-
"""
Contagem ANÔNIMA de quantos computadores (e de quantas escolas) usam o
Registro SED (função da Vercel, em Python). Serve só para o mantenedor saber
o tamanho do uso.

    POST /api/uso   {"id": "<32 caracteres hex>", "versao": "2.3.0",
                     "escola": "<nome da lista oficial>"}   (escola é opcional)
                    com o cabeçalho x-app-token (o mesmo segredo da IA)
    GET  /api/uso   os totais, em JSON (público: são só números)
    GET  /api/uso?detalhe=escolas
                    a lista de escolas, SÓ com o cabeçalho x-painel-token
                    (a senha do mantenedor; nunca em cache público)

O QUE FICA GUARDADO — E O QUE NÃO FICA:
  - Cada computador manda um número aleatório que ele mesmo inventou (sem
    ligação com nome, CPF ou usuário do Windows), a versão do programa e a
    escola escolhida no cadastro. Nada mais é lido: campos a mais são
    jogados fora.
  - A escola só entra se for IGUAL a um nome da lista oficial da CRE
    (_escolas.py, cópia exata de escolas.py): texto livre, nome de pessoa ou
    outra grafia são descartados, e o computador conta do mesmo jeito.
  - O número do computador entra em contadores HyperLogLog do Redis
    (Upstash): eles dão a quantidade de números DIFERENTES, com cerca de 1%
    de erro, mas não guardam os números — não dá para listá-los nem
    descobrir quem é quem. Para as escolas guarda-se, além disso, só
    "escola -> último dia em que apareceu" e um contador de computadores por
    escola (também HyperLogLog): o número do computador NUNCA fica ao lado
    do nome da escola em forma que se possa listar.
  - Este código não grava o endereço de IP e não registra o número, o
    segredo nem conteúdo nenhum: o registro só diz o MOTIVO de uma recusa.
  - As contas são por dia (horário de Brasília), por versão e no total.

VARIÁVEIS DE AMBIENTE (painel da Vercel):
  APP_TOKEN                            o mesmo da IA (ver api/ia.py);
  PAINEL_TOKEN                         a senha que abre a lista de escolas
                                       (só do mantenedor; sem ela a lista
                                       fica fechada para todo mundo);
  KV_REST_API_URL, KV_REST_API_TOKEN   criadas sozinhas quando o Redis da
                                       Upstash é ligado ao projeto (também
                                       valem UPSTASH_REDIS_REST_URL e
                                       UPSTASH_REDIS_REST_TOKEN).
"""

from __future__ import annotations

import datetime
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _escolas  # noqa: E402  (cópia exata de escolas.py, na raiz do repositório)

LIMITE_CORPO = 1_000  # bytes
FUSO = datetime.timezone(datetime.timedelta(hours=-3))  # Brasília
VALIDADE_EM_SEGUNDOS = 400 * 24 * 3600  # cada chave diária some depois de ~13 meses
ESCOLAS_OFICIAIS = frozenset(_escolas.ESCOLAS_CRE_BLUMENAU)  # a ÚNICA lista de escolas que entra

# [0-9], e não \d: \d aceitaria dígitos de outros alfabetos. fullmatch, e não
# match com $: o $ aceitaria uma quebra de linha sobrando no fim.
_RE_ID = re.compile(r"[0-9a-f]{32}")
_RE_VERSAO = re.compile(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}")
_RE_DIA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class ArmazenamentoIndisponivel(RuntimeError):
    """O Redis não está configurado, não respondeu ou respondeu com erro."""


def _registrar(motivo: str) -> None:
    # Só o motivo: nunca o número da instalação, o segredo ou o endereço de ninguém.
    print(f"[uso] {motivo}", file=sys.stderr)


def _redis(comandos: list) -> list:
    """Manda uma lista de comandos ao Redis (POST /pipeline) e devolve o resultado de cada um."""
    url = (os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip().rstrip("/")
    token = (os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    seguro = url.startswith(("https://", "http://127.0.0.1", "http://localhost"))
    if not (seguro and token):
        raise ArmazenamentoIndisponivel("Redis não configurado")
    requisicao = urllib.request.Request(
        url + "/pipeline",
        data=json.dumps(comandos).encode("utf-8"),
        method="POST",
        headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=8) as resposta:
            resultados = json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        raise ArmazenamentoIndisponivel("falha na chamada ao Redis") from None
    if not isinstance(resultados, list) or len(resultados) != len(comandos):
        raise ArmazenamentoIndisponivel("resposta inesperada do Redis")
    if any(not isinstance(r, dict) or "error" in r for r in resultados):
        raise ArmazenamentoIndisponivel("o Redis recusou um comando")
    return [r.get("result") for r in resultados]


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _datas(agora: datetime.datetime, quantas: int) -> list:
    """As últimas `quantas` datas (a de hoje primeiro), no horário de Brasília."""
    hoje = agora.astimezone(FUSO).date()
    return [(hoje - datetime.timedelta(days=i)).isoformat() for i in range(quantas)]


def _como_numero(versao: str) -> tuple:
    return tuple(int(parte) for parte in versao.split("."))


def registrar(
    id_instalacao: str, versao: str, agora: datetime.datetime | None = None, escola: str = ""
) -> None:
    """
    Conta este computador hoje, na versão e no total. Repetir no mesmo dia
    não muda nada. Com `escola` (só vale um nome da lista oficial; qualquer
    outra coisa é ignorada) conta também o computador naquela escola e
    anota o dia em que a escola apareceu por último.
    """
    dia = _datas(agora or _agora(), 1)[0]
    chave_do_dia = f"uso:dia:{dia}"
    chave_da_versao = f"uso:v:{versao}:{dia}"
    comandos = [
        ["PFADD", chave_do_dia, id_instalacao],
        ["EXPIRE", chave_do_dia, VALIDADE_EM_SEGUNDOS],
        ["PFADD", chave_da_versao, id_instalacao],
        ["EXPIRE", chave_da_versao, VALIDADE_EM_SEGUNDOS],
        ["PFADD", "uso:todos", id_instalacao],
        ["SADD", "uso:versoes", versao],
    ]
    if escola in ESCOLAS_OFICIAIS:
        # O número do computador só entra no contador (HyperLogLog, que não
        # dá para listar); o que fica legível é "escola -> último dia".
        chave_da_escola = f"uso:escola:{escola}"
        comandos += [
            ["PFADD", chave_da_escola, id_instalacao],
            ["EXPIRE", chave_da_escola, VALIDADE_EM_SEGUNDOS],
            ["HSET", "uso:escolas", escola, dia],
        ]
    _redis(comandos)


def _escolas_vistas(resultado) -> dict:
    """
    {escola: último dia} a partir do HGETALL do Redis (que devolve campo,
    valor, campo, valor...). Só passa nome da lista oficial com data no
    formato certo: o que estiver estragado ou for de fora é jogado fora.
    """
    if isinstance(resultado, dict):
        pares = list(resultado.items())
    else:
        itens = list(resultado or [])
        pares = list(zip(itens[0::2], itens[1::2]))
    return {
        nome: dia
        for nome, dia in pares
        if isinstance(nome, str) and nome in ESCOLAS_OFICIAIS and isinstance(dia, str) and _RE_DIA.fullmatch(dia)
    }


def totais(agora: datetime.datetime | None = None) -> dict:
    """Quantos computadores usaram o programa: hoje, ontem, em 7 e 30 dias, no total e por versão."""
    agora = agora or _agora()
    dias = [f"uso:dia:{d}" for d in _datas(agora, 30)]
    hoje, ontem, sete, trinta, desde_o_inicio, versoes, escolas_bruto = _redis(
        [
            ["PFCOUNT", dias[0]],
            ["PFCOUNT", dias[1]],
            ["PFCOUNT", *dias[:7]],
            ["PFCOUNT", *dias],
            ["PFCOUNT", "uso:todos"],
            ["SMEMBERS", "uso:versoes"],
            ["HGETALL", "uso:escolas"],
        ]
    )
    escolas_vistas = _escolas_vistas(escolas_bruto)
    ultimos_30_dias = set(_datas(agora, 30))
    versoes = sorted(
        (v for v in (versoes or []) if isinstance(v, str) and _RE_VERSAO.fullmatch(v)),
        key=_como_numero,
        reverse=True,
    )
    por_versao: dict = {}
    if versoes:
        datas = _datas(agora, 30)
        contagens = _redis([["PFCOUNT", *[f"uso:v:{v}:{d}" for d in datas]] for v in versoes])
        por_versao = {v: n for v, n in zip(versoes, contagens) if n}
    return {
        "atualizado_em": agora.astimezone(FUSO).strftime("%Y-%m-%d %H:%M"),
        "hoje": hoje,
        "ontem": ontem,
        "ultimos_7_dias": sete,
        "ultimos_30_dias": trinta,
        "desde_o_inicio": desde_o_inicio,
        "por_versao": por_versao,
        # só os NÚMEROS: quais são as escolas, só com a senha do painel (detalhe_escolas)
        "escolas_diferentes": len(escolas_vistas),
        "escolas_ultimos_30_dias": sum(1 for dia in escolas_vistas.values() if dia in ultimos_30_dias),
        "aviso": "contagem aproximada de computadores (instalações), não de pessoas",
    }


def detalhe_escolas(agora: datetime.datetime | None = None) -> dict:
    """As escolas que já apareceram, com o nº de computadores de cada uma e o último dia de uso. PRIVADO."""
    agora = agora or _agora()
    (bruto,) = _redis([["HGETALL", "uso:escolas"]])
    vistas = _escolas_vistas(bruto)
    nomes = sorted(vistas)
    contagens = _redis([["PFCOUNT", f"uso:escola:{nome}"] for nome in nomes]) if nomes else []
    return {
        "atualizado_em": agora.astimezone(FUSO).strftime("%Y-%m-%d %H:%M"),
        "escolas": [
            {"escola": nome, "computadores": quantos, "ultimo_uso": vistas[nome]}
            for nome, quantos in zip(nomes, contagens)
        ],
        "aviso": "computadores por escola são aproximados; um computador usado em duas escolas conta nas duas",
    }


def responder_aviso(corpo: bytes, token_recebido: str) -> tuple:
    """(status HTTP, dicionário JSON) para um aviso do programa."""
    token = os.environ.get("APP_TOKEN", "").strip()
    if not token:
        _registrar("servidor sem APP_TOKEN configurado")
        return 503, {"erro": "A contagem ainda não está configurada."}
    if not hmac.compare_digest(token_recebido.encode("utf-8"), token.encode("utf-8")):
        _registrar("recusado: segredo do programa errado")
        return 401, {"erro": "Segredo do programa não reconhecido."}
    if len(corpo) > LIMITE_CORPO:
        return 413, {"erro": "Pedido grande demais."}
    try:
        dados = json.loads(corpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return 400, {"erro": "Pedido mal formado."}
    id_instalacao = dados.get("id") if isinstance(dados, dict) else None
    versao = dados.get("versao") if isinstance(dados, dict) else None
    valido = (
        isinstance(id_instalacao, str)
        and _RE_ID.fullmatch(id_instalacao)
        and isinstance(versao, str)
        and _RE_VERSAO.fullmatch(versao)
    )
    if not valido:
        _registrar("recusado: pedido fora do combinado")
        return 400, {"erro": "Pedido mal formado."}
    # A escola é opcional e só vale se for um nome da lista oficial; qualquer
    # outra coisa (tipo errado, texto livre) é ignorada: o computador conta igual.
    escola = dados.get("escola")
    if not (isinstance(escola, str) and escola in ESCOLAS_OFICIAIS):
        escola = ""
    try:
        registrar(id_instalacao, versao, escola=escola)
    except ArmazenamentoIndisponivel:
        _registrar("armazenamento indisponível")
        return 503, {"erro": "A contagem está indisponível agora."}
    return 200, {"ok": True}


def responder_totais() -> tuple:
    """(status HTTP, dicionário JSON) para quem pede os totais."""
    try:
        return 200, totais()
    except ArmazenamentoIndisponivel:
        _registrar("armazenamento indisponível")
        return 503, {"erro": "A contagem está indisponível agora."}


def responder_detalhe(token_recebido: str) -> tuple:
    """
    (status HTTP, dicionário JSON) para a lista de escolas — só com a senha
    do mantenedor (PAINEL_TOKEN). O segredo do programa (APP_TOKEN) NÃO abre
    isto: ele viaja dentro do .exe e qualquer pessoa consegue extraí-lo. Sem
    PAINEL_TOKEN configurado a lista fica fechada para todos (nem "vazio
    igual a vazio" abre).
    """
    token = os.environ.get("PAINEL_TOKEN", "").strip()
    if not token:
        _registrar("painel sem PAINEL_TOKEN configurado")
        return 503, {"erro": "O painel ainda não está configurado."}
    if not hmac.compare_digest(token_recebido.encode("utf-8"), token.encode("utf-8")):
        _registrar("recusado: senha do painel errada")
        return 401, {"erro": "Senha do painel não reconhecida."}
    try:
        return 200, detalhe_escolas()
    except ArmazenamentoIndisponivel:
        _registrar("armazenamento indisponível")
        return 503, {"erro": "A contagem está indisponível agora."}


class handler(BaseHTTPRequestHandler):  # nome exigido pela Vercel
    def _enviar(self, status: int, dados: dict, publico: bool = False) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        # Os totais podem ficar 5 minutos em cache: ninguém precisa deles segundo a segundo.
        self.send_header("Cache-Control", "public, s-maxage=300" if publico and status == 200 else "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):  # noqa: N802 (nome exigido pelo http.server)
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            tamanho = -1
        if tamanho < 0 or tamanho > LIMITE_CORPO:
            self._enviar(413, {"erro": "Pedido grande demais."})
            return
        corpo = self.rfile.read(tamanho)
        status, dados = responder_aviso(corpo, self.headers.get("x-app-token", ""))
        self._enviar(status, dados)

    def do_GET(self):  # noqa: N802
        consulta = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
        if "detalhe" in consulta:
            # a lista de escolas: com a senha do painel, nunca em cache público
            if consulta["detalhe"] == ["escolas"]:
                status, dados = responder_detalhe(self.headers.get("x-painel-token", ""))
            else:
                status, dados = 400, {"erro": "Consulta não reconhecida."}
            self._enviar(status, dados)
            return
        status, dados = responder_totais()
        self._enviar(status, dados, publico=True)

    def _nao_permitido(self):
        self._enviar(405, {"erro": "Use POST (aviso) ou GET (totais)."})

    do_PUT = do_DELETE = do_PATCH = _nao_permitido  # noqa: N815

    def log_message(self, *_args):
        pass  # o registro padrão escreveria o IP de quem chama; não queremos isso
