# -*- coding: utf-8 -*-
"""
Testes do lado do programa (assistente_ia.py): a chave própria do
professor, o endereço do serviço da escola, o pedido a esse serviço e a
escolha do caminho. Só biblioteca padrão, sem internet:

    python -m unittest discover -s tests -v

O núcleo (instrução, chamada ao Gemini) é testado em test_ia_gemini.py, e
o servidor em test_servidor_ia.py.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import assistente_ia  # noqa: E402
from ia_gemini import ErroDaIA  # noqa: E402

PEDIDOS: list = []
RESPOSTA = {"status": 200, "corpo": {"texto": "Texto."}, "bruto": None}


class _ServidorDeMentira(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (nome exigido pelo http.server)
        tamanho = int(self.headers.get("Content-Length") or 0)
        PEDIDOS.append(
            {
                "cabecalhos": {k.lower(): v for k, v in self.headers.items()},
                "corpo": json.loads(self.rfile.read(tamanho).decode("utf-8")),
            }
        )
        corpo = RESPOSTA["bruto"] or json.dumps(RESPOSTA["corpo"]).encode("utf-8")
        self.send_response(RESPOSTA["status"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_args):
        pass


CONTEXTO = {
    "disciplina": "Geografia",
    "turma": "8º ano",
    "etapa": "Ensino Fundamental - Anos Finais",
    "numero_aulas": "2",
    "recursos": ["Lousa Digital"],
    "assunto": "atividade de geografia - mercantilismo",
    "professor": "FULANA DE TAL DA SILVA",  # nunca pode sair
}
CONVERSA = [{"role": "user", "content": "atividade de geografia - mercantilismo"}]


class _Ambiente(unittest.TestCase):
    """Pasta do usuário e variáveis de ambiente isoladas do computador de quem testa."""

    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        ambiente = mock.patch.dict(os.environ, {"APPDATA": self.pasta}, clear=False)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        for nome in ("GEMINI_API_KEY", "SERVIDOR_IA_URL", "SERVIDOR_IA_TOKEN"):
            os.environ.pop(nome, None)
        # sem um servidor_ia.json de verdade por perto
        recurso = mock.patch.object(
            assistente_ia.caminhos, "recurso", lambda nome: Path(self.pasta) / "recurso" / nome
        )
        recurso.start()
        self.addCleanup(recurso.stop)


class ChaveDaApi(_Ambiente):
    def test_sem_chave(self):
        self.assertEqual(assistente_ia.carregar_chave(), "")

    def test_salva_na_pasta_do_usuario(self):
        assistente_ia.salvar_chave("  chave-salva \n")
        self.assertEqual(assistente_ia.carregar_chave(), "chave-salva")
        arquivo = Path(self.pasta) / "RegistroSED" / assistente_ia.ARQUIVO_CHAVE
        self.assertTrue(arquivo.exists())

    def test_variavel_de_ambiente_como_alternativa(self):
        os.environ["GEMINI_API_KEY"] = "chave-do-env"
        self.assertEqual(assistente_ia.carregar_chave(), "chave-do-env")
        assistente_ia.salvar_chave("chave-da-tela")
        self.assertEqual(assistente_ia.carregar_chave(), "chave-da-tela")

    def test_apagar_chave_salva(self):
        assistente_ia.salvar_chave("chave-salva")
        assistente_ia.apagar_chave()
        self.assertEqual(assistente_ia.carregar_chave(), "")

    def test_apagar_sem_nada_salvo_nao_estoura(self):
        assistente_ia.apagar_chave()


class ConfiguracaoDoServidor(_Ambiente):
    def _env(self, url, token="segredo"):
        os.environ["SERVIDOR_IA_URL"] = url
        os.environ["SERVIDOR_IA_TOKEN"] = token

    def test_sem_nada_nao_ha_servidor(self):
        self.assertIsNone(assistente_ia.configuracao_do_servidor())

    def test_https_pelas_variaveis(self):
        self._env("https://escola.vercel.app/api/ia")
        self.assertEqual(
            assistente_ia.configuracao_do_servidor(), ("https://escola.vercel.app/api/ia", "segredo")
        )

    def test_http_remoto_e_recusado(self):
        # o segredo viajaria às claras pela rede da escola
        self._env("http://escola.exemplo/api/ia")
        self.assertIsNone(assistente_ia.configuracao_do_servidor())

    def test_localhost_vale_para_testar(self):
        self._env("http://127.0.0.1:8787/api/ia", "teste-local")
        self.assertEqual(
            assistente_ia.configuracao_do_servidor(), ("http://127.0.0.1:8787/api/ia", "teste-local")
        )
        self._env("http://localhost:8787/api/ia", "teste-local")
        self.assertIsNotNone(assistente_ia.configuracao_do_servidor())

    def test_sem_segredo_nao_conta(self):
        self._env("https://escola.vercel.app/api/ia", token="")
        self.assertIsNone(assistente_ia.configuracao_do_servidor())

    def test_arquivo_embutido_no_exe(self):
        pasta = Path(self.pasta) / "recurso"
        pasta.mkdir()
        (pasta / assistente_ia.ARQUIVO_SERVIDOR).write_text(
            json.dumps({"url": "https://escola.vercel.app/api/ia", "token": "do-arquivo"}),
            encoding="utf-8",
        )
        self.assertEqual(
            assistente_ia.configuracao_do_servidor(),
            ("https://escola.vercel.app/api/ia", "do-arquivo"),
        )

    def test_arquivo_quebrado_nao_estoura(self):
        pasta = Path(self.pasta) / "recurso"
        pasta.mkdir()
        (pasta / assistente_ia.ARQUIVO_SERVIDOR).write_text("{ isso nao e json", encoding="utf-8")
        self.assertIsNone(assistente_ia.configuracao_do_servidor())

    def test_variaveis_tem_preferencia_sobre_o_arquivo(self):
        pasta = Path(self.pasta) / "recurso"
        pasta.mkdir()
        (pasta / assistente_ia.ARQUIVO_SERVIDOR).write_text(
            json.dumps({"url": "https://do-arquivo.exemplo/api/ia", "token": "a"}), encoding="utf-8"
        )
        self._env("http://127.0.0.1:8787/api/ia", "teste-local")
        self.assertEqual(
            assistente_ia.configuracao_do_servidor(), ("http://127.0.0.1:8787/api/ia", "teste-local")
        )


class AvisoDePrivacidade(unittest.TestCase):
    def test_diz_o_essencial_sobre_o_plano_gratuito_e_dados_pessoais(self):
        aviso = assistente_ia.AVISO_DE_PRIVACIDADE
        for trecho in ("Google", "plano gratuito", "nomes de estudantes", "dados pessoais", "CPF"):
            self.assertIn(trecho, aviso)


class ContextoParaEnviar(unittest.TestCase):
    def test_so_os_campos_combinados(self):
        limpo = assistente_ia.contexto_para_enviar(CONTEXTO)
        self.assertEqual(
            sorted(limpo), ["assunto", "disciplina", "etapa", "numero_aulas", "recursos", "turma"]
        )
        self.assertNotIn("professor", limpo)

    def test_campo_com_dado_pessoal_fica_de_fora_em_vez_de_travar(self):
        # o assunto vem da agenda, que a pessoa não edita na janela da IA
        com_telefone = dict(CONTEXTO, assunto="falar com a mãe no (47) 99999-8888")
        limpo = assistente_ia.contexto_para_enviar(com_telefone)
        self.assertNotIn("assunto", limpo)
        self.assertEqual(limpo["disciplina"], "Geografia")

    def test_recurso_com_dado_pessoal_tambem(self):
        limpo = assistente_ia.contexto_para_enviar(dict(CONTEXTO, recursos=["Lousa", "a@b.com"]))
        self.assertNotIn("recursos", limpo)

    def test_contexto_vazio(self):
        self.assertEqual(assistente_ia.contexto_para_enviar(None), {})


class ClienteDoServidor(_Ambiente):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _ServidorDeMentira)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.servidor.server_address[1]}/api/ia"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        super().setUp()
        PEDIDOS.clear()
        RESPOSTA.update(status=200, corpo={"texto": "Texto."}, bruto=None)

    def _pedir(self):
        return assistente_ia.pedir_ao_servidor(self.url, "segredo-do-teste", CONTEXTO, CONVERSA)

    def test_pedido_leva_o_segredo_e_so_os_campos_permitidos(self):
        RESPOSTA["corpo"] = {"texto": "Foram abordados conteúdos de Geografia."}
        self.assertEqual(self._pedir(), "Foram abordados conteúdos de Geografia.")
        pedido = PEDIDOS[-1]
        self.assertEqual(pedido["cabecalhos"]["x-app-token"], "segredo-do-teste")
        self.assertIn("application/json", pedido["cabecalhos"]["content-type"])
        self.assertEqual(pedido["corpo"]["conversa"], CONVERSA)
        self.assertEqual(
            sorted(pedido["corpo"]["contexto"]),
            ["assunto", "disciplina", "etapa", "numero_aulas", "recursos", "turma"],
        )

    def test_nome_de_professor_nunca_sai_do_computador(self):
        self._pedir()
        self.assertNotIn("FULANA", json.dumps(PEDIDOS[-1]["corpo"], ensure_ascii=False))

    def test_resposta_sai_limpa_para_o_formulario(self):
        RESPOSTA["corpo"] = {"texto": '"Foram **trabalhados** conteúdos.\nTambém habilidades."'}
        self.assertEqual(self._pedir(), "Foram trabalhados conteúdos. Também habilidades.")

    def test_mensagem_do_servidor_aparece_como_esta(self):
        RESPOSTA.update(status=429, corpo={"erro": "O serviço de IA está muito ocupado agora."})
        with self.assertRaises(ErroDaIA) as caso:
            self._pedir()
        self.assertEqual(str(caso.exception), "O serviço de IA está muito ocupado agora.")

    def test_erro_sem_json_ganha_mensagem_generica(self):
        RESPOSTA.update(status=500, bruto=b"<html>Internal Server Error</html>")
        with self.assertRaisesRegex(ErroDaIA, r"erro 500"):
            self._pedir()

    def test_resposta_sem_texto(self):
        RESPOSTA["corpo"] = {"texto": "   "}
        with self.assertRaisesRegex(ErroDaIA, "em branco"):
            self._pedir()

    def test_resposta_que_nao_e_json(self):
        RESPOSTA["bruto"] = b"isso nao e json"
        with self.assertRaisesRegex(ErroDaIA, "não consegui ler"):
            self._pedir()

    def test_sem_internet(self):
        with self.assertRaisesRegex(ErroDaIA, "internet"):
            assistente_ia.pedir_ao_servidor(
                "http://127.0.0.1:9/api/ia", "segredo", CONTEXTO, CONVERSA
            )


class EscolhaDoCaminho(_Ambiente):
    def _servidor(self):
        os.environ["SERVIDOR_IA_URL"] = "http://127.0.0.1:8787/api/ia"
        os.environ["SERVIDOR_IA_TOKEN"] = "teste-local"

    def test_nenhum_caminho(self):
        self.assertEqual(assistente_ia.modo_disponivel(), "")
        with self.assertRaises(ErroDaIA):
            assistente_ia.pedir(CONTEXTO, CONVERSA)

    def test_so_servidor(self):
        self._servidor()
        self.assertEqual(assistente_ia.modo_disponivel(), "servidor")
        with mock.patch.object(assistente_ia, "pedir_ao_servidor", return_value="do servidor") as m:
            self.assertEqual(assistente_ia.pedir(CONTEXTO, CONVERSA), "do servidor")
        m.assert_called_once_with(
            "http://127.0.0.1:8787/api/ia",
            "teste-local",
            assistente_ia.contexto_para_enviar(CONTEXTO),
            CONVERSA,
        )

    def test_so_chave_propria(self):
        assistente_ia.salvar_chave("minha-chave")
        self.assertEqual(assistente_ia.modo_disponivel(), "chave")
        with mock.patch.object(
            assistente_ia, "pedir_com_chave_propria", return_value="direto"
        ) as m:
            self.assertEqual(assistente_ia.pedir(CONTEXTO, CONVERSA), "direto")
        # na chave própria também: o nome do professor nunca chega à instrução
        m.assert_called_once_with(
            "minha-chave", assistente_ia.contexto_para_enviar(CONTEXTO), CONVERSA
        )
        self.assertNotIn("professor", m.call_args.args[1])

    def test_chave_propria_tem_preferencia_sobre_o_servidor(self):
        self._servidor()
        assistente_ia.salvar_chave("minha-chave")
        self.assertEqual(assistente_ia.modo_disponivel(), "chave")
        with mock.patch.object(assistente_ia, "pedir_ao_servidor") as servidor, mock.patch.object(
            assistente_ia, "pedir_com_chave_propria", return_value="direto"
        ):
            assistente_ia.pedir(CONTEXTO, CONVERSA)
        servidor.assert_not_called()

    def test_esquecer_a_chave_volta_ao_servidor(self):
        self._servidor()
        assistente_ia.salvar_chave("minha-chave")
        assistente_ia.apagar_chave()
        self.assertEqual(assistente_ia.modo_disponivel(), "servidor")


if __name__ == "__main__":
    unittest.main()
