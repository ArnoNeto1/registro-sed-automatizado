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
import ia_gemini  # noqa: E402
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
        for nome in ("CHAVE_GEMINI", "GEMINI_API_KEY", "SERVIDOR_IA_URL", "SERVIDOR_IA_TOKEN"):
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
        os.environ["CHAVE_GEMINI"] = "chave-do-env"
        self.assertEqual(assistente_ia.carregar_chave(), "chave-do-env")
        assistente_ia.salvar_chave("chave-da-tela")
        self.assertEqual(assistente_ia.carregar_chave(), "chave-da-tela")

    def test_nome_generico_de_outras_ferramentas_e_ignorado(self):
        # quem tem GEMINI_API_KEY no Windows (outra ferramenta do Gemini) NÃO
        # pode ter o programa usando essa chave em silêncio, sem passar pelo
        # serviço da escola
        os.environ["GEMINI_API_KEY"] = "chave-de-outra-ferramenta"
        self.assertEqual(assistente_ia.carregar_chave(), "")
        self.assertEqual(assistente_ia.modo_disponivel(), "")

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

    def test_vale_tambem_para_colegas_e_outras_pessoas(self):
        # a janela agora serve a suporte, manutenção e formação, onde o nome citado costuma ser de um colega
        self.assertIn("colegas", assistente_ia.AVISO_DE_PRIVACIDADE)
        for texto in (assistente_ia.TEXTO_CHAVE_PROPRIA, assistente_ia.TEXTO_CHAVE_COM_SERVIDOR):
            self.assertIn("colegas", texto)


class TextosDaJanela(unittest.TestCase):
    TEXTOS = {"titulo_da_janela", "titulo", "dica", "sem_texto", "chave_guardada"}

    def test_todo_tipo_de_texto_tem_todos_os_textos(self):
        self.assertEqual(set(assistente_ia.TEXTOS_DA_JANELA), set(ia_gemini.FINALIDADES))
        for finalidade, textos in assistente_ia.TEXTOS_DA_JANELA.items():
            self.assertEqual(set(textos), self.TEXTOS, finalidade)
            for chave, texto in textos.items():
                self.assertTrue(texto.strip(), f"{finalidade}/{chave} vazio")

    def test_o_laboratorio_continua_com_os_textos_de_sempre(self):
        lab = assistente_ia.TEXTOS_DA_JANELA["objetos"]
        self.assertEqual(lab["titulo_da_janela"], "Registro SED — objetos do conhecimento com IA")
        self.assertEqual(lab["titulo"], "Objetos do conhecimento com IA")
        self.assertEqual(lab["sem_texto"], "Escreva algo sobre a aula antes de enviar.")
        self.assertIn("objetos do conhecimento", lab["dica"])

    def test_os_outros_tipos_nao_falam_de_aula_nem_de_objetos_do_conhecimento(self):
        for finalidade, textos in assistente_ia.TEXTOS_DA_JANELA.items():
            if finalidade == "objetos":
                continue
            for chave, texto in textos.items():
                minusculo = texto.lower()
                self.assertNotIn("objetos do conhecimento", minusculo, f"{finalidade}/{chave}")
                self.assertNotIn("aula", minusculo, f"{finalidade}/{chave}")

    def test_cada_tipo_diz_do_que_se_trata(self):
        textos = assistente_ia.TEXTOS_DA_JANELA
        self.assertIn("suporte", textos["suporte"]["titulo"].lower())
        self.assertIn("manutenção", textos["manutencao"]["titulo"].lower())
        self.assertIn("encontro", textos["formacao"]["titulo"].lower())


