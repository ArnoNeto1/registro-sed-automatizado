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
from dataclasses import dataclass, field

from config import AGENDA_LOGIN_URL, AGENDA_URL, DISCIPLINAS_IGNORADAS

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
    slots: list = field(default_factory=list)


def login(page, cpf: str, senha: str) -> None:
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
        "verifique se o site mudou de layout."
    )


def scrape_week(page, monday: dt.date, turnos: list[str] | None = None) -> list[Agendamento]:
    """Coleta todos os agendamentos da semana que começa em `monday`."""
    turnos = turnos or TURNOS
    page.goto(AGENDA_URL, wait_until="domcontentloaded", timeout=60000)
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
        todos.extend(_scrape_current_view(page, turno))

    return todos


def filtrar_e_agrupar(
    agendamentos: list[Agendamento],
    professor_filtro: str | None = None,
) -> list[AtividadeAgrupada]:
    """
    Remove disciplinas ignoradas (formação/reunião interna), opcionalmente
    filtra por professor, e agrupa slots contíguos (mesmo dia + professor +
    disciplina + turma, horário emendado) em uma única atividade — cada 45
    min conta como 1 aula, conforme as regras do formulário da SED.
    """
    relevantes = [
        a
        for a in agendamentos
        if a.disciplina not in DISCIPLINAS_IGNORADAS
        and (professor_filtro is None or a.professor.strip().lower() == professor_filtro.strip().lower())
    ]

    # ordena por dia, professor, disciplina, turma, horário de início
    relevantes.sort(key=lambda a: (a.data, a.turno, a.professor, a.disciplina, a.turma, a.inicio))

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
            and atual.fim == a.inicio  # slot contíguo (emenda exata)
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
