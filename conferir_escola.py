# -*- coding: utf-8 -*-
"""
Confere se o nome da escola é um dos da lista da SED (escolas.py).

POR QUE EXISTE: o formulário da SED só aceita o texto EXATO de uma das opções
("EEB PROF JOAO WIDEMANN"). Nas versões 1.3 a 1.5 a escola do cadastro era uma
caixa em que dava para DIGITAR, e o que foi digitado ("EEE Profº João Widemann")
ficou salvo para sempre: as versões novas só leem o valor e o repetem, e o
formulário só descobria o problema depois de abrir o navegador, com um erro
técnico ("Não consegui confirmar a seleção... confira manualmente a janela do
Chrome") que ninguém entende. A tela "Meus dados" ainda repunha o valor errado
no campo e o gravava de novo.

O QUE FAZ, em ordem de segurança:
  - "certa": o nome é igual a um da lista. Nada a fazer.
  - "so_grafia": só a escrita difere (maiúsculas, acento, "Profº", espaço
    sobrando) e UMA escola da lista bate. Corrigir sozinho é seguro.
  - "sugerida": não bate, mas há escola parecida (outra sigla — "EEE" no lugar
    de "EEB" —, erro de digitação). NUNCA se troca sozinho: o registro iria
    para a escola errada na SED. Pergunta-se à pessoa.
  - "desconhecida": nada parecido. Só se explica o que fazer.
  - "vazia": não há escola salva (outras checagens cuidam disso).

Só biblioteca padrão e nada de tela: é usado pelo programa, pelo preenchimento
do formulário e pelos testes.
"""

from __future__ import annotations

import copy
import difflib
import re
import unicodedata
from collections import namedtuple

Conferencia = namedtuple("Conferencia", "situacao escola sugestoes")

# A primeira palavra costuma ser o tipo da escola; sem ela dá para achar a
# mesma escola escrita com outra sigla ("EEE Profº João Widemann").
_TIPOS_DE_ESCOLA = frozenset({"eeb", "eef", "eem", "eee", "cedup", "ceja", "ee", "ei", "eb", "emef"})
_SEMELHANCA_MINIMA = 0.8
_MAXIMO_DE_SUGESTOES = 3
_MAXIMO_DO_NOME_NO_AVISO = 40


def _lista_oficial() -> list:
    try:
        from escolas import ESCOLAS_CRE_BLUMENAU

        return list(ESCOLAS_CRE_BLUMENAU)
    except Exception:
        return []


