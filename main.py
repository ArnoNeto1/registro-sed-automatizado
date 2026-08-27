# -*- coding: utf-8 -*-
"""
Preenchimento automático do formulário da SED-SC a partir da agenda do
laboratório do NTE Blumenau.

USO BÁSICO
----------
    python main.py --semana 2026-08-17

Isso vai:
  1. Logar no site de agendamento (nteblumenau.com.br) usando as credenciais
     do arquivo .env;
  2. Ler todos os agendamentos da semana informada (qualquer dia dessa
     semana serve — o script acha a segunda-feira sozinho);
  3. Agrupar aulas emendadas da mesma turma/disciplina em uma única
     atividade (contando quantas "aulas de 45min" foram usadas);
  4. Para cada atividade, perguntar no terminal o número de estudantes
     atendidos e quais recursos do laboratório foram usados (isso NÃO está
     disponível no site de agendamento, por isso é sempre perguntado);
  5. Abrir o formulário da SED no navegador e preencher tudo automaticamente
     até a última página;
  6. Mostrar um resumo e pedir confirmação explícita antes de clicar em
     "Enviar" — nada é enviado sem você digitar "s".

Na PRIMEIRA vez que você usar o formulário, uma janela do Chrome vai abrir
pedindo login da conta Google da SED — faça o login manualmente uma vez; a
sessão fica salva em ./browser_profile e não será pedida de novo enquanto
essa pasta existir.

Veja README.md para instruções completas e .env.example para configurar
suas credenciais.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# O .env precisa ser carregado ANTES do "from config import ...", porque o
# config lê os dados do ambiente no momento em que é importado. Se o
# load_dotenv() vier depois (como estava, lá dentro do main()), o arquivo
# .env é ignorado para nome, escola e regional — e o script usa os valores
# padrão do config sem avisar ninguém.
from caminhos import abrir_contexto, caminho_de_dados, pasta_de_dados  # noqa: E402

load_dotenv(pasta_de_dados() / ".env")
from playwright.sync_api import sync_playwright

from agenda_scraper import TURNOS, filtrar_e_agrupar, login, scrape_week  # noqa: E402
from config import (  # noqa: E402
    PROFESSOR_FILTRO,
    RECURSOS_PADRAO,
    disciplina_tem_mapeamento,
    etapa_para_turma,
    resolver_componente,
)
from sed_form_filler import (  # noqa: E402
    enviar,
    preencher_atividade_com_estudantes,
    preencher_dados_fixos,
)

try:
    from zoneinfo import ZoneInfo

    FUSO_SC = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover - fallback muito raro (Python sem tzdata)
    FUSO_SC = None

RECURSOS_DISPONIVEIS = [
    "Lousa Digital",
    "Computadores/notebooks (pesquisa) no laboratório",
    "Computadores/notebooks (software/programa) no laboratório",
    "Computadores/notebooks (edição de imagens/vídeos) no laboratório",
    "Computadores/notebooks (sites educacionais) no laboratório",
    "Celulares",
    "Tablets",
    "Notebooks (recurso móvel para sala de aula)",
    # existe no formulário e faltava aqui — conferido na estrutura da SED
    "Outros recursos",
]

PROFILE_DIR = caminho_de_dados("browser_profile")
ESTADO_FILE = caminho_de_dados("registros_enviados.json")


def chave_grupo(g) -> str:
    return f"{g.data}|{g.inicio}|{g.fim}|{g.professor}|{g.disciplina}|{g.turma}"


# Depois de quanto tempo uma chave (aula) some sozinha do histórico. Um mês
# é folga de sobra: a SED não deixa registrar aula de mês passado, e
# ninguém reabre a agenda tão velha assim — o único motivo de guardar a
# chave é evitar duplicar um registro enquanto a aula ainda pode aparecer
# de novo na tela.
DIAS_PARA_ESQUECER = 30


def _data_da_chave(chave: str):
    """
    A primeira parte de toda chave é a data (AAAA-MM-DD) — ver
    `chave_grupo()`. Devolve None se não conseguir entender: uma chave
    num formato inesperado é melhor guardar para sempre por engano do
    que apagar por engano (o preço de guardar demais é um arquivo um
    pouco maior; o de apagar demais é duplicar registro na SED).
    """
    try:
        return dt.date.fromisoformat(chave.split("|", 1)[0])
    except (ValueError, IndexError):
        return None


def purgar_antigas(chaves: set, dias: int = DIAS_PARA_ESQUECER) -> set:
    """
    Tira do conjunto as chaves de aulas com mais de `dias` dias.

    Sem isto, `registros_enviados.json` (e `aulas_nao_realizadas.json`,
    que usa o mesmo formato de chave — ver app.py) cresceriam para
    sempre: nada nunca saía de lá.
    """
    hoje = agora_sc().date()
    atuais = set()
    for chave in chaves:
        data = _data_da_chave(chave)
        if data is None or (hoje - data).days <= dias:
            atuais.add(chave)
    return atuais


def carregar_enviados() -> set:
    """
    Lê o histórico do que já foi enviado à SED — e aproveita para
    esquecer sozinho o que passou de `DIAS_PARA_ESQUECER`.

    Um .json corrompido (queda de luz, antivírus no meio de uma escrita)
    não pode derrubar o programa — mas também não pode ficar em silêncio
    absoluto aqui: é este arquivo que impede reenviar pra SED uma aula já
    registrada. Por isso quem chama (main() / app.py) avisa a pessoa
    quando `estado_corrompido` vem True, em vez de só seguir como se o
    histórico estivesse vazio de verdade.
    """
    if not os.path.exists(ESTADO_FILE):
        return set()
    try:
        with open(ESTADO_FILE, "r", encoding="utf-8") as f:
            enviados = set(json.load(f))
    except Exception:
        return set()
    atuais = purgar_antigas(enviados)
    if len(atuais) != len(enviados):
        # a limpeza só é gravada quando tira algo de verdade — uma leitura
        # comum não precisa reescrever o arquivo à toa
        _escrever_estado(atuais)
    return atuais


def estado_corrompido() -> bool:
    """O ESTADO_FILE existe, mas não é um .json válido?"""
    if not os.path.exists(ESTADO_FILE):
        return False
    try:
        with open(ESTADO_FILE, "r", encoding="utf-8") as f:
            json.load(f)
        return False
    except Exception:
        return True


def _escrever_estado(enviados: set) -> None:
    """
    Grava o histórico de forma atômica: escreve num arquivo temporário ao
    lado e só troca de nome no final (`os.replace` é atômico no Windows
    dentro da mesma pasta). Uma queda de luz ou fechamento forçado no
    meio de uma escrita comum (abrir em "w", que já zera o arquivo antes
    de escrever) deixaria o .json pela metade — corrompido — e o próximo
    carregamento esqueceria tudo que já foi enviado, arriscando duplicar
    registro na SED. Com o arquivo temporário, ou a troca acontece
    inteira, ou o arquivo antigo (íntegro) continua valendo.
    """
    tmp = ESTADO_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(enviados), f, ensure_ascii=False, indent=2)
    os.replace(tmp, ESTADO_FILE)


def marcar_enviado(chave: str) -> None:
    enviados = carregar_enviados()
    enviados.add(chave)
    _escrever_estado(enviados)


def agora_sc() -> dt.datetime:
    if FUSO_SC is not None:
        return dt.datetime.now(FUSO_SC)
    return dt.datetime.now()  # fallback: horário local da máquina


def ja_comecou(grupo, agora: dt.datetime) -> bool:
    """
    Regra de ouro: nunca adiantar aula futura. Só considera uma atividade se
    ela já começou (está acontecendo agora ou já terminou) — nunca uma que
    ainda vai acontecer mais tarde no mesmo dia.
    """
    data = dt.date.fromisoformat(grupo.data)
    hora_inicio = dt.datetime.strptime(grupo.inicio, "%H:%M").time()
    inicio_dt = dt.datetime.combine(data, hora_inicio, tzinfo=agora.tzinfo)
    return inicio_dt <= agora


def monday_of(data: dt.date) -> dt.date:
    return data - dt.timedelta(days=data.weekday())


def perguntar_numero(prompt: str) -> int:
    while True:
        raw = input(prompt).strip().replace(",", "")
        if raw.isdigit():
            return int(raw)
        print("  Digite apenas números inteiros.")


def perguntar_recursos() -> list[str]:
    print("  Recursos disponíveis:")
    for i, r in enumerate(RECURSOS_DISPONIVEIS, start=1):
        print(f"    {i}. {r}")
    raw = input("  Quais foram usados? (números separados por vírgula): ").strip()
    indices = [int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()]
    return [RECURSOS_DISPONIVEIS[i - 1] for i in indices if 1 <= i <= len(RECURSOS_DISPONIVEIS)]


def perguntar_etapa_manual() -> str:
    opcoes = [
        "Ensino Fundamental - Anos Iniciais",
        "Ensino Fundamental - Anos Finais",
        "Ensino Médio",
        "Ensino Profissional",
        "Educação de Jovens e Adultos",
        "Educação Especial (AEE)",
    ]
    print("  Não consegui deduzir a etapa a partir da turma. Escolha:")
    for i, o in enumerate(opcoes, start=1):
        print(f"    {i}. {o}")
    while True:
        raw = input("  Número da etapa: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(opcoes):
            return opcoes[int(raw) - 1]


def main() -> None:
    # (o .env já foi carregado no topo do arquivo, antes dos imports)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--semana",
        default=dt.date.today().isoformat(),
        help="Qualquer data (YYYY-MM-DD) dentro da semana a processar. Padrão: hoje.",
    )
    parser.add_argument(
        "--turnos",
        default=",".join(TURNOS),
        help=f"Turnos a ler, separados por vírgula. Padrão: {','.join(TURNOS)}",
    )
    parser.add_argument(
        "--professor",
        default=PROFESSOR_FILTRO,
        help="Filtra pelo nome do professor exatamente como aparece na agenda. "
        "Padrão: valor de PROFESSOR_FILTRO no .env (ou todos, se vazio).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Só lê e mostra os agendamentos agrupados, sem abrir o formulário da SED.",
    )
    parser.add_argument(
        "--auto-submit",
        action="store_true",
        help="Pula a confirmação manual e clica em Enviar automaticamente. "
        "Use com cuidado — recomendado só depois de validar bastante o fluxo.",
    )
    parser.add_argument(
        "--incluir-futuras",
        action="store_true",
        help="Mostra também aulas que ainda vão acontecer mais tarde (só para "
        "conferência com --dry-run). Por padrão, aulas futuras nunca são "
        "processadas nem enviadas — regra de ouro: só depois que aconteceu.",
    )
    parser.add_argument(
        "--perguntar-recursos",
        action="store_true",
        help="Pergunta no terminal quais recursos foram usados em cada aula, em "
        f"vez de usar os padrões automaticamente ({', '.join(RECURSOS_PADRAO)}).",
    )
    args = parser.parse_args()

    data_semana = monday_of(dt.date.fromisoformat(args.semana))
    turnos = [t.strip() for t in args.turnos.split(",") if t.strip()]

    cpf = os.environ.get("AGENDA_CPF")
    senha = os.environ.get("AGENDA_SENHA")
    if not args.dry_run and (not cpf or not senha):
        sys.exit(
            "Defina AGENDA_CPF e AGENDA_SENHA no arquivo .env (veja .env.example) "
            "antes de rodar sem --dry-run."
        )

    with sync_playwright() as p:
        context, _nome = abrir_contexto(
            p,
            PROFILE_DIR,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()

        print(f"Lendo agenda da semana de {data_semana.isoformat()} ({', '.join(turnos)})...")
        login(page, cpf or "", senha or "")
        agendamentos = scrape_week(page, data_semana, turnos)
        grupos_todos = filtrar_e_agrupar(agendamentos, args.professor)

        agora = agora_sc()
        enviados = carregar_enviados()
        grupos_futuros = [g for g in grupos_todos if not ja_comecou(g, agora)]
        grupos = grupos_todos if args.incluir_futuras else [g for g in grupos_todos if ja_comecou(g, agora)]

        if not grupos:
            print("Nenhuma atividade encontrada com esses filtros (que já tenha começado).")
            if grupos_futuros and not args.incluir_futuras:
                print(
                    f"  ({len(grupos_futuros)} aula(s) futura(s) nessa semana foram "
                    "ignoradas — use --incluir-futuras só para conferir, nunca para enviar.)"
                )
            context.close()
            return

        print(f"\n{len(grupos)} atividade(s) encontrada(s):\n")
        for i, g in enumerate(grupos, start=1):
            futura = " [AINDA NÃO ACONTECEU]" if not ja_comecou(g, agora) else ""
            ja_enviado = " [JÁ ENVIADO ANTERIORMENTE]" if chave_grupo(g) in enviados else ""
            print(
                f"  [{i}] {g.data} {g.inicio}-{g.fim}  {g.professor}  "
                f"{g.disciplina}  |  {g.turma}  ({g.numero_aulas} aula(s)){futura}{ja_enviado}"
            )
            if not disciplina_tem_mapeamento(g.disciplina):
                print(
                    "      Aviso: essa disciplina não está mapeada em "
                    "config.DISCIPLINA_PARA_COMPONENTE — vai marcar 'Outro:' "
                    f"com o texto '{g.disciplina}' (como está na agenda)."
                )

        if args.dry_run:
            context.close()
            return

        for g in grupos:
            if not ja_comecou(g, agora):
                # Só chega aqui com --incluir-futuras; nunca processa/envia.
                continue
            if chave_grupo(g) in enviados:
                continue  # já enviado numa execução anterior — não repete

            etapa = etapa_para_turma(g.turma) or perguntar_etapa_manual()

            print(f"\n--- {g.data} {g.inicio}-{g.fim}  {g.professor}  {g.disciplina}  ({g.turma}) ---")
            resp_aconteceu = input("  Essa aula realmente aconteceu? [s/N]: ").strip().lower()
            if resp_aconteceu != "s":
                print("  Pulado — não registrado (aula não confirmada).")
                continue

            numero_estudantes = perguntar_numero(
                f"  Número de estudantes atendidos nas {g.numero_aulas} aula(s): "
            )
            recursos = perguntar_recursos() if args.perguntar_recursos else list(RECURSOS_PADRAO)

            resumo_projeto = f"{g.disciplina} ({g.turma}) - Prof(a). {g.professor} - {g.inicio}-{g.fim}"
            conteudos = g.conteudo or resumo_projeto

            preencher_dados_fixos(page)
            preencher_atividade_com_estudantes(
                page,
                disciplina_agendamento=g.disciplina,
                etapa=etapa,
                resumo_projeto=resumo_projeto,
                numero_aulas=g.numero_aulas,
                numero_estudantes=numero_estudantes,
                conteudos_abordados=conteudos,
                recursos_utilizados=recursos,
            )

            componente_resumo = resolver_componente(g.disciplina, etapa)
            if componente_resumo is None:
                componente_resumo = ("OUTRO", g.disciplina)
            print("\n  Resumo do que será enviado:")
            print(f"    Etapa: {etapa}")
            print(f"    Componente(s): {componente_resumo}")
            print(f"    Resumo: {resumo_projeto}")
            print(f"    Nº aulas: {g.numero_aulas}  |  Nº estudantes: {numero_estudantes}")
            print(f"    Conteúdos: {conteudos}")
            print(f"    Recursos: {recursos}")

            if args.auto_submit:
                enviar(page)
                marcar_enviado(chave_grupo(g))
                print("  Enviado automaticamente (--auto-submit).")
            else:
                resp = input("  Enviar este registro para a SED agora? [s/N]: ").strip().lower()
                if resp == "s":
                    enviar(page)
                    marcar_enviado(chave_grupo(g))
                    print("  Enviado.")
                else:
                    print("  Pulado (não enviado). A aba ficou aberta para revisão manual.")

        context.close()


if __name__ == "__main__":
    main()
