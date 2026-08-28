# -*- coding: utf-8 -*-
"""
Funções para logar no site de agendamento do NTE Blumenau e extrair os
agendamentos de uma semana específica.

O HTML do site tem uma estrutura limpa e estável:

    <div class="weekly-cell reserved" data-date="2026-08-19"
         data-inicio="07:15" data-fim="08:00">
        <div class="reserva-container">
            <div class="reserva-header">
                <div class="reserva-horario">07:15</div>
            </div>
            <div class="reserva-professor">NAYARA BIANCHI STUPP</div>
            <div class="reserva-disciplina">ETI - Educação Financeira</div>
            <div class="reserva-turma">Anos Finais - 6º ano - Anos Finais</div>
            <div class="reserva-assunto">https://www.bcb.gov.br/meubc/...</div>
            <div class="reserva-data-agendamento">Agendado em: ...</div>
        </div>
    </div>

Isso foi confirmado inspecionando a página ao vivo em 20/08/2026. Se o NTE
mudar o layout do site no futuro, ajuste os seletores abaixo.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from caminhos import caminho_de_dados
from config import AGENDA_LOGIN_URL, AGENDA_URL, DISCIPLINAS_IGNORADAS, chave_comparacao

TURNOS = ["Matutino", "Vespertino", "Noturno"]


@dataclass
class Agendamento:
    data: str          # "2026-08-19"
    inicio: str         # "07:15"
    fim: str            # "08:00"
    professor: str
    disciplina: str
    turma: str
    conteudo: str
    agendado_em: str
    # De qual aba do site esta reserva veio: "Matutino", "Vespertino" ou
    # "Noturno". Vem da PRÓPRIA agenda, não é deduzido do horário — assim
    # não erramos em escola com horário fora do comum. É o que permite dar
    # a cada orientador só as aulas do turno dele.
    turno: str = ""
    # Qual agenda do NTE esta reserva veio: "Lab. Tecs" (o laboratório,
    # sempre lida) ou o nome de outro recurso reservável da escola
    # (Projetor 1, Tablets...) — ver _descobrir_outros_recursos. Cada
    # escola tem seus próprios recursos, com nomes e números diferentes.
    recurso: str = "Lab. Tecs"


@dataclass
class AtividadeAgrupada:
    """Um grupo de slots contíguos (mesmo professor/disciplina/turma/dia)."""
    data: str
    inicio: str
    fim: str
    professor: str
    disciplina: str
    turma: str
    conteudo: str
    numero_aulas: int
    turno: str = ""
    recurso: str = "Lab. Tecs"
    slots: list = field(default_factory=list)


def _normalizar_para_comparar_escola(texto: str) -> str:
    """
    `chave_comparacao()` (de config.py) sozinha não basta aqui: o site do
    NTE escreve a escola abreviada ("Profº", "Profª") e às vezes com um
    complemento entre parênteses ("(Admin)") que não existe no nome
    oficial da SED (escolas.py, "PROF" por extenso). Sem tratar isso,
    "EEB Profº João Widemann" nunca bateria com "EEB PROF JOAO WIDEMANN".
    """
    t = chave_comparacao(texto)
    t = t.replace("profº", "prof").replace("profª", "prof")
    t = re.sub(r"\([^)]*\)", "", t)  # tira "(admin)" e afins
    return re.sub(r"\s+", " ", t).strip()


def _escolher_escola_se_pedir(page, escola: str) -> None:
    """
    Alguns professores dão aula em mais de uma escola — o CPF deles fica
    associado a mais de uma no cadastro do NTE, e o login mostra uma
    janela "Selecione a Escola" por cima do formulário, com uma lista das
    escolas. Quem só tem uma escola nunca vê essa janela; por isso ela é
    só uma tentativa (`wait_for` com timeout curto), não uma etapa
    obrigatória do login.
    """
    # Ancorado no texto do PRÓPRIO aviso da janela ("você está associado
    # a múltiplas escolas"), não em "existe algum combobox visível na
    # página" — a agenda tem outros menus suspensos (o seletor de mês,
    # por exemplo) que batem com get_by_role("combobox") sozinho. Foi
    # assim que um professor de escola ÚNICA acabou caindo aqui dentro,
    # com o programa tentando escolher escola no seletor de MÊS da
    # agenda normal, sem nenhuma tela de escolha ter aparecido de verdade.
    #
    # Prazo curto de propósito: a MAIORIA dos professores nunca vê esta
    # tela (só um CPF de escola única), e o login acontece a cada
    # releitura da agenda (de 30 em 30 min, em segundo plano) — não pode
    # atrasar todo mundo esperando algo que quase nunca aparece.
    aviso = page.get_by_text("associado a múltiplas escolas")
    try:
        aviso.wait_for(state="visible", timeout=2000)
    except Exception:
        return  # não apareceu -- CPF de escola única, segue o fluxo normal

    # Não "o combobox da página" (get_by_role("combobox") sozinho bate
    # com qualquer outro select que exista ali, e explode com "vários
    # elementos encontrados" em vez de simplesmente escolher o certo) —
    # o que só ESTE select tem é a opção "-- Selecione uma escola --".
    seletor = page.locator("select").filter(
        has=page.locator("option", has_text="Selecione uma escola")
    )

    if not escola:
        raise RuntimeError(
            "O site do NTE pediu para escolher a escola no login (este "
            "CPF está associado a mais de uma) — mas o programa não tem "
            "nenhuma escola configurada para escolher sozinho. Preencha "
            "a escola no cadastro (\"Meus dados\")."
        )

    alvo = _normalizar_para_comparar_escola(escola)
    opcoes = seletor.locator("option")
    disponiveis = []
    for i in range(opcoes.count()):
        opcao = opcoes.nth(i)
        # o placeholder ("-- Selecione uma escola --") sempre tem
        # value="" — filtrar pelo texto seria frágil (o texto dele
        # também "sobrevive" à normalização, já que só tira acento e
        # maiúscula, não as palavras)
        if not (opcao.get_attribute("value") or "").strip():
            continue
        texto = opcao.inner_text().strip()
        disponiveis.append(texto)
        if _normalizar_para_comparar_escola(texto) == alvo:
            seletor.select_option(label=texto)
            # A lista sozinha não confirma nada — tem um botão
            # "Confirmar" próprio, ao lado do "Cancelar". Sem clicar
            # nele, a janela nunca fecha: o programa escolhia a escola
            # certa na lista e ficava esperando ali para sempre, achando
            # (depois de 15s) que ela tinha fechado — e a busca pela
            # semana batia de frente com a janela ainda aberta,
            # confundindo com "site mudou de layout".
            page.get_by_role("button", name="Confirmar").click()
            try:
                aviso.wait_for(state="hidden", timeout=15000)
            except Exception:
                pass  # segue mesmo assim; scrape_week ainda vai navegar de novo
            return
    lista = "\n".join(f"   • {op}" for op in disponiveis) or "   (nenhuma opção encontrada)"
    raise RuntimeError(
        "O site do NTE pediu para escolher a escola no login, mas "
        f'nenhuma das opções bateu com a escola configurada ("{escola}"). '
        "Confira se o nome da escola no cadastro está certo.\n\n"
        f"Escolas que o site ofereceu para este login:\n{lista}"
    )


def login(page, cpf: str, senha: str, escola: str = "") -> None:
    """Loga no site de agendamento, se a tela de login aparecer."""
    # wait_until="domcontentloaded" + timeout maior: o site as vezes demora
    # a disparar o evento "load" (recursos externos lentos), mas o
    # formulário de login já está pronto bem antes disso.
    page.goto(AGENDA_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    if page.locator("#username").count() == 0:
        # já estava logado (sessão anterior ainda válida)
        return
    page.fill("#username", cpf)
    page.fill("#senha", senha)
    page.get_by_role("button", name="Entrar").click()
    _escolher_escola_se_pedir(page, escola)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        # alguns sites nunca ficam 100% "idle" (polling em segundo plano);
        # o login já deve ter completado, então seguimos em frente.
        pass


def _scrape_current_view(page, turno: str = "") -> list[Agendamento]:
    """Extrai todos os '.weekly-cell.reserved' visíveis na página atual."""
    cells = page.locator(".weekly-cell.reserved")
    count = cells.count()
    resultado = []
    for i in range(count):
        cell = cells.nth(i)
        data = cell.get_attribute("data-date")
        inicio = cell.get_attribute("data-inicio")
        fim = cell.get_attribute("data-fim")

        def texto(seletor: str) -> str:
            loc = cell.locator(seletor)
            return loc.inner_text().strip() if loc.count() else ""

        resultado.append(
            Agendamento(
                data=data,
                inicio=inicio,
                fim=fim,
                professor=texto(".reserva-professor"),
                disciplina=texto(".reserva-disciplina"),
                turma=texto(".reserva-turma"),
                conteudo=texto(".reserva-assunto"),
                agendado_em=texto(".reserva-data-agendamento"),
                turno=turno,
            )
        )
    return resultado


def _goto_week_containing(page, target_monday: dt.date, max_steps: int = 26) -> None:
    """Navega semana a semana até que a semana exibida contenha target_monday."""
    # A grade da semana (".weekly-cell") tem uma célula por horário, todo
    # dia, MESMO nas semanas sem nenhuma aula agendada — "zero células"
    # nunca significa "semana vazia", só "a página ainda não carregou a
    # grade". Sem esperar por ela aqui, uma navegação um pouco mais lenta
    # (por exemplo, vindo direto da tela de escolha de escola) já contava
    # como "site mudou de layout" no primeiro instante em que a grade
    # ainda não tinha aparecido.
    try:
        page.locator(".weekly-cell").first.wait_for(state="attached", timeout=15000)
    except Exception:
        pass  # ou carregou devagar demais, ou é aqui mesmo que vai falhar

    for _ in range(max_steps):
        cells = page.locator(".weekly-cell")
        if cells.count() == 0:
            break
        first_date_str = cells.first.get_attribute("data-date")
        if not first_date_str:
            break
        first_date = dt.date.fromisoformat(first_date_str)
        # a semana exibida começa na segunda-feira "first_date"
        if first_date == target_monday:
            return
        if first_date < target_monday:
            page.get_by_role("button", name="Próxima Semana ›").click()
        else:
            page.get_by_role("button", name="‹ Semana Anterior").click()
        page.wait_for_timeout(400)
    raise RuntimeError(
        "Não foi possível navegar até a semana desejada — "
        "verifique se o site mudou de layout.\n\n"
        + _diagnostico_falha_agenda(page)
    )


def _diagnostico_falha_agenda(page) -> str:
    """
    Pista de diagnóstico guardada junto do erro de "não achei a semana".

    Sem isto, entender POR ONDE o site travou dependia de alguém
    descrever de memória o que via na tela — e já levou mais de uma
    rodada de tentativa e erro sem resolver de vez. Um print de tela e a
    URL onde parou dizem isso na hora.
    """
    partes = [f"Página onde parou: {page.url}"]
    try:
        if page.get_by_text("associado a múltiplas escolas").is_visible():
            partes.append(
                "A tela de 'escolha a escola' AINDA estava na tela — a "
                "escolha não chegou a acontecer, ou não fechou a tempo."
            )
    except Exception:
        pass
    try:
        caminho_print = caminho_de_dados("erro_agenda.png")
        page.screenshot(path=caminho_print)
        partes.append(f"Print de tela salvo em: {caminho_print}")
    except Exception:
        pass
    try:
        # O HTML de verdade, não só o print: uma imagem mostra COMO a
        # página parecia, mas não diz o nome da classe/estrutura por
        # trás do que apareceu (por exemplo, um "cadeado" em vez da
        # grade normal) — e é isso que decide o ajuste certo no código.
        caminho_html = caminho_de_dados("erro_agenda.html")
        with open(caminho_html, "w", encoding="utf-8") as f:
            f.write(page.content())
        partes.append(f"HTML da página salvo em: {caminho_html}")
    except Exception:
        pass
    return "\n".join(partes)


def scrape_week(
    page,
    monday: dt.date,
    turnos: list[str] | None = None,
    agenda_id: str | None = None,
    nome_recurso: str = "Lab. Tecs",
) -> list[Agendamento]:
    """
    Coleta todos os agendamentos da semana que começa em `monday`, de UMA
    agenda (`agenda_id`, ou a padrão — o laboratório — se não informado).

    Cada resultado vem marcado com `nome_recurso` — ver scrape_semana_completa,
    que chama isto uma vez por recurso da escola (laboratório, projetor...).
    """
    turnos = turnos or TURNOS
    url = AGENDA_URL if not agenda_id else f"{AGENDA_URL}?agenda={agenda_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        pass

    # garante visão "Semana" — usa o id (#weekViewBtn) em vez do texto porque
    # "Semana" combina com 4 botões diferentes (Semana Atual, ‹ Semana
    # Anterior, Próxima Semana ›, e o próprio botão de alternar view), o que
    # quebra get_by_role em modo estrito. Só clica se ainda não estiver ativo.
    semana_btn = page.locator("#weekViewBtn")
    if semana_btn.count() and "active" not in (semana_btn.get_attribute("class") or ""):
        semana_btn.click()
        page.wait_for_timeout(300)

    _goto_week_containing(page, monday)

    todos: list[Agendamento] = []
    for turno in turnos:
        page.get_by_role("button", name=turno, exact=True).click()
        page.wait_for_timeout(300)
        for agendamento in _scrape_current_view(page, turno):
            agendamento.recurso = nome_recurso
            todos.append(agendamento)

    return todos


# Recursos de Tecnologias Educacionais que a escola pode ter, ALÉM do
# laboratório — reconhecidos pela PALAVRA no nome do recurso, não por uma
# lista fixa de números: cada escola tem os seus, com nomes e IDs
# diferentes (confirmado ao vivo — a mesma etiqueta "Projetor 1" tem um
# número numa escola e outro noutra, e nem toda escola tem os mesmos
# recursos: uma tinha Projetor/Tablets, outra tinha Auditório/Biblioteca
# no lugar). Só entram aqui palavras que também existem na lista de
# "Recursos utilizados" do formulário da SED — uma sala qualquer
# (Auditório, Biblioteca) não é trabalho do orientador de Tec. Educ./Maker,
# e puxar essas reservas juntaria aula de gente que nada tem a ver com o
# laboratório.
_CATEGORIAS_RECURSO_RELEVANTE = {
    "projetor": "Projetores",
    "tablet": "Tablets/Celular",
    "celular": "Tablets/Celular",
    "notebook": "Tablets/Celular",
    "chromebook": "Tablets/Celular",
}


def categoria_do_recurso(nome: str) -> str | None:
    """A aba ("Projetores"/"Tablets/Celular") deste recurso, ou None se
    não for um recurso de Tecnologias Educacionais reconhecido."""
    chave = chave_comparacao(nome)
    for palavra, categoria in _CATEGORIAS_RECURSO_RELEVANTE.items():
        if palavra in chave:
            return categoria
    return None


def descobrir_outros_recursos(page) -> list[tuple[str, str, str]]:
    """
    Lê o menu "Agenda: ..." da página atual e devolve os recursos
    reserváveis desta escola que valem a pena ler além do laboratório —
    já filtrados pelo nome (ver categoria_do_recurso). O Lab. Tecs em si
    nunca aparece aqui: não bate com nenhuma palavra da lista, porque já
    é lido à parte por quem chama esta função.

    Devolve lista de (nome, id_da_agenda, categoria) — vazia se a escola
    não tiver nenhum recurso reconhecido (o caso mais comum).
    """
    encontrados = []
    try:
        links = page.locator('a[href*="agenda="]')
        for i in range(links.count()):
            a = links.nth(i)
            texto = (a.inner_text() or "").strip()
            href = a.get_attribute("href") or ""
            if not texto:
                continue
            m = re.search(r"agenda=(\d+)", href)
            if not m:
                continue
            categoria = categoria_do_recurso(texto)
            if categoria:
                encontrados.append((texto, m.group(1), categoria))
    except Exception:
        pass
    return encontrados


def scrape_semana_completa(page, monday: dt.date, turnos: list[str] | None = None) -> list[Agendamento]:
    """
    Lê a semana inteira: o laboratório (sempre) e qualquer outro recurso
    de Tecnologias Educacionais que a escola tenha (Projetor, Tablets,
    Celulares, notebook móvel) — descobertos sozinho no menu da própria
    página, já que cada escola tem os seus (às vezes nenhum extra).
    """
    todos = scrape_week(page, monday, turnos, nome_recurso="Lab. Tecs")
    try:
        extras = descobrir_outros_recursos(page)
    except Exception:
        extras = []
    for nome, agenda_id, _categoria in extras:
        try:
            todos.extend(scrape_week(page, monday, turnos, agenda_id=agenda_id, nome_recurso=nome))
        except Exception:
            # Um recurso extra falhando (site fora do ar bem naquela hora,
            # nome mudou) não pode derrubar a leitura do laboratório, que
            # já funcionava antes disto existir — só essa parte some
            # silenciosamente desta vez.
            continue
    return todos


# Intervalo (recreio) entre dois slots que ainda conta como a MESMA
# atividade emendada, e não uma aula nova — visto ao vivo: a mesma
# professora, turma e disciplina, com um buraco de 15 min no meio
# (07:15-08:45, cadeado, 09:00-09:45), que é o recreio da escola, não
# duas atividades diferentes. Generoso de propósito (recreios variam de
# escola pra escola) sem chegar a emendar coisas realmente sem relação.
TOLERANCIA_RECREIO_MIN = 20


def _minutos(horario: str) -> int:
    h, m = horario.split(":")
    return int(h) * 60 + int(m)


def filtrar_e_agrupar(
    agendamentos: list[Agendamento],
    professor_filtro: str | None = None,
) -> list[AtividadeAgrupada]:
    """
    Remove disciplinas ignoradas (formação/reunião interna), opcionalmente
    filtra por professor, e agrupa slots contíguos (mesmo dia + professor +
    disciplina + turma, horário emendado — ou só separados pelo recreio,
    ver TOLERANCIA_RECREIO_MIN) em uma única atividade — cada 45 min conta
    como 1 aula, conforme as regras do formulário da SED.
    """
    relevantes = [
        a
        for a in agendamentos
        if a.disciplina not in DISCIPLINAS_IGNORADAS
        and (professor_filtro is None or a.professor.strip().lower() == professor_filtro.strip().lower())
    ]

    # ordena por dia, professor, disciplina, turma, horário de início — o
    # recurso entra na ordenação (não só na comparação abaixo) para que
    # duas aulas emendadas de recursos DIFERENTES nunca fiquem vizinhas
    # na lista por coincidência de horário.
    relevantes.sort(
        key=lambda a: (a.data, a.turno, a.professor, a.disciplina, a.turma, a.recurso, a.inicio)
    )

    grupos: list[AtividadeAgrupada] = []
    atual: AtividadeAgrupada | None = None

    for a in relevantes:
        if (
            atual is not None
            and atual.data == a.data
            and atual.professor == a.professor
            and atual.disciplina == a.disciplina
            and atual.turma == a.turma
            and atual.turno == a.turno
            # recurso diferente (ex: laboratório e projetor) nunca emenda,
            # mesmo com horário contíguo — são reservas de coisas distintas
            and atual.recurso == a.recurso
            # emenda exata, OU só um intervalo de recreio no meio
            and 0 <= (_minutos(a.inicio) - _minutos(atual.fim)) <= TOLERANCIA_RECREIO_MIN
        ):
            atual.fim = a.fim
            atual.numero_aulas += 1
            atual.slots.append(a)
            if a.conteudo and a.conteudo not in atual.conteudo:
                atual.conteudo = (atual.conteudo + " | " + a.conteudo).strip(" |")
        else:
            if atual is not None:
                grupos.append(atual)
            atual = AtividadeAgrupada(
                data=a.data,
                inicio=a.inicio,
                fim=a.fim,
                professor=a.professor,
                disciplina=a.disciplina,
                turma=a.turma,
                conteudo=a.conteudo,
                numero_aulas=1,
                turno=a.turno,
                recurso=a.recurso,
                slots=[a],
            )
    if atual is not None:
        grupos.append(atual)

    # A ordenação lá em cima precisa vir por professor/disciplina/turma —
    # é ela que faz as aulas emendadas ficarem lado a lado para serem
    # agrupadas. Só que essa ordem sobrava na saída, e a lista aparecia
    # embaralhada (uma aula das 14h antes de uma das 9h), tanto na janela
    # quanto no terminal. Aqui reordenamos por dia e horário, que é como
    # a pessoa lê a própria agenda.
    grupos.sort(key=lambda g: (g.data, g.inicio, g.professor))

    return grupos
