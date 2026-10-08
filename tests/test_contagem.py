# -*- coding: utf-8 -*-
"""
Testes da contagem anônima do lado do programa (contagem.py) — sem
internet: o servidor da escola é de mentira e a pasta de dados é temporária.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import ast
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
ESCOLA = "EEB PEDRO II"  # da lista oficial (escolas.py)
OUTRA_ESCOLA = "EEB SANTOS DUMONT"


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


class Escola(_Base):
    """A escola do cadastro vai junto, mas SÓ se for um nome da lista oficial."""

    def dados(self, i: int = -1) -> dict:
        return json.loads(PEDIDOS[i]["corpo"].decode("utf-8"))

    def test_escola_da_lista_oficial_vai_junto(self):
        self.assertTrue(contagem.registrar_uso(self.config, self.dia, ESCOLA))
        dados = self.dados()
        self.assertEqual(set(dados), {"id", "versao", "escola"})
        self.assertEqual(dados["escola"], ESCOLA)

    def test_escola_fora_da_lista_nao_sai_do_computador(self):
        # texto livre, outra grafia, o aviso da tela de cadastro, tipo errado: nada disso é enviado
        for estranha in ("EEB QUALQUER", "fulana da silva", "eeb pedro ii", ESCOLA + " ", "Selecione uma escola", "", None, 5):
            PEDIDOS.clear()
            self.arquivo("ultima_contagem.txt").unlink(missing_ok=True)
            self.assertTrue(contagem.registrar_uso(self.config, self.dia, estranha), repr(estranha))
            self.assertEqual(set(self.dados()), {"id", "versao"}, repr(estranha))

    def test_sem_escola_o_pedido_e_o_de_antes(self):
        contagem.registrar_uso(self.config, self.dia)
        self.assertEqual(set(self.dados()), {"id", "versao"})

    def test_no_maximo_uma_vez_por_dia_por_escola(self):
        self.assertTrue(contagem.registrar_uso(self.config, self.dia, ESCOLA))
        self.assertFalse(contagem.registrar_uso(self.config, self.dia, ESCOLA))
        self.assertEqual(len(PEDIDOS), 1)
        self.assertTrue(contagem.registrar_uso(self.config, self.dia + datetime.timedelta(days=1), ESCOLA))

    def test_trocar_de_escola_no_mesmo_dia_avisa_de_novo(self):
        # o notebook de quem atende em duas escolas conta nas duas
        self.assertTrue(contagem.registrar_uso(self.config, self.dia, ESCOLA))
        self.assertTrue(contagem.registrar_uso(self.config, self.dia, OUTRA_ESCOLA))
        self.assertFalse(contagem.registrar_uso(self.config, self.dia, OUTRA_ESCOLA))
        self.assertEqual([self.dados(i)["escola"] for i in range(2)], [ESCOLA, OUTRA_ESCOLA])

    def test_marcador_do_formato_antigo_nao_impede_o_primeiro_aviso_com_escola(self):
        # quem já avisou hoje com a versão que não mandava escola (arquivo só com o dia)
        self.arquivo("ultima_contagem.txt").write_text(self.dia.isoformat(), encoding="utf-8")
        self.assertTrue(contagem.registrar_uso(self.config, self.dia, ESCOLA))

    def test_marcador_do_formato_antigo_sem_escola_nao_repete_o_aviso(self):
        self.arquivo("ultima_contagem.txt").write_text(self.dia.isoformat(), encoding="utf-8")
        self.assertFalse(contagem.registrar_uso(self.config, self.dia))
        self.assertEqual(PEDIDOS, [])

    def test_falha_do_servidor_nao_marca_o_dia(self):
        RESPOSTA["status"] = 500
        self.assertFalse(contagem.registrar_uso(self.config, self.dia, ESCOLA))
        self.assertFalse(self.arquivo("ultima_contagem.txt").exists())
        RESPOSTA["status"] = 200
        self.assertTrue(contagem.registrar_uso(self.config, self.dia, ESCOLA))

    def test_computador_do_mantenedor_nao_manda_escola_nenhuma(self):
        self.arquivo("modo_teste.txt").write_text("teste", encoding="utf-8")
        self.assertFalse(contagem.registrar_uso(self.config, self.dia, ESCOLA))
        self.assertEqual(PEDIDOS, [])

    def test_nunca_levanta_erro_mesmo_sem_a_lista_de_escolas(self):
        with mock.patch.dict(sys.modules, {"escolas": None}):  # o import da lista falha
            self.assertTrue(contagem.registrar_uso(self.config, self.dia, ESCOLA))
        self.assertEqual(set(self.dados()), {"id", "versao"})  # sem poder conferir a lista, a escola não vai


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
    def setUp(self):
        self.fonte = (RAIZ / "app.py").read_text(encoding="utf-8")

    def test_app_chama_a_contagem_em_segundo_plano(self):
        for trecho in (
            "import contagem",
            "threading.Thread(target=self._contar_uso, daemon=True).start()",
        ):
            # assertTrue, e não assertIn: se falhar, assertIn despejaria o app.py inteiro na tela
            self.assertTrue(trecho in self.fonte, f"app.py não tem: {trecho}")

    def test_app_entrega_a_escola_do_cadastro_a_contagem(self):
        chamadas = [
            no
            for no in ast.walk(ast.parse(self.fonte))
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "registrar_uso"
        ]
        self.assertEqual(len(chamadas), 1, "o app deve chamar contagem.registrar_uso uma vez só")
        chamada = chamadas[0]
        self.assertEqual(ast.get_source_segment(self.fonte, chamada.args[0]), "assistente_ia.configuracao_do_servidor()")
        palavras = {k.arg: ast.get_source_segment(self.fonte, k.value) for k in chamada.keywords}
        # a escola ESCOLHIDA no cadastro (a mesma que vai para a SED), e nada mais
        self.assertEqual(palavras, {"escola": 'self.orientador.get("escola", "")'})


if __name__ == "__main__":
    unittest.main()
