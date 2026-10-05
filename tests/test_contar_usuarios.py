# -*- coding: utf-8 -*-
"""
Testes do leitor de totais (contar_usuarios.py) — sem internet: o servidor
da escola é de mentira.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import sys
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contar_usuarios  # noqa: E402

TOTAIS = {
    "atualizado_em": "2026-10-05 12:00",
    "hoje": 7,
    "ontem": 9,
    "ultimos_7_dias": 14,
    "ultimos_30_dias": 21,
    "desde_o_inicio": 30,
    "por_versao": {"2.1.0": 12, "2.0.1": 9},
    "aviso": "contagem aproximada de computadores (instalações), não de pessoas",
}


class _Servidor(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        corpo = json.dumps(TOTAIS).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_args):
        pass


class Leitura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.endereco = f"http://127.0.0.1:{cls.servidor.server_address[1]}/api/uso"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def test_busca_os_totais(self):
        self.assertEqual(contar_usuarios.buscar(self.endereco), TOTAIS)

    def test_texto_traz_todos_os_numeros_e_a_explicacao(self):
        texto = contar_usuarios.montar_texto(TOTAIS)
        for esperado in ("hoje", "7", "ontem", "9", "14", "21", "30", "2.1.0", "12", "2.0.1"):
            self.assertIn(esperado, texto)
        self.assertIn("não são pessoas", texto.lower())

    def test_texto_sem_ninguem_por_versao(self):
        texto = contar_usuarios.montar_texto({"hoje": 0, "por_versao": {}})
        self.assertIn("ainda ninguém", texto)

    def test_main_imprime(self):
        saida = io.StringIO()
        original = sys.argv
        sys.argv = ["contar_usuarios.py", self.endereco]
        try:
            with redirect_stdout(saida):
                contar_usuarios.main()
        finally:
            sys.argv = original
        self.assertIn("desde o início", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
