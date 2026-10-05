# -*- coding: utf-8 -*-
"""
Testes do núcleo da IA (ia_gemini.py) — só com a biblioteca padrão do
Python, sem chamar a API de verdade:

    python -m unittest discover -s tests -v

Um servidor HTTP de mentira, na própria máquina, faz o papel da API do
Gemini: grava o pedido que chegou (para conferir endereço, cabeçalhos,
instruções e conversa) e devolve a resposta que o teste mandar.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ia_gemini  # noqa: E402

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
        "candidates": [
            {
                "content": {"parts": [{"text": texto}], "role": "model"},
                "finishReason": "STOP",
                "index": 0,
            }
        ]
    }


def _erro(codigo: int, status: str, mensagem: str) -> dict:
    return {"error": {"code": codigo, "message": mensagem, "status": status}}


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
        porta = cls.servidor.server_address[1]
        cls.url = f"http://127.0.0.1:{porta}/v1beta/models/" + "{modelo}:generateContent"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        PEDIDOS.clear()
        RESPOSTA.update(status=200, corpo=_resposta_ok("Texto."))
        alvo = mock.patch.object(ia_gemini, "URL_API", self.url)
        alvo.start()
        self.addCleanup(alvo.stop)
        ambiente = mock.patch.dict(os.environ, {}, clear=False)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop("MODELO_IA", None)

    def _pedir(self, conversa=None):
        conversa = conversa or [{"role": "user", "content": CONTEXTO["assunto"]}]
        return ia_gemini.pedir_texto("chave-de-teste", CONTEXTO, conversa)


class PedidoParaAApi(_ComServidor):
    def test_endereco_cabecalhos_e_corpo_do_pedido(self):
        RESPOSTA["corpo"] = _resposta_ok(
            "Foram abordados conteúdos de Geografia relacionados ao mercantilismo."
        )
        texto = self._pedir()
        self.assertEqual(texto, "Foram abordados conteúdos de Geografia relacionados ao mercantilismo.")

        pedido = PEDIDOS[-1]
        self.assertEqual(
            pedido["caminho"], f"/v1beta/models/{ia_gemini.MODELO_PADRAO}:generateContent"
        )
        self.assertEqual(pedido["cabecalhos"]["x-goog-api-key"], "chave-de-teste")
        self.assertIn("application/json", pedido["cabecalhos"]["content-type"])

        corpo = pedido["corpo"]
        # sem temperature: o padrão de cada modelo é o recomendado
        self.assertNotIn("temperature", json.dumps(corpo))
        self.assertGreaterEqual(corpo["generationConfig"]["maxOutputTokens"], 1000)
        self.assertEqual(
            corpo["contents"],
            [{"role": "user", "parts": [{"text": CONTEXTO["assunto"]}]}],
        )
        sistema = corpo["systemInstruction"]["parts"][0]["text"]
        self.assertIn("- Disciplina: Geografia", sistema)
        self.assertIn("- Assunto anotado na agenda: atividade de geografia - mercantilismo", sistema)
        self.assertIn("Computadores/notebooks (pesquisa) no laboratório, Lousa Digital", sistema)

    def test_chave_nunca_vai_no_endereco(self):
        self._pedir()
        self.assertNotIn("chave-de-teste", PEDIDOS[-1]["caminho"])
        self.assertNotIn("key=", PEDIDOS[-1]["caminho"])

    def test_nome_de_professor_nunca_sai_do_computador(self):
        self._pedir()
        tudo = json.dumps(PEDIDOS[-1]["corpo"], ensure_ascii=False)
        self.assertNotIn("FULANA", tudo)

    def test_conversa_inteira_vai_a_cada_pedido_com_papel_model(self):
        conversa = [
            {"role": "user", "content": "O professor de artes projetou no datashow."},
            {"role": "assistant", "content": "Foram abordados conteúdos de Matemática..."},
            {"role": "user", "content": "foi o professor de ARTES, não matemática"},
        ]
        self._pedir(conversa)
        self.assertEqual(
            PEDIDOS[-1]["corpo"]["contents"],
            [
                {"role": "user", "parts": [{"text": "O professor de artes projetou no datashow."}]},
                {"role": "model", "parts": [{"text": "Foram abordados conteúdos de Matemática..."}]},
                {"role": "user", "parts": [{"text": "foi o professor de ARTES, não matemática"}]},
            ],
        )

    def test_modelo_pode_ser_trocado_pelo_env(self):
        os.environ["MODELO_IA"] = "gemini-outro-modelo"
        self._pedir()
        self.assertEqual(PEDIDOS[-1]["caminho"], "/v1beta/models/gemini-outro-modelo:generateContent")

    def test_modelo_com_caracteres_estranhos_nao_muda_o_endereco(self):
        os.environ["MODELO_IA"] = "x/../../outro"
        self._pedir()
        self.assertNotIn("/../", PEDIDOS[-1]["caminho"])

    def test_pensamento_do_modelo_fica_de_fora(self):
        RESPOSTA["corpo"] = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "raciocinando em voz alta...", "thought": True},
                            {"text": "Foram abordados conteúdos de Geografia."},
                        ],
                        "role": "model",
                    }
                }
            ]
        }
        self.assertEqual(self._pedir(), "Foram abordados conteúdos de Geografia.")

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
    def _erro_esperado(self, status: int, corpo: dict, trecho: str, tipo: str):
        RESPOSTA.update(status=status, corpo=corpo)
        with self.assertRaises(ia_gemini.ErroDaIA) as caso:
            self._pedir()
        self.assertIn(trecho, str(caso.exception))
        self.assertEqual(caso.exception.tipo, tipo)

    def test_chave_recusada_o_gemini_responde_400(self):
        self._erro_esperado(
            400,
            _erro(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."),
            "não foi aceita",
            "chave",
        )

    def test_chave_recusada_401(self):
        self._erro_esperado(401, _erro(401, "UNAUTHENTICATED", "bad key"), "não foi aceita", "chave")

    def test_chave_bloqueada(self):
        self._erro_esperado(
            403,
            _erro(403, "PERMISSION_DENIED", "Your API key was reported as leaked."),
            "bloqueada",
            "permissao",
        )

    def test_modelo_inexistente(self):
        self._erro_esperado(404, _erro(404, "NOT_FOUND", "model not found"), "MODELO_IA", "modelo")

    def test_limite_da_chave_gratuita(self):
        self._erro_esperado(
            429, _erro(429, "RESOURCE_EXHAUSTED", "quota exceeded"), "Espere um pouco", "limite"
        )

    def test_servico_sobrecarregado(self):
        self._erro_esperado(
            503, _erro(503, "UNAVAILABLE", "overloaded"), "sobrecarregado", "indisponivel"
        )

    def test_pedido_recusado_por_outro_motivo(self):
        self._erro_esperado(
            400, _erro(400, "INVALID_ARGUMENT", "texto grande demais"), "recusou", "recusado"
        )

    def test_resposta_em_branco(self):
        self._erro_esperado(200, _resposta_ok("   "), "em branco", "vazio")

    def test_sem_candidatos(self):
        self._erro_esperado(200, {"candidates": []}, "em branco", "vazio")

    def test_bloqueado_pelo_filtro_de_seguranca(self):
        self._erro_esperado(
            200, {"promptFeedback": {"blockReason": "SAFETY"}}, "filtro de segurança", "bloqueado"
        )

    def test_sem_internet(self):
        with mock.patch.object(
            ia_gemini, "URL_API", "http://127.0.0.1:9/v1beta/models/{modelo}:generateContent"
        ):
            with self.assertRaisesRegex(ia_gemini.ErroDaIA, "internet") as caso:
                self._pedir()
        self.assertEqual(caso.exception.tipo, "rede")


class DadoPessoal(unittest.TestCase):
    ACHAR = {
        "meu e-mail é fulana@escola.sc.gov.br": "e-mail",
        "CPF 529.982.247-25 do responsável": "CPF",
        "cpf 52998224725": "CPF",
        "CPF digitado errado 123.456.789-00": "CPF",
        "ligue (47) 99999-8888": "telefone",
        "whats 47 99999-8888": "telefone",
        "fone 47999998888": "telefone",
        "99999-8888": "telefone",
        "+55 47 99999-8888": "telefone",
        "telefone (47) 3333-4444": "telefone",
        "(47)33334444": "telefone",
    }
    # texto de aula de verdade: nada disso pode ser barrado
    NAO_ACHAR = [
        "atividade de geografia - mercantilismo",
        "Brasil Colônia, de 1500 a 1822",
        "período de 1500-1822",
        "século XVI e 1500 1822",
        "Revolução Francesa (1789-1799)",
        "aula de 50 minutos com 2 aulas, turma 8º ano 2026",
        "data 17/10/2026 às 14h30",
        "11111111111 alunos",  # 11 dígitos iguais não é CPF
        "12345678901",  # 11 dígitos que não fecham como CPF
        "população de 1.234.567 habitantes",
        "o 9º ano 2024-2025",
        "números 3.14 e 2.718",
        "notas 10 9 8 7",
        "ano 1999 2000 2001",
        "3333-4444 sem DDD não é telefone",
        "",
    ]

    def test_acha_o_que_e_dado_pessoal(self):
        for texto, tipo in self.ACHAR.items():
            self.assertEqual(ia_gemini.achar_dado_pessoal(texto), tipo, texto)

    def test_nao_barra_texto_de_aula(self):
        for texto in self.NAO_ACHAR:
            self.assertEqual(ia_gemini.achar_dado_pessoal(texto), "", texto)

    def test_texto_vazio_ou_none(self):
        self.assertEqual(ia_gemini.achar_dado_pessoal(None), "")

    def test_cpf_com_digito_verificador_certo(self):
        self.assertTrue(ia_gemini._cpf_valido("52998224725"))
        self.assertTrue(ia_gemini._cpf_valido("11144477735"))
        self.assertFalse(ia_gemini._cpf_valido("52998224726"))
        self.assertFalse(ia_gemini._cpf_valido("00000000000"))
        self.assertFalse(ia_gemini._cpf_valido("123"))

    def test_aviso_diz_o_que_foi_achado(self):
        self.assertIn("CPF", ia_gemini.aviso_de_dado_pessoal("CPF"))
        self.assertIn("Tire esse dado pessoal", ia_gemini.aviso_de_dado_pessoal("telefone"))

    def test_textos_do_pedido_so_levam_o_que_a_pessoa_escreveu(self):
        textos = ia_gemini.textos_do_pedido(
            {"disciplina": "Arte", "recursos": ["Lousa", "Tablet"], "numero_aulas": 2},
            [
                {"role": "user", "content": "fala dela"},
                {"role": "assistant", "content": "resposta da IA"},
                {"role": "user", "content": "outra fala"},
            ],
        )
        self.assertEqual(sorted(textos), sorted(["Arte", "Lousa", "Tablet", "2", "fala dela", "outra fala"]))


class Instrucoes(unittest.TestCase):
    def test_pede_para_nao_repetir_nome_de_estudante(self):
        self.assertIn("nomes de estudantes", ia_gemini.montar_instrucoes({}))

    def test_cita_metodologia_so_se_foi_dita(self):
        texto = ia_gemini.montar_instrucoes({})
        self.assertIn("metodologia", texto)
        self.assertIn("Não deduza nem invente a metodologia", texto)

    def test_campos_vazios_ficam_de_fora(self):
        texto = ia_gemini.montar_instrucoes({"disciplina": "Arte", "turma": "", "recursos": []})
        self.assertIn("- Disciplina: Arte", texto)
        self.assertNotIn("- Turma:", texto)
        self.assertNotIn("- Recursos utilizados:", texto)

    def test_sem_dados_da_agenda(self):
        self.assertIn("nenhum dado da agenda", ia_gemini.montar_instrucoes({}))

    def test_campos_permitidos_nao_incluem_pessoa(self):
        self.assertEqual(
            ia_gemini.CHAVES_DO_CONTEXTO,
            ("disciplina", "turma", "etapa", "numero_aulas", "recursos", "assunto"),
        )


if __name__ == "__main__":
    unittest.main()
