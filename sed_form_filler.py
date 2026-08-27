# -*- coding: utf-8 -*-
"""
Preenche o formulário Google "REGISTRO DE ATIVIDADES DOS PROFESSORES
ORIENTADORES DE TECNOLOGIAS EDUCACIONAIS OU MAKER" da SED-SC, página por
página, para uma AtividadeAgrupada vinda do site de agendamento.

Este módulo automatiza apenas o fluxo "Atividade/Aula com estudantes". Os
fluxos "Suporte a outros espaços", "Manutenção de equipamentos" e
"Formação/Reunião" ainda não estão implementados (ver README).

IMPORTANTE: por padrão o script SEMPRE para na última página (antes do botão
"Enviar") e espera confirmação no terminal — ele nunca envia um registro para
a SED sem você revisar e digitar "s". Use --auto-submit por sua conta e risco
se quiser pular essa confirmação.
"""

from __future__ import annotations

import re

from config import (
    ESCOLA,
    ETAPA_AEE,
    ETAPA_EJA,
    ETAPA_PROFISSIONAL,
    chave_comparacao,
    ORIENTADOR_NOME,
    ORIENTADOR_TIPO,
    REGIONAL,
    SED_FORM_URL,
    resolver_componente,
)

TIPO_LABEL = {
    "tecnologias": "Tecnologias Educacionais",
    "maker": "Laboratório Maker",
}


# ---------------------------------------------------------------------------
# Conferência: o que a PÁGINA diz, e não o que o programa quis escrever
# ---------------------------------------------------------------------------
# Com o navegador rodando em segundo plano, ninguém mais vê o formulário
# sendo preenchido. Se o resumo mostrasse só a intenção do programa
# ("vou marcar História"), a pessoa estaria confirmando uma promessa: um
# clique que não pegou passaria batido e o registro sairia errado sem
# ninguém perceber — e clique que não pega já aconteceu aqui mais de uma
# vez.
#
# Por isso cada valor abaixo é LIDO DE VOLTA da página depois de escrito.
# O que aparece no resumo é o estado real do formulário.
_CONFERENCIA: list = []


def iniciar_conferencia() -> None:
    _CONFERENCIA.clear()


def pegar_conferencia() -> list:
    return list(_CONFERENCIA)


def _anotar(campo: str, valor: str) -> None:
    if valor:
        _CONFERENCIA.append((campo, valor))


def _rotulo_atuacao(tipo: str) -> str:
    """
    Traduz o tipo do .env para o texto exato da opção no formulário.

    Aceita tanto a palavra-chave ("tecnologias", "maker") quanto o rótulo
    escrito por extenso, com ou sem acento: quem preenche o .env escreve
    o que lhe parece natural, e um KeyError seco não ajudaria ninguém a
    entender que o problema está numa linha do arquivo de configuração.
    """
    bruto = (tipo or ORIENTADOR_TIPO or "tecnologias").strip()
    chave = chave_comparacao(bruto)
    if chave in TIPO_LABEL:
        return TIPO_LABEL[chave]
    for palavra, rotulo in TIPO_LABEL.items():
        if chave == chave_comparacao(rotulo) or palavra in chave:
            return rotulo
    raise RuntimeError(
        f"Não reconheço o tipo de orientador \"{bruto}\" configurado no .env. "
        "Use 'tecnologias' ou 'maker'."
    )


_MARCADOR_DA_ETAPA = {
    ETAPA_PROFISSIONAL: "Qual o curso?",
    ETAPA_AEE: "Breve descrição da atividade",
    ETAPA_EJA: "Componente(s) Curricular",
}


def _descrever_pagina(page) -> str:
    """
    Fotografa a página onde o programa está: título e opções disponíveis.

    Serve para as mensagens de erro. Um "não encontrei o item X" sozinho
    não diz nada — o mesmo texto aparece tanto quando a opção realmente
    não existe quanto quando o formulário parou numa página anterior. Com
    o título e a lista do que existe ali, dá para saber qual dos dois é
    sem precisar reproduzir o problema.
    """
    try:
        dados = page.evaluate(
            """
            () => {
              const titulos = Array.from(document.querySelectorAll('[role="heading"]'))
                .map(e => (e.textContent || '').trim()).filter(Boolean);
              const opcoes = Array.from(
                  document.querySelectorAll('[role="checkbox"],[role="radio"]'))
                .map(e => e.getAttribute('aria-label') || '').filter(Boolean);
              return {titulo: titulos[0] || '', opcoes: opcoes.slice(0, 25)};
            }
            """
        )
    except Exception:
        return ""
    if not isinstance(dados, dict):
        return ""

    partes = []
    if dados.get("titulo"):
        partes.append(f"A página aberta é: \"{dados['titulo']}\".")
    opcoes = dados.get("opcoes") or []
    if opcoes:
        partes.append("As opções que existem nela são: " + "; ".join(opcoes) + ".")
    else:
        partes.append("Ela não tem nenhuma opção para marcar.")
    return " ".join(partes)


