# -*- coding: utf-8 -*-
"""
Atualização automática do programa.

COMO FUNCIONA
-------------
Ao abrir, o programa consulta um endereço na internet que contém um
arquivo `versao.json` descrevendo a versão mais recente. Se houver uma
versão mais nova que a instalada, ele avisa e — só depois de você
concordar — baixa o pacote e substitui os arquivos do programa.

O ENDEREÇO É CONFIGURÁVEL de propósito (URL_ATUALIZACAO no .env). Hoje
pode apontar para o GitHub; se um dia o NTE/SED hospedar os arquivos no
servidor deles, muda-se uma linha do .env e pronto — o mecanismo é o
mesmo, não precisa reescrever nada nem reinstalar em cada escola.

O QUE NUNCA É TOCADO
--------------------
Arquivos pessoais e de histórico ficam de fora da atualização, sempre:

    .env                       (CPF e senha de cada professor)
    browser_profile/           (login do Google da escola)
    registros_enviados.json    (o que já foi enviado à SED)
    aulas_nao_realizadas.json  (aulas marcadas como não realizadas)
    ultimo_professor.txt       (quem usou por último)

Isso não é detalhe: uma atualização que apagasse o .env faria todo mundo
reconfigurar tudo, e uma que apagasse o histórico faria o programa
oferecer de novo aulas já registradas — ou seja, risco de duplicar
registro na SED.

Antes de substituir qualquer coisa, é feita uma cópia de segurança em
`backup_versao_anterior/`, para dar pra voltar atrás.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from caminhos import empacotado, pasta_do_programa, recurso

PASTA = str(pasta_do_programa())
ARQUIVO_VERSAO = os.path.join(PASTA, "VERSAO.txt")
PASTA_BACKUP = os.path.join(PASTA, "backup_versao_anterior")

# Só arquivos com estas extensões são substituídos. Note que .json está
# fora da lista de propósito: todo arquivo de estado do programa é .json,
# e nenhum deles pode ser sobrescrito por uma atualização.
EXTENSOES_ATUALIZAVEIS = {".py", ".bat", ".txt", ".md", ".pdf", ".example"}

# Nunca substituídos, mesmo que venham no pacote e tenham extensão da
# lista acima.
NUNCA_TOCAR = {
    ".env",
    "VERSAO.txt",
    "ultimo_professor.txt",
}

TEMPO_LIMITE = 20  # segundos


def versao_atual() -> str:
    """
    A versão que está rodando agora.

    Como .exe, a versão vem de DENTRO do executável: ela é uma
    característica dele, não da pasta. Assim, um professor que baixou só
    o .exe e o largou numa pasta vazia não é tratado como se estivesse na
    versão 0.0.0 — o que faria o programa oferecer atualização toda vez,
    para sempre.
    """
    try:
        with open(recurso("VERSAO.txt"), "r", encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def _como_numero(versao: str) -> tuple:
    """
    Transforma "1.10.2" em (1, 10, 2) para comparar de verdade.

    Comparar como texto daria errado: "1.10" < "1.9" alfabeticamente, e o
    programa deixaria de oferecer uma atualização mais nova.
    """
    partes = []
    for pedaco in str(versao).strip().split("."):
        digitos = "".join(c for c in pedaco if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    while len(partes) < 3:
        partes.append(0)
    return tuple(partes[:3])


def ha_versao_mais_nova(instalada: str, publicada: str) -> bool:
    return _como_numero(publicada) > _como_numero(instalada)


def consultar(url_base: str) -> dict | None:
    """
    Pergunta ao servidor qual é a versão publicada.

    Devolve um dicionário com os dados da versão nova, ou None quando já
    está atualizado. Qualquer problema de rede levanta exceção para quem
    chamou decidir — mas o programa trata isso como "hoje não deu", nunca
    como erro que atrapalhe o uso.
    """
    if not url_base:
        return None
    url = url_base.rstrip("/") + "/versao.json"
    requisicao = urllib.request.Request(
        url, headers={"User-Agent": "RegistroSED-atualizador"}
    )
    with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
        dados = json.loads(resposta.read().decode("utf-8"))

    publicada = str(dados.get("versao", "")).strip()
    if not publicada or not ha_versao_mais_nova(versao_atual(), publicada):
        return None
    return {
        "versao": publicada,
        "zip": dados.get("zip", ""),
        "exe": dados.get("exe", ""),
        # Impressão digital (SHA-256) do .exe publicado — escrita pelo
        # GitHub Actions no versao.json (ver montar-programa.yml) e
        # conferida em _aplicar_exe antes de trocar o programa. Um
        # versao.json de antes disso não tem essa linha: fica "" e a
        # conferência cai só no tamanho anunciado pelo servidor.
        "sha256": str(dados.get("sha256", "")).strip().lower(),
        "notas": str(dados.get("notas", "")).strip(),
    }


def _baixar(url: str, destino: Path, tempo_limite: int) -> tuple:
    """
    Baixa `url` para o arquivo `destino` e devolve (bytes_recebidos,
    sha256_em_hexadecimal).

    CONFERE SE O ARQUIVO VEIO INTEIRO — e isso não é zelo à toa. Quando a
    conexão fecha no meio de um download (internet de escola oscilando,
    proxy, antivírus cortando a transferência), o urllib do Python NÃO
    avisa: a leitura simplesmente termina, como se o arquivo tivesse
    acabado ali (comportamento antigo do http.client, mantido de
    propósito por compatibilidade). Sem esta conferência, um .exe cortado
    pela metade passava por todas as outras checagens de _aplicar_exe —
    ele começa com "MZ" e tem bem mais de 2 MB — e tomava o lugar do
    programa, que aí não abria mais. E nem o erro.txt aparecia: com o
    executável cortado, o Python nem chega a nascer para gravá-lo.

    O servidor anuncia o tamanho do arquivo antes de mandar
    (Content-Length); se chegou menos (ou mais) que isso, é erro — e
    quem chama nunca troca nada.
    """
    requisicao = urllib.request.Request(
        url, headers={"User-Agent": "RegistroSED-atualizador"}
    )
    impressao = hashlib.sha256()
    recebidos = 0
    with urllib.request.urlopen(requisicao, timeout=tempo_limite) as resposta:
        anunciado = (resposta.headers.get("Content-Length") or "").strip()
        with open(destino, "wb") as f:
            while True:
                bloco = resposta.read(1024 * 1024)
                if not bloco:
                    break
                f.write(bloco)
                impressao.update(bloco)
                recebidos += len(bloco)
    if anunciado.isdigit() and int(anunciado) != recebidos:
        mb = 1024 * 1024
        raise RuntimeError(
            "O download da versão nova veio incompleto "
            f"({recebidos / mb:.1f} de {int(anunciado) / mb:.1f} MB) — "
            "provavelmente a internet oscilou no meio. Nada foi alterado; "
            "tente de novo mais tarde."
        )
    return recebidos, impressao.hexdigest()


def _aplicar_exe(info: dict) -> list:
    """
    Troca o próprio executável pela versão nova.

    O Windows não deixa sobrescrever um programa que está aberto — e o
    programa está aberto, é ele que está fazendo isto. Mas o Windows
    DEIXA renomear. Então: o executável em uso vira ".antigo.exe", o novo
    ocupa o nome de sempre (o atalho do professor continua valendo) e a
    sobra é apagada na próxima abertura, quando ninguém mais a estiver
    usando.

    A ordem importa: o novo só é baixado e conferido ANTES de mexer no
    que já funciona. Se o download vier pela metade (ver `_baixar`), vier
    uma página de erro no lugar do programa ou não bater com a impressão
    digital publicada no versao.json, nada é trocado.
    """
    url_exe = info.get("exe")
    if not url_exe:
        raise RuntimeError(
            "A versão publicada não trouxe o programa novo (.exe). "
            "Nada foi alterado."
        )

    atual = Path(sys.executable).resolve()
    novo = atual.with_name(atual.stem + ".novo.exe")
    antigo = atual.with_name(atual.stem + ".antigo.exe")

    # O download fica DENTRO do try: se ele falhar no meio (internet caiu,
    # download incompleto), o finally lá embaixo apaga o .novo.exe pela
    # metade em vez de deixá-lo esquecido na pasta do programa.
    try:
        tamanho, impressao = _baixar(url_exe, novo, TEMPO_LIMITE * 6)
        with open(novo, "rb") as f:
            assinatura = f.read(2)
        # "MZ" é a assinatura de todo executável do Windows. Uma página de
        # erro do GitHub salva como .exe não tem isso — e tem uns poucos KB.
        if assinatura != b"MZ" or tamanho < 2_000_000:
            raise RuntimeError(
                "O arquivo baixado não é o programa (veio com "
                f"{tamanho // 1024} KB). Nada foi alterado."
            )
        esperada = (info.get("sha256") or "").strip().lower()
        if esperada and impressao != esperada:
            raise RuntimeError(
                "O arquivo baixado não confere com a versão publicada (a "
                "impressão digital SHA-256 é diferente) — pode ter vindo "
                "corrompido no caminho. Nada foi alterado; tente de novo "
                "mais tarde."
            )

        if antigo.exists():
            try:
                os.remove(antigo)
            except OSError:
                pass
        os.replace(atual, antigo)
        try:
            os.replace(novo, atual)
        except Exception:
            os.replace(antigo, atual)  # desfaz: melhor a versão velha que nenhuma
            raise

        with open(ARQUIVO_VERSAO, "w", encoding="utf-8") as f:
            f.write(info["versao"])
        return [atual.name]
    finally:
        if novo.exists():
            try:
                os.remove(novo)
            except OSError:
                pass


def _arquivos_do_pacote(caminho_zip: str) -> dict:
    """
    Mapeia nome-do-arquivo -> caminho dentro do zip.

    O zip do GitHub embrulha tudo numa pasta ("repo-main/"), por isso
    trabalhamos pelo NOME do arquivo e ignoramos a estrutura de pastas.
    """
    encontrados = {}
    with zipfile.ZipFile(caminho_zip) as pacote:
        for item in pacote.namelist():
            if item.endswith("/"):
                continue
            nome = os.path.basename(item)
            if not nome or nome in NUNCA_TOCAR:
                continue
            if os.path.splitext(nome)[1].lower() not in EXTENSOES_ATUALIZAVEIS:
                continue
            encontrados[nome] = item
    return encontrados


def aplicar(info: dict) -> list:
    """
    Baixa o pacote da versão nova e substitui os arquivos do programa.

    Devolve a lista de arquivos atualizados. Levanta exceção se o pacote
    vier vazio ou sem os arquivos principais — melhor não atualizar do
    que deixar a instalação pela metade.
    """
    # Como .exe, o programa é UM arquivo só: trocar os .py não mudaria
    # nada, porque o código roda de dentro do executável.
    if empacotado():
        return _aplicar_exe(info)

    url_zip = info.get("zip")
    if not url_zip:
        raise RuntimeError("A versão publicada não informou o endereço do pacote.")

    destino_zip = os.path.join(PASTA, "_atualizacao.zip")
    try:
        _baixar(url_zip, Path(destino_zip), TEMPO_LIMITE * 3)
        arquivos = _arquivos_do_pacote(destino_zip)

        # Conferência de sanidade: sem estes, não é um pacote do programa.
        # Sem isso, um endereço errado (ou uma página de erro salva como
        # zip) poderia "atualizar" a pasta para o nada.
        essenciais = {"app.py", "config.py", "sed_form_filler.py", "agenda_scraper.py"}
        if not essenciais.issubset(arquivos.keys()):
            faltando = sorted(essenciais - set(arquivos.keys()))
            raise RuntimeError(
                "O pacote baixado não parece ser do programa (falta: "
                + ", ".join(faltando)
                + "). Nada foi alterado."
            )

        # Lê TUDO antes de trocar QUALQUER arquivo: o zipfile só confere
        # a integridade (CRC) de cada arquivo quando termina de lê-lo.
        # Trocando um por um, um arquivo corrompido no meio do pacote só
        # seria descoberto com metade da pasta já trocada — o programa
        # ficaria com arquivos de duas versões misturados.
        conteudos = {}
        with zipfile.ZipFile(destino_zip) as pacote:
            for nome, dentro_do_zip in arquivos.items():
                with pacote.open(dentro_do_zip) as origem:
                    conteudos[nome] = origem.read()

        os.makedirs(PASTA_BACKUP, exist_ok=True)
        atualizados = []
        for nome, conteudo in conteudos.items():
            atual = os.path.join(PASTA, nome)
            if os.path.exists(atual):
                shutil.copy2(atual, os.path.join(PASTA_BACKUP, nome))
            with open(atual, "wb") as saida:
                saida.write(conteudo)
            atualizados.append(nome)

        with open(ARQUIVO_VERSAO, "w", encoding="utf-8") as f:
            f.write(info["versao"])
        return sorted(atualizados)
    finally:
        try:
            os.remove(destino_zip)
        except Exception:
            pass
