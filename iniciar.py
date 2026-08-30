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


def _declarar_dpi_awareness() -> None:
    """
    Avisa o Windows que o programa sabe lidar com escala de tela (125%,
    150%...) por conta própria — sem isto, o Windows finge que a tela é
    100% e depois ESTICA o desenho inteiro do programa como se fosse uma
    imagem, pixel a pixel. A maioria das telas fica só um pouco borrada,
    mas alguns detalhes do Tk saem visivelmente errados nesse esticar —
    é assim que a barra de rolagem da lista de aulas sumia sozinha até a
    pessoa arrastar a borda de uma coluna, o que força o Windows a
    redesenhar aquele pedaço direito na hora (visto ao vivo, com print de
    tela, numa tela em 125%).

    Precisa ser chamado ANTES de qualquer janela existir — inclusive a de
    configuração/cadastro, que pode abrir logo abaixo, em
    `_garantir_configuracao()`. Por isso fica aqui, não em `app.py` (que
    só é importado bem depois).
    """
    try:
        import ctypes

        # PROCESS_SYSTEM_DPI_AWARE — o suficiente pra corrigir o
        # esticamento; não tenta acompanhar o monitor se a janela for
        # arrastada para outro com escala diferente (PER_MONITOR_AWARE),
        # o que o Tk não lida bem sozinho de qualquer forma.
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass  # Windows mais antigo sem esta API, ou algo bloqueou —
            # o programa continua funcionando, só sem a correção


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


# Quantas vezes o programa se reabre sozinho (como processo NOVO) antes de
# desistir e mostrar o erro de verdade — ver _relancar_processo_novo_se_possivel.
_LIMITE_RELANCAMENTOS = 3
_ARQUIVO_MARCADOR_RELANCAMENTO = "_tentativas_reabrir.txt"


def _tentativas_de_relancamento_ja_feitas() -> int:
    """
    Quantas vezes ESTE MESMO problema já fez o programa se reabrir
    sozinho, guardado num arquivo de texto pequeno na pasta de dados
    (mesmo esquema do marcador de reinício pós-atualização, em
    atualizador.py — repetido aqui, não importado, porque este arquivo
    não pode depender de mais nada do programa).

    Um marcador com mais de 2 minutos não conta — é de um problema
    ANTIGO, já resolvido (a pessoa fechou e abriu na mão, por exemplo),
    não desta sequência de tentativas.
    """
    caminho = os.path.join(_pasta_de_dados(), _ARQUIVO_MARCADOR_RELANCAMENTO)
    try:
        with open(caminho, encoding="utf-8") as f:
            quando_texto, numero_texto = f.read().strip().split("|")
        if time.time() - float(quando_texto) > 120:
            return 0
        return int(numero_texto)
    except Exception:
        return 0


def _registrar_tentativa_de_relancamento(numero: int) -> None:
    caminho = os.path.join(_pasta_de_dados(), _ARQUIVO_MARCADOR_RELANCAMENTO)
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(f"{time.time()}|{numero}")
    except Exception:
        pass  # sem o marcador, só perde a contagem — não impede reabrir


def _limpar_marcador_de_relancamento() -> None:
    try:
        os.remove(os.path.join(_pasta_de_dados(), _ARQUIVO_MARCADOR_RELANCAMENTO))
    except OSError:
        pass


def _relancar_processo_novo_se_possivel() -> bool:
    """
    Quando o "init.tcl" resiste às 6 tentativas dentro do MESMO processo
    (ver main()), o motivo mais provável é que a extração do .exe onefile
    — feita pelo Windows/PyInstaller UMA VEZ SÓ, antes até deste arquivo
    começar a rodar — saiu incompleta por inteiro. Tentar de nova AQUI
    DENTRO não adianta nada: é a mesma pasta quebrada de novo, porque a
    extração não se repete dentro do mesmo processo. Só abrir um processo
    NOVO (que ganha uma pasta de extração NOVA) resolve de verdade — foi
    exatamente isso que sempre "consertava" quando a pessoa fechava o
    erro e abria o programa na mão de novo.

    Limitado a poucas vezes (_LIMITE_RELANCAMENTOS) pra não virar um
    abre-fecha infinito se o problema for outro, persistente de verdade
    (disco cheio, antivírus bloqueando pra sempre, instalação
    corrompida) — nesses casos é melhor mostrar o erro logo.

    Devolve True se relançou (quem chamou deve sair sem mostrar nada);
    False se já tentou demais e é hora de mostrar o erro de verdade.
    """
    if not getattr(sys, "frozen", False):
        return False  # rodando do código-fonte: não tem .exe pra reabrir
    ja_tentado = _tentativas_de_relancamento_ja_feitas()
    if ja_tentado >= _LIMITE_RELANCAMENTOS:
        return False
    _registrar_tentativa_de_relancamento(ja_tentado + 1)
    try:
        os.startfile(sys.executable, cwd=_pasta_do_programa())
    except Exception:
        return False
    return True


def main() -> None:
    _declarar_dpi_awareness()
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
            _limpar_marcador_de_relancamento()  # deu certo — zera a contagem
            return
        except SystemExit:
            raise            # reabrir o programa não é erro
        except BaseException as exc:
            if tentativa < tentativas and _falha_passageira_no_tcl(exc):
                time.sleep(3 * tentativa)
                continue
            # As 6 tentativas ACIMA rodam dentro do MESMO processo — inúteis
            # contra uma extração do .exe onefile que nasceu incompleta
            # (isso só acontece uma vez, antes deste arquivo sequer
            # começar a rodar). Só um processo novo tem uma extração nova
            # — ver _relancar_processo_novo_se_possivel.
            if _falha_passageira_no_tcl(exc) and _relancar_processo_novo_se_possivel():
                return
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
