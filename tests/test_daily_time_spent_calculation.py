

import datetime
import unittest

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from helpdesk.lib import daily_time_spent_calculation


#  5odos os testes usam segunda-feira, 12/10/2026, exceto o teste dos dias da semana

HOUR = 3600
SEGUNDA = 12  # 12/10/2026 é uma segunda-feira
EXPEDIENTE = {"monday": (8.5, 18)}  # das 8h30 às 18h


def at(hour, minute=0, second=0, microsecond=0, day=SEGUNDA):
    """Instante do dia informado (por padrão, segunda-feira 12/10/2026)."""
    return datetime.datetime(2026, 10, day, hour, minute, second, microsecond)


def fim_do_dia(day=SEGUNDA):
    """Último instante do dia, como o cálculo de follow-ups o envia."""
    return at(23, 59, 59, 999999, day=day)


class DailyTimeSpentCalculationWhiteBoxTests(SimpleTestCase):
 

    def test_ct01_expediente_valido_intervalo_dentro_da_janela(self):
        earliest, latest = at(10), at(12)
        resultado = daily_time_spent_calculation(earliest, latest, EXPEDIENTE)
        self.assertEqual(resultado, 2 * HOUR)

    def test_ct02_inicio_negativo_lanca_erro(self):
        expediente = {"monday": (-1, 5)}
        with self.assertRaises(ImproperlyConfigured):
            daily_time_spent_calculation(at(10), at(12), expediente)


    def test_ct03_inicio_depois_do_fim_lanca_erro(self):
        expediente = {"monday": (10, 5)}
        with self.assertRaises(ImproperlyConfigured):
            daily_time_spent_calculation(at(10), at(12), expediente)

    def test_ct04_fim_acima_do_limite_lanca_erro(self):
        expediente = {"monday": (8, 24)}
        with self.assertRaises(ImproperlyConfigured):
            daily_time_spent_calculation(at(10), at(12), expediente)



    def test_ct05_fim_do_dia_com_expediente_ate_a_meia_noite_soma_um_segundo(self):
        # Dia ausente do dicionário vale o dia inteiro (0, 23.9999)
        resultado = daily_time_spent_calculation(at(0), fim_do_dia(), {})
        self.assertEqual(resultado, 24 * HOUR)

    def test_ct06_intervalo_nao_chega_ao_fim_do_dia_nao_soma_segundo(self):
        resultado = daily_time_spent_calculation(at(10), at(12), {})
        self.assertEqual(resultado, 2 * HOUR)

    def test_ct07_expediente_fecha_antes_do_fim_do_dia_nao_soma_segundo(self):
        resultado = daily_time_spent_calculation(at(10), fim_do_dia(), EXPEDIENTE)
        self.assertEqual(resultado, 8 * HOUR)



    def test_ct08_inicio_antes_da_abertura_conta_a_partir_da_abertura(self):
        resultado = daily_time_spent_calculation(at(7), at(10), EXPEDIENTE)
        # 8h30 às 10h
        self.assertEqual(resultado, 1 * HOUR + 30 * 60)

    def test_ct09_intervalo_depois_do_fechamento_nao_conta(self):
        resultado = daily_time_spent_calculation(at(19), at(21), EXPEDIENTE)
        self.assertEqual(resultado, 0)

    def test_ct10_fim_depois_do_fechamento_conta_ate_o_fechamento(self):
        resultado = daily_time_spent_calculation(at(17), at(21), EXPEDIENTE)
        # 17h às 18h
        self.assertEqual(resultado, 1 * HOUR)

    def test_ct11_intervalo_antes_da_abertura_nao_conta(self):
        resultado = daily_time_spent_calculation(at(6), at(7), EXPEDIENTE)
        self.assertEqual(resultado, 0)


