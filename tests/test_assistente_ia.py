# -*- coding: utf-8 -*-
"""
Testes do assistente de IA (assistente_ia.py) — só com a biblioteca
padrão do Python, sem chamar a API de verdade:

    python -m unittest discover -s tests -v

Um servidor HTTP de mentira, na própria máquina, faz o papel da API do
Claude: grava o pedido que chegou (para conferir cabeçalhos, instruções e
conversa) e devolve a resposta que o teste mandar.
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

PEDIDOS: list = []
RESPOSTA = {"status": 200, "corpo": {}}


class _ApiDeMentira(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (nome exigido pelo http.server)
        tamanho = int(self.headers.get("Content-Length") or 0)
        PEDIDOS.append(
            {
                "caminho": self.path,
                "cabecalhos": {k.lower(): v for k, v in self.headers.items()},
                "corpo": json.loads(self.rfile.read(tamanho).decode("utf-8")),
            }
        )
        corpo = json.dumps(RESPOSTA["corpo"]).encode("utf-8")
        self.send_response(RESPOSTA["status"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_args):
        pass


def _resposta_ok(texto: str) -> dict:
    return {
        "id": "msg_teste",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": texto}],
        "stop_reason": "end_turn",
    }


def _erro(tipo: str, mensagem: str) -> dict:
    return {"type": "error", "error": {"type": tipo, "message": mensagem}}


CONTEXTO = {
    "disciplina": "Geografia",
    "turma": "Anos Finais - 8º ano - Anos Finais",
    "etapa": "Ensino Fundamental - Anos Finais",
    "numero_aulas": "2",
    "recursos": ["Computadores/notebooks (pesquisa) no laboratório", "Lousa Digital"],
    "assunto": "atividade de geografia - mercantilismo",
    # não faz parte do que pode sair do computador — tem que ficar de fora
    "professor": "FULANA DE TAL DA SILVA",
}


class _ComServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _ApiDeMentira)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.servidor.server_address[1]}/v1/messages"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        PEDIDOS.clear()
        RESPOSTA.update(status=200, corpo=_resposta_ok("Texto."))
        alvo = mock.patch.object(assistente_ia, "URL_API", self.url)
        alvo.start()
        self.addCleanup(alvo.stop)
        ambiente = mock.patch.dict(os.environ, {}, clear=False)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop("MODELO_IA", None)

    def _pedir(self, conversa=None):
        conversa = conversa or [{"role": "user", "content": CONTEXTO["assunto"]}]
        return assistente_ia.pedir_texto("chave-de-teste", CONTEXTO, conversa)


class PedidoParaAApi(_ComServidor):
    def test_cabecalhos_e_corpo_do_pedido(self):
        RESPOSTA["corpo"] = _resposta_ok(
            "Foram abordados conteúdos de Geografia relacionados ao mercantilismo."
        )
        texto = self._pedir()
        self.assertEqual(texto, "Foram abordados conteúdos de Geografia relacionados ao mercantilismo.")

        pedido = PEDIDOS[-1]
        self.assertEqual(pedido["caminho"], "/v1/messages")
        self.assertEqual(pedido["cabecalhos"]["x-api-key"], "chave-de-teste")
        self.assertEqual(pedido["cabecalhos"]["anthropic-version"], "2023-06-01")
        self.assertIn("application/json", pedido["cabecalhos"]["content-type"])

        corpo = pedido["corpo"]
        self.assertEqual(corpo["model"], assistente_ia.MODELO_PADRAO)
        # os modelos maiores recusam "temperature" (400): nunca enviar
        self.assertNotIn("temperature", corpo)
        self.assertEqual(corpo["messages"], [{"role": "user", "content": CONTEXTO["assunto"]}])
        self.assertIn("- Disciplina: Geografia", corpo["system"])
        self.assertIn("- Assunto anotado na agenda: atividade de geografia - mercantilismo", corpo["system"])
        self.assertIn("Computadores/notebooks (pesquisa) no laboratório, Lousa Digital", corpo["system"])

    def test_nome_de_professor_nunca_sai_do_computador(self):
        self._pedir()
        tudo = json.dumps(PEDIDOS[-1]["corpo"], ensure_ascii=False)
        self.assertNotIn("FULANA", tudo)

    def test_conversa_inteira_vai_a_cada_pedido(self):
        conversa = [
            {"role": "user", "content": "O professor de artes projetou no datashow."},
            {"role": "assistant", "content": "Foram abordados conteúdos de Matemática..."},
            {"role": "user", "content": "foi o professor de ARTES, não matemática"},
        ]
        self._pedir(conversa)
        self.assertEqual(PEDIDOS[-1]["corpo"]["messages"], conversa)

    def test_modelo_pode_ser_trocado_pelo_env(self):
        os.environ["MODELO_IA"] = "claude-sonnet-5-5"
        self._pedir()
        self.assertEqual(PEDIDOS[-1]["corpo"]["model"], "claude-sonnet-5-5")

    def test_resposta_sai_limpa_para_o_formulario(self):
        RESPOSTA["corpo"] = _resposta_ok(
            '"Foram trabalhados pelo professor de **Arte** conteúdos de cálculo da média.\n'
            'Também foram apresentados o **Google Sala de Aula**."'
        )
        self.assertEqual(
            self._pedir(),
            "Foram trabalhados pelo professor de Arte conteúdos de cálculo da média. "
            "Também foram apresentados o Google Sala de Aula.",
        )

    def test_linha_de_apresentacao_sai(self):
        RESPOSTA["corpo"] = _resposta_ok(
            "Aqui está o texto:\n\nForam abordados conteúdos de Geografia.\n"
            "Também foram desenvolvidas habilidades de pesquisa."
        )
        self.assertEqual(
            self._pedir(),
            "Foram abordados conteúdos de Geografia. "
            "Também foram desenvolvidas habilidades de pesquisa.",
        )


class ErrosExplicados(_ComServidor):
    def _erro_esperado(self, status: int, corpo: dict, trecho: str):
        RESPOSTA.update(status=status, corpo=corpo)
        with self.assertRaises(assistente_ia.ErroDaIA) as caso:
            self._pedir()
        self.assertIn(trecho, str(caso.exception))

    def test_chave_recusada(self):
        self._erro_esperado(401, _erro("authentication_error", "invalid x-api-key"), "não foi aceita")

    def test_conta_sem_credito(self):
        self._erro_esperado(
            400,
            _erro("invalid_request_error", "Your credit balance is too low to access the Anthropic API."),
            "sem créditos",
        )

    def test_servico_sobrecarregado(self):
        self._erro_esperado(529, _erro("overloaded_error", "Overloaded"), "sobrecarregado")

    def test_muitos_pedidos(self):
        self._erro_esperado(429, _erro("rate_limit_error", "rate limited"), "Espere alguns segundos")

    def test_resposta_em_branco(self):
        self._erro_esperado(200, _resposta_ok("   "), "em branco")

    def test_sem_internet(self):
        with mock.patch.object(assistente_ia, "URL_API", "http://127.0.0.1:9/v1/messages"):
            with self.assertRaisesRegex(assistente_ia.ErroDaIA, "internet"):
                self._pedir()


class Instrucoes(unittest.TestCase):
    def test_pede_para_nao_repetir_nome_de_estudante(self):
        self.assertIn("nomes de estudantes", assistente_ia.montar_instrucoes({}))

    def test_campos_vazios_ficam_de_fora(self):
        texto = assistente_ia.montar_instrucoes({"disciplina": "Arte", "turma": "", "recursos": []})
        self.assertIn("- Disciplina: Arte", texto)
        self.assertNotIn("- Turma:", texto)
        self.assertNotIn("- Recursos utilizados:", texto)

    def test_sem_dados_da_agenda(self):
        self.assertIn("nenhum dado da agenda", assistente_ia.montar_instrucoes({}))


class ChaveDaApi(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        ambiente = mock.patch.dict(os.environ, {"APPDATA": self.pasta}, clear=False)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_sem_chave(self):
        self.assertEqual(assistente_ia.carregar_chave(), "")

    def test_salva_na_pasta_do_usuario(self):
        assistente_ia.salvar_chave("  chave-salva \n")
        self.assertEqual(assistente_ia.carregar_chave(), "chave-salva")
        arquivo = Path(self.pasta) / "RegistroSED" / assistente_ia.ARQUIVO_CHAVE
        self.assertTrue(arquivo.exists())

    def test_variavel_de_ambiente_como_alternativa(self):
        os.environ["ANTHROPIC_API_KEY"] = "chave-do-env"
        self.assertEqual(assistente_ia.carregar_chave(), "chave-do-env")
        assistente_ia.salvar_chave("chave-da-tela")
        self.assertEqual(assistente_ia.carregar_chave(), "chave-da-tela")


if __name__ == "__main__":
    unittest.main()
