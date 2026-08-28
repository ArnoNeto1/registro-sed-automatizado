# -*- coding: utf-8 -*-
"""
Porta de entrada do programa — e rede de segurança contra a falha pior de
todas: a que não aparece.

Como .exe, o programa roda sem janela de terminal atrás. Se algo estourar
ANTES da tela existir (uma peça que não foi junto no executável, um
arquivo corrompido no meio do download), o Windows simplesmente não faz
nada: o professor dá dois cliques, espera, e não acontece coisa alguma.
Não há mensagem, não há onde olhar, e quem recebe o relato do outro lado
— eu ou você — não tem nenhuma pista para trabalhar.

Por isso este arquivo existe e é ele que o executável chama primeiro. Ele
envolve TUDO, inclusive a importação dos outros módulos (que é justamente
onde essas falhas acontecem), e transforma qualquer estouro em duas
coisas concretas:

    1. um arquivo erro.txt na pasta de dados do professor, com o relato
       técnico (mesma pasta do .env — ver `_pasta_de_dados` abaixo);
    2. uma caixinha do Windows dizendo que o arquivo existe e onde está.

Ele não depende de nada do programa: só da biblioteca padrão do Python e
de uma caixa de mensagem nativa do Windows. Uma rede de segurança que
precisasse do resto funcionando não seria rede de segurança nenhuma.
"""

import datetime
import os
import sys
import time
import traceback

TITULO = "Registro SED — não consegui abrir"


def _pasta_do_programa() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _pasta_de_dados() -> str:
    """
    Onde ficam os dados do professor (.env, histórico, erro.txt) desde a
    versão 1.5 — ver `caminhos.pasta_de_dados()` para a explicação
    completa (por que é %ProgramData%, compartilhado pela máquina, e não
    %LOCALAPPDATA%, que seria por usuário do Windows — o histórico
    precisa ser visto por todo mundo que usa o mesmo laboratório).

    Repetido aqui, em vez de importado de `caminhos`, de propósito: este
    arquivo é a rede de segurança contra falha na importação dos outros
    módulos do programa — inclusive `caminhos.py`. Se ele dependesse de
    algo que pode falhar, não seria rede de segurança nenhuma.
    """
    pasta_programa = _pasta_do_programa()
    if not getattr(sys, "frozen", False):
        return pasta_programa
    candidatos = (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramW6432"),
    )
    dentro_de_arquivos_de_programas = any(
        c and pasta_programa.casefold().startswith(c.casefold()) for c in candidatos if c
    )
    if not dentro_de_arquivos_de_programas:
        return pasta_programa
    base = os.environ.get("ProgramData") or os.environ.get("ALLUSERSPROFILE") or r"C:\ProgramData"
    pasta = os.path.join(base, "RegistroSED")
    try:
        os.makedirs(pasta, exist_ok=True)
    except OSError:
        return pasta_programa
    return pasta


def _guardar(detalhe: str) -> str:
    """Escreve o relato no erro.txt e devolve o caminho do arquivo."""
    arquivo = os.path.join(_pasta_de_dados(), "erro.txt")
    try:
        with open(arquivo, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 70 + "\n")
            f.write(datetime.datetime.now().strftime("%d/%m/%Y às %H:%M:%S") + "\n")
            try:
                with open(
                    os.path.join(_pasta_do_programa(), "VERSAO.txt"), encoding="utf-8"
                ) as v:
                    f.write("Versão " + v.read().strip() + "\n")
            except Exception:
                pass
            f.write("\n" + detalhe)
    except Exception:
        pass
    return arquivo