class ContextoDosRegistrosBreves(unittest.TestCase):
    """O que cada tela entrega à janela da IA (as regras que dependem do que está marcado na tela)."""

    def test_suporte_com_agenda(self):
        contexto = assistente_ia.contexto_do_suporte(
            "Instalação de equipamento (projetor, computador, lousa digital, etc.)", " 2 ", "levar o projetor"
        )
        self.assertEqual(
            contexto,
            {
                "finalidade": "suporte",
                "atendimento": "Instalação de equipamento (projetor, computador, lousa digital, etc.)",
                "numero_aulas": "2",
                "assunto": "levar o projetor",
            },
        )

    def test_suporte_avulso_nao_tem_assunto(self):
        contexto = assistente_ia.contexto_do_suporte("Outros", "1")
        self.assertEqual(contexto["finalidade"], "suporte")
        self.assertFalse(contexto.get("assunto"))

    def test_numero_de_aulas_so_conta_se_for_numero(self):
        for bruto, esperado in (("3", "3"), (" 12 ", "12"), ("", ""), ("abc", ""), ("2,5", ""), ("-1", "")):
            contexto = assistente_ia.contexto_do_suporte("Outros", bruto)
            self.assertEqual(contexto["numero_aulas"], esperado, repr(bruto))

    def test_manutencao_leva_os_itens_marcados_num_texto_so(self):
        contexto = assistente_ia.contexto_da_manutencao(["Computadores/ notebooks", "Projetor"], "", "3")
        self.assertEqual(contexto["finalidade"], "manutencao")
        self.assertEqual(contexto["itens"], "Computadores/ notebooks, Projetor")
        self.assertEqual(contexto["outro"], "")
        self.assertEqual(contexto["numero_aulas"], "3")

    def test_manutencao_o_texto_de_outro_so_vale_com_outro_marcado(self):
        com = assistente_ia.contexto_da_manutencao(["Projetor", "Outro:"], " caixas de som ", "1")
        self.assertEqual(com["outro"], "caixas de som")
        # sobrou texto no campo de uma tentativa antiga, mas "Outro:" não está marcado
        sem = assistente_ia.contexto_da_manutencao(["Projetor"], "caixas de som", "1")
        self.assertEqual(sem["outro"], "")

    def test_formacao_organizador_da_lista(self):
        contexto = assistente_ia.contexto_da_formacao("CRE/NTE", "texto esquecido", "4")
        self.assertEqual(
            contexto, {"finalidade": "formacao", "organizador": "CRE/NTE", "outro": "", "numero_aulas": "4"}
        )

    def test_formacao_com_outro(self):
        contexto = assistente_ia.contexto_da_formacao("Outro:", " Secretaria Municipal ", "2")
        self.assertEqual(contexto["outro"], "Secretaria Municipal")

    def test_formacao_sem_organizador_marcado(self):
        contexto = assistente_ia.contexto_da_formacao("", "", "")
        self.assertEqual(contexto["organizador"], "")
        self.assertEqual(contexto["numero_aulas"], "")

    def test_nenhum_contexto_leva_nome_de_pessoa(self):
        for contexto in (
            assistente_ia.contexto_do_suporte("Outros", "1", "x"),
            assistente_ia.contexto_da_manutencao(["Projetor"], "", "1"),
            assistente_ia.contexto_da_formacao("CRE/NTE", "", "1"),
        ):
            self.assertTrue(set(contexto) <= set(ia_gemini.CHAVES_DO_CONTEXTO), contexto)


class ResumoDoRegistro(unittest.TestCase):
    """A linha da janela que mostra o que a IA já recebe: tem de ser o que SAI, e não o que a tela tem."""

    def test_suporte_mostra_atendimento_aulas_e_agenda(self):
        contexto = assistente_ia.contexto_do_suporte(
            "Instalação de equipamento (projetor, computador, lousa digital, etc.)", "2", "levar o projetor"
        )
        self.assertEqual(
            assistente_ia.resumo_do_registro(contexto),
            'Instalação de equipamento · 2 aula(s) · agenda: "levar o projetor"',
        )

    def test_assunto_comprido_e_abreviado(self):
        contexto = assistente_ia.contexto_do_suporte("Outros", "1", "palavra " * 40)
        resumo = assistente_ia.resumo_do_registro(contexto)
        self.assertLess(len(resumo), 120)
        self.assertIn("…", resumo)

    def test_manutencao_e_formacao(self):
        manutencao = assistente_ia.contexto_da_manutencao(["Projetor", "Outro:"], "caixas de som", "1")
        self.assertEqual(
            assistente_ia.resumo_do_registro(manutencao), "Projetor · caixas de som · 1 aula(s)"
        )
        formacao = assistente_ia.contexto_da_formacao("CRE/NTE", "", "4")
        self.assertEqual(assistente_ia.resumo_do_registro(formacao), "CRE/NTE · 4 aula(s)")

    def test_so_aparece_o_que_vai_para_a_ia(self):
        # um telefone no "Outro" não sai do computador, então também não aparece como enviado
        contexto = {"finalidade": "manutencao", "itens": "Projetor, Outro:", "outro": "ligar 47 99999-8888"}
        self.assertEqual(assistente_ia.resumo_do_registro(contexto), "Projetor")

    def test_sem_dados(self):
        resumo = assistente_ia.resumo_do_registro({"finalidade": "formacao"})
        self.assertEqual(resumo, "Nada marcado ainda")


