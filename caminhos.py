# -*- coding: utf-8 -*-
"""
Onde ficam os arquivos do programa — e qual navegador usar.

Duas coisas que só viram problema quando o programa deixa de ser uma pasta
com arquivos .py e passa a ser um .exe:

1. DENTRO DE UM .EXE, `__file__` NÃO É A PASTA DO PROGRAMA.
   O PyInstaller descompacta tudo numa pasta temporária do Windows a cada
   execução e apaga no fim. Um programa que procurasse o .env por ali
   nunca acharia a configuração do professor, e guardaria o histórico de
   envios num lugar que some quando ele fecha. Por isso todo caminho do
   programa passa por `caminho()`: como .exe ele aponta para a pasta do
   executável; rodando pelos .py, para a pasta dos arquivos.

2. O NAVEGADOR PRECISA JÁ EXISTIR NA MÁQUINA.
   Antes, a instalação baixava um Chromium só para o programa (uns
   150 MB). Num .exe distribuído para várias escolas, esse download é o
   passo que mais tem chance de falhar — internet de escola, antivírus,
   proxy. Então usamos o Chrome que já está instalado; não havendo, o
   Edge (que vem de fábrica no Windows); e só em último caso o navegador
   próprio, para quem já o tinha baixado.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ordem de preferência. None = o Chromium próprio do Playwright.
CANAIS = ("chrome", "msedge", None)

NOME_DO_CANAL = {
    "chrome": "Google Chrome",
    "msedge": "Microsoft Edge",
    None: "navegador próprio do programa",
}


def empacotado() -> bool:
    """O programa está rodando como .exe?"""
    return bool(getattr(sys, "frozen", False))


def pasta_do_programa() -> Path:
    if empacotado():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def caminho(*partes: str) -> str:
    """Caminho de um arquivo do programa, seja .py ou .exe."""
    return str(pasta_do_programa().joinpath(*partes))


def recurso(nome: str) -> Path:
    """
    Arquivo que veio DENTRO do programa (e não ao lado dele).

    A diferença importa: o VERSAO.txt embutido diz a versão deste
    executável — é um fato sobre o programa. Já o .env é do professor e
    fica ao lado do executável, onde ele pode editar.
    """
    if empacotado():
        base = Path(getattr(sys, "_MEIPASS", pasta_do_programa()))
        embutido = base / nome
        if embutido.exists():
            return embutido
    return pasta_do_programa() / nome


def garantir_env() -> bool:
    """
    Cria o .env do professor na primeira execução, a partir do modelo.

    Quem baixa um .exe baixa um arquivo só — não vem pasta, não vem
    modelo de configuração, não vem nada para editar. Sem isto, o
    programa abriria dizendo "configuração pendente" e a pessoa não teria
    onde preencher. Agora o arquivo aparece ao lado do programa na
    primeira vez que ele roda.

    Só vale para o .exe: quem roda pelos arquivos .py recebeu a pasta
    inteira, com o modelo dentro dela e o instalador para copiar. Criar
    um .env sozinho ali seria mexer numa pasta que não é só do programa.

    Nunca sobrescreve um .env existente. Devolve True se criou agora.
    """
    if not empacotado():
        return False
    destino = pasta_do_programa() / ".env"
    if destino.exists():
        return False
    modelo = recurso(".env.example")
    try:
        if modelo.exists():
            destino.write_text(modelo.read_text(encoding="utf-8"), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def _erro_sem_navegador(motivos: list) -> RuntimeError:
    detalhe = "; ".join(motivos[-2:]) if motivos else ""
    return RuntimeError(
        "Não consegui abrir nenhum navegador nesta máquina. O programa usa o "
        "Google Chrome ou o Microsoft Edge — instale um dos dois e tente de "
        "novo." + (f"\n\n(detalhe técnico: {detalhe})" if detalhe else "")
    )


def abrir_contexto(playwright, pasta_do_perfil: str, **kwargs):
    """
    Abre o navegador VISÍVEL do formulário, com perfil salvo em disco.

    O perfil fica numa pasta do próprio programa, separada do Chrome
    pessoal do professor: nada do que o programa faz aparece no histórico
    dele, e abrir o programa não mexe nas abas que ele já tem abertas.

    Devolve (contexto, nome_do_navegador).
    """
    motivos = []
    for canal in CANAIS:
        try:
            extras = dict(kwargs)
            if canal:
                extras["channel"] = canal
            return (
                playwright.chromium.launch_persistent_context(
                    pasta_do_perfil, **extras
                ),
                NOME_DO_CANAL[canal],
            )
        except Exception as e:  # navegador não instalado nesta máquina
            motivos.append(f"{NOME_DO_CANAL[canal]}: {str(e).splitlines()[0][:120]}")
    raise _erro_sem_navegador(motivos)


def abrir_navegador(playwright, **kwargs):
    """
    Abre um navegador sem perfil salvo — usado para ler a agenda em
    segundo plano. Mesma ordem de preferência.
    """
    motivos = []
    for canal in CANAIS:
        try:
            extras = dict(kwargs)
            if canal:
                extras["channel"] = canal
            return playwright.chromium.launch(**extras)
        except Exception as e:
            motivos.append(f"{NOME_DO_CANAL[canal]}: {str(e).splitlines()[0][:120]}")
    raise _erro_sem_navegador(motivos)


def limpar_sobras() -> None:
    """
    Apaga o .exe antigo deixado para trás por uma atualização.

    O Windows não deixa sobrescrever um programa que está aberto. Então,
    ao atualizar, o executável em uso é renomeado para ".antigo" e o novo
    toma o lugar dele. Na próxima abertura — esta aqui — a sobra some.
    """
    if not empacotado():
        return
    try:
        for arquivo in pasta_do_programa().glob("*.antigo.exe"):
            try:
                os.remove(arquivo)
            except OSError:
                pass  # ainda em uso; some na próxima vez
    except Exception:
        pass
