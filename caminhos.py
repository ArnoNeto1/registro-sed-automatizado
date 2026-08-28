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
import shutil
import sys
import time
from pathlib import Path

# Nome da pasta usada dentro de %ProgramData% para os dados do professor,
# quando instalado dentro de "Arquivos de Programas" (ver `pasta_de_dados()`
# abaixo).
NOME_PASTA_DE_DADOS = "RegistroSED"

# Os dados que, num .exe instalado, moraram do lado do executável até a
# versão 1.4.3 — e que agora precisam ser encontrados (e migrados, na
# primeira vez) na pasta nova. Ver `pasta_de_dados()` e
# `migrar_dados_antigos()` logo abaixo.
_ARQUIVOS_DE_DADOS = (
    ".env",
    "browser_profile",
    "registros_enviados.json",
    "aulas_nao_realizadas.json",
    "ultimo_professor.txt",
    "configuracao.json",
    "erro.txt",
)

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


def _dentro_de_arquivos_de_programas() -> bool:
    """
    O executável está instalado em "Arquivos de Programas"?

    Por caminho, não por marcador de instalação: assim continua correto
    mesmo depois de uma autoatualização (que só troca o .exe, sem tocar
    em mais nada — ver atualizador.py) — não há como esquecer de
    "reinstalar" nada.
    """
    pasta = str(pasta_do_programa()).casefold()
    candidatos = (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramW6432"),
    )
    return any(c and pasta.startswith(c.casefold()) for c in candidatos if c)


def caminho(*partes: str) -> str:
    """Caminho de um arquivo do programa, seja .py ou .exe."""
    return str(pasta_do_programa().joinpath(*partes))


def pasta_de_dados() -> Path:
    """
    Onde ficam os dados do professor: .env, login salvo do navegador
    (browser_profile/), histórico de envios e configuração feita pela
    tela (que pode ter mais de um professor cadastrado — ver "DOIS
    PROFESSORES NO MESMO COMPUTADOR" no COMECE AQUI.txt).

    ESSES DADOS SÃO DO COMPUTADOR, NÃO DA PESSOA — de propósito: dois
    professores que dividem o mesmo laboratório precisam ver a mesma
    agenda, o mesmo histórico de envios (senão um reenviaria o que o
    outro já registrou) e usar o mesmo login salvo do navegador. Por
    isso a pasta de dados NUNCA é "por usuário do Windows"
    (%LOCALAPPDATA% seria isso, e foi cogitado e descartado por causa
    disso) — é sempre uma só por instalação.

    Rodando pelos .py, ou como .exe PORTÁTIL (baixado avulso e colocado
    numa pasta própria — a forma como o programa é distribuído e
    documentado desde sempre, ver COMECE AQUI.txt), os dados continuam
    ao lado do executável, exatamente como sempre foi: essa pasta já é
    gravável por quem a criou, e é a própria pasta que identifica "esta
    instalação" pra quem a está usando.

    Só o .exe rodando de dentro de "Arquivos de Programas" usa em vez
    disso %ProgramData%\\RegistroSED — pasta compartilhada por TODOS os
    usuários do Windows na máquina (ao contrário de %LOCALAPPDATA%, que
    é por usuário), gravável por qualquer um. Resolve o problema de
    escrita em "Arquivos de Programas" sem quebrar o compartilhamento
    entre professores nem depender de que todos usem a mesma conta do
    Windows.
    """
    if not empacotado() or not _dentro_de_arquivos_de_programas():
        return pasta_do_programa()
    base = (
        os.environ.get("ProgramData")
        or os.environ.get("ALLUSERSPROFILE")
        or r"C:\ProgramData"
    )
    pasta = Path(base) / NOME_PASTA_DE_DADOS
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except OSError:
        return pasta_do_programa()  # último recurso: como era antes da 1.5
    return pasta


def caminho_de_dados(*partes: str) -> str:
    """Caminho de um arquivo de dados do professor (ver `pasta_de_dados`)."""
    return str(pasta_de_dados().joinpath(*partes))


def migrar_dados_antigos() -> None:
    """
    Move os dados de quem já usava uma versão anterior à 1.5 — que
    gravava tudo do lado do próprio .exe — para a pasta nova.

    Sem isto, quem já tinha o .env preenchido, o login do Google feito e
    o histórico de envios veria tudo "sumir" ao atualizar: o programa
    pediria para configurar tudo de novo, pediria login de novo e, pior,
    sem o histórico, ofereceria de novo aulas já registradas na SED —
    risco de duplicar registro.

    Só copia o que ainda não existe no destino, e só apaga da origem
    depois de confirmar que a cópia terminou — rodar isto de novo (ou
    duas instalações abrindo ao mesmo tempo) não perde nem duplica nada.
    """
    if not empacotado():
        return
    origem = Path(sys.executable).resolve().parent
    destino = pasta_de_dados()
    if origem == destino:
        return
    for nome in _ARQUIVOS_DE_DADOS:
        de, para = origem / nome, destino / nome
        if not de.exists() or para.exists():
            continue
        try:
            shutil.move(str(de), str(para))
        except OSError:
            pass  # sem permissão de apagar a origem, por exemplo — não é fatal


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

    Tenta de novo uma vez, depois de uma pausa curta, se a primeira
    tentativa falhar em TODOS os navegadores. Diferente de
    `abrir_navegador()` (sem perfil salvo), este aqui usa uma pasta que
    outro processo pode ainda estar liberando — logo depois de uma
    autoatualização, por exemplo, ou se um antivírus está examinando o
    `.exe` recém-trocado. Isso é passageiro; desistir na primeira
    tentativa não é.

    Devolve (contexto, nome_do_navegador).
    """
    for tentativa in (1, 2):
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
            except Exception as e:  # navegador não instalado, ou perfil ocupado
                motivos.append(f"{NOME_DO_CANAL[canal]}: {str(e).splitlines()[0][:120]}")
        if tentativa == 1:
            time.sleep(3)
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
