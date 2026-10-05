# -*- coding: utf-8 -*-
"""
Quantas vezes o programa foi baixado — lido direto do GitHub, sem instalar
nada e sem mexer no programa dos professores:

    python contar_downloads.py

O GitHub conta cada download dos arquivos de uma Release (a contagem é
pública; não precisa de senha nem de login). Como ler cada coluna:

  Instalador  = Registro-SED-Instalador.exe. É por onde uma pessoa NOVA
                costuma começar: é o número mais próximo de "quantas
                pessoas instalaram".
  Portátil    = Registro-SED.exe. Soma quem baixou a versão portátil E
                também cada atualização automática: o programa se atualiza
                baixando justamente este arquivo. Por isso, numa versão
                nova, este número sobe com a quantidade de computadores
                que atualizaram — o que também é uma informação útil.

O que NÃO dá para saber por aqui: "pessoas diferentes". Quem baixa duas
vezes conta duas, e o GitHub não diz quem baixou. Também não aparece quem
recebeu o programa por pen drive ou por e-mail.
"""

from __future__ import annotations

import json
import sys
import urllib.request

REPOSITORIO = "ArnoNeto1/registro-sed-automatizado"
NOME_INSTALADOR = "Registro-SED-Instalador.exe"
NOME_PORTATIL = "Registro-SED.exe"


def baixar_releases(repositorio: str = REPOSITORIO) -> list:
    """Todas as Releases do repositório (a API devolve até 100 por página)."""
    todas: list = []
    pagina = 1
    while True:
        requisicao = urllib.request.Request(
            f"https://api.github.com/repos/{repositorio}/releases?per_page=100&page={pagina}",
            headers={"User-Agent": "contar-downloads", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            lote = json.loads(resposta.read().decode("utf-8"))
        todas.extend(lote)
        if len(lote) < 100:
            return todas
        pagina += 1


def resumir(releases: list) -> list:
    """
    [(versão, instalador, portátil, outros)] na ordem recebida (a mais nova
    primeiro). Rascunhos não contam; arquivo ausente conta zero.
    """
    linhas = []
    for release in releases:
        if release.get("draft"):
            continue
        contagem = {
            asset.get("name"): int(asset.get("download_count") or 0)
            for asset in (release.get("assets") or [])
        }
        outros = sum(
            quantos
            for nome, quantos in contagem.items()
            if nome not in (NOME_INSTALADOR, NOME_PORTATIL)
        )
        linhas.append(
            (
                str(release.get("tag_name") or "?"),
                contagem.get(NOME_INSTALADOR, 0),
                contagem.get(NOME_PORTATIL, 0),
                outros,
            )
        )
    return linhas


def montar_tabela(linhas: list) -> str:
    cabecalho = ("Versão", "Instalador", "Portátil + atualizações", "Outros")
    corpo = [(v, str(i), str(p), str(o)) for v, i, p, o in linhas]
    total = (
        "TOTAL",
        str(sum(i for _, i, _, _ in linhas)),
        str(sum(p for _, _, p, _ in linhas)),
        str(sum(o for _, _, _, o in linhas)),
    )
    todas = [cabecalho] + corpo + [total]
    larguras = [max(len(linha[c]) for linha in todas) for c in range(4)]

    def formatar(linha) -> str:
        return "  ".join(
            texto.ljust(larguras[c]) if c == 0 else texto.rjust(larguras[c])
            for c, texto in enumerate(linha)
        )

    separador = "-" * len(formatar(cabecalho))
    return "\n".join([formatar(cabecalho), separador, *map(formatar, corpo), separador, formatar(total)])


def main() -> None:
    repositorio = sys.argv[1] if len(sys.argv) > 1 else REPOSITORIO
    linhas = resumir(baixar_releases(repositorio))
    if not linhas:
        print("Nenhuma versão publicada ainda.")
        return
    print(f"Downloads de {repositorio}\n")
    print(montar_tabela(linhas))
    print(
        "\nInstalador = novas instalações (o mais próximo de 'quantas pessoas').\n"
        "Portátil + atualizações = quem baixou o portátil e cada atualização automática.\n"
        "Não são pessoas diferentes: quem baixa duas vezes conta duas."
    )


if __name__ == "__main__":
    main()
