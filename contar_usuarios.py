# -*- coding: utf-8 -*-
"""
Quantos computadores usam o programa — lido do endereço de totais do
servidor da escola (servidor-ia/api/uso.py). Só números: ninguém é
identificado.

    python contar_usuarios.py              # endereço de sempre
    python contar_usuarios.py <endereço>   # outro endereço (para testes)

Cada número é de COMPUTADORES (instalações do programa que mandaram o aviso
do dia), não de pessoas: dois professores no mesmo computador contam uma
vez, e quem reinstala ou apaga a pasta de dados conta de novo. Os computadores
do mantenedor ficam de fora (arquivo modo_teste.txt). A contagem só vale para
quem já atualizou para a versão 2.1.0 ou mais nova.
"""

from __future__ import annotations

import json
import sys
import urllib.request

ENDERECO = "https://registro-sed-ia-plexe1.vercel.app/api/uso"


def buscar(endereco: str = ENDERECO) -> dict:
    requisicao = urllib.request.Request(endereco, headers={"User-Agent": "contar-usuarios"})
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def montar_texto(totais: dict) -> str:
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
    linhas += [
        "",
        "São COMPUTADORES (instalações), não são pessoas exatas: dois professores no mesmo",
        "computador contam uma vez. Só entram os que já atualizaram para a 2.1.0 ou mais nova.",
    ]
    if totais.get("atualizado_em"):
        linhas.append(f"Atualizado em {totais['atualizado_em']} (horário de Brasília).")
    return "\n".join(linhas)


def main() -> None:
    endereco = sys.argv[1] if len(sys.argv) > 1 else ENDERECO
    print(montar_texto(buscar(endereco)))


if __name__ == "__main__":
    main()