RAIZ = Path(__file__).resolve().parent.parent


class LigacaoDosBotoesNoPrograma(unittest.TestCase):
    """
    O app.py não se importa em teste (abre janela, navegador...), então a
    ligação dos quatro botões "Escrever com IA..." de breve descrição é
    conferida lendo o código: cada campo tem o botão dele, e o contexto de
    cada um vem dos campos CERTOS da tela. O erro clássico aqui seria o
    suporte avulso ler os campos do suporte da agenda (a mesma classe de bug
    que o app.py já teve com "Ver no navegador").
    """

    CAMPOS = {
        # campo -> (rótulo, quem monta o contexto)
        "campo_descricao_suporte": (
            "Breve descrição da atividade (quem, onde e para quê):",
            "_contexto_ia_suporte_agenda",
        ),
        "campo_suporte_avulso_descricao": (
            "Breve descrição da atividade (quem, onde e para quê):",
            "_contexto_ia_suporte_avulso",
        ),
        "campo_manutencao_descricao": ("Breve descrição da manutenção:", "_contexto_ia_manutencao"),
        "campo_formacao_descricao": ("Breve descrição do encontro:", "_contexto_ia_formacao"),
    }
    # o que cada montador de contexto lê da tela, e a função que o monta
    LEITURAS = {
        "_contexto_ia_suporte_agenda": (
            "assistente_ia.contexto_do_suporte(",
            ("self.var_tipo_suporte", "self.campo_aulas_suporte", "grupo_atual"),
            ("var_suporte_avulso_tipo", "campo_suporte_avulso_aulas"),
        ),
        "_contexto_ia_suporte_avulso": (
            "assistente_ia.contexto_do_suporte(",
            ("self.var_suporte_avulso_tipo", "self.campo_suporte_avulso_aulas"),
            ("var_tipo_suporte", "campo_aulas_suporte", "grupo_atual"),
        ),
        "_contexto_ia_manutencao": (
            "assistente_ia.contexto_da_manutencao(",
            ("self.vars_manutencao", "self.campo_manutencao_outro", "self.campo_manutencao_aulas"),
            (),
        ),
        "_contexto_ia_formacao": (
            "assistente_ia.contexto_da_formacao(",
            ("self.var_formacao_organizador", "self.campo_formacao_outro", "self.campo_formacao_aulas"),
            (),
        ),
    }

    @classmethod
    def setUpClass(cls):
        import ast

        cls.fonte = (RAIZ / "app.py").read_text(encoding="utf-8")
        cls.arvore = ast.parse(cls.fonte)
        cls.ast = ast

    def _metodo(self, nome: str) -> str:
        for no in self.ast.walk(self.arvore):
            if isinstance(no, self.ast.FunctionDef) and no.name == nome:
                return self.ast.get_source_segment(self.fonte, no)
        self.fail(f"app.py não tem o método {nome}")

    def _linhas_com_ia(self) -> list:
        """[(texto do rótulo, campo, contexto)] de cada chamada de _linha_rotulo_com_ia."""
        chamadas = []
        for no in self.ast.walk(self.arvore):
            if (
                isinstance(no, self.ast.Call)
                and isinstance(no.func, self.ast.Attribute)
                and no.func.attr == "_linha_rotulo_com_ia"
            ):
                _pai, rotulo, campo, contexto = no.args
                chamadas.append((rotulo.value, campo.attr, contexto.attr))
        return chamadas

    def test_cada_campo_de_breve_descricao_tem_o_botao_certo(self):
        achadas = {campo: (rotulo, contexto) for rotulo, campo, contexto in self._linhas_com_ia()}
        self.assertEqual(len(self._linhas_com_ia()), 4, "são quatro campos de breve descrição")
        self.assertEqual(achadas, self.CAMPOS)

    def test_os_campos_continuam_existindo_e_nenhum_rotulo_ficou_solto(self):
        for campo in self.CAMPOS:
            self.assertTrue(f"self.{campo} = ttk.Entry(" in self.fonte, f"sumiu o campo {campo}")
        # o rótulo antigo (um ttk.Label solto) foi trocado pela linha com o botão
        rotulos = {rotulo for rotulo, _ in self.CAMPOS.values()}
        for no in self.ast.walk(self.arvore):
            if isinstance(no, self.ast.Call) and isinstance(no.func, self.ast.Attribute) and no.func.attr == "Label":
                for palavra in no.keywords:
                    if palavra.arg == "text" and isinstance(palavra.value, self.ast.Constant):
                        self.assertNotIn(
                            palavra.value.value, rotulos, "rótulo de breve descrição ainda solto, sem o botão"
                        )

    def test_cada_contexto_le_os_campos_da_tela_dele(self):
        for nome, (funcao, deve_ler, nao_deve_ler) in self.LEITURAS.items():
            corpo = self._metodo(nome)
            self.assertTrue(funcao in corpo, f"{nome} não chama {funcao}")
            for trecho in deve_ler:
                self.assertTrue(trecho in corpo, f"{nome} não lê {trecho}")
            for trecho in nao_deve_ler:
                self.assertFalse(trecho in corpo, f"{nome} lê {trecho}, que é de outra tela")

    def test_o_botao_abre_a_conversa_e_so_troca_o_texto_do_campo_ao_usar(self):
        corpo = self._metodo("_escrever_descricao_com_ia")
        for trecho in ("assistente_ia.abrir(", "campo.delete(0, \"end\")", "campo.insert(0, texto)", "_PALETA"):
            self.assertTrue(trecho in corpo, f"_escrever_descricao_com_ia não tem: {trecho}")
        # o campo só muda dentro do "Usar este texto" (a função aninhada), nunca ao abrir
        self.assertTrue(corpo.index("def _usar") < corpo.index("campo.delete"))
        self.assertTrue(corpo.index("campo.delete") < corpo.index("assistente_ia.abrir("))

    def test_o_botao_do_laboratorio_continua_igual(self):
        corpo = self._metodo("_escrever_conteudo_com_ia")
        self.assertTrue("finalidade" not in corpo, "o laboratório não manda finalidade: é o padrão")
        self.assertTrue("self.campo_conteudo" in corpo)


