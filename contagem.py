# -*- coding: utf-8 -*-
"""
Contagem de quantos computadores (e de quantas escolas) usam o programa —
só para quem mantém o programa saber o tamanho do uso. Sem tela, sem
pergunta, e sem nunca atrapalhar a abertura.

O QUE VAI PARA O SERVIDOR DA ESCOLA (api/uso.py), NO MÁXIMO UMA VEZ POR DIA
(POR ESCOLA, se o mesmo computador trocar de escola no dia):
  - um número aleatório desta instalação (guardado em id_instalacao.txt, na
    pasta de dados; inventado aqui, na primeira vez, sem relação com nome,
    CPF, usuário do Windows ou com o computador);
  - a versão do programa;
  - a escola escolhida no cadastro, mas SÓ se for IGUAL a um nome da lista
    oficial da CRE (escolas.py): são nomes públicos, e texto livre ou outra
    grafia nunca saem do computador.
NADA MAIS. Nem nome de professor, nem CPF, nem aulas, nem o que se escreve
na IA. O servidor não guarda o número em forma que dê para listar, e a
lista de escolas só abre com uma senha do mantenedor.

QUEM FICA DE FORA: o computador que tem o arquivo `modo_teste.txt` na pasta
de dados (os do mantenedor) ou a variável REGISTRO_SED_NAO_CONTAR definida
(qualquer valor, menos vazio, 0 ou false). Nesses casos nem o número da
instalação é criado. Rodando pelos .py não há servidor configurado, então
também não conta.

Se a internet falhar, o servidor estiver fora do ar ou a pasta não for
gravável, não acontece nada: o programa segue igual e tenta de novo na
próxima abertura.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import secrets
import urllib.parse
import urllib.request

import atualizador
from caminhos import caminho_de_dados

ARQUIVO_ID = "id_instalacao.txt"
ARQUIVO_ULTIMA = "ultima_contagem.txt"
ARQUIVO_MARCADOR = "modo_teste.txt"
VARIAVEL_DESLIGAR = "REGISTRO_SED_NAO_CONTAR"
TEMPO_LIMITE = 6  # segundos; é uma thread de fundo, mas não vale esperar mais que isso

_RE_ID = re.compile(r"[0-9a-f]{32}")


def _desligada() -> bool:
    if os.path.exists(caminho_de_dados(ARQUIVO_MARCADOR)):
        return True
    valor = (os.environ.get(VARIAVEL_DESLIGAR) or "").strip().lower()
    return valor not in ("", "0", "false")


def _ler(nome: str) -> str:
    try:
        with open(caminho_de_dados(nome), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _gravar(nome: str, texto: str) -> None:
    with open(caminho_de_dados(nome), "w", encoding="utf-8") as f:
        f.write(texto)


def id_da_instalacao() -> str:
    """O número aleatório desta instalação (32 caracteres hex). Inventa e guarda na primeira vez."""
    atual = _ler(ARQUIVO_ID).lower()
    if _RE_ID.fullmatch(atual):
        return atual
    novo = secrets.token_hex(16)
    _gravar(ARQUIVO_ID, novo)
    return novo


def _endereco_do_aviso(url_da_ia: str) -> str:
    """.../api/ia  ->  .../api/uso (o mesmo servidor da escola)."""
    return urllib.parse.urljoin(url_da_ia, "uso")


def _escola_oficial(escola) -> str:
    """
    A escola só vale se for IGUAL a um nome da lista oficial da CRE; qualquer
    outra coisa (texto livre, outra grafia, o aviso "Selecione uma escola",
    tipo errado) vira vazio e não sai do computador. Se nem a lista puder ser
    lida, também não vai nada.
    """
    try:
        from escolas import ESCOLAS_CRE_BLUMENAU
    except ImportError:
        return ""
    return escola if isinstance(escola, str) and escola in ESCOLAS_CRE_BLUMENAU else ""


def _marcador(dia: str, escola: str) -> str:
    """O que fica em ultima_contagem.txt. Sem escola é só o dia, como sempre foi."""
    return f"{dia}|{escola}" if escola else dia


def registrar_uso(servidor, hoje: datetime.date | None = None, escola: str = "") -> bool:
    """
    Manda o aviso do dia, se ainda não mandou hoje (para esta escola).
    `servidor` é o (endereço, segredo) do serviço da escola — o mesmo da IA —
    ou None (programa sem servidor configurado: nada a fazer). `escola` é a
    escolhida no cadastro e só vai se for um nome da lista oficial. Devolve
    True só quando o aviso foi enviado e aceito. NUNCA levanta exceção.
    """
    try:
        if not servidor or _desligada():
            return False
        url_da_ia, token = servidor
        dia = (hoje or datetime.date.today()).isoformat()
        escola = _escola_oficial(escola)
        marcador = _marcador(dia, escola)
        # trocar de escola no mesmo dia (o notebook de quem atende em duas) avisa de novo
        if _ler(ARQUIVO_ULTIMA) == marcador:
            return False
        dados = {"id": id_da_instalacao(), "versao": atualizador.versao_atual()}
        if escola:
            dados["escola"] = escola
        corpo = json.dumps(dados).encode("utf-8")
        requisicao = urllib.request.Request(
            _endereco_do_aviso(url_da_ia),
            data=corpo,
            method="POST",
            headers={"content-type": "application/json", "x-app-token": token},
        )
        with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
            if not 200 <= resposta.status < 300:
                return False
        _gravar(ARQUIVO_ULTIMA, marcador)  # só depois de dar certo: se falhar, tenta de novo na próxima abertura
        return True
    except Exception:  # noqa: BLE001 - contar é a última coisa que pode atrapalhar alguém
        return False
