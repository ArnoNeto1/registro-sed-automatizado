# -*- coding: utf-8 -*-
"""
Testes do contador de downloads (contar_downloads.py) — sem internet: a
resposta do GitHub é simulada.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contar_downloads  # noqa: E402


def _asset(nome: str, baixados: int) -> dict:
    return {"name": nome, "download_count": baixados}


RELEASES = [
    {
        "tag_name": "v2.0.0",
        "draft": False,
        "assets": [
            _asset("Registro-SED-Instalador.exe", 12),
            _asset("Registro-SED.exe", 40),
        ],
    },
    {"tag_name": "v1.9.3", "draft": False, "assets": [_asset("Registro-SED.exe", 7)]},  # sem instalador
    {"tag_name": "v1.0.0", "draft": False, "assets": []},  # sem arquivos
    {"tag_name": "v3.0.0", "draft": True, "assets": [_asset("Registro-SED.exe", 999)]},  # rascunho
    {
        "tag_name": "v1.5.0",
        "draft": False,
        "assets": [_asset("Registro-SED.exe", 3), _asset("Registro-SED.zip", 5)],  # arquivo de outro tipo
    },
]


class Resumo(unittest.TestCase):
    def test_conta_por_arquivo_e_ignora_rascunho(self):
        linhas = contar_downloads.resumir(RELEASES)
        self.assertEqual(
            linhas,
            [
                ("v2.0.0", 12, 40, 0),
                ("v1.9.3", 0, 7, 0),
                ("v1.0.0", 0, 0, 0),
                ("v1.5.0", 0, 3, 5),
            ],
        )

    def test_download_count_ausente_ou_nulo_conta_zero(self):
        linhas = contar_downloads.resumir(
            [{"tag_name": "v1", "assets": [{"name": "Registro-SED.exe", "download_count": None}, {"name": "Registro-SED-Instalador.exe"}]}]
        )
        self.assertEqual(linhas, [("v1", 0, 0, 0)])

    def test_sem_nenhuma_release(self):
        self.assertEqual(contar_downloads.resumir([]), [])


class Tabela(unittest.TestCase):
    def test_traz_cabecalho_linhas_e_total(self):
        texto = contar_downloads.montar_tabela(contar_downloads.resumir(RELEASES))
        self.assertIn("Instalador", texto)
        self.assertIn("v2.0.0", texto)
        ultima = texto.splitlines()[-1]
        self.assertTrue(ultima.startswith("TOTAL"))
        # 12 instaladores; 40+7+0+3 portátil/atualizações; 5 de outro tipo
        self.assertEqual(ultima.split(), ["TOTAL", "12", "50", "5"])
        self.assertNotIn("999", texto)  # o rascunho não aparece


class BuscaNoGitHub(unittest.TestCase):
    def _resposta(self, lote):
        corpo = io.BytesIO(json.dumps(lote).encode("utf-8"))
        corpo.__enter__ = lambda s: s  # type: ignore[attr-defined]
        corpo.__exit__ = lambda *a: False  # type: ignore[attr-defined]
        return corpo

    def test_segue_as_paginas_ate_acabar(self):
        pagina_cheia = [{"tag_name": f"v{i}", "assets": []} for i in range(100)]
        ultima = [{"tag_name": "v-ultima", "assets": []}]
        respostas = [self._resposta(pagina_cheia), self._resposta(ultima)]
        with mock.patch.object(contar_downloads.urllib.request, "urlopen", side_effect=respostas) as m:
            todas = contar_downloads.baixar_releases("dono/repo")
        self.assertEqual(len(todas), 101)
        enderecos = [c.args[0].full_url for c in m.call_args_list]
        self.assertIn("page=1", enderecos[0])
        self.assertIn("page=2", enderecos[1])
        self.assertIn("dono/repo", enderecos[0])

    def test_saida_do_programa_explica_o_que_cada_coluna_quer_dizer(self):
        with mock.patch.object(contar_downloads, "baixar_releases", return_value=RELEASES):
            saida = io.StringIO()
            with redirect_stdout(saida):
                contar_downloads.main()
        texto = saida.getvalue()
        self.assertIn("novas instalações", texto)
        self.assertIn("Não são pessoas diferentes", texto)


if __name__ == "__main__":
    unittest.main()