class DailyTimeSpentCalculationBlackBoxTests(SimpleTestCase):
  

    def test_ct12_intervalo_cobre_a_janela_inteira(self):
        resultado = daily_time_spent_calculation(at(6), at(22), EXPEDIENTE)
        # 8h30 às 18h = 9h30
        self.assertEqual(resultado, 9 * HOUR + 30 * 60)

    def test_ct13_dia_sem_expediente_nao_conta_nada(self):
        expediente = {"monday": (0, 0)}
        resultado = daily_time_spent_calculation(at(10), at(12), expediente)
        self.assertEqual(resultado, 0)

    def test_ct14_cada_dia_da_semana_usa_a_propria_janela(self):
        # Janelas de 1h (segunda) a 7h (domingo), todas abrindo às 9h
        dias = (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
        expediente = {dia: (9, 9 + i + 1) for i, dia in enumerate(dias)}
        for i, dia in enumerate(dias):
            with self.subTest(dia=dia):
                day = SEGUNDA + i
                resultado = daily_time_spent_calculation(
                    at(0, day=day), fim_do_dia(day), expediente
                )
                self.assertEqual(resultado, (i + 1) * HOUR)

    def test_ct15_intervalo_de_duracao_zero(self):
        resultado = daily_time_spent_calculation(at(10), at(10), EXPEDIENTE)
        self.assertEqual(resultado, 0)

    def test_ct16_horas_decimais_exatas_viram_horas_e_minutos(self):
        # 8.25 = 8h15 e 18.75 = 18h45
        expediente = {"monday": (8.25, 18.75)}
        resultado = daily_time_spent_calculation(at(7), at(20), expediente)
        # 10h30
        self.assertEqual(resultado, 10 * HOUR + 30 * 60)




    # Análise de valor limite: faixa permitida para o expediente

    def test_ct17_inicio_no_limite_inferior_zero_e_valido(self):
        expediente = {"monday": (0, 5)}
        resultado = daily_time_spent_calculation(at(1), at(3), expediente)
        self.assertEqual(resultado, 2 * HOUR)

    def test_ct18_fim_no_limite_superior_e_valido(self):
        expediente = {"monday": (0, 23.9999)}
        resultado = daily_time_spent_calculation(at(0), fim_do_dia(), expediente)
        self.assertEqual(resultado, 24 * HOUR)

    def test_ct19_inicio_logo_abaixo_do_limite_inferior_lanca_erro(self):
        expediente = {"monday": (-0.0001, 5)}
        with self.assertRaises(ImproperlyConfigured):
            daily_time_spent_calculation(at(1), at(3), expediente)

    def test_ct20_fim_logo_acima_do_limite_superior_lanca_erro(self):
        expediente = {"monday": (0, 23.99991)}
        with self.assertRaises(ImproperlyConfigured):
            daily_time_spent_calculation(at(1), at(3), expediente)

    def test_ct21_inicio_igual_ao_fim_e_valido_e_nao_conta_nada(self):
        expediente = {"monday": (9, 9)}
        resultado = daily_time_spent_calculation(at(8), at(10), expediente)
        self.assertEqual(resultado, 0)




    # Análise de valor limite: instantes na abertura e no fechamento

    def test_ct22_instantes_ao_redor_da_abertura(self):
        # Abertura às 8h30, fim do intervalo às 10h
        casos = (
            (at(8, 29, 59), 1 * HOUR + 30 * 60),  # um segundo antes: conta da abertura
            (at(8, 30, 0), 1 * HOUR + 30 * 60),  # exatamente na abertura
            (at(8, 30, 1), 1 * HOUR + 30 * 60 - 1),  # um segundo depois
        )
        for earliest, esperado in casos:
            with self.subTest(inicio=earliest.time()):
                resultado = daily_time_spent_calculation(
                    earliest, at(10), EXPEDIENTE
                )
                self.assertEqual(resultado, esperado)

    def test_ct23_instantes_ao_redor_do_fechamento(self):
        # Início do intervalo às 10h, fechamento às 18h
        casos = (
            (at(17, 59, 59), 8 * HOUR - 1),  # um segundo antes
            (at(18, 0, 0), 8 * HOUR),  # exatamente no fechamento
            (at(18, 0, 1), 8 * HOUR),  # um segundo depois: não passa do fechamento
        )
        for latest, esperado in casos:
            with self.subTest(fim=latest.time()):
                resultado = daily_time_spent_calculation(
                    at(10), latest, EXPEDIENTE
                )
                self.assertEqual(resultado, esperado)



    # Horas decimais não exatas: defeito encontrado (ver relatório,  item 5.4.4)
    
    # O teste afirma o comportamento especificado e está marcado como falha
    # esperada;   se o código for corrigido, o teste passa a acusar "unexpected
    # success", sinalizando que a marcação deve ser removida.

    @unittest.expectedFailure
    def test_ct24_abertura_decimal_nao_exata_8_1_equivale_a_8h06(self):
        # 8.1 = 8h06
        expediente = {"monday": (8.1, 18)}
        resultado = daily_time_spent_calculation(at(7), at(10), expediente)
        # 8h06 às 10h = 1h54
        self.assertEqual(resultado, 1 * HOUR + 54 * 60)

    @unittest.expectedFailure
    def test_ct25_fechamento_decimal_nao_exato_17_9_equivale_a_17h54(self):
        # 17.9 = 17h54
        expediente = {"monday": (8, 17.9)}
        resultado = daily_time_spent_calculation(at(16), at(20), expediente)
        # 16h às 17h54 = 1h54
        self.assertEqual(resultado, 1 * HOUR + 54 * 60)