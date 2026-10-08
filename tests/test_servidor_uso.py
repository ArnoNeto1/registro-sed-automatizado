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
HASHES: dict = {}     # chave -> {campo: valor} (HSET/HGETALL: escola -> último dia)
ESTADO = {"falhar": False}

ID_A = "a" * 32
ID_B = "b" * 32
ESCOLA_A = "EEB PEDRO II"          # as três são da lista oficial (escolas.py)
ESCOLA_B = "EEB SANTOS DUMONT"
ESCOLA_C = "EEB VICTOR HERING"
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
    if nome == "HSET":
        HASHES.setdefault(args[0], {})[args[1]] = args[2]
        return {"result": 1}
    if nome == "HGETALL":  # o Upstash devolve campo, valor, campo, valor...
        return {"result": [x for par in HASHES.get(args[0], {}).items() for x in par]}
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
        HASHES.clear()
        ESTADO["falhar"] = False
        ambiente = mock.patch.dict(
            os.environ,
            {
                "KV_REST_API_URL": self.url_redis,
                "KV_REST_API_TOKEN": "token-do-redis",
                "APP_TOKEN": "segredo-certo",
                "PAINEL_TOKEN": "senha-do-painel",
            },
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
        self.assertEqual(usados, {"PFADD", "EXPIRE", "SADD", "PFCOUNT", "SMEMBERS", "HGETALL"})
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


class Escolas(_Base):
    """A escola (SÓ da lista oficial) conta computadores por escola, sem ficar junto do número do computador."""

    def test_escola_oficial_conta_computadores_diferentes_e_guarda_o_ultimo_dia(self):
        uso.registrar(ID_A, "2.3.0", AGORA, ESCOLA_A)
        uso.registrar(ID_A, "2.3.0", AGORA, ESCOLA_A)  # o mesmo computador de novo
        uso.registrar(ID_B, "2.3.0", AGORA, ESCOLA_A)
        self.assertEqual(CONJUNTOS[f"uso:escola:{ESCOLA_A}"], {ID_A, ID_B})
        self.assertEqual(HASHES["uso:escolas"], {ESCOLA_A: "2026-10-05"})
        self.assertEqual(VALIDADES[f"uso:escola:{ESCOLA_A}"], uso.VALIDADE_EM_SEGUNDOS)

    def test_sem_escola_o_computador_conta_igual_e_nada_de_escola_e_guardado(self):
        uso.registrar(ID_A, "2.1.0", AGORA)
        self.assertEqual(uso.totais(AGORA)["desde_o_inicio"], 1)
        self.assertEqual(HASHES, {})
        self.assertEqual([c for c in CONJUNTOS if c.startswith("uso:escola:")], [])

    def test_escola_fora_da_lista_e_ignorada_mas_o_computador_conta(self):
        # só os nomes oficiais entram: nada de texto livre, nome de gente ou variação de escrita
        for estranha in ("EEB QUALQUER COISA", "eeb pedro ii", ESCOLA_A + " ", "", "FULANA DA SILVA", ESCOLA_A + "\n"):
            uso.registrar(ID_A, "2.3.0", AGORA, estranha)
        self.assertEqual(HASHES, {})
        self.assertEqual([c for c in CONJUNTOS if c.startswith("uso:escola:")], [])
        self.assertIn(ID_A, CONJUNTOS["uso:todos"])

    def test_o_numero_do_computador_nunca_fica_num_lugar_que_se_possa_listar(self):
        uso.registrar(ID_A, "2.3.0", AGORA, ESCOLA_A)
        for chamada in CHAMADAS:
            for comando in chamada["comandos"]:
                if comando[0] in ("HSET", "SADD", "SET", "RPUSH", "LPUSH", "ZADD"):
                    self.assertNotIn(ID_A, [str(x) for x in comando[1:]], comando)
        # a escola vai para o HSET (com o dia) e para o nome da chave do contador, e só
        usos_da_escola = [c for ch in CHAMADAS for c in ch["comandos"] if any(ESCOLA_A in str(x) for x in c)]
        self.assertEqual(sorted(c[0] for c in usos_da_escola), ["EXPIRE", "HSET", "PFADD"])

    def test_totais_publicos_so_trazem_numeros_de_escolas(self):
        uso.registrar("c" * 32, "2.3.0", _dias_atras(40), ESCOLA_C)
        uso.registrar(ID_B, "2.3.0", _dias_atras(5), ESCOLA_B)
        uso.registrar(ID_A, "2.3.0", AGORA, ESCOLA_A)
        total = uso.totais(AGORA)
        self.assertEqual(total["escolas_diferentes"], 3)
        self.assertEqual(total["escolas_ultimos_30_dias"], 2)
        texto = json.dumps(total, ensure_ascii=False)
        for nome in (ESCOLA_A, ESCOLA_B, ESCOLA_C):
            self.assertNotIn(nome, texto)

    def test_totais_sem_nenhuma_escola_ainda(self):
        uso.registrar(ID_A, "2.1.0", AGORA)
        total = uso.totais(AGORA)
        self.assertEqual((total["escolas_diferentes"], total["escolas_ultimos_30_dias"]), (0, 0))

    def test_detalhe_lista_escolas_com_computadores_e_ultimo_uso(self):
        uso.registrar(ID_A, "2.3.0", _dias_atras(9), ESCOLA_A)
        uso.registrar(ID_A, "2.3.0", _dias_atras(2), ESCOLA_B)
        uso.registrar(ID_B, "2.3.0", AGORA, ESCOLA_B)
        detalhe = uso.detalhe_escolas(AGORA)
        self.assertEqual(
            detalhe["escolas"],
            [
                {"escola": ESCOLA_A, "computadores": 1, "ultimo_uso": "2026-09-26"},
                {"escola": ESCOLA_B, "computadores": 2, "ultimo_uso": "2026-10-05"},
            ],
        )
        self.assertEqual(detalhe["atualizado_em"], "2026-10-05 12:00")

    def test_detalhe_so_devolve_nomes_da_lista_oficial(self):
        uso.registrar(ID_A, "2.3.0", AGORA, ESCOLA_A)
        HASHES["uso:escolas"]["FULANA DA SILVA"] = "2026-10-05"  # sujeira posta à força no Redis
        HASHES["uso:escolas"][ESCOLA_B] = "lixo"  # nome certo, data estragada
        nomes = [e["escola"] for e in uso.detalhe_escolas(AGORA)["escolas"]]
        self.assertEqual(nomes, [ESCOLA_A])

    def test_aviso_com_escola_oficial_e_aceito_e_guardado(self):
        status, _ = uso.responder_aviso(self.corpo(versao="2.3.0", escola=ESCOLA_A), "segredo-certo")
        self.assertEqual(status, 200)
        self.assertIn(ID_A, CONJUNTOS[f"uso:escola:{ESCOLA_A}"])

    def test_aviso_com_escola_estranha_nao_e_recusado_so_a_escola_e_ignorada(self):
        for estranha in (123, ["x"], {"a": 1}, None, "EEB QUALQUER", True):
            status, _ = uso.responder_aviso(self.corpo(escola=estranha), "segredo-certo")
            self.assertEqual(status, 200, repr(estranha))
        self.assertEqual(HASHES, {})


class Painel(_Base):
    """A lista de nomes fica atrás de uma senha só do mantenedor (PAINEL_TOKEN); o endereço público só tem números."""

    def test_senha_certa_abre_a_lista(self):
        uso.registrar(ID_A, "2.3.0", AGORA, ESCOLA_A)
        status, dados = uso.responder_detalhe("senha-do-painel")
        self.assertEqual(status, 200)
        self.assertEqual([e["escola"] for e in dados["escolas"]], [ESCOLA_A])

    def test_senha_errada_ou_ausente_nao_abre_nem_toca_no_redis(self):
        uso.registrar(ID_A, "2.3.0", AGORA, ESCOLA_A)
        CHAMADAS.clear()
        for token in ("", "errada", "senha-do-painel-e-mais", " senha-do-painel"):
            status, dados = uso.responder_detalhe(token)
            self.assertEqual(status, 401, repr(token))
            self.assertNotIn("escolas", dados)
        self.assertEqual(CHAMADAS, [])

    def test_o_segredo_do_programa_nao_abre_o_painel(self):
        # esse segredo viaja dentro do .exe: qualquer pessoa consegue extraí-lo
        self.assertEqual(uso.responder_detalhe("segredo-certo")[0], 401)

    def test_sem_senha_configurada_o_painel_fica_fechado(self):
        os.environ.pop("PAINEL_TOKEN")
        for token in ("", "qualquer"):  # nem "vazio igual a vazio" abre
            self.assertEqual(uso.responder_detalhe(token)[0], 503, repr(token))
        self.assertEqual(CHAMADAS, [])

    def test_senha_so_com_espacos_conta_como_ausente(self):
        os.environ["PAINEL_TOKEN"] = "   "
        self.assertEqual(uso.responder_detalhe("   ")[0], 503)

    def test_redis_fora_do_ar_nao_vaza_detalhe(self):
        ESTADO["falhar"] = True
        status, dados = uso.responder_detalhe("senha-do-painel")
        self.assertEqual(status, 503)
        self.assertNotIn("detalhe-interno", json.dumps(dados))

    def test_a_senha_nunca_vai_para_o_registro(self):
        saida = io.StringIO()
        with contextlib.redirect_stderr(saida), contextlib.redirect_stdout(saida):
            uso.responder_detalhe("senha-errada-de-teste")
            uso.responder_detalhe("senha-do-painel")
        registro = saida.getvalue()
        for proibido in ("senha-errada-de-teste", "senha-do-painel", "token-do-redis"):
            self.assertNotIn(proibido, registro)


class ListaOficialDasEscolas(unittest.TestCase):
    def test_copia_do_servidor_e_igual_a_lista_do_programa(self):
        def ler(caminho: Path) -> str:
            return caminho.read_text(encoding="utf-8").replace("\r\n", "\n")

        self.assertEqual(
            ler(RAIZ / "servidor-ia" / "api" / "_escolas.py"),
            ler(RAIZ / "escolas.py"),
            "servidor-ia/api/_escolas.py ficou diferente de escolas.py: "
            "copie escolas.py por cima (cp escolas.py servidor-ia/api/_escolas.py).",
        )


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

    def _chamar(self, metodo="GET", corpo=None, token=None, consulta="", painel=None):
        cabecalhos = {"content-type": "application/json"}
        if token is not None:
            cabecalhos["x-app-token"] = token
        if painel is not None:
            cabecalhos["x-painel-token"] = painel
        requisicao = urllib.request.Request(self.url + consulta, data=corpo, method=metodo, headers=cabecalhos)
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

    def test_lista_de_escolas_pela_rede_so_com_a_senha_do_painel(self):
        self.assertEqual(self._chamar("POST", self.corpo(versao="2.3.0", escola=ESCOLA_A), "segredo-certo")[0], 200)
        status, cabecalhos, dados = self._chamar("GET", consulta="?detalhe=escolas", painel="senha-do-painel")
        self.assertEqual(status, 200)
        self.assertEqual([e["escola"] for e in dados["escolas"]], [ESCOLA_A])
        self.assertEqual(cabecalhos.get("Cache-Control"), "no-store")  # nunca em cache público
        for painel in (None, "errada", "segredo-certo"):
            status, cabecalhos, dados = self._chamar("GET", consulta="?detalhe=escolas", painel=painel)
            self.assertEqual(status, 401, painel)
            self.assertEqual(cabecalhos.get("Cache-Control"), "no-store")
            self.assertNotIn("escolas", dados)

    def test_o_endereco_publico_continua_so_com_numeros_mesmo_com_escolas_no_ar(self):
        self._chamar("POST", self.corpo(versao="2.3.0", escola=ESCOLA_A), "segredo-certo")
        status, cabecalhos, totais = self._chamar("GET")
        self.assertEqual(status, 200)
        self.assertEqual(totais["escolas_diferentes"], 1)
        self.assertNotIn(ESCOLA_A, json.dumps(totais, ensure_ascii=False))
        self.assertEqual(cabecalhos.get("Cache-Control"), "public, s-maxage=300")

    def test_consulta_desconhecida_e_recusada(self):
        self.assertEqual(self._chamar("GET", consulta="?detalhe=tudo", painel="senha-do-painel")[0], 400)
        self.assertEqual(self._chamar("GET", consulta="?detalhe=", painel="senha-do-painel")[0], 400)

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
