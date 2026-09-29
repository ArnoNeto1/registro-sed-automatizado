# -*- coding: utf-8 -*-
"""
Testes do atualizador automático — só com a biblioteca padrão do Python.

    python -m unittest discover -s tests -v

Um servidor HTTP de mentira, na própria máquina, faz o papel do GitHub.
Ele sabe "cortar" um download no meio do caminho, do jeito que acontece
com internet de escola: a conexão fecha educadamente antes do arquivo
acabar, sem erro nenhum de rede.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import atualizador  # noqa: E402

# ---------------------------------------------------------------------------
# Servidor de mentira
# ---------------------------------------------------------------------------
# caminho -> (corpo, quantos bytes mandar de verdade)
ROTAS: dict = {}


class _Servidor(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (nome exigido pelo http.server)
        if self.path not in ROTAS:
            self.send_error(404)
            return
        corpo, enviar = ROTAS[self.path]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(corpo)))  # anuncia TUDO
        self.end_headers()
        self.wfile.write(corpo[:enviar])  # ...mas pode mandar só um pedaço
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *_args):
        pass  # silêncio no terminal dos testes


def _exe_falso(tamanho: int, marca: bytes) -> bytes:
    """Algo com cara de .exe: começa com "MZ" e passa dos 2 MB."""
    return (b"MZ" + marca * (tamanho // len(marca) + 1))[:tamanho]


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
        cls.url = f"http://127.0.0.1:{cls.servidor.server_address[1]}"
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        ROTAS.clear()
        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.pasta, ignore_errors=True))


# ---------------------------------------------------------------------------
# Programa instalado como .exe
# ---------------------------------------------------------------------------
class TrocaDoExe(_Base):
    def setUp(self):
        super().setUp()
        self.exe = self.pasta / "Registro-SED.exe"
        self.original = _exe_falso(2_500_000, b"VERSAO-QUE-FUNCIONA")
        self.exe.write_bytes(self.original)
        self.novo = _exe_falso(3_000_000, b"VERSAO-NOVA")
        # o atualizador acha o .exe em uso por sys.executable, e grava o
        # VERSAO.txt ao lado dele
        for alvo in (
            mock.patch.object(sys, "executable", str(self.exe)),
            mock.patch.object(atualizador, "ARQUIVO_VERSAO", str(self.pasta / "VERSAO.txt")),
        ):
            alvo.start()
            self.addCleanup(alvo.stop)

    def _info(self, **extras) -> dict:
        return {"versao": "9.9.9", "exe": self.url + "/Registro-SED.exe", **extras}

    def _nada_mudou(self):
        self.assertEqual(self.exe.read_bytes(), self.original)
        self.assertFalse((self.pasta / "Registro-SED.novo.exe").exists())
        self.assertFalse((self.pasta / "Registro-SED.antigo.exe").exists())
        self.assertFalse((self.pasta / "VERSAO.txt").exists())

    def test_download_cortado_no_meio_nao_troca_o_programa(self):
        # O caso real: a conexão cai com 2/3 do arquivo baixado. Antes, o
        # pedaço (que começa com "MZ" e passa de 2 MB) tomava o lugar do
        # programa, que deixava de abrir.
        ROTAS["/Registro-SED.exe"] = (self.novo, 2_000_000)
        with self.assertRaisesRegex(RuntimeError, "incompleto"):
            atualizador._aplicar_exe(self._info())
        self._nada_mudou()

    def test_impressao_digital_diferente_nao_troca_o_programa(self):
        ROTAS["/Registro-SED.exe"] = (self.novo, len(self.novo))
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            atualizador._aplicar_exe(self._info(sha256="0" * 64))
        self._nada_mudou()

    def test_download_inteiro_e_conferido_troca_o_programa(self):
        ROTAS["/Registro-SED.exe"] = (self.novo, len(self.novo))
        impressao = hashlib.sha256(self.novo).hexdigest()
        trocados = atualizador._aplicar_exe(self._info(sha256=impressao.upper()))
        self.assertEqual(trocados, ["Registro-SED.exe"])
        self.assertEqual(self.exe.read_bytes(), self.novo)
        self.assertEqual((self.pasta / "VERSAO.txt").read_text(encoding="utf-8"), "9.9.9")
        self.assertFalse((self.pasta / "Registro-SED.novo.exe").exists())

    def test_versao_json_antigo_sem_sha256_continua_funcionando(self):
        ROTAS["/Registro-SED.exe"] = (self.novo, len(self.novo))
        atualizador._aplicar_exe(self._info())
        self.assertEqual(self.exe.read_bytes(), self.novo)

    def test_pagina_de_erro_no_lugar_do_exe_nao_troca_o_programa(self):
        pagina = b"<html>Not Found</html>"
        ROTAS["/Registro-SED.exe"] = (pagina, len(pagina))
        with self.assertRaisesRegex(RuntimeError, "não é o programa"):
            atualizador._aplicar_exe(self._info())
        self._nada_mudou()


# ---------------------------------------------------------------------------
# Consulta ao versao.json
# ---------------------------------------------------------------------------
class ConsultaDaVersao(_Base):
    def test_repassa_a_impressao_digital_publicada(self):
        dados = {
            "versao": "999.0.0",
            "exe": "https://exemplo/Registro-SED.exe",
            "sha256": "ABCDEF" + "0" * 58,
            "notas": "x",
        }
        corpo = json.dumps(dados).encode("utf-8")
        ROTAS["/versao.json"] = (corpo, len(corpo))
        info = atualizador.consultar(self.url)
        self.assertEqual(info["sha256"], "abcdef" + "0" * 58)

    def test_versao_json_sem_impressao_digital(self):
        corpo = json.dumps({"versao": "999.0.0", "exe": "x"}).encode("utf-8")
        ROTAS["/versao.json"] = (corpo, len(corpo))
        self.assertEqual(atualizador.consultar(self.url)["sha256"], "")


# ---------------------------------------------------------------------------
# Rodando pelos .py (pacote .zip)
# ---------------------------------------------------------------------------
class TrocaPeloZip(_Base):
    ESSENCIAIS = ("app.py", "config.py", "sed_form_filler.py", "agenda_scraper.py")

    def setUp(self):
        super().setUp()
        for nome in self.ESSENCIAIS:
            (self.pasta / nome).write_text(f"# {nome} antigo\n", encoding="utf-8")
        for alvo in (
            mock.patch.object(atualizador, "PASTA", str(self.pasta)),
            mock.patch.object(atualizador, "PASTA_BACKUP", str(self.pasta / "backup")),
            mock.patch.object(atualizador, "ARQUIVO_VERSAO", str(self.pasta / "VERSAO.txt")),
            mock.patch.object(atualizador, "empacotado", lambda: False),
        ):
            alvo.start()
            self.addCleanup(alvo.stop)

    def _zip(self, corromper: str = "") -> bytes:
        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w", zipfile.ZIP_STORED) as z:
            for nome in self.ESSENCIAIS:
                z.writestr(f"repo-main/{nome}", f"# {nome} NOVO\n" * 50)
        dados = bytearray(memoria.getvalue())
        if corromper:
            # estraga o conteúdo de um arquivo sem mexer na estrutura do
            # zip: só o CRC denuncia, e só quando o arquivo é lido
            marca = f"# {corromper} NOVO".encode()
            pos = dados.find(marca)
            dados[pos + 2] ^= 0xFF
        return bytes(dados)

    def _conteudos(self) -> dict:
        return {n: (self.pasta / n).read_text(encoding="utf-8") for n in self.ESSENCIAIS}

    def test_arquivo_corrompido_no_meio_nao_mistura_versoes(self):
        antes = self._conteudos()
        pacote = self._zip(corromper="sed_form_filler.py")
        ROTAS["/main.zip"] = (pacote, len(pacote))
        with self.assertRaises(Exception):
            atualizador.aplicar({"versao": "9.9.9", "zip": self.url + "/main.zip"})
        self.assertEqual(self._conteudos(), antes)
        self.assertFalse((self.pasta / "_atualizacao.zip").exists())

    def test_zip_cortado_no_meio_nao_troca_nada(self):
        antes = self._conteudos()
        pacote = self._zip()
        ROTAS["/main.zip"] = (pacote, len(pacote) // 2)
        with self.assertRaises(Exception):
            atualizador.aplicar({"versao": "9.9.9", "zip": self.url + "/main.zip"})
        self.assertEqual(self._conteudos(), antes)
        self.assertFalse((self.pasta / "_atualizacao.zip").exists())

    def test_zip_inteiro_troca_tudo(self):
        pacote = self._zip()
        ROTAS["/main.zip"] = (pacote, len(pacote))
        trocados = atualizador.aplicar({"versao": "9.9.9", "zip": self.url + "/main.zip"})
        self.assertEqual(trocados, sorted(self.ESSENCIAIS))
        for nome, texto in self._conteudos().items():
            self.assertIn("NOVO", texto, nome)
        self.assertTrue((self.pasta / "backup" / "app.py").exists())


if __name__ == "__main__":
    unittest.main()