def _click_radio(page, label: str) -> None:
    """
    Marca uma opção redonda e confere se pegou.

    O mesmo clique-que-só-passa-o-mouse dos checkboxes acontece aqui — e
    numa opção redonda ele é pior, porque várias delas decidem para qual
    página o formulário vai em seguida.
    """
    alvo = page.get_by_role("radio", name=label, exact=True)
    if alvo.count() == 0:
        raise RuntimeError(
            f"Não encontrei a opção '{label}' nesta página do formulário. "
            + _descrever_pagina(page)
        )
    alvo = alvo.first
    alvo.scroll_into_view_if_needed(timeout=3000)
    for _ in range(4):
        try:
            if alvo.is_checked():
                _anotar("opção", label)
                return
        except Exception:
            return  # sem como conferir: segue o baile, como era antes
        alvo.click()
        page.wait_for_timeout(200)
    if not alvo.is_checked():
        raise RuntimeError(
            f"Não consegui marcar a opção '{label}' — o clique não pegou. "
            "Confira a janela do Chrome."
        )


def _achar_checkbox(page, label: str):
    """
    Acha o checkbox de um rótulo, tolerando diferenças de escrita.

    Primeiro tenta a correspondência exata (rápida). Não achando, varre
    os checkboxes da página e compara pela forma "crua" do texto — sem
    acento, tudo minúsculo, espaços colapsados.

    Isso não é preciosismo: os rótulos do próprio formulário da SED têm
    espaço duplo em vários itens ("LEIA  (ETI)", "Musicalização  (ETI)"),
    e o texto vindo da agenda varia em acento e maiúsculas. Foi assim que
    uma aula de História acabou marcada como "Outro: História" mesmo
    existindo a opção "História" logo ali na lista.

    Devolve o checkbox ou None.
    """
    exato = page.get_by_role("checkbox", name=label, exact=True)
    if exato.count():
        return exato.first

    alvo = chave_comparacao(label)
    todos = page.get_by_role("checkbox")
    for i in range(todos.count()):
        candidato = todos.nth(i)
        try:
            nome = candidato.get_attribute("aria-label") or ""
        except Exception:
            continue
        if nome and chave_comparacao(nome) == alvo:
            return candidato
    return None


def _tentar_casar_pela_pagina(page, disciplina: str):
    """
    Última tentativa antes de marcar "Outro:": procurar o nome da própria
    disciplina entre as opções da página.

    A tabela de equivalência em config.py cobre o que já conhecemos, mas
    ninguém consegue listar de antemão toda disciplina que pode aparecer
    na agenda de toda escola do estado. Se o nome bate com uma opção que
    está ali na tela, marcar essa opção é melhor do que escrever no
    "Outro" — e é exatamente o que uma pessoa faria olhando a lista.

    Testamos algumas formas do nome porque a agenda usa prefixos que o
    formulário não usa: "ETI - Educação Financeira" na agenda é
    "Educação Financeira  (ETI)" no formulário.

    Devolve o rótulo da opção encontrada, ou None.
    """
    bruto = (disciplina or "").strip()
    if not bruto:
        return None

    sem_prefixo = bruto
    for prefixo in ("ETI - ", "ETI-", "ETI "):
        if sem_prefixo.upper().startswith(prefixo.upper()):
            sem_prefixo = sem_prefixo[len(prefixo):].strip()
            break

    candidatos = [bruto, sem_prefixo, f"{sem_prefixo} (ETI)"]
    vistos = set()
    for nome in candidatos:
        if not nome or nome in vistos:
            continue
        vistos.add(nome)
        achado = _achar_checkbox(page, nome)
        if achado is not None:
            # devolve o rótulo REAL da página (e não o que procuramos):
            # é ele que aparece nas mensagens e é o texto que a SED usa.
            try:
                real = achado.get_attribute("aria-label")
                if real:
                    return real
            except Exception:
                pass
            return nome
    return None


def _click_checkbox(page, label: str) -> None:
    """
    Marca um checkbox do Forms. Confere se marcou de verdade
    (is_checked()) e tenta de novo se não — mesmo tipo de
    clique-que-não-registra já visto em outros lugares do formulário
    (ex: uma corrida real deixou "Computadores/notebooks (pesquisa) no
    laboratório" sem marcar mesmo com o clique disparado).
    """
    box = _achar_checkbox(page, label)
    if box is None:
        raise RuntimeError(
            f"Não encontrei o item '{label}' nesta página do formulário. "
            + _descrever_pagina(page)
        )
    box.scroll_into_view_if_needed(timeout=3000)
    for _ in range(4):
        if box.is_checked():
            _anotar("marcado", label)
            return
        box.click()
        page.wait_for_timeout(250)
    if not box.is_checked():
        raise RuntimeError(
            f"Não consegui marcar o checkbox '{label}' — confira manualmente "
            "a janela do Chrome."
        )


