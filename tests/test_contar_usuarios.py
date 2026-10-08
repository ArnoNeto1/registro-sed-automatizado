# -*- coding: utf-8 -*-
"""
Testes do leitor de totais (contar_usuarios.py) — sem internet: o servidor
da escola é de mentira.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

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
    "escolas_diferentes": 2,
    "escolas_ultimos_30_dias": 1,
    "aviso": "contagem aproximada de computadores (instalações), não de pessoas",
}
SENHA = "senha-de-teste-do-painel"
DETALHE = {
    "atualizado_em": "2026-10-05 12:00",
    "escolas": [
        {"escola": "EEB PEDRO II", "computadores": 2, "ultimo_uso": "2026-10-05"},
        {"escola": "EEB SANTOS DUMONT", "computadores": 1, "ultimo_uso": "2026-08-30"},
    ],
    "aviso": "computadores por escola são aproximados",
}
OFICIAIS = ["COORDENADORIA", "EEB PEDRO II", "EEB SANTOS DUMONT", "EEB VICTOR HERING"]
CONSULTAS: list = []  # (caminho, senha recebida) de cada pedido que chegou


class _Servidor(BaseHTTPRequestHandler):
    def _responder(self, status, dados):
        corpo = json.dumps(dados).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):  # noqa: N802
        senha = self.headers.get("x-painel-token")
        CONSULTAS.append((self.path, senha))
        if "detalhe=escolas" not in self.path:
            self._responder(200, TOTAIS)
        elif senha == "servidor-sem-painel":
            self._responder(503, {"erro": "O painel ainda não está configurado."})
        elif senha != SENHA:
            self._responder(401, {"erro": "Senha do painel não reconhecida."})
        else:
            self._responder(200, DETALHE)

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


class Escolas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.endereco = f"http://127.0.0.1:{cls.servidor.server_address[1]}/api/uso"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        CONSULTAS.clear()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        ambiente = mock.patch.dict(os.environ, {"APPDATA": self.pasta.name})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop(contar_usuarios.VARIAVEL_SENHA, None)

    def guardar_senha(self, texto: str) -> None:
        pasta = Path(self.pasta.name) / "RegistroSED"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / contar_usuarios.ARQUIVO_SENHA).write_text(texto, encoding="utf-8")

    def rodar_main(self) -> str:
        saida = io.StringIO()
        original = sys.argv
        sys.argv = ["contar_usuarios.py", self.endereco]
        try:
            with redirect_stdout(saida):
                contar_usuarios.main()
        finally:
            sys.argv = original
        return saida.getvalue()

    # -- os números de escolas, que são públicos
    def test_texto_traz_os_numeros_de_escolas(self):
        texto = contar_usuarios.montar_texto(TOTAIS)
        self.assertIn("Escolas", texto)
        self.assertRegex(texto, r"já apareceram \.+ 2")
        self.assertRegex(texto, r"últimos 30 dias \.+ 1")
        self.assertIn("2.3.0", texto)  # a escola só vem de quem já atualizou

    def test_servidor_sem_numeros_de_escolas_nao_inventa_a_secao(self):
        self.assertNotIn("Escolas", contar_usuarios.montar_texto({"hoje": 0, "por_versao": {}}))

    # -- a lista de quais escolas, que só abre com a senha
    def test_busca_a_lista_mandando_a_senha_no_cabecalho_e_nao_no_endereco(self):
        self.assertEqual(contar_usuarios.buscar_escolas(self.endereco, SENHA), DETALHE)
        caminho, senha = CONSULTAS[-1]
        self.assertEqual(senha, SENHA)
        self.assertNotIn(SENHA, caminho)

    def test_senha_errada_vira_um_aviso_claro(self):
        with self.assertRaises(contar_usuarios.PainelFechado) as erro:
            contar_usuarios.buscar_escolas(self.endereco, "errada")
        self.assertIn("senha", str(erro.exception).lower())
        self.assertNotIn("errada", str(erro.exception))

    def test_painel_nao_configurado_no_servidor_vira_um_aviso_claro(self):
        with self.assertRaises(contar_usuarios.PainelFechado) as erro:
            contar_usuarios.buscar_escolas(self.endereco, "servidor-sem-painel")
        self.assertIn("configurado", str(erro.exception))

    def test_texto_com_a_lista_mostra_as_escolas_e_quem_ainda_nao_apareceu(self):
        texto = contar_usuarios.montar_texto(TOTAIS, DETALHE, OFICIAIS)
        for esperado in ("EEB PEDRO II", "EEB SANTOS DUMONT", "2026-10-05", "2026-08-30"):
            self.assertIn(esperado, texto)
        self.assertRegex(texto, r"EEB PEDRO II \.+ +2 +2026-10-05")
        self.assertIn("Ainda não apareceram (2 de 4)", texto)
        faltando = texto.split("Ainda não apareceram")[1]
        self.assertIn("COORDENADORIA", faltando)
        self.assertIn("EEB VICTOR HERING", faltando)
        self.assertNotIn("EEB PEDRO II", faltando)

    def test_texto_sem_a_lista_explica_como_ver(self):
        texto = contar_usuarios.montar_texto(TOTAIS, None, OFICIAIS, "Para ver QUAIS escolas, falta a senha do painel.")
        self.assertIn("Para ver QUAIS escolas", texto)
        self.assertNotIn("EEB PEDRO II", texto)

    # -- onde a senha fica: só no computador do mantenedor
    def test_senha_vem_do_ambiente_ou_do_arquivo_e_o_ambiente_ganha(self):
        self.assertEqual(contar_usuarios.senha_do_painel(), "")
        self.guardar_senha("  da-pasta\n")
        self.assertEqual(contar_usuarios.senha_do_painel(), "da-pasta")
        os.environ[contar_usuarios.VARIAVEL_SENHA] = " do-ambiente "
        self.assertEqual(contar_usuarios.senha_do_painel(), "do-ambiente")

    def test_arquivo_da_senha_fica_fora_do_repositorio(self):
        raiz = Path(contar_usuarios.__file__).resolve().parent
        self.guardar_senha("x")
        pasta = Path(os.environ["APPDATA"]).resolve()
        self.assertNotIn(raiz, [pasta, *pasta.parents])
        self.assertFalse((raiz / contar_usuarios.ARQUIVO_SENHA).exists())

    def test_main_com_senha_mostra_a_lista(self):
        os.environ[contar_usuarios.VARIAVEL_SENHA] = SENHA
        saida = self.rodar_main()
        self.assertIn("EEB PEDRO II", saida)
        self.assertIn("Ainda não apareceram", saida)

    def test_main_sem_senha_mostra_so_numeros_e_a_dica(self):
        saida = self.rodar_main()
        self.assertIn("desde o início", saida)
        self.assertNotIn("EEB PEDRO II", saida)
        self.assertIn(contar_usuarios.ARQUIVO_SENHA, saida)
        self.assertEqual([senha for _caminho, senha in CONSULTAS if "detalhe" in _caminho], [])  # nem tentou

    def test_main_com_senha_errada_avisa_e_nao_imprime_a_senha(self):
        os.environ[contar_usuarios.VARIAVEL_SENHA] = "senha-errada-de-teste"
        saida = self.rodar_main()
        self.assertIn("desde o início", saida)  # os números continuam saindo
        self.assertIn("senha", saida.lower())
        self.assertNotIn("senha-errada-de-teste", saida)
        self.assertNotIn("EEB PEDRO II", saida)

    def test_a_senha_do_painel_nunca_aparece_na_saida(self):
        os.environ[contar_usuarios.VARIAVEL_SENHA] = SENHA
        self.assertNotIn(SENHA, self.rodar_main())


if __name__ == "__main__":
    unittest.main()