def _avisar(texto: str) -> None:
    """Caixa de mensagem do próprio Windows — não depende do Tkinter."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, texto, TITULO, 0x10)
    except Exception:
        print(texto)


def _env_utilizavel() -> bool:
    """
    O .env do formato antigo está preenchido a ponto de servir?

    Confere a pasta de dados nova primeiro (caso comum, já migrado) e cai
    para a pasta do programa como está aqui só para quem está abrindo,
    pela primeira vez, uma versão nova em cima de uma instalação antiga —
    a migração de verdade (mover o arquivo) acontece depois, dentro de
    `app.py`; aqui só se PERGUNTA se dá para pular a tela de cadastro.
    """
    for pasta in (_pasta_de_dados(), _pasta_do_programa()):
        caminho_env = os.path.join(pasta, ".env")
        try:
            with open(caminho_env, encoding="utf-8") as f:
                linhas = [l.strip() for l in f if not l.strip().startswith("#")]
        except OSError:
            continue
        valores = {}
        for linha in linhas:
            if "=" in linha:
                chave, _, valor = linha.partition("=")
                valores[chave.strip()] = valor.strip()
        if valores.get("ORIENTADOR_NOME") and valores.get("ESCOLA"):
            return True
    return False


def _garantir_configuracao() -> bool:
    """
    Primeira execução: abre o cadastro ANTES de carregar o resto.

    A ordem é o ponto: escola, nome e regional são lidos uma única vez, no
    instante em que o programa carrega. Cadastrar depois disso deixaria a
    tela certa e o registro errado.

    Devolve False se a pessoa fechou o cadastro sem preencher.
    """
    try:
        import configuracao
    except BaseException:
        return True          # sem a tela de cadastro, segue o fluxo antigo
    if configuracao.esta_configurado() or _env_utilizavel():
        return True
    return configuracao.pedir_configuracao_inicial() is not None


def _falha_passageira_no_tcl(exc: BaseException) -> bool:
    """
    "Can't find a usable init.tcl" logo na abertura — visto ao vivo bem
    depois de sair da versão 1.5.1, sempre num processo RECÉM aberto
    sozinho (depois de cadastrar/editar um professor, ou depois de uma
    atualização automática).

    A causa mais provável é a mesma já documentada em `atualizador.
    reiniciar()` para o navegador: alguma coisa (antivírus examinando o
    .exe recém-criado, por exemplo) segura por um instante os arquivos
    que o PyInstaller acabou de extrair para a pasta temporária — e
    tentar criar a janela bem nesse instante encontra a extração pela
    metade. Passageiro: tentar de novo alguns segundos depois resolve
    sozinho.
    """
    return "init.tcl" in str(exc)


def main() -> None:
    app = None
    # 6 tentativas, esperando mais a cada uma (3s, 6s, 9s...): visto ao
    # vivo que 3 tentativas de 2s (6s no total) não bastavam sempre —
    # ainda apareceu depois de esgotar as 3. Isso é espera parada, sem
    # nada na tela ainda (a janela nem existe até dar certo), então
    # alguns segundos a mais não incomodam ninguém — o que incomoda é
    # desistir cedo demais e mostrar erro de algo que ia se resolver
    # sozinho.
    tentativas = 6
    for tentativa in range(1, tentativas + 1):
        try:
            if not _garantir_configuracao():
                return
            import app as modulo

            app = modulo
            app.main()
            return
        except SystemExit:
            raise            # reabrir o programa não é erro
        except BaseException as exc:
            if tentativa < tentativas and _falha_passageira_no_tcl(exc):
                time.sleep(3 * tentativa)
                continue
            arquivo = _guardar(traceback.format_exc())
            # o próprio programa já avisa dos erros que ele consegue tratar;
            # avisar de novo só deixaria duas caixinhas na tela dizendo o mesmo
            if not getattr(app, "ERRO_JA_MOSTRADO", False):
                _avisar(
                    "O programa não conseguiu abrir.\n\n"
                    "Guardei o motivo neste arquivo:\n"
                    f"{arquivo}\n\n"
                    "Mande esse arquivo para quem cuida do programa."
                )
            raise


if __name__ == "__main__":
    main()
