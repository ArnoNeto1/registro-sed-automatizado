# -*- coding: utf-8 -*-
"""
Testes da contagem anônima do lado do programa (contagem.py) — sem
internet: o servidor da escola é de mentira e a pasta de dados é temporária.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import contagem  # noqa: E402

PEDIDOS: list = []
RESPOSTA = {"status": 200}


class _ServidorDeMentira(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (nome exigido pelo http.server)
        tamanho = int(self.headers.get("Content-Length") or 0)
        PEDIDOS.append(
            {
                "caminho": self.path,
                "cabecalhos": {k.lower(): v for k, v in self.headers.items()},
                "corpo": self.rfile.read(tamanho),
            }
        )
        corpo = b'{"ok": true}'
        self.send_response(RESPOSTA["status"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_args):
        pass


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _ServidorDeMentira)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.config = (f"http://127.0.0.1:{cls.servidor.server_address[1]}/api/ia", "segredo-do-teste")

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        PEDIDOS.clear()
        RESPOSTA["status"] = 200
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        alvos = (
            mock.patch.object(contagem, "caminho_de_dados", lambda *p: str(Path(self.pasta.name).joinpath(*p))),
            mock.patch.object(contagem.atualizador, "versao_atual", lambda: "2.1.0"),
            mock.patch.dict(os.environ),
        )
        for alvo in alvos:
            alvo.start()
            self.addCleanup(alvo.stop)
        os.environ.pop(contagem.VARIAVEL_DESLIGAR, None)
        self.dia = datetime.date(2026, 10, 5)

    def arquivo(self, nome: str) -> Path:
        return Path(self.pasta.name) / nome


class Envio(_Base):
    def test_manda_so_o_numero_da_instalacao_e_a_versao(self):
        self.assertTrue(contagem.registrar_uso(self.config, self.dia))
        self.assertEqual(len(PEDIDOS), 1)
        pedido = PEDIDOS[0]
        self.assertEqual(pedido["caminho"], "/api/uso")
        self.assertEqual(pedido["cabecalhos"]["x-app-token"], "segredo-do-teste")
        dados = json.loads(pedido["corpo"].decode("utf-8"))
        self.assertEqual(set(dados), {"id", "versao"})  # NADA além disso
        self.assertRegex(dados["id"], r"^[0-9a-f]{32}$")
        self.assertEqual(dados["versao"], "2.1.0")

    def test_o_numero_da_instalacao_e_sempre_o_mesmo(self):
        contagem.registrar_uso(self.config, self.dia)
        contagem.registrar_uso(self.config, self.dia + datetime.timedelta(days=1))
        ids = [json.loads(p["corpo"].decode("utf-8"))["id"] for p in PEDIDOS]
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(self.arquivo("id_instalacao.txt").read_text(encoding="utf-8").strip(), ids[0])

    def test_no_maximo_uma_vez_por_dia(self):
        self.assertTrue(contagem.registrar_uso(self.config, self.dia))
        self.assertFalse(contagem.registrar_uso(self.config, self.dia))
        self.assertEqual(len(PEDIDOS), 1)
        self.assertTrue(contagem.registrar_uso(self.config, self.dia + datetime.timedelta(days=1)))
        self.assertEqual(len(PEDIDOS), 2)

    def test_numero_estragado_e_refeito(self):
        self.arquivo("id_instalacao.txt").write_text("lixo", encoding="utf-8")
        contagem.registrar_uso(self.config, self.dia)
        self.assertRegex(json.loads(PEDIDOS[0]["corpo"].decode("utf-8"))["id"], r"^[0-9a-f]{32}$")

    def test_endereco_do_aviso_sai_do_endereco_da_ia(self):
        self.assertEqual(contagem._endereco_do_aviso("https://x.vercel.app/api/ia"), "https://x.vercel.app/api/uso")
        self.assertEqual(contagem._endereco_do_aviso("http://127.0.0.1:8787/api/ia"), "http://127.0.0.1:8787/api/uso")


class QuemFicaDeFora(_Base):
    def test_computador_do_mantenedor_nao_conta_nem_cria_arquivo(self):
        self.arquivo("modo_teste.txt").write_text("teste", encoding="utf-8")
        self.assertFalse(contagem.registrar_uso(self.config, self.dia))
        self.assertEqual(PEDIDOS, [])
        self.assertFalse(self.arquivo("id_instalacao.txt").exists())
        self.assertFalse(self.arquivo("ultima_contagem.txt").exists())

    def test_variavel_de_ambiente_desliga(self):
        for valor in ("1", "sim", "true"):
            os.environ[contagem.VARIAVEL_DESLIGAR] = valor
            self.assertFalse(contagem.registrar_uso(self.config, self.dia), valor)
        self.assertEqual(PEDIDOS, [])
        for i, valor in enumerate(("0", "false", "", "  ")):  # estes NÃO desligam
            os.environ[contagem.VARIAVEL_DESLIGAR] = valor
            self.assertTrue(contagem.registrar_uso(self.config, self.dia + datetime.timedelta(days=i)), valor)

    def test_sem_servidor_configurado_nada_acontece(self):
        self.assertFalse(contagem.registrar_uso(None, self.dia))
        self.assertEqual(PEDIDOS, [])
        self.assertFalse(self.arquivo("id_instalacao.txt").exists())


class Falhas(_Base):
    def test_servidor_com_erro_nao_conta_o_dia_e_tenta_de_novo(self):
        RESPOSTA["status"] = 500
        self.assertFalse(contagem.registrar_uso(self.config, self.dia))
        self.assertFalse(self.arquivo("ultima_contagem.txt").exists())
        RESPOSTA["status"] = 200
        self.assertTrue(contagem.registrar_uso(self.config, self.dia))  # mesmo dia: ainda não tinha dado certo
        self.assertEqual(len(PEDIDOS), 2)

    def test_sem_internet_nunca_levanta_erro(self):
        sem_servidor = ("http://127.0.0.1:9/api/ia", "segredo")
        self.assertFalse(contagem.registrar_uso(sem_servidor, self.dia))

    def test_pasta_sem_permissao_nunca_levanta_erro(self):
        with mock.patch.object(contagem, "caminho_de_dados", side_effect=OSError("sem permissão")):
            self.assertFalse(contagem.registrar_uso(self.config, self.dia))
        self.assertEqual(PEDIDOS, [])


class LigacaoComOPrograma(unittest.TestCase):
    def test_app_chama_a_contagem_em_segundo_plano(self):
        fonte = (RAIZ / "app.py").read_text(encoding="utf-8")
        for trecho in (
            "import contagem",
            "contagem.registrar_uso(assistente_ia.configuracao_do_servidor())",
            "threading.Thread(target=self._contar_uso, daemon=True).start()",
        ):
            # assertTrue, e não assertIn: se falhar, assertIn despejaria o app.py inteiro na tela
            self.assertTrue(trecho in fonte, f"app.py não tem: {trecho}")


if __name__ == "__main__":
    unittest.main()
