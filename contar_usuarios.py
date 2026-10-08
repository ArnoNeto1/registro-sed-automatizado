# -*- coding: utf-8 -*-
"""
Quantos computadores e quantas escolas usam o programa — lido do endereço de
totais do servidor da escola (servidor-ia/api/uso.py).

    python contar_usuarios.py              # endereço de sempre
    python contar_usuarios.py <endereço>   # outro endereço (para testes)

OS NÚMEROS (computadores, escolas diferentes) são públicos: qualquer um pode
abrir o endereço de totais. Cada número de computadores é de COMPUTADORES
(instalações do programa que mandaram o aviso do dia), não de pessoas: dois
professores no mesmo computador contam uma vez, e quem reinstala ou apaga a
pasta de dados conta de novo. Os computadores do mantenedor ficam de fora
(arquivo modo_teste.txt). A contagem só vale para quem já atualizou para a
versão 2.1.0 ou mais nova, e a escola só para quem atualizou para a 2.3.0 ou
mais nova.

QUAIS ESCOLAS usam só aparece para quem tem a SENHA DO PAINEL (a variável
PAINEL_TOKEN do servidor). Ela fica só no computador do mantenedor, FORA do
repositório: no arquivo painel_token.txt, na pasta %APPDATA%\\RegistroSED, ou
na variável REGISTRO_SED_PAINEL_TOKEN. Sem a senha, o script mostra só os
números. Nenhum nome de professor é coletado em lugar nenhum.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

from escolas import ESCOLAS_CRE_BLUMENAU

ENDERECO = "https://registro-sed-ia-plexe1.vercel.app/api/uso"
ARQUIVO_SENHA = "painel_token.txt"
VARIAVEL_SENHA = "REGISTRO_SED_PAINEL_TOKEN"


class PainelFechado(RuntimeError):
    """O servidor não abriu a lista de escolas (senha não aceita ou painel sem senha). A mensagem é para o mantenedor."""


def buscar(endereco: str = ENDERECO) -> dict:
    requisicao = urllib.request.Request(endereco, headers={"User-Agent": "contar-usuarios"})
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def pasta_da_senha() -> Path:
    """A mesma pasta pessoal da chave da IA: por usuário do Windows, longe do repositório."""
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "RegistroSED"
    return Path.home() / ".config" / "RegistroSED"  # fora do Windows (desenvolvimento)


def senha_do_painel() -> str:
    """A senha do painel (variável de ambiente, ou o arquivo na pasta pessoal); vazio se não houver."""
    do_ambiente = (os.environ.get(VARIAVEL_SENHA) or "").strip()
    if do_ambiente:
        return do_ambiente
    try:
        return (pasta_da_senha() / ARQUIVO_SENHA).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def buscar_escolas(endereco: str = ENDERECO, senha: str = "") -> dict:
    """
    A lista de escolas (nome, computadores, último uso). A senha vai no CABEÇALHO,
    nunca no endereço. Levanta PainelFechado se o servidor não a aceitar.
    """
    requisicao = urllib.request.Request(
        endereco + "?detalhe=escolas",
        headers={"User-Agent": "contar-usuarios", "x-painel-token": senha},
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        if erro.code == 401:
            raise PainelFechado(
                "O servidor não aceitou a senha do painel. Confira o arquivo "
                f"{ARQUIVO_SENHA} (ou a variável {VARIAVEL_SENHA})."
            ) from None
        if erro.code == 503:
            raise PainelFechado(
                "O painel ainda não está configurado no servidor (falta a variável PAINEL_TOKEN na Vercel)."
            ) from None
        raise


def _linha_da_escola(escola: dict, largura: int) -> str:
    nome = str(escola.get("escola", ""))
    pontos = "." * max(2, largura - len(nome))
    return f"  {nome} {pontos} {escola.get('computadores', 0):>3}   {escola.get('ultimo_uso', '')}"


def montar_texto(totais: dict, escolas: dict | None = None, oficiais=(), aviso_do_painel: str = "") -> str:
    linhas = [
        "Computadores que usaram o programa",
        "----------------------------------",
        f"  hoje .................. {totais.get('hoje', 0)}",
        f"  ontem ................. {totais.get('ontem', 0)}",
        f"  últimos 7 dias ........ {totais.get('ultimos_7_dias', 0)}",
        f"  últimos 30 dias ....... {totais.get('ultimos_30_dias', 0)}",
        f"  desde o início ........ {totais.get('desde_o_inicio', 0)}",
        "",
        "Por versão (últimos 30 dias):",
    ]
    por_versao = totais.get("por_versao") or {}
    linhas += [f"  {versao:<10} {quantos}" for versao, quantos in por_versao.items()] or ["  (ainda ninguém)"]

    if "escolas_diferentes" in totais:  # números públicos; os nomes só vêm com a senha do painel
        linhas += [
            "",
            "Escolas que usam o programa",
            "---------------------------",
            f"  já apareceram ......... {totais.get('escolas_diferentes', 0)}",
            f"  últimos 30 dias ....... {totais.get('escolas_ultimos_30_dias', 0)}",
        ]
    if escolas and escolas.get("escolas") is not None:
        lista = escolas["escolas"]
        largura = max([len(str(e.get("escola", ""))) for e in lista] + [20]) + 3
        linhas += ["", "Quais escolas (nome, computadores, último uso)", "----------------------------------------------"]
        linhas += [_linha_da_escola(e, largura) for e in lista] or ["  (ainda nenhuma)"]
        vistas = {e.get("escola") for e in lista}
        faltando = [nome for nome in oficiais if nome not in vistas]
        if oficiais:
            linhas += ["", f"Ainda não apareceram ({len(faltando)} de {len(oficiais)}):"]
            linhas += (
                textwrap.fill(", ".join(faltando), width=88, initial_indent="  ", subsequent_indent="  ").splitlines()
                or ["  (todas já apareceram)"]
            )
    elif aviso_do_painel:
        linhas += ["", aviso_do_painel]

    linhas += [
        "",
        "São COMPUTADORES (instalações), não são pessoas exatas: dois professores no mesmo",
        "computador contam uma vez. Só entram os que já atualizaram para a 2.1.0 ou mais nova;",
        "a escola só aparece para quem já atualizou para a 2.3.0 ou mais nova.",
    ]
    if totais.get("atualizado_em"):
        linhas.append(f"Atualizado em {totais['atualizado_em']} (horário de Brasília).")
    return "\n".join(linhas)


def main() -> None:
    endereco = sys.argv[1] if len(sys.argv) > 1 else ENDERECO
    totais = buscar(endereco)
    escolas, aviso = None, ""
    senha = senha_do_painel()
    if senha:
        try:
            escolas = buscar_escolas(endereco, senha)
        except PainelFechado as erro:
            aviso = str(erro)
        except Exception as erro:  # noqa: BLE001 - os números já saíram bem; só a lista falhou
            # só o tipo do erro: nada que possa trazer a senha para a tela
            aviso = f"Não consegui abrir a lista de escolas ({type(erro).__name__})."
    else:
        aviso = (
            "Para ver QUAIS escolas usam, falta a senha do painel: guarde-a no arquivo "
            f"{pasta_da_senha() / ARQUIVO_SENHA} (ou na variável {VARIAVEL_SENHA})."
        )
    print(montar_texto(totais, escolas, ESCOLAS_CRE_BLUMENAU, aviso))


if __name__ == "__main__":
    main()
