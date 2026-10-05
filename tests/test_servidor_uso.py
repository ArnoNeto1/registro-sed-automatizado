# -*- coding: utf-8 -*-
"""
Testes da contagem anônima do servidor (servidor-ia/api/uso.py). Só
biblioteca padrão, sem internet: um Redis (Upstash) de mentira roda na
própria máquina e guarda tudo na memória, contando números DIFERENTES
como faz o HyperLogLog.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "servidor-ia" / "api"))

import uso  # noqa: E402  (servidor-ia/api/uso.py)

CHAMADAS: list = []   # tudo o que chegou ao Redis de mentira
CONJUNTOS: dict = {}  # chave -> conjunto (serve para o HyperLogLog e para o SADD)
VALIDADES: dict = {}  # chave -> segundos de validade pedidos no EXPIRE
ESTADO = {"falhar": False}

ID_A = "a" * 32
ID_B = "b" * 32
AGORA = datetime.datetime(2026, 10, 5, 15, 0, tzinfo=datetime.timezone.utc)  # 12h em Brasília


def _dias_atras(dias: int) -> datetime.datetime:
    return AGORA - datetime.timedelta(days=dias)


def _executar(comando: list) -> dict:
    nome, args = str(comando[0]).upper(), [str(a) for a in comando[1:]]
    if nome in ("PFADD", "SADD"):
        CONJUNTOS.setdefault(args[0], set()).update(args[1:])
        return {"result": 1}
    if nome == "PFCOUNT":
        uniao: set = set()
        for chave in args:
            uniao |= CONJUNTOS.get(chave, set())
        return {"result": len(uniao)}
    if nome == "SMEMBERS":
        return {"result": sorted(CONJUNTOS.get(args[0], set()))}
    if nome == "EXPIRE":
        VALIDADES[args[0]] = int(args[1])
        return {"result": 1}
    return {"error": f"comando desconhecido: {nome}"}


class _RedisDeMentira(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (nome exigido pelo http.server)
        tamanho = int(self.headers.get("Content-Length") or 0)
        comandos = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        CHAMADAS.append(
            {"caminho": self.path, "auth": self.headers.get("Authorization"), "comandos": comandos}
        )
        if ESTADO["falhar"]:
            status, corpo = 500, {"error": "ERR detalhe-interno-do-redis"}
        else:
            status, corpo = 200, [_executar(c) for c in comandos]
        bruto = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(bruto)))
        self.end_headers()
        self.wfile.write(bruto)

    def log_message(self, *_args):
        pass


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.redis = ThreadingHTTPServer(("127.0.0.1", 0), _RedisDeMentira)
        threading.Thread(target=cls.redis.serve_forever, daemon=True).start()
        cls.url_redis = f"http://127.0.0.1:{cls.redis.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.redis.shutdown()
        cls.redis.server_close()

    def setUp(self):
        CHAMADAS.clear()
        CONJUNTOS.clear()
        VALIDADES.clear()
        ESTADO["falhar"] = False
        ambiente = mock.patch.dict(
            os.environ,
            {"KV_REST_API_URL": self.url_redis, "KV_REST_API_TOKEN": "token-do-redis", "APP_TOKEN": "segredo-certo"},
        )
        ambiente.start()
        self.addCleanup(ambiente.stop)
        for nome in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
            os.environ.pop(nome, None)

    def corpo(self, id_instalacao=ID_A, **mudancas) -> bytes:
        dados = {"id": id_instalacao, "versao": "2.1.0"}
        dados.update(mudancas)
        return json.dumps(dados).encode("utf-8")


class Contagem(_Base):
    def test_um_computador_conta_uma_vez_por_dia(self):
        uso.registrar(ID_A, "2.1.0", AGORA)
        uso.registrar(ID_A, "2.1.0", AGORA)
        total = uso.totais(AGORA)
        self.assertEqual((total["hoje"], total["desde_o_inicio"]), (1, 1))

    def test_computadores_diferentes_somam(self):
        uso.registrar(ID_A, "2.1.0", AGORA)
        uso.registrar(ID_B, "2.1.0", AGORA)
        self.assertEqual(uso.totais(AGORA)["hoje"], 2)

    def test_janelas_de_tempo(self):
        # um computador por dia: hoje, ontem, e há 6, 7, 29, 30 e 40 dias
        for numero, dias in enumerate((0, 1, 6, 7, 29, 30, 40)):
            uso.registrar(f"{numero:032x}", "2.1.0", _dias_atras(dias))
        total = uso.totais(AGORA)
        self.assertEqual(total["hoje"], 1)
        self.assertEqual(total["ontem"], 1)
        self.assertEqual(total["ultimos_7_dias"], 3)   # hoje, ontem e há 6 dias
        self.assertEqual(total["ultimos_30_dias"], 5)  # até há 29 dias
        self.assertEqual(total["desde_o_inicio"], 7)

    def test_o_dia_vira_a_meia_noite_de_brasilia(self):
        antes = datetime.datetime(2026, 10, 6, 2, 30, tzinfo=datetime.timezone.utc)   # 23h30 de 05/10 em Brasília
        depois = datetime.datetime(2026, 10, 6, 3, 30, tzinfo=datetime.timezone.utc)  # 0h30 de 06/10
        uso.registrar(ID_A, "2.1.0", antes)
        uso.registrar(ID_B, "2.1.0", depois)
        self.assertIn(ID_A, CONJUNTOS["uso:dia:2026-10-05"])
        self.assertIn(ID_B, CONJUNTOS["uso:dia:2026-10-06"])
        self.assertNotIn(ID_B, CONJUNTOS["uso:dia:2026-10-05"])

    def test_por_versao_so_conta_os_ultimos_30_dias_e_vem_da_mais_nova(self):
        uso.registrar(ID_A, "2.0.1", AGORA)
        uso.registrar(ID_B, "2.1.0", AGORA)
        uso.registrar("c" * 32, "2.1.0", AGORA)
        uso.registrar("d" * 32, "2.0.0", _dias_atras(45))
        por_versao = uso.totais(AGORA)["por_versao"]
        self.assertEqual(por_versao, {"2.1.0": 2, "2.0.1": 1})
        self.assertEqual(list(por_versao), ["2.1.0", "2.0.1"])

    def test_chaves_diarias_expiram_sozinhas(self):
        uso.registrar(ID_A, "2.1.0", AGORA)
        self.assertEqual(VALIDADES["uso:dia:2026-10-05"], uso.VALIDADE_EM_SEGUNDOS)
        self.assertEqual(VALIDADES["uso:v:2.1.0:2026-10-05"], uso.VALIDADE_EM_SEGUNDOS)

    def test_so_comandos_de_contagem_e_com_a_chave_do_redis(self):
        uso.registrar(ID_A, "2.1.0", AGORA)
        uso.totais(AGORA)
        usados = {c[0] for chamada in CHAMADAS for c in chamada["comandos"]}
        self.assertEqual(usados, {"PFADD", "EXPIRE", "SADD", "PFCOUNT", "SMEMBERS"})
        self.assertTrue(all(c["auth"] == "Bearer token-do-redis" for c in CHAMADAS))
        self.assertTrue(all(c["caminho"] == "/pipeline" for c in CHAMADAS))

    def test_nomes_antigos_das_variaveis_da_upstash_tambem_valem(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("KV_REST_API_URL")
            os.environ.pop("KV_REST_API_TOKEN")
            os.environ["UPSTASH_REDIS_REST_URL"] = self.url_redis + "/"  # barra no fim não atrapalha
            os.environ["UPSTASH_REDIS_REST_TOKEN"] = "outro-token"
            uso.registrar(ID_A, "2.1.0", AGORA)
        self.assertEqual(CHAMADAS[-1]["auth"], "Bearer outro-token")
        self.assertEqual(CHAMADAS[-1]["caminho"], "/pipeline")


class Aviso(_Base):
    def test_aviso_valido_e_contado(self):
        status, dados = uso.responder_aviso(self.corpo(), "segredo-certo")
        self.assertEqual((status, dados), (200, {"ok": True}))
        self.assertIn(ID_A, CONJUNTOS["uso:todos"])

    def test_sem_o_segredo_certo_nada_e_guardado(self):
        for token in ("", "errado", "segredo-certo-e-mais"):
            status, _ = uso.responder_aviso(self.corpo(), token)
            self.assertEqual(status, 401, token)
        self.assertEqual(CHAMADAS, [])

    def test_servidor_sem_segredo_configurado(self):
        os.environ.pop("APP_TOKEN")
        status, _ = uso.responder_aviso(self.corpo(), "")
        self.assertEqual(status, 503)
        self.assertEqual(CHAMADAS, [])

    def test_id_fora_do_formato_e_recusado(self):
        ruins = ["", "x" * 32, "A" * 32, "a" * 31, "a" * 33, "a" * 32 + "\n", 123, None, ["a" * 32]]
        for ruim in ruins:
            status, _ = uso.responder_aviso(self.corpo(ruim), "segredo-certo")
            self.assertEqual(status, 400, repr(ruim))
        self.assertEqual(CHAMADAS, [])

    def test_versao_fora_do_formato_e_recusada(self):
        ruins = ["", "2.1", "v2.1.0", "2.1.0-beta", "2.1.0\n", "1.2.3.4", "٢.١.٠", 2.1, None]
        for ruim in ruins:
            status, _ = uso.responder_aviso(self.corpo(versao=ruim), "segredo-certo")
            self.assertEqual(status, 400, repr(ruim))
        self.assertEqual(CHAMADAS, [])

    def test_campos_a_mais_sao_ignorados_e_nunca_guardados(self):
        corpo = self.corpo(nome="FULANA DE TAL", cpf="529.982.247-25", escola="EEB Teste")
        status, _ = uso.responder_aviso(corpo, "segredo-certo")
        self.assertEqual(status, 200)
        tudo = json.dumps(CHAMADAS, ensure_ascii=False) + json.dumps(
            {chave: sorted(valores) for chave, valores in CONJUNTOS.items()}, ensure_ascii=False
        )
        for segredo in ("FULANA", "529.982", "EEB Teste"):
            self.assertNotIn(segredo, tudo)

    def test_corpo_ruim(self):
        self.assertEqual(uso.responder_aviso(b"x" * (uso.LIMITE_CORPO + 1), "segredo-certo")[0], 413)
        for ruim in (b"nao e json", b"\xff\xfe", b"[]", b"3", b"null"):
            self.assertEqual(uso.responder_aviso(ruim, "segredo-certo")[0], 400, ruim)
        self.assertEqual(CHAMADAS, [])

    def test_redis_fora_do_ar_nao_vaza_detalhe(self):
        ESTADO["falhar"] = True
        status, dados = uso.responder_aviso(self.corpo(), "segredo-certo")
        self.assertEqual(status, 503)
        self.assertNotIn("detalhe-interno", json.dumps(dados))

    def test_sem_configuracao_do_redis(self):
        for nome in ("KV_REST_API_URL", "KV_REST_API_TOKEN"):
            with mock.patch.dict(os.environ):
                os.environ.pop(nome)
                self.assertEqual(uso.responder_aviso(self.corpo(), "segredo-certo")[0], 503, nome)

    def test_redis_so_aceita_enderecos_seguros(self):
        with mock.patch.dict(os.environ, {"KV_REST_API_URL": "http://exemplo.com.br"}):
            self.assertEqual(uso.responder_aviso(self.corpo(), "segredo-certo")[0], 503)
        self.assertEqual(CHAMADAS, [])


class SemVazamentos(_Base):
    def test_registro_nao_tem_o_numero_nem_o_ip_nem_o_conteudo(self):
        saida = io.StringIO()
        with contextlib.redirect_stderr(saida), contextlib.redirect_stdout(saida):
            uso.responder_aviso(self.corpo(), "segredo-certo")                   # certo
            uso.responder_aviso(self.corpo(), "errado")                          # recusado
            uso.responder_aviso(b"lixo " + ID_A.encode("ascii"), "segredo-certo")  # corpo ruim
            ESTADO["falhar"] = True
            uso.responder_aviso(self.corpo(), "segredo-certo")                   # Redis fora
        registro = saida.getvalue()
        self.assertIn("recusado", registro)
        for proibido in (ID_A, "127.0.0.1", "segredo-certo", "token-do-redis", "detalhe-interno"):
            self.assertNotIn(proibido, registro)


class ServidorHttpDeVerdade(_Base):
    """O mesmo servidor, mas pela rede (loopback), como o programa e o navegador o chamam."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), uso.handler)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.http.server_address[1]}/api/uso"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        super().tearDownClass()

    def _chamar(self, metodo="GET", corpo=None, token=None):
        cabecalhos = {"content-type": "application/json"}
        if token is not None:
            cabecalhos["x-app-token"] = token
        requisicao = urllib.request.Request(self.url, data=corpo, method=metodo, headers=cabecalhos)
        try:
            with urllib.request.urlopen(requisicao, timeout=10) as resposta:
                return resposta.status, dict(resposta.headers), json.loads(resposta.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:
            return erro.code, dict(erro.headers), json.loads(erro.read().decode("utf-8"))

    def test_aviso_e_totais_pela_rede(self):
        self.assertEqual(self._chamar("POST", self.corpo(), "segredo-certo")[0], 200)
        status, cabecalhos, totais = self._chamar("GET")
        self.assertEqual(status, 200)
        self.assertEqual(totais["desde_o_inicio"], 1)
        self.assertEqual(cabecalhos.get("Cache-Control"), "public, s-maxage=300")

    def test_aviso_sem_o_segredo_certo_pela_rede(self):
        self.assertEqual(self._chamar("POST", self.corpo(), "errado")[0], 401)
        self.assertEqual(self._chamar("POST", self.corpo())[0], 401)
        self.assertEqual(CHAMADAS, [])

    def test_totais_com_redis_fora_do_ar(self):
        ESTADO["falhar"] = True
        status, cabecalhos, _ = self._chamar("GET")
        self.assertEqual(status, 503)
        self.assertEqual(cabecalhos.get("Cache-Control"), "no-store")

    def test_outros_metodos_nao_valem(self):
        self.assertEqual(self._chamar("PUT", b"{}", "segredo-certo")[0], 405)
        self.assertEqual(self._chamar("DELETE")[0], 405)

    def test_o_servidor_nao_escreve_o_ip_de_ninguem_no_registro(self):
        saida = io.StringIO()
        with contextlib.redirect_stderr(saida):
            self._chamar("GET")
            self._chamar("POST", self.corpo(), "segredo-certo")
        self.assertNotIn("127.0.0.1", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
