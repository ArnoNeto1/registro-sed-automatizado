# -*- coding: utf-8 -*-
"""
Testes da leitura de escola com MAIS DE UM laboratório (agenda_scraper.py).

O caso de origem: um professor trabalha numa escola com dois laboratórios de
Tecnologias Educacionais, e o programa só trazia as aulas de um. A agenda padrão
do site do NTE é um laboratório só; o segundo aparece no menu "Agenda: ..." com o
nome que a escola deu, e não batia com nenhuma palavra reconhecida (projetor,
tablet...). Estes testes seguram a correção: reconhecer o outro laboratório pelo
nome, sem puxar sala de outra área, e sem ler o laboratório padrão duas vezes.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agenda_scraper  # noqa: E402
from agenda_scraper import Agendamento, e_outro_laboratorio_tec  # noqa: E402


class ReconhecerOutroLaboratorio(unittest.TestCase):
    def test_menu_real_da_escola_do_relato(self):
        # Print do menu "Agenda:" mandado pelo professor (19/10/2026),
        # na ordem em que o site mostra.
        esperado = {
            "Auditório": None,
            "Biblioteca": None,
            "Lab. Maker": "Laboratório",
            "Lab. Tecs": "Laboratório",  # o padrão; descartado por repetir
            "Laboratório de Informática 02": "Laboratório",
            "Notebooks": "Tablets/Celular",
            "Tablets": "Tablets/Celular",
        }
        for nome, aba in esperado.items():
            with self.subTest(nome=nome):
                if e_outro_laboratorio_tec(nome):
                    obtida = "Laboratório"
                else:
                    obtida = agenda_scraper.categoria_do_recurso(nome)
                self.assertEqual(obtida, aba)

    def test_nomes_de_laboratorio_de_tecnologia(self):
        for nome in (
            "Lab. Tecs 2",
            "Laboratório 2",
            "Laboratório de Informática",
            "Sala de Informática",
            "Lab Maker",
            "Espaço Maker",
            "Sala de Robótica",
            "Tecnologias Educacionais II",
            "Sala de Tecnologia",
            "STE",
            "Sala Maker",
            "Lab. Informática 2",
        ):
            with self.subTest(nome=nome):
                self.assertTrue(e_outro_laboratorio_tec(nome))

    def test_salas_que_nao_sao_do_orientador(self):
        for nome in (
            "Laboratório de Ciências",
            "Lab. de Química",
            "Biblioteca",
            "Auditório",
            "Espaço Colaborativo",
            "Quadra",
            "Sala Steam 3",
            "Estúdio",
        ):
            with self.subTest(nome=nome):
                self.assertFalse(e_outro_laboratorio_tec(nome))

    def test_projetor_e_tablet_continuam_na_aba_propria(self):
        self.assertFalse(e_outro_laboratorio_tec("Projetor 1"))
        self.assertFalse(e_outro_laboratorio_tec("Tablets do Lab"))
        self.assertEqual(agenda_scraper.categoria_do_recurso("Tablets do Lab"), "Tablets/Celular")


def _aula(professor: str, inicio: str = "07:15", recurso: str = "Lab. Tecs") -> Agendamento:
    return Agendamento(
        data="2026-10-19", inicio=inicio, fim="08:00", professor=professor,
        disciplina="Arte", turma="6º ano", conteudo="", agendado_em="",
        turno="Matutino", recurso=recurso,
    )


class LerSemanaComDoisLaboratorios(unittest.TestCase):
    """scrape_semana_completa com o site simulado: a agenda padrão, mais o
    menu com o próprio laboratório padrão (id 10) e o segundo (id 11)."""

    def _ler(self, menu, agendas):
        def falso_scrape_week(page, monday, turnos=None, agenda_id=None, nome_recurso="Lab. Tecs"):
            aulas = [_aula(p, i) for p, i in agendas[agenda_id]]
            for a in aulas:
                a.recurso = nome_recurso
            return aulas

        with mock.patch.object(agenda_scraper, "scrape_week", falso_scrape_week), \
                mock.patch.object(agenda_scraper, "descobrir_outros_recursos", lambda page: menu):
            return agenda_scraper.scrape_semana_completa(None, dt.date(2026, 10, 19))

    def test_traz_as_aulas_dos_dois_sem_repetir_o_padrao(self):
        agendas = {
            None: [("ANA", "07:15")],   # padrão = laboratório 1
            "10": [("ANA", "07:15")],   # o mesmo laboratório 1, pelo menu
            "11": [("BRUNO", "08:00")],  # laboratório 2
        }
        menu = [("Lab. Tecs", "10", "Laboratório"), ("Lab. Tecs 2", "11", "Laboratório")]
        lidas = self._ler(menu, agendas)
        self.assertEqual(
            sorted((a.professor, a.recurso) for a in lidas),
            [("ANA", "Lab. Tecs"), ("BRUNO", "Lab. Tecs 2")],
        )

    def test_escola_de_um_laboratorio_so_nao_muda(self):
        agendas = {None: [("ANA", "07:15")], "10": [("ANA", "07:15")]}
        lidas = self._ler([("Lab. Tecs", "10", "Laboratório")], agendas)
        self.assertEqual([(a.professor, a.recurso) for a in lidas], [("ANA", "Lab. Tecs")])

    def test_projetor_com_mesmas_reservas_nao_e_descartado(self):
        # a regra de "mesma agenda" vale só entre laboratórios
        agendas = {None: [], "20": []}
        agendas["20"] = [("ANA", "07:15")]
        agendas[None] = [("ANA", "07:15")]
        lidas = self._ler([("Projetor 1", "20", "Projetores")], agendas)
        self.assertEqual(len(lidas), 2)


if __name__ == "__main__":
    unittest.main()
