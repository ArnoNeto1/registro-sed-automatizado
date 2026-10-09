# -*- coding: utf-8 -*-
"""
Testes da conferência do nome da escola (conferir_escola.py) e de onde ela é usada.

O caso de origem: uma professora abriu o programa e o formulário da SED não aceitou a
escola "EEE Profº João Widemann". Nas versões 1.3 a 1.5 a escola do cadastro era uma caixa
em que se podia DIGITAR; o que foi digitado ficou salvo para sempre (as versões novas só
leem o valor, nunca o conferem), e o formulário só aceita o texto EXATO da lista da SED
("EEB PROF JOAO WIDEMANN"). Estes testes seguram a correção: conferir cedo, corrigir sozinho
só o que é pura grafia, perguntar quando há dúvida e explicar em português.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import ast
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import conferir_escola  # noqa: E402
import escolas  # noqa: E402

WIDEMANN = "EEB PROF JOAO WIDEMANN"
EEE_DA_PROFESSORA = "EEE Profº João Widemann"  # exatamente como aparece na tela dela


class Conferir(unittest.TestCase):
    def test_nome_exato_da_lista_esta_certo(self):
        conferencia = conferir_escola.conferir(WIDEMANN)
        self.assertEqual(conferencia.situacao, "certa")
        self.assertEqual(conferencia.escola, WIDEMANN)

    def test_toda_a_lista_oficial_confere_e_nenhuma_se_confunde_com_outra(self):
        chaves = [conferir_escola.chave(nome) for nome in escolas.ESCOLAS_CRE_BLUMENAU]
        self.assertEqual(len(chaves), len(set(chaves)), "duas escolas da lista ficariam iguais depois de normalizar")
        for nome in escolas.ESCOLAS_CRE_BLUMENAU:
            self.assertEqual(conferir_escola.conferir(nome).situacao, "certa", nome)

    def test_so_a_grafia_diferente_e_corrigida_sozinha(self):
        # o site do NTE escreve "Profº"; gente digita minúsculas, sem acento, com espaço sobrando
        variacoes = (
            "EEB Profº João Widemann",
            "eeb prof joao widemann",
            "  EEB   PROF  JOAO   WIDEMANN ",
            "EEB Prof. João Widemann",
            "EEB Profª João Widemann",
            "EEB Professor João Widemann",
            "EEB PROF. JOÃO WIDEMANN",
        )
        for texto in variacoes:
            conferencia = conferir_escola.conferir(texto)
            self.assertEqual((conferencia.situacao, conferencia.escola), ("so_grafia", WIDEMANN), repr(texto))

    def test_apostrofo_e_sigla_tambem_sao_so_grafia(self):
        conferencia = conferir_escola.conferir("EEB Ivo D'Aquino")
        self.assertEqual((conferencia.situacao, conferencia.escola), ("so_grafia", "EEB IVO D AQUINO"))

    def test_todo_nome_oficial_digitado_em_minusculas_volta_ao_oficial(self):
        for nome in escolas.ESCOLAS_CRE_BLUMENAU:
            conferencia = conferir_escola.conferir(nome.lower())
            self.assertEqual((conferencia.situacao, conferencia.escola), ("so_grafia", nome), nome)

    def test_o_caso_da_professora_vira_pergunta_e_nao_e_corrigido_sozinho(self):
        # "EEE" no lugar de "EEB": pode ser engano de digitação OU outra escola; só quem sabe é a pessoa
        conferencia = conferir_escola.conferir(EEE_DA_PROFESSORA)
        self.assertEqual(conferencia.situacao, "sugerida")
        self.assertEqual(conferencia.escola, "")  # nada é trocado sem confirmar
        self.assertEqual(conferencia.sugestoes, [WIDEMANN])

    def test_outro_tipo_de_escola_com_o_mesmo_nome_nunca_e_corrigido_sozinho(self):
        for texto in ("EEM PROF JOAO WIDEMANN", "EEF Profº João Widemann", "CEDUP Prof João Widemann"):
            conferencia = conferir_escola.conferir(texto)
            self.assertEqual(conferencia.situacao, "sugerida", texto)
            self.assertIn(WIDEMANN, conferencia.sugestoes, texto)

    def test_erro_de_digitacao_vira_sugestao(self):
        conferencia = conferir_escola.conferir("EEB PROF JOAO WIDEMAN")
        self.assertEqual(conferencia.situacao, "sugerida")
        self.assertEqual(conferencia.sugestoes[0], WIDEMANN)

    def test_nome_parecido_de_outra_escola_nao_e_corrigido_sozinho(self):
        # "EEB JOAO GAYA" e "EEB PROF JOAO WIDEMANN" existem; "PROF JOAO GAYA" não é nenhuma das duas
        conferencia = conferir_escola.conferir("EEB PROF JOAO GAYA")
        self.assertNotEqual(conferencia.situacao, "so_grafia")
        self.assertEqual(conferencia.escola, "")

    def test_nome_sem_nada_a_ver_nao_tem_sugestao(self):
        for texto in ("Colégio Qualquer Coisa", "FULANA DA SILVA", "PREENCHA ESCOLA NO .env !!"):
            conferencia = conferir_escola.conferir(texto)
            self.assertEqual((conferencia.situacao, conferencia.sugestoes), ("desconhecida", []), texto)

    def test_vazio_nao_e_escola_errada(self):
        for texto in ("", "   ", None):
            self.assertEqual(conferir_escola.conferir(texto).situacao, "vazia", repr(texto))

    def test_sem_a_lista_nao_da_para_julgar_e_nada_e_barrado(self):
        # se a lista não puder ser lida, o programa já deixa digitar livremente (configuracao.escolas_conhecidas)
        conferencia = conferir_escola.conferir("Qualquer coisa", oficiais=[])
        self.assertEqual((conferencia.situacao, conferencia.escola), ("certa", "Qualquer coisa"))

    def test_dois_oficiais_iguais_depois_de_normalizar_nao_corrigem_sozinhos(self):
        oficiais = ["EEB PROF A B", "EEB Profº A B"]
        conferencia = conferir_escola.conferir("eeb prof a b", oficiais=oficiais)
        self.assertEqual(conferencia.situacao, "sugerida")
        self.assertEqual(conferencia.escola, "")
        self.assertEqual(sorted(conferencia.sugestoes), sorted(oficiais))

    def test_no_maximo_tres_sugestoes(self):
        oficiais = [f"EEB ESCOLA NUMERO {n}" for n in "ABCDEF"]
        self.assertLessEqual(len(conferir_escola.conferir("EEB ESCOLA NUMERO", oficiais=oficiais).sugestoes), 3)


class EscolaParaMostrar(unittest.TestCase):
    """O que a tela "Meus dados" põe no campo da escola: nunca um valor que a lista não tem."""

    def test_valor_da_lista_fica_como_esta(self):
        self.assertEqual(conferir_escola.escola_para_mostrar(WIDEMANN), (WIDEMANN, ""))

    def test_sem_escola_salva_nao_ha_o_que_mostrar_nem_avisar(self):
        self.assertEqual(conferir_escola.escola_para_mostrar(""), ("", ""))
        self.assertEqual(conferir_escola.escola_para_mostrar(None), ("", ""))

    def test_so_grafia_entra_ja_corrigida_sem_barulho(self):
        self.assertEqual(conferir_escola.escola_para_mostrar("EEB Profº João Widemann"), (WIDEMANN, ""))

    def test_valor_fora_da_lista_fica_em_branco_e_a_tela_avisa(self):
        # sem isto, "Meus dados" repunha o valor errado no campo e o gravava de novo ao salvar
        texto, aviso = conferir_escola.escola_para_mostrar(EEE_DA_PROFESSORA)
        self.assertEqual(texto, "")
        self.assertIn(EEE_DA_PROFESSORA, aviso)
        self.assertIn(WIDEMANN, aviso)  # a sugestão ajuda a pessoa a achar a certa na lista

    def test_o_aviso_e_curto_para_nao_empurrar_o_botao_salvar_para_fora_da_tela(self):
        # "Meus dados" não rola: num monitor de 768 px de altura cada linha a mais pode esconder o Salvar
        for salvo in (EEE_DA_PROFESSORA, "Colégio Qualquer Coisa", "EEF PROF. JOÃO WIDEMANN DA SILVA JUNIOR"):
            _texto, aviso = conferir_escola.escola_para_mostrar(salvo)
            self.assertLessEqual(len(aviso), 150, aviso)

    def test_valor_sem_nenhuma_sugestao_tambem_fica_em_branco(self):
        texto, aviso = conferir_escola.escola_para_mostrar("Colégio Qualquer Coisa")
        self.assertEqual(texto, "")
        self.assertIn("Colégio Qualquer Coisa", aviso)

    def test_sem_a_lista_o_valor_salvo_e_mantido(self):
        self.assertEqual(conferir_escola.escola_para_mostrar("Qualquer coisa", oficiais=[]), ("Qualquer coisa", ""))


class Explicar(unittest.TestCase):
    def test_com_uma_sugestao_diz_qual_e_manda_para_meus_dados(self):
        texto = conferir_escola.explicar(EEE_DA_PROFESSORA, conferir_escola.conferir(EEE_DA_PROFESSORA))
        self.assertIn(EEE_DA_PROFESSORA, texto)
        self.assertIn(WIDEMANN, texto)
        self.assertIn("Meus dados", texto)

    def test_com_varias_sugestoes_lista_todas(self):
        oficiais = ["EEB PROF A B", "EEM PROF A B"]
        texto = conferir_escola.explicar("EEF Prof A B", conferir_escola.conferir("EEF Prof A B", oficiais=oficiais))
        for nome in oficiais:
            self.assertIn(nome, texto)

    def test_sem_sugestao_ainda_diz_o_que_fazer(self):
        texto = conferir_escola.explicar("Colégio X", conferir_escola.conferir("Colégio X"))
        self.assertIn("Colégio X", texto)
        self.assertIn("Meus dados", texto)
        self.assertIn("lista", texto)

    def test_nao_usa_o_texto_tecnico_do_erro_antigo(self):
        texto = conferir_escola.explicar(EEE_DA_PROFESSORA, conferir_escola.conferir(EEE_DA_PROFESSORA))
        self.assertNotIn("RuntimeError", texto)
        self.assertNotIn("janela do Chrome", texto)


class CorrigirEscola(unittest.TestCase):
    """Reescreve o configuracao.json trocando a escola errada pela certa, sem perder turnos nem professores."""

    DADOS = {
        "escola": EEE_DA_PROFESSORA,
        "regional": "BLUMENAU",
        "tema": "Escuro",
        "professores": [
            {
                "nome": "Ana",
                "cpf": "11111111111",
                "tipo": "tecnologias",
                "escolas": [EEE_DA_PROFESSORA, "EEB PEDRO II"],
                "turnos_por_escola": {EEE_DA_PROFESSORA: ["Matutino"], "EEB PEDRO II": ["Noturno"]},
                "turnos": ["Matutino", "Noturno"],
            },
            {"nome": "Beto", "cpf": "22222222222", "escola": EEE_DA_PROFESSORA, "turnos": ["Vespertino"]},
            {
                "nome": "Cida",
                "cpf": "33333333333",
                "escolas": ["EEB SANTOS DUMONT"],
                "turnos_por_escola": {"EEB SANTOS DUMONT": ["Matutino"]},
            },
        ],
    }

    def setUp(self):
        # cada teste recebe a SUA cópia: se a função alterasse o que recebe, o "antes" de
        # um teste não pode já vir contaminado pelos outros
        self.dados = copy.deepcopy(self.DADOS)

    def corrigido(self, dados=None):
        return conferir_escola.corrigir_escola(self.dados if dados is None else dados, EEE_DA_PROFESSORA, WIDEMANN)

    def test_nao_mexe_no_dicionario_que_recebeu(self):
        self.corrigido()
        self.assertEqual(self.dados, self.DADOS)

    def test_troca_a_escola_padrao_do_computador(self):
        self.assertEqual(self.corrigido()["escola"], WIDEMANN)

    def test_troca_na_lista_de_escolas_do_professor_mantendo_a_ordem(self):
        ana = self.corrigido()["professores"][0]
        self.assertEqual(ana["escolas"], [WIDEMANN, "EEB PEDRO II"])

    def test_os_turnos_acompanham_a_escola_nova(self):
        ana = self.corrigido()["professores"][0]
        self.assertEqual(ana["turnos_por_escola"], {WIDEMANN: ["Matutino"], "EEB PEDRO II": ["Noturno"]})
        self.assertEqual(ana["turnos"], ["Matutino", "Noturno"])

    def test_cadastro_antigo_com_escola_em_texto_tambem_e_corrigido(self):
        self.assertEqual(self.corrigido()["professores"][1]["escola"], WIDEMANN)

    def test_quem_e_de_outra_escola_nao_e_tocado(self):
        self.assertEqual(self.corrigido()["professores"][2], self.DADOS["professores"][2])

    def test_o_resto_do_arquivo_fica_igual(self):
        novo = self.corrigido()
        for chave in ("regional", "tema"):
            self.assertEqual(novo[chave], self.DADOS[chave])
        self.assertEqual([p["nome"] for p in novo["professores"]], ["Ana", "Beto", "Cida"])

    def test_se_a_escola_certa_ja_estava_na_lista_nao_duplica_e_guarda_os_turnos_dela(self):
        dados = self.dados
        dados["professores"][0]["escolas"] = [EEE_DA_PROFESSORA, WIDEMANN]
        dados["professores"][0]["turnos_por_escola"] = {EEE_DA_PROFESSORA: ["Matutino"], WIDEMANN: ["Noturno"]}
        ana = self.corrigido(dados)["professores"][0]
        self.assertEqual(ana["escolas"], [WIDEMANN])
        self.assertEqual(ana["turnos_por_escola"], {WIDEMANN: ["Noturno"]})  # o que a pessoa já tinha marcado na certa

    def test_dados_sem_nada_a_corrigir_ou_vazios(self):
        self.assertEqual(conferir_escola.corrigir_escola({}, EEE_DA_PROFESSORA, WIDEMANN), {})
        outro = {"escola": "EEB PEDRO II", "professores": []}
        self.assertEqual(conferir_escola.corrigir_escola(outro, EEE_DA_PROFESSORA, WIDEMANN), outro)


class GravarACorrecaoNoArquivo(unittest.TestCase):
    """
    configuracao.carregar() devolve {} quando a leitura FALHA (arquivo preso, JSON cortado...). Se a
    correção gravasse esse {} por cima, o cadastro inteiro (professores, CPFs, turnos) sumiria. Como a
    conferência roda sozinha, a cada abertura, ela tem de ser incapaz disso.
    """

    DADOS = {
        "escola": EEE_DA_PROFESSORA,
        "regional": "BLUMENAU",
        "professores": [
            {
                "nome": "Ana",
                "cpf": "11111111111",
                "escolas": [EEE_DA_PROFESSORA],
                "turnos_por_escola": {EEE_DA_PROFESSORA: ["Matutino"]},
            }
        ],
    }

    def setUp(self):
        import configuracao

        self.configuracao = configuracao
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        alvo = mock.patch.object(
            configuracao, "caminho_de_dados", lambda *p: str(Path(self.pasta.name).joinpath(*p))
        )
        alvo.start()
        self.addCleanup(alvo.stop)
        self.arquivo = Path(self.pasta.name) / "configuracao.json"

    def escrever(self, dados=None):
        self.arquivo.write_text(json.dumps(self.DADOS if dados is None else dados, ensure_ascii=False), encoding="utf-8")

    def test_corrige_e_grava(self):
        self.escrever()
        self.assertTrue(self.configuracao.corrigir_escola_salva(EEE_DA_PROFESSORA, WIDEMANN))
        salvo = json.loads(self.arquivo.read_text(encoding="utf-8"))
        self.assertEqual(salvo["escola"], WIDEMANN)
        self.assertEqual(salvo["professores"][0]["escolas"], [WIDEMANN])
        self.assertEqual(salvo["professores"][0]["turnos_por_escola"], {WIDEMANN: ["Matutino"]})
        self.assertEqual(salvo["professores"][0]["cpf"], "11111111111")

    def test_sem_nada_a_corrigir_nao_grava(self):
        self.escrever({"escola": "EEB PEDRO II", "professores": [{"nome": "Ana", "cpf": "1", "escolas": ["EEB PEDRO II"]}]})
        antes = self.arquivo.read_bytes()
        self.assertFalse(self.configuracao.corrigir_escola_salva(EEE_DA_PROFESSORA, WIDEMANN))
        self.assertEqual(self.arquivo.read_bytes(), antes)

    def test_arquivo_ausente_nao_cria_nada(self):
        self.assertFalse(self.configuracao.corrigir_escola_salva(EEE_DA_PROFESSORA, WIDEMANN))
        self.assertFalse(self.arquivo.exists())

    def test_arquivo_ilegivel_nunca_e_sobrescrito_com_vazio(self):
        self.arquivo.write_text('{"professores": [ {"nome": "Ana", ', encoding="utf-8")  # JSON cortado
        antes = self.arquivo.read_bytes()
        self.assertFalse(self.configuracao.corrigir_escola_salva(EEE_DA_PROFESSORA, WIDEMANN))
        self.assertEqual(self.arquivo.read_bytes(), antes)

    def test_falha_de_leitura_passageira_nao_apaga_o_cadastro(self):
        self.escrever()
        antes = self.arquivo.read_bytes()
        with mock.patch.object(self.configuracao, "carregar", return_value={}):  # é o que carregar() devolve ao falhar
            self.assertFalse(self.configuracao.corrigir_escola_salva(EEE_DA_PROFESSORA, WIDEMANN))
        self.assertEqual(self.arquivo.read_bytes(), antes)


class EscolherNoFormulario(unittest.TestCase):
    """A página 2 do formulário: usa o nome da lista e, se falhar, explica em vez do erro genérico."""

    PAGINA = object()  # a conferência acontece antes de qualquer toque na página

    def setUp(self):
        import sed_form_filler

        self.filler = sed_form_filler
        alvo = mock.patch.object(sed_form_filler, "_select_google_dropdown")
        self.dropdown = alvo.start()
        self.addCleanup(alvo.stop)

    def test_nome_certo_vai_como_esta(self):
        self.filler._escolher_escola(self.PAGINA, WIDEMANN)
        self.dropdown.assert_called_once_with(self.PAGINA, "Selecione a sua Escola", WIDEMANN)

    def test_so_grafia_diferente_usa_o_nome_exato_da_lista(self):
        self.filler._escolher_escola(self.PAGINA, "EEB Profº João Widemann")
        self.dropdown.assert_called_once_with(self.PAGINA, "Selecione a sua Escola", WIDEMANN)

    def test_nome_fora_da_lista_e_tentado_do_jeito_que_veio_e_o_erro_explica(self):
        # a lista do programa pode estar atrasada em relação ao formulário: por isso a tentativa ainda é feita
        self.dropdown.side_effect = RuntimeError(
            "Não consegui confirmar a seleção de 'X' no menu 'Selecione a sua Escola' — confira manualmente a janela do Chrome."
        )
        with self.assertRaises(RuntimeError) as caso:
            self.filler._escolher_escola(self.PAGINA, EEE_DA_PROFESSORA)
        self.dropdown.assert_called_once_with(self.PAGINA, "Selecione a sua Escola", EEE_DA_PROFESSORA)
        mensagem = str(caso.exception)
        self.assertIn(EEE_DA_PROFESSORA, mensagem)
        self.assertIn(WIDEMANN, mensagem)
        self.assertIn("Meus dados", mensagem)
        self.assertNotIn("janela do Chrome", mensagem)

    def test_no_formato_antigo_do_env_manda_corrigir_a_linha_escola_e_nao_o_meus_dados(self):
        # quem usa o .env não tem o botão "Meus dados": mandar clicar nele é uma instrução impossível
        self.dropdown.side_effect = RuntimeError("x")
        with mock.patch.object(self.filler, "SENHAS_SALVAS", True):
            with self.assertRaises(RuntimeError) as caso:
                self.filler._escolher_escola(self.PAGINA, EEE_DA_PROFESSORA)
        mensagem = str(caso.exception)
        self.assertIn("ESCOLA=", mensagem)
        self.assertNotIn("Meus dados", mensagem)

    def test_na_configuracao_pela_tela_manda_para_meus_dados(self):
        self.dropdown.side_effect = RuntimeError("x")
        with mock.patch.object(self.filler, "SENHAS_SALVAS", False):
            with self.assertRaises(RuntimeError) as caso:
                self.filler._escolher_escola(self.PAGINA, EEE_DA_PROFESSORA)
        self.assertIn("Meus dados", str(caso.exception))

    def test_falha_com_nome_da_lista_mantem_o_erro_original(self):
        # o nome está certo: o problema é outro (menu que não abriu...), e a mensagem antiga é a que ajuda
        self.dropdown.side_effect = RuntimeError("Não consegui confirmar a seleção de 'X'")
        with self.assertRaises(RuntimeError) as caso:
            self.filler._escolher_escola(self.PAGINA, WIDEMANN)
        self.assertIn("Não consegui confirmar a seleção", str(caso.exception))

    def test_a_pagina_2_do_formulario_passa_por_essa_funcao(self):
        fonte = (RAIZ / "sed_form_filler.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        funcao = next(
            n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == "preencher_dados_fixos"
        )
        chamadas = [
            n.func.id
            for n in ast.walk(funcao)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        self.assertIn("_escolher_escola", chamadas)
        self.assertNotIn(
            '"Selecione a sua Escola", esc)', ast.get_source_segment(fonte, funcao),
            "a escolha da escola voltou a chamar o menu direto, sem conferir",
        )


class LigacaoComOPrograma(unittest.TestCase):
    """app.py não se importa em teste (abre janela); confere-se pela árvore do código."""

    @classmethod
    def setUpClass(cls):
        cls.fonte = (RAIZ / "app.py").read_text(encoding="utf-8")
        cls.arvore = ast.parse(cls.fonte)

    def metodo(self, nome: str) -> str:
        for no in ast.walk(self.arvore):
            if isinstance(no, ast.FunctionDef) and no.name == nome:
                return ast.get_source_segment(self.fonte, no)
        self.fail(f"app.py não tem o método {nome}")

    def test_a_escola_e_conferida_ao_abrir(self):
        self.assertTrue("self._conferir_escola_do_cadastro()" in self.metodo("_checar_configuracao"))

    def test_o_conferidor_usa_a_conferencia_e_a_correcao_do_arquivo(self):
        self.assertTrue("conferir_escola.conferir(" in self.metodo("_conferir_escola_do_cadastro"))
        gravacao = self.metodo("_guardar_escola_corrigida")
        for trecho in ("configuracao.corrigir_escola_salva(", 'self.orientador["escola"] = nova'):
            self.assertTrue(trecho in gravacao, f"_guardar_escola_corrigida não tem: {trecho}")

    def test_so_a_grafia_e_corrigida_sem_perguntar_e_o_resto_pergunta_antes_de_trocar(self):
        corpo = self.metodo("_conferir_escola_do_cadastro")
        self.assertTrue('"so_grafia"' in corpo)
        # a troca com pergunta só acontece depois do "Sim" da pessoa
        self.assertTrue(corpo.index("askyesno") < corpo.index("_guardar_escola_corrigida(escola, sugestoes[0])"))

    def test_no_formato_antigo_do_env_nada_e_gravado_no_configuracao_json(self):
        self.assertTrue("SENHAS_SALVAS" in self.metodo("_guardar_escola_corrigida"))

    def test_os_textos_nao_prometem_que_o_programa_reabre_sozinho(self):
        # no .exe o programa só FECHA (app._reabrir_e_sair não reabre quando empacotado): quem
        # lê "abre de novo" acha que travou. Os outros avisos do programa mandam abrir pelo atalho.
        corpo = self.metodo("_conferir_escola_do_cadastro")
        self.assertFalse("abre de novo" in corpo, "o texto promete reabertura automática")
        self.assertTrue("abra de novo pelo atalho de sempre" in corpo)

    def test_a_tela_de_cadastro_nao_repoe_valor_fora_da_lista(self):
        fonte = (RAIZ / "configuracao.py").read_text(encoding="utf-8")
        self.assertTrue("conferir_escola.escola_para_mostrar(" in fonte)


if __name__ == "__main__":
    unittest.main()
