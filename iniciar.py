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

    1. um arquivo erro.txt ao lado do programa, com o relato técnico;
    2. uma caixinha do Windows dizendo que o arquivo existe e onde está.

Ele não depende de nada do programa: só da biblioteca padrão do Python e
de uma caixa de mensagem nativa do Windows. Uma rede de segurança que
precisasse do resto funcionando não seria rede de segurança nenhuma.
"""

import datetime
import os
import sys
import traceback

TITULO = "Registro SED — não consegui abrir"


def _pasta_do_programa() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _guardar(detalhe: str) -> str:
    """Escreve o relato no erro.txt e devolve o caminho do arquivo."""
    arquivo = os.path.join(_pasta_do_programa(), "erro.txt")
    try:
        with open(arquivo, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 70 + "\n")
            f.write(datetime.datetime.now().strftime("%d/%m/%Y às %H:%M:%S") + "\n")
            try:
                with open(
                    os.path.join(_pasta_do_programa(), "VERSAO.txt"), encoding="utf-8"
                ) as v:
                    f.write("versão " + v.read().strip() + "\n")
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
    """O .env do formato antigo está preenchido a ponto de servir?"""
    caminho_env = os.path.join(_pasta_do_programa(), ".env")
    try:
        with open(caminho_env, encoding="utf-8") as f:
            linhas = [l.strip() for l in f if not l.strip().startswith("#")]
    except Exception:
        return False
    valores = {}
    for linha in linhas:
        if "=" in linha:
            chave, _, valor = linha.partition("=")
            valores[chave.strip()] = valor.strip()
    return bool(valores.get("ORIENTADOR_NOME") and valores.get("ESCOLA"))


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


def main() -> None:
    app = None
    try:
        if not _garantir_configuracao():
            return
        import app as modulo

        app = modulo
        app.main()
    except SystemExit:
        raise                # reabrir o programa não é erro
    except BaseException:
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
