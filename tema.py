# -*- coding: utf-8 -*-
"""
Tema da interface: claro, escuro, ou igual ao do Windows.

USADO POR app.py E configuracao.py — os dois pedem a paleta atual aqui
em vez de cravar cores no próprio código, para que trocar de tema
(guardado dentro de "Meus dados", na tela principal) valha nos dois
lugares: a tela principal e as telas de entrar/cadastrar.

POR QUE É UMA PREFERÊNCIA DO COMPUTADOR, NÃO DE CADA PROFESSOR
----------------------------------------------------------------
Igual a escola configurada, o tema é sobre O MONITOR daquele
computador/laboratório (claro para uma sala iluminada, escuro para uma
sala escura ou de manhã cedo) — não sobre quem está logado no momento.
Por isso fica junto do resto em configuracao.json, e não é apagado
quando a pessoa sai da conta.

POR QUE NÃO MUDA AO VIVO
----------------------------------------------------------------
Trocar tema sem reabrir exigiria reconfigurar CADA estilo já em uso e
torcer para nenhum widget escapar — arriscado, e o programa já tem um
jeito consagrado de aplicar mudança de configuração: "salve e reabra"
(o mesmo usado para nome/CPF/turnos em "Meus dados"). Reaproveitado
aqui de propósito, em vez de inventar um sistema de troca ao vivo só
para isto.

NÃO FUNCIONA (silenciosamente) FORA DO WINDOWS
----------------------------------------------------------------
sistema_esta_escuro() lê uma chave do Registro do Windows que só existe
lá — é o único sistema onde este programa roda de verdade (ver
caminhos.py). Em qualquer outro lugar, ou se a chave não existir por
algum motivo, "Sistema" se comporta como "Claro".
"""

from __future__ import annotations

CLARO = "claro"
ESCURO = "escuro"
SISTEMA = "sistema"
OPCOES = (CLARO, ESCURO, SISTEMA)

ROTULOS = {
    CLARO: "Claro",
    ESCURO: "Escuro",
    SISTEMA: "Igual ao sistema",
}

# Cada chave é usada em pelo menos um lugar de app.py ou configuracao.py
# — não é uma paleta "genérica", é o inventário real das cores que a
# tela usa hoje, com uma versão escura de cada uma. "campo" é o fundo
# das caixas de digitação (Entry/Combobox/Text) — em telas claras é
# igual ao cartão (branco), mas no escuro precisa ser um tom que não se
# confunda com o cartão em volta, senão a caixa de digitar some visualmente.
PALETA_CLARA = {
    "fundo": "#f4f6f8",
    "fundo_dialogo": "#eef1f5",
    "cartao": "#ffffff",
    "campo": "#ffffff",
    "texto": "#1f2933",
    "suave": "#6b7280",
    "destaque": "#2f6f4e",
    "selecao_bg": "#4a5568",
    "selecao_fg": "#ffffff",
    "verde_pisca": ("#dff3e7", "#7fd4a8"),
    "azul": "#1d5fa8",
    "laranja": "#a1663a",
    "cinza": "#9aa5b1",
    "sugerida_bg": "#dff3e7",
    "sugerida_fg": "#14532d",
    "sugerida_fg_selecionada": "#0b3d26",
}


# "suave" e "cinza" ficaram um pouco mais claros do que a primeira
# tentativa (#9aa0a6 e #7a828c) depois de uma revisão adversarial
# calcular o contraste (fórmula WCAG) contra "campo"/"cartao"/"fundo" —
# as cores originais ficavam abaixo do mínimo de 4,5:1 pra texto normal
# contra pelo menos um desses fundos, ficando fracas de mais pra ler
# (ex: o texto "· outro turno" ou "Selecione uma escola").
PALETA_ESCURA = {
    "fundo": "#1e2124",
    "fundo_dialogo": "#1a1d1f",
    "cartao": "#2a2d31",
    "campo": "#35393e",
    "texto": "#e8eaed",
    "suave": "#a5abb1",
    "destaque": "#4caf7d",
    "selecao_bg": "#3f4650",
    "selecao_fg": "#ffffff",
    "verde_pisca": ("#1f3d2e", "#3f7a5c"),
    "azul": "#6fa8dc",
    "laranja": "#d99a5b",
    "cinza": "#a3aeb9",
    "sugerida_bg": "#1f3d2e",
    "sugerida_fg": "#8fd9b0",
    "sugerida_fg_selecionada": "#c3f0d9",
}


def sistema_esta_escuro() -> bool:
    """
    Confere o modo claro/escuro do Windows — a mesma chave que o próprio
    Windows usa para decidir se o Explorer e a barra de tarefas aparecem
    claros ou escuros.
    """
    try:
        import winreg

        chave = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        valor, _ = winreg.QueryValueEx(chave, "AppsUseLightTheme")
        return valor == 0
    except Exception:
        return False


def resolver_paleta(preferencia: str) -> dict:
    """
    A paleta pra usar AGORA, já resolvendo "sistema" pro que o Windows
    está usando neste instante. `preferencia` normalmente vem de
    `configuracao.carregar().get("tema", tema.SISTEMA)`.
    """
    escuro = preferencia == ESCURO or (
        preferencia not in (CLARO, ESCURO) and sistema_esta_escuro()
    )
    return PALETA_ESCURA if escuro else PALETA_CLARA