def _select_google_dropdown(page, current_or_placeholder: str, option_text: str) -> None:
    """
    Abre um <div role="listbox"> do Google Forms e escolhe uma opção.

    Usa o texto da pergunta (current_or_placeholder) para achar o listbox
    certo, em vez de simplesmente ".first" — importante porque a partir da
    2ª atividade processada na mesma execução o Forms pode restaurar
    progresso salvo (rascunho) e deixar mais de um listbox presente/aberto,
    o que fazia ".first" pegar o elemento errado ou já aberto.

    HISTÓRICO (investigado ao vivo, com o formulário real, depois de vários
    tiros no escuro que não resolveram — deixando registrado pra não
    repetir os mesmos erros):

    1) Tentamos digitar o texto da opção (com `type` tecla-por-tecla e depois
       com `insert_text` de uma vez só) para o Forms filtrar/selecionar
       sozinho. Isso funciona para nomes de UMA palavra (ex: BLUMENAU), mas
       para nomes com espaço (ex: "EEB HERMANN HAMANN") a tecla Espaço
       FECHA o menu imediatamente sem selecionar nada — não é "seleciona o
       item atual" como pensamos antes, é fechar puro e simples. Por isso
       nomes com espaço nunca funcionavam por digitação, com nenhum dos dois
       métodos.
    2) A lista de opções NÃO é virtualizada de verdade — todas as opções já
       ficam no DOM o tempo todo (confirmado: 47 <div role="option"> para a
       pergunta da Escola, mesmo com o menu fechado), só ficam escondidas
       visualmente. O que fazia o clique direto na opção falhar antes não
       era a opção "sumir", era ela estar fora da parte visível da lista
       (que tem scroll interno) — faltava rolar até ela antes de clicar.
    3) Sinal confiável de que a seleção realmente aconteceu (testado ao
       vivo): o próprio <div role="listbox"> fica com aria-expanded="false"
       E a opção escolhida fica com aria-selected="true". Texto sozinho não
       basta pra conferir (o texto de todas as opções sempre está presente
       no listitem, esteja o menu aberto ou fechado).

    Solução: abrir o menu, rolar a opção certa pra dentro da área visível e
    clicar nela diretamente — sem digitar nada.
    """
    item = page.locator(f'div[role="listitem"]:has-text("{current_or_placeholder}")').first
    listbox = item.locator('div[role="listbox"]').first
    padrao_exato = re.compile(r"^\s*" + re.escape(option_text) + r"\s*$")
    option = item.locator('div[role="option"]').filter(has_text=padrao_exato).first
    selecionada = item.locator('div[role="option"][aria-selected="true"]')

    for _ in range(4):
        _fechar_dialogo_rascunho(page)
        listbox.click()
        page.wait_for_timeout(300)
        try:
            option.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(150)
            option.click(timeout=3000)
        except Exception:
            pass
        page.wait_for_timeout(300)
        _fechar_dialogo_rascunho(page)
        # às vezes o Forms marca aria-selected="true" em 2 elementos ao
        # mesmo tempo (o "chip" mostrado fechado + a opção dentro da lista)
        # — .inner_text() dá erro de "strict mode" com mais de 1 elemento,
        # então juntamos o texto de todos em vez de usar só o primeiro.
        if selecionada.count() and option_text in " ".join(selecionada.all_inner_texts()):
            _anotar(current_or_placeholder[:40], option_text)
            return
        # não selecionou (ou o menu ainda estava aberto/fechou sozinho) —
        # tenta de novo do zero.
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

    raise RuntimeError(
        f"Não consegui confirmar a seleção de '{option_text}' no menu "
        f"'{current_or_placeholder}' — confira manualmente a janela do "
        "Chrome."
    )


def _fill_textbox_near(page, question_text: str, value: str) -> None:
    """
    Encontra a caixa de texto associada à pergunta cujo enunciado contém
    `question_text` e preenche `value`. O Google Forms marca cada pergunta
    como um div[role='listitem'] contendo o texto da pergunta e o input.
    """
    item = page.locator(f'div[role="listitem"]:has-text("{question_text}")').first
    box = item.locator('input[type="text"], textarea').first
    box.click()
    box.fill(value)
    try:
        escrito = box.input_value()
    except Exception:
        escrito = ""
    _anotar(question_text[:40], escrito)


def _perguntas_obrigatorias_pendentes(page) -> list:
    """
    Devolve os títulos das perguntas que o Forms está acusando como
    obrigatórias e sem resposta ("Esta pergunta é obrigatória").

    Feito em JavaScript, varrendo a página inteira, porque NEM TODA
    pergunta do Forms é um div[role="listitem"] — a pergunta "Enviar por
    e-mail" é nativa do Forms e fica fora dessa estrutura (conferido ao
    vivo). A primeira versão disto só olhava listitems e por isso não
    enxergava justamente a pergunta que estava travando tudo, deixando o
    script morrer com um timeout genérico que não ajudava em nada.
    """
    return page.evaluate(
        """
        () => {
          const saida = [];
          document.querySelectorAll('*').forEach((el) => {
            if (el.children.length !== 0) return;
            if ((el.textContent || '').trim() !== 'Esta pergunta é obrigatória') return;
            let cartao = el;
            for (let i = 0; i < 8 && cartao.parentElement; i++) {
              cartao = cartao.parentElement;
              const t = (cartao.innerText || '').trim();
              if (t.length > 30) break;
            }
            // String.fromCharCode(10) = quebra de linha. Usado no lugar de
            // '\n' de propósito: este trecho de JavaScript vive dentro de
            // uma string do Python, e a barra invertida acabava escapada
            // duas vezes no caminho — o resultado era um split por barra
            // invertida literal, que nunca casa com nada.
            const linha = (cartao.innerText || '').trim().split(String.fromCharCode(10))[0];
            if (linha) saida.push(linha);
          });
          return Array.from(new Set(saida));
        }
        """
    )