def chave(texto) -> str:
    """
    O nome sem o que não muda a escola: maiúsculas, acento, pontuação, espaço
    sobrando e as formas de "Prof" ("Profº", "Profª", "Prof.", "Professor").
    O site do NTE, por exemplo, escreve "EEB Profº João Widemann" para a escola
    que a SED escreve "EEB PROF JOAO WIDEMANN".
    """
    t = unicodedata.normalize("NFD", str(texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").casefold()
    t = re.sub(r"\bprof(?:essora|essor)?[º°ª.]*", "prof", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def _parte_do_nome(chave_do_nome: str) -> str:
    """O nome sem a sigla do tipo da escola ("eee prof joao widemann" -> "prof joao widemann")."""
    palavras = chave_do_nome.split()
    if len(palavras) > 1 and palavras[0] in _TIPOS_DE_ESCOLA:
        palavras = palavras[1:]
    return " ".join(palavras)


def conferir(texto, oficiais=None) -> Conferencia:
    """
    Confere `texto` com a lista de escolas (`oficiais`, por padrão a de
    escolas.py). Devolve Conferencia(situacao, escola, sugestoes): `escola` só
    vem preenchida quando é seguro usá-la no lugar do texto ("certa" e
    "so_grafia"); `sugestoes` são até 3 escolas da lista, só para perguntar.
    """
    if texto is None or not str(texto).strip():
        return Conferencia("vazia", "", [])
    oficiais = list(_lista_oficial() if oficiais is None else oficiais)
    if not oficiais:
        # sem a lista não dá para julgar — e nada deve ser barrado por isso
        # (o cadastro, nesse caso, já deixa digitar livremente)
        return Conferencia("certa", texto, [])
    if texto in oficiais:
        return Conferencia("certa", texto, [])

    k = chave(texto)
    iguais = [o for o in oficiais if chave(o) == k]
    if len(iguais) == 1:
        return Conferencia("so_grafia", iguais[0], [])

    sugestoes = list(iguais)  # mais de uma igual: ambíguo, não dá para escolher sozinho
    parte = _parte_do_nome(k)
    if parte:
        sugestoes += [o for o in oficiais if o not in sugestoes and _parte_do_nome(chave(o)) == parte]
    if not sugestoes:
        por_chave = {chave(o): o for o in oficiais}
        for parecida in difflib.get_close_matches(k, list(por_chave), n=_MAXIMO_DE_SUGESTOES, cutoff=_SEMELHANCA_MINIMA):
            sugestoes.append(por_chave[parecida])
    sugestoes = sugestoes[:_MAXIMO_DE_SUGESTOES]
    if sugestoes:
        return Conferencia("sugerida", "", sugestoes)
    return Conferencia("desconhecida", "", [])


def diagnostico(escola: str, conferencia: Conferencia) -> str:
    """O que está errado, em português, com a sugestão quando há."""
    texto = (
        f'A escola do seu cadastro, "{escola}", não existe na lista da SED, '
        "por isso o programa não consegue marcá-la no formulário."
    )
    sugestoes = conferencia.sugestoes
    if len(sugestoes) == 1:
        texto += f' Pelo nome, deve ser "{sugestoes[0]}".'
    elif sugestoes:
        texto += " Pode ser uma destas: " + "; ".join(f'"{s}"' for s in sugestoes) + "."
    return texto


def explicar(escola: str, conferencia: Conferencia, no_env: bool = False) -> str:
    """O diagnóstico mais o que fazer. `no_env`: quem ainda usa o arquivo .env em vez da tela de cadastro."""
    if no_env:
        como = "Corrija a linha ESCOLA= do arquivo .env, escrevendo o nome exato da lista da SED, e abra o programa de novo."
    else:
        como = 'Clique em "Meus dados", escolha a sua escola na lista (é o nome exato que a SED usa) e salve.'
    return diagnostico(escola, conferencia) + " " + como


def escola_para_mostrar(valor_salvo, oficiais=None) -> tuple:
    """
    O que a tela "Meus dados" põe no campo da escola, como (texto, aviso).
    Nunca um valor que a lista da SED não tenha: só a grafia diferente entra já
    corrigida; o resto fica em branco, com um aviso, para a pessoa escolher.
    """
    conferencia = conferir(valor_salvo, oficiais)
    if conferencia.situacao == "vazia":
        return ("", "")
    if conferencia.situacao in ("certa", "so_grafia"):
        return (conferencia.escola, "")
    # CURTO de propósito: a tela "Meus dados" não rola, e num monitor de 768 px de altura cada linha
    # a mais pode empurrar o botão Salvar para fora da tela (por isso o nome salvo também é cortado).
    mostrado = str(valor_salvo).strip()
    if len(mostrado) > _MAXIMO_DO_NOME_NO_AVISO:
        mostrado = mostrado[: _MAXIMO_DO_NOME_NO_AVISO - 1].rstrip() + "…"
    aviso = f'Estava salva "{mostrado}", que não está na lista da SED.'
    sugestoes = conferencia.sugestoes
    if len(sugestoes) == 1:
        aviso += f' Parece ser "{sugestoes[0]}": escolha-a na lista.'
    elif sugestoes:
        aviso += " Pode ser: " + "; ".join(sugestoes[:2]) + ". Escolha na lista."
    else:
        aviso += " Escolha a correta na lista."
    return ("", aviso)


def corrigir_escola(dados: dict, antiga: str, nova: str) -> dict:
    """
    O conteúdo do configuracao.json com `antiga` trocada por `nova` em todo
    lugar que a guarda (escola padrão do computador, lista de escolas de cada
    professor e os turnos por escola), sem perder professores nem turnos.
    Não altera o dicionário recebido.
    """
    novo = copy.deepcopy(dados or {})
    if novo.get("escola") == antiga:
        novo["escola"] = nova
    for professor in novo.get("professores") or []:
        if not isinstance(professor, dict):
            continue
        if professor.get("escola") == antiga:
            professor["escola"] = nova
        if isinstance(professor.get("escolas"), list):
            trocadas = [nova if escola == antiga else escola for escola in professor["escolas"]]
            professor["escolas"] = list(dict.fromkeys(trocadas))  # sem repetir, na mesma ordem
        turnos = professor.get("turnos_por_escola")
        if isinstance(turnos, dict) and antiga in turnos:
            marcados = turnos.pop(antiga)
            turnos.setdefault(nova, marcados)  # se a certa já tinha turnos, valem os dela
    return novo