class ContextoParaEnviar(unittest.TestCase):
    def test_so_os_campos_combinados(self):
        limpo = assistente_ia.contexto_para_enviar(CONTEXTO)
        self.assertEqual(sorted(limpo), ["assunto", "disciplina", "etapa", "numero_aulas", "turma"])
        self.assertNotIn("professor", limpo)

    def test_campo_com_dado_pessoal_fica_de_fora_em_vez_de_travar(self):
        # o assunto vem da agenda, que a pessoa não edita na janela da IA
        com_telefone = dict(CONTEXTO, assunto="falar com a mãe no (47) 99999-8888")
        limpo = assistente_ia.contexto_para_enviar(com_telefone)
        self.assertNotIn("assunto", limpo)
        self.assertEqual(limpo["disciplina"], "Geografia")

    def test_recursos_marcados_nao_saem_do_computador(self):
        # a IA deixou de receber os recursos (já vão em outro campo do formulário)
        self.assertIn("recursos", CONTEXTO)
        self.assertNotIn("recursos", assistente_ia.contexto_para_enviar(CONTEXTO))

    def test_contexto_vazio(self):
        self.assertEqual(assistente_ia.contexto_para_enviar(None), {})

    def test_registros_breves_levam_a_finalidade_e_os_campos_deles(self):
        limpo = assistente_ia.contexto_para_enviar(
            {
                "finalidade": "manutencao",
                "itens": ["Projetor", "Tablets"],  # o servidor só aceita texto: a lista vira um texto só
                "outro": "caixas de som",
                "numero_aulas": "2",
                "professor": "FULANA DE TAL",
            }
        )
        self.assertEqual(
            limpo,
            {"finalidade": "manutencao", "itens": "Projetor, Tablets", "outro": "caixas de som", "numero_aulas": "2"},
        )

    def test_texto_de_outro_com_dado_pessoal_fica_de_fora(self):
        limpo = assistente_ia.contexto_para_enviar(
            {"finalidade": "manutencao", "itens": "Projetor", "outro": "ligar para 47 99999-8888"}
        )
        self.assertNotIn("outro", limpo)
        self.assertEqual(limpo["itens"], "Projetor")

    def test_lista_com_dado_pessoal_dentro_tambem_fica_de_fora(self):
        limpo = assistente_ia.contexto_para_enviar({"itens": ["Projetor", "a@b.com"]})
        self.assertNotIn("itens", limpo)


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
            ["assunto", "disciplina", "etapa", "numero_aulas", "turma"],
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