def _avancar(page, proxima_pagina: str | None = None) -> None:
    """
    Clica em 'Avançar'. Se `proxima_pagina` for passado (um texto que só
    existe na PRÓXIMA página, ex: o título da próxima pergunta), espera essa
    página aparecer e clica em Avançar de novo se ela não aparecer depois de
    um tempo — o primeiro clique às vezes só registra um hover, sem navegar
    de verdade (mesmo problema já visto no preenchimento manual via
    navegador). Importante: verificamos a CHEGADA na próxima página (não a
    saída da atual) para não arriscar clicar Avançar demais e pular página.
    """
    _fechar_dialogo_rascunho(page)
    page.get_by_role("button", name="Avançar").click()
    if not proxima_pagina:
        page.wait_for_timeout(400)
        return
    marcador = page.locator(f'div[role="listitem"]:has-text("{proxima_pagina}")').first
    for _ in range(4):
        try:
            marcador.wait_for(state="visible", timeout=2000)
            return
        except Exception:
            _fechar_dialogo_rascunho(page)
            page.get_by_role("button", name="Avançar").click()
    # Não navegou depois de várias tentativas. Quase sempre isso significa
    # que alguma pergunta OBRIGATÓRIA da página atual ficou sem resposta —
    # o Forms marca essas com "Esta pergunta é obrigatória" e simplesmente
    # não sai da página. Vale muito mais dizer QUAL pergunta travou do que
    # só estourar um timeout genérico (foi o que nos custou várias rodadas
    # de tentativa e erro com o checkbox "Enviar por e-mail").
    pendentes = _perguntas_obrigatorias_pendentes(page)
    if pendentes:
        raise RuntimeError(
            "O formulário não avançou porque ficou pergunta obrigatória sem "
            "resposta nesta página: "
            + "; ".join(pendentes)
            + ". Confira a janela do Chrome."
        )
    # última tentativa — deixa estourar um erro claro se ainda não navegou
    marcador.wait_for(state="visible", timeout=5000)


def _fechar_dialogo_rascunho(page) -> bool:
    """
    O Google Forms às vezes mostra um diálogo "Progresso salvo" avisando que
    há um rascunho mais recente das respostas (achado investigando ao vivo:
    isso acontece de verdade, não é só teoria) — enquanto ele está na tela,
    nenhum clique chega nos campos do formulário, e é exatamente esse tipo
    de travamento que vínhamos vendo na Escola. O único botão do diálogo é
    "Atualizar"; clicamos nele pra liberar a tela (o preenchimento que já
    fizemos na página atual pode precisar ser conferido/refeito depois
    disso, por isso quem chama deve tratar o retorno True como um sinal de
    "recomece a conferência desta página").
    """
    dialogo = page.get_by_role("dialog")
    if dialogo.count() == 0:
        return False
    botao = dialogo.get_by_role("button", name="Atualizar")
    if botao.count() == 0:
        return False
    botao.click()
    page.wait_for_timeout(500)
    return True


def estado_da_conta_google(page) -> dict:
    """
    Onde a janela do navegador parou: no formulário ou na tela de login?

    O programa depende de UMA sessão do Google, guardada na pasta
    browser_profile — feito o login uma vez naquele computador, ele abre
    sempre conectado. Quando a sessão expira (ou é a primeira vez), o
    Google desvia para a tela de entrar, e o formulário simplesmente não
    aparece. Sem esta verificação, o que a pessoa vê é o programa
    "travando" num campo que não existe naquela página.

    Devolve {"conectado": bool, "conta": e-mail visível na página ou ""}.
    """
    try:
        url = page.url or ""
    except Exception:
        url = ""
    if "accounts.google.com" in url or "signin" in url.lower():
        return {"conectado": False, "conta": ""}

    conta = ""
    try:
        achado = page.evaluate(
            r"""
            () => {
              const texto = document.body ? document.body.innerText : '';
              const m = texto.match(/[\w.+-]+@[\w-]+\.[\w.-]+/);
              return m ? m[0] : '';
            }
            """
        )
        if isinstance(achado, str):
            conta = achado
    except Exception:
        pass
    return {"conectado": True, "conta": conta}


