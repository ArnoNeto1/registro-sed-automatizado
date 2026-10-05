# -*- coding: utf-8 -*-
"""
O .gitignore protege o que NUNCA pode subir para o repositório público (CPF
e senha, login do Google, o segredo do servidor...). O Git NÃO aceita
comentário na mesma linha do nome: ".env    # CPF" vira um padrão que não
casa com nada, e o arquivo sobe sem ninguém perceber. Estes testes garantem
as duas coisas: comentário só em linha própria, e cada nome protegido
presente como padrão exato.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

PROTEGIDOS = (
    ".env",
    "configuracao.json",
    "browser_profile/",
    "registros_enviados.json",
    "aulas_nao_realizadas.json",
    "ultimo_professor.txt",
    "servidor_ia.json",
    ".vercel/",
    "id_instalacao.txt",
    "ultima_contagem.txt",
    "modo_teste.txt",
)


def _linhas() -> list:
    texto = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    return [linha.rstrip("\r") for linha in texto.split("\n")]


class GitIgnore(unittest.TestCase):
    def test_nenhum_comentario_na_mesma_linha_do_nome(self):
        ruins = [l for l in _linhas() if l.strip() and not l.lstrip().startswith("#") and "#" in l]
        self.assertEqual(
            ruins, [], "o Git trata a linha inteira como nome do arquivo: ponha o comentário numa linha só dele"
        )

    def test_o_que_nunca_pode_subir_esta_na_lista_com_o_nome_exato(self):
        padroes = {l.rstrip() for l in _linhas() if l.strip() and not l.lstrip().startswith("#")}
        faltando = [nome for nome in PROTEGIDOS if nome not in padroes]
        self.assertEqual(faltando, [])


if __name__ == "__main__":
    unittest.main()