def abrir_formulario(page) -> dict:
    """Abre o formulário e diz em que estado a conta Google está."""
    page.goto(SED_FORM_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    return estado_da_conta_google(page)


def _garantir_pagina_1(page) -> None:
    """
    Garante que o formulário está mostrando a página 1 ("Nome do professor
    orientador"). Da 2ª aula em diante — mesmo depois de recarregar a
    página — o Google Forms pode restaurar o rascunho/resposta anterior
    (guardado do lado da própria conta Google logada, não só localStorage)
    e mostrar uma página diferente da 1ª. Se isso acontecer, clica em
    "Enviar outra resposta" (tela de confirmação de envio) ou em "Voltar"
    (páginas seguintes) até achar a página 1 de verdade.
    """
    for _ in range(15):
        if page.locator('div[role="listitem"]:has-text("Nome do professor orientador")').count():
            return
        if _fechar_dialogo_rascunho(page):
            continue
        outra_resposta = page.get_by_role("link", name="Enviar outra resposta")
        if outra_resposta.count():
            outra_resposta.click()
            page.wait_for_timeout(600)
            continue
        voltar = page.get_by_role("button", name="Voltar")
        if voltar.count():
            voltar.click()
            page.wait_for_timeout(400)
            continue
        # nada reconhecido pra clicar — espera um pouco e tenta de novo (a
        # página pode ainda estar carregando)
        page.wait_for_timeout(500)
    raise RuntimeError(
        "Não foi possível voltar para a página 1 do formulário (nem "
        "'Nome do professor orientador' nem botões 'Voltar'/'Enviar outra "
        "resposta' foram encontrados) — confira manualmente a janela do "
        "Chrome."
    )


def _limpar_formulario_se_necessario(page) -> None:
    """
    Clica em "Limpar formulário" (se existir na tela) logo ao abrir o
    formulário, ANTES de preencher qualquer coisa.

    Achado ao vivo (rodando o script de verdade, na 2ª execução): o Google
    Forms guarda rascunho por CONTA GOOGLE logada, não só no navegador —
    então reabrir o formulário pode restaurar uma resposta de uma execução
    anterior (inclusive de uma que travou no meio do caminho, como o
    TargetClosedError de quando a janela do Chrome fechou sozinha). Isso
    deixava o formulário numa página/estado imprevisível, e o código que
    tentava adivinhar e voltar passo a passo (_garantir_pagina_1) nem
    sempre dava conta — daí o timeout esperando "Selecione a sua Escola"
    aparecer. Clicar em "Limpar formulário" resolve isso de vez, sem
    precisar adivinhar nada: sempre começa 100% em branco.
    """
    limpar = page.get_by_role("link", name="Limpar formulário")
    if limpar.count() == 0:
        return
    limpar.click()
    page.wait_for_timeout(300)
    confirmar = page.get_by_role("button", name="Limpar formulário")
    if confirmar.count():
        confirmar.click()
        page.wait_for_timeout(500)
    _fechar_dialogo_rascunho(page)


def _marcar_enviar_por_email(page) -> None:
    """
    Marca o checkbox da pergunta "Enviar por e-mail" da página 1.

    ESSA ERA A CAUSA REAL do erro "timeout esperando 'Selecione a sua
    Escola'": essa pergunta é OBRIGATÓRIA (tem asterisco vermelho) e o
    script nunca a marcava. Sem ela, o Google Forms simplesmente se recusa
    a sair da página 1 — o clique em "Avançar" acontece, mas o Forms mostra
    "Esta pergunta é obrigatória" e fica onde está. Como o `_avancar`
    esperava a página 2 aparecer, ele estourava o timeout.

    Por que só quebrou agora: antes o Forms restaurava um rascunho antigo
    (de quando esse checkbox tinha sido marcado à mão), então ele já vinha
    marcado "de graça". Ao passar a limpar o formulário no início de cada
    registro, esse presente sumiu e o furo apareceu toda vez.

    COMO ACHAR ESSE CHECKBOX (inspecionado ao vivo no formulário real —
    a 1ª tentativa de correção falhou justamente por eu ter chutado isso):

    - Ele NÃO fica dentro de um div[role="listitem"]. Essa pergunta é um
      recurso nativo do Forms (coleta de e-mail), não uma pergunta criada
      pela SED. Na página 1 existem só 3 listitems: Nome do professor,
      Professor Orientador de, e Regional. Procurar o checkbox "dentro da
      pergunta Enviar por e-mail" nunca casava com nada — e como o código
      antigo só fazia `return` quando não achava, ele falhava EM SILÊNCIO:
      o script seguia em frente como se tivesse marcado, e só quebrava lá
      na frente com um timeout que não dizia nada sobre a causa.
    - O rótulo dele inclui o e-mail da conta logada ("Registrar
      fulano@sed.sc.gov.br como o e-mail a ser incluído na minha
      resposta"), então casamos só pelo trecho final, que não muda de
      conta pra conta.
    - Ele é um div[role="checkbox"] com aria-checked. O aria-checked leva
      um instante pra atualizar depois do clique (conferido ao vivo: lido
      rápido demais ainda vem "false" mesmo já estando marcado na tela),
      por isso esperamos antes de reconferir — senão o laço clicaria de
      novo e DESmarcaria o que já estava certo.

    Se não conseguir marcar, levanta erro na hora em vez de seguir adiante
    em silêncio: é sempre melhor falhar aqui, apontando a causa, do que
    estourar um timeout genérico três páginas depois.
    """
    box = page.get_by_role(
        "checkbox", name=re.compile("e-mail a ser incluído na minha resposta")
    ).first
    if box.count() == 0:
        # Retaguarda: na página 1 esse é o único checkbox da tela (as
        # páginas com vários checkboxes — componentes e recursos — vêm bem
        # depois). Se o rótulo mudar, isso ainda acha o elemento certo.
        box = page.get_by_role("checkbox").first
    if box.count() == 0:
        raise RuntimeError(
            "Não encontrei o checkbox obrigatório 'Enviar por e-mail' na "
            "página 1 do formulário — confira manualmente a janela do Chrome."
        )

    box.scroll_into_view_if_needed(timeout=5000)
    for tentativa in range(4):
        if box.is_checked():
            return
        box.click()
        page.wait_for_timeout(600)
        if box.is_checked():
            return
        print(
            f"  (checkbox 'Enviar por e-mail' ainda não marcou — tentativa "
            f"{tentativa + 1} de 4)"
        )
    raise RuntimeError(
        "Não consegui marcar o checkbox obrigatório 'Enviar por e-mail' "
        "na página 1 — confira manualmente a janela do Chrome."
    )


def preencher_dados_fixos(page, orientador_nome: str = "", orientador_tipo: str = "") -> None:
    """
    Página 1 (orientador/regional) + página 2 (escola).

    `orientador_nome` e `orientador_tipo` existem porque há escolas com
    dois orientadores no mesmo computador (um no diurno, outro no
    noturno): quem chama diz qual dos dois está registrando. Sem eles,
    usa o professor configurado — que é o caso de quem tem um só.
    """
    nome = orientador_nome or ORIENTADOR_NOME
    tipo = orientador_tipo or ORIENTADOR_TIPO
    page.goto(SED_FORM_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        pass
    # Antes de procurar campo nenhum: a janela está no formulário ou na
    # tela de login do Google? Perguntar isso aqui é a diferença entre uma
    # frase que resolve e um travamento de cinco minutos num campo que
    # ainda não existe.
    if not estado_da_conta_google(page)["conectado"]:
        raise RuntimeError(
            "A conta Google da escola não está conectada neste computador.\n\n"
            "Na janela do Chrome que abriu, entre com o e-mail institucional "
            "da escola (o mesmo que responde o formulário da SED) e depois "
            "clique em 'Preencher formulário' de novo.\n\n"
            "Isso é pedido uma vez por computador: feito o login, ele fica "
            "guardado e o programa passa a abrir já conectado."
        )
    # O Google Forms às vezes mostra um diálogo "Progresso salvo" (rascunho
    # mais recente disponível) logo ao abrir — fecha se aparecer.
    _fechar_dialogo_rascunho(page)
    _limpar_formulario_se_necessario(page)

    # Página 1 — na primeira execução (browser_profile ainda sem sessão
    # salva), o Google pode pedir login antes de mostrar o formulário. O
    # campo abaixo só existe depois desse login manual, então damos um
    # timeout bem maior (5 minutos) só neste primeiro clique, para dar
    # tempo de você fazer login na janela do Chrome que abriu.
    print(
        "Se aparecer uma tela de login do Google na janela do Chrome que "
        "abriu, faça login manualmente agora (você tem até 5 minutos). Se "
        "já estiver logado, pode ignorar esta mensagem."
    )
    nome_box = page.locator('div[role="listitem"]:has-text("Nome do professor orientador")').locator("input")
    if nome_box.count() == 0:
        # não é a página 1 (resposta anterior/confirmação restaurada) —
        # navega de volta antes de continuar.
        _garantir_pagina_1(page)
        nome_box = page.locator('div[role="listitem"]:has-text("Nome do professor orientador")').locator("input")
    nome_box.click(timeout=300000)
    nome_box.fill("")
    nome_box.fill(nome)

    _click_radio(page, _rotulo_atuacao(tipo))
    _select_google_dropdown(page, "Selecione seu local de trabalho", REGIONAL)

    # Pergunta obrigatória — sem ela o Forms não sai da página 1.
    #
    # Deixado de propósito por ÚLTIMO, logo antes do "Avançar": marcando-o
    # no começo, alguma coisa entre a marcação e o avanço estava desfazendo
    # a marcação (o menu suspenso da Regional mexe no foco e chega a apertar
    # Escape nas tentativas; o Forms também pode re-renderizar a página
    # depois do "Limpar formulário"). Marcando por último, não sobra nada
    # entre a marcação e o clique em Avançar que possa desfazê-la.
    _marcar_enviar_por_email(page)

    _avancar(page, proxima_pagina="Selecione a sua Escola")

    # Página 2 — Escola
    _select_google_dropdown(page, "Selecione a sua Escola", ESCOLA)
    _avancar(page, proxima_pagina="Atividade/Aula com estudantes")


def preencher_atividade_com_estudantes(
    page,
    disciplina_agendamento: str,
    etapa: str,
    resumo_projeto: str,
    numero_aulas: int,
    numero_estudantes: int,
    conteudos_abordados: str,
    recursos_utilizados: list[str],
    orientador_tipo: str = "",
    subetapa: str = "",
    curso: str = "",
) -> None:
    """
    Preenche as páginas do fluxo "Atividade/Aula com estudantes"
    (páginas 3 a 8 do formulário). Chame preencher_dados_fixos(page) antes.
    """
    # Página 3 — Tipo de registro
    _click_radio(page, "Atividade/Aula com estudantes")
    _avancar(page, proxima_pagina=etapa)

    # Página 4 — Etapa da Educação Básica
    #
    # Cada etapa cai numa página diferente, então cada uma tem o SEU
    # marcador de chegada. Sem marcador, o programa clicava em "Avançar" e
    # seguia em frente sem conferir se a página realmente mudou — e o
    # clique que não registra (só passa o mouse por cima) é um problema
    # velho conhecido deste formulário. Quando isso acontecia, o passo
    # seguinte ia procurar campos numa página que não era a esperada, e o
    # erro só aparecia lá adiante, apontando para o lugar errado.
    _click_radio(page, etapa)
    _avancar(page, proxima_pagina=_MARCADOR_DA_ETAPA.get(etapa, "Componente(s) Curricular"))

    # Página 5 — depende da etapa
    #
    # Ensino Profissional e Educação Especial (AEE) têm páginas com outra
    # cara: não existe lista de componentes curriculares nelas — e, no caso
    # do AEE, não existe nem a opção "Outro:". Tratados antes de tudo, senão
    # o programa procura uma lista que não está lá.
    if etapa == ETAPA_PROFISSIONAL:
        # duas caixas de texto: curso e componente curricular
        _fill_textbox_near(page, "Qual o curso?", curso or disciplina_agendamento)
        _fill_textbox_near(page, "Qual o componente curricular?", disciplina_agendamento)
        _avancar(page, proxima_pagina="Professor orientador de")
        _depois_da_etapa(
            page, orientador_tipo, recursos_utilizados, resumo_projeto,
            numero_aulas, numero_estudantes, conteudos_abordados,
        )
        return

    if etapa == ETAPA_AEE:
        if not subetapa:
            raise RuntimeError(
                "A etapa 'Educação Especial (AEE)' precisa da resposta de "
                "'Qual etapa?' (Anos Iniciais, Anos Finais ou Ensino Médio). "
                "Escolha na tela do programa e tente de novo."
            )
        _click_checkbox(page, subetapa)
        _fill_textbox_near(
            page, "Breve descrição da atividade", conteudos_abordados or resumo_projeto
        )
        _avancar(page, proxima_pagina="Professor orientador de")
        _depois_da_etapa(
            page, orientador_tipo, recursos_utilizados, resumo_projeto,
            numero_aulas, numero_estudantes, conteudos_abordados,
        )
        return

    if etapa == ETAPA_EJA:
        # na EJA a lista de componentes vem DEPOIS de "Qual etapa?", na
        # mesma página — e essa pergunta é obrigatória.
        if not subetapa:
            raise RuntimeError(
                "A etapa 'Educação de Jovens e Adultos' precisa da resposta de "
                "'Qual etapa?' (Ensino Fundamental ou Ensino Médio). "
                "Escolha na tela do programa e tente de novo."
            )
        _click_radio(page, subetapa)

    # Componente(s) curricular(es)
    componente = resolver_componente(disciplina_agendamento, etapa)
    if componente is None:
        # sem equivalência cadastrada: talvez o nome da disciplina seja
        # igual ao de uma opção da página (Física, Química, Filosofia...)
        achado = _tentar_casar_pela_pagina(page, disciplina_agendamento)
        if achado:
            componente = [achado]
    if componente is None:
        # Regra combinada com o usuário: disciplina sem mapeamento em
        # config.DISCIPLINA_PARA_COMPONENTE não trava mais o registro — marca
        # "Outro:" e usa o texto da disciplina exatamente como está na
        # agenda.
        componente = ("OUTRO", disciplina_agendamento)
    if isinstance(componente, tuple) and componente[0] == "OUTRO":
        _click_checkbox(page, "Outro:")
        _fill_textbox_near(page, "Outro:", componente[1])
    else:
        # Cada etapa tem a SUA lista de componentes: "Ciências" e "Ensino
        # Religioso" existem no Fundamental mas não no Ensino Médio;
        # "Biologia", "Física" e "Química" existem no Médio mas não no
        # Fundamental. Então um componente mapeado pode simplesmente não
        # estar nesta página — e nesse caso marcamos "Outro:" com o nome
        # da disciplina, em vez de travar o registro.
        marcados = []
        ausentes = []
        for c in componente:
            if _achar_checkbox(page, c) is not None:
                _click_checkbox(page, c)
                marcados.append(c)
            else:
                ausentes.append(c)
        if ausentes and not marcados:
            # antes de desistir, ver se o nome da disciplina bate com
            # alguma opção desta página
            achado = _tentar_casar_pela_pagina(page, disciplina_agendamento)
            if achado:
                print(f"  (usando a opção '{achado}' encontrada na página)")
                _click_checkbox(page, achado)
            else:
                print(
                    f"  (nenhum componente da lista {ausentes} existe nesta etapa — "
                    f"marcando 'Outro: {disciplina_agendamento}')"
                )
                _click_checkbox(page, "Outro:")
                _fill_textbox_near(page, "Outro:", disciplina_agendamento)
        elif ausentes:
            print(f"  (componente(s) sem opção nesta etapa, ignorado(s): {ausentes})")
    _avancar(page, proxima_pagina="Professor orientador de")

    _depois_da_etapa(
        page, orientador_tipo, recursos_utilizados, resumo_projeto,
        numero_aulas, numero_estudantes, conteudos_abordados,
    )


def _depois_da_etapa(
    page,
    orientador_tipo: str,
    recursos_utilizados: list[str],
    resumo_projeto: str,
    numero_aulas: int,
    numero_estudantes: int,
    conteudos_abordados: str,
) -> None:
    """
    Da página "Confirme sua atuação" até a última antes do Enviar.

    Esse trecho é igual para TODAS as etapas — por isso vive numa função
    só: o que muda entre Anos Iniciais, Ensino Profissional e AEE é apenas
    a página anterior a esta.
    """
    # Confirme sua atuação
    #
    # Esta resposta decide QUAL página de recursos vem a seguir: o
    # formulário tem duas listas completamente diferentes — a de
    # Tecnologias Educacionais (lousa, notebooks, tablets...) e a do
    # Laboratório Maker (robótica, impressora 3D, cortadora a laser...).
    # Por isso aqui se confere a chegada na página seguinte: se o clique
    # em "Avançar" não pegasse, o programa tentava marcar os recursos
    # ainda na página da atuação e o erro saía com cara de "não existe
    # esse recurso", escondendo a causa real.
    _click_radio(page, _rotulo_atuacao(orientador_tipo))
    _avancar(page, proxima_pagina="Quais recursos foram utilizados")

    # Recursos utilizados
    for recurso in recursos_utilizados:
        _click_checkbox(page, recurso)
    _avancar(page, proxima_pagina="nome/resumo do seu projeto")

    # Objetivos / números / conteúdos
    _fill_textbox_near(page, "nome/resumo do seu projeto", resumo_projeto)
    _fill_textbox_near(page, "Número de aulas efetivamente utilizadas", str(numero_aulas))
    _fill_textbox_near(page, "Número de estudantes efetivamente atendidos", str(numero_estudantes))
    _fill_textbox_near(page, "objetos do conhecimento", conteudos_abordados)
    _avancar(page)

    # Página final — termo de consentimento + Enviar
    # NÃO clicamos em "Enviar" aqui — isso é feito pelo chamador depois de
    # mostrar o resumo e receber confirmação explícita.


def enviar(page) -> None:
    """
    Clica em 'Enviar' e confere que o Forms REALMENTE recebeu o envio
    antes de devolver.

    Todo outro clique deste arquivo é lido de volta da página antes de
    seguir em frente (ver o comentário no topo do arquivo) — inclusive o
    de "Avançar", que tenta de novo se o primeiro clique só passou o
    mouse sem navegar. Este aqui, até agora, era o único que não
    conferia nada: quem chama `enviar()` marca a aula como enviada logo
    em seguida, sem checar mais nada.

    NÃO clicamos "Enviar" de novo se a confirmação não aparecer, ao
    contrário do padrão usado no resto do arquivo: um segundo clique
    aqui pode ser um segundo envio de verdade para o Google Forms, se o
    primeiro só estava demorando a responder. É melhor levantar um erro
    claro e deixar a pessoa olhar a janela do Chrome do que arriscar
    duplicar o registro tentando "corrigir" sozinho.

    Devolve normalmente só quando a tela de confirmação do Forms
    ("Enviar outra resposta") aparece — a mesma que `_garantir_pagina_1`
    já reconhece como prova de que uma resposta anterior foi recebida.

    Se a página JÁ estiver nessa tela de confirmação ao entrar aqui, não
    clica em nada — devolve na hora. É o que permite mandar chamar
    `enviar()` de novo com segurança depois de um erro "não vi a
    confirmação a tempo": se o primeiro envio, na verdade, tinha dado
    certo (só demorou a mostrar a tela), a segunda chamada não encontra
    mais o botão "Enviar" — encontra a confirmação já visível — e não há
    o que duplicar.

    Dois tipos de falha são tratados separado, com mensagens diferentes,
    porque contam histórias BEM diferentes pra quem vai ler:

    - a janela do Chrome fechou (ou travou) ANTES do clique acontecer —
      Playwright levanta TargetClosedError/erro parecido. Aqui dá pra
      afirmar com certeza que nada foi enviado: o clique nem chegou a
      acontecer.
    - o clique aconteceu e a confirmação não apareceu depois — aí não dá
      pra saber se chegou na SED ou não (ver o motivo acima, na mensagem
      correspondente).

    Sem essa distinção, as duas apareciam pra quem usa como o mesmo erro
    técnico cru do Playwright ("TargetClosedError: Target page, context
    or browser has been closed"), que não diz o que fazer a seguir.
    """
    try:
        confirmacao = page.get_by_role("link", name="Enviar outra resposta")
        ja_confirmado = confirmacao.count() > 0
    except Exception as e:
        raise RuntimeError(
            "A janela do Chrome fechou (ou parou de responder) antes de eu "
            "conseguir conferir o formulário. Nada foi enviado — o clique em "
            "\"Enviar\" nem chegou a acontecer.\n\n"
            "Clique em \"Preencher formulário\" de novo e tente outra vez.\n\n"
            f"(detalhe técnico: {str(e).splitlines()[0][:200]})"
        ) from None
    if ja_confirmado:
        return
    try:
        page.get_by_role("button", name="Enviar").click()
    except Exception as e:
        raise RuntimeError(
            "A janela do Chrome fechou (ou parou de responder) bem na hora "
            "de clicar em \"Enviar\". Nada foi enviado — o clique nem chegou "
            "a acontecer.\n\n"
            "Clique em \"Preencher formulário\" de novo e tente outra vez.\n\n"
            f"(detalhe técnico: {str(e).splitlines()[0][:200]})"
        ) from None
    try:
        confirmacao.wait_for(state="visible", timeout=20000)
    except Exception:
        raise RuntimeError(
            "Cliquei em 'Enviar', mas não vi a confirmação do Google Forms "
            "('Enviar outra resposta') depois de esperar — não dá para "
            "saber se o registro chegou na SED ou não. NÃO marquei esta "
            "aula como enviada. Olhe a janela do Chrome: se ela já mostra "
            "a confirmação, é só clicar em \"Enviar para a SED\" de novo "
            "aqui (não vai duplicar); se ainda mostra o formulário, espere "
            "a internet normalizar e tente de novo."
        ) from None
