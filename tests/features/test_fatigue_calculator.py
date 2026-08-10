import csv

from src.features.fatigue_calculator import FatigueCalculator


def test_fatigue_calculator_cap_limit():
    """
    Verifica que la diferencia de días de descanso se limite al límite máximo establecido
    (ej. 20 días de diferencia entre partidos se capean a 14.0 días).
    """
    calculator = FatigueCalculator(max_days=14.0, default_days=7.0)

    # Estado inicial simulando un partido jugado hace 20 días
    initial_state = {
        'TeamA': '2023-10-01',
        'TeamB': '2023-10-01'
    }

    # Partido disputado 20 días después
    rows = [
        {'Fecha': '2023-10-21', 'Equipo_L': 'TeamA', 'Equipo_V': 'TeamB'}
    ]

    results = calculator.calculate_rest_days(rows, initial_state)

    assert len(results) == 1
    # 20 días de descanso deben caparse a 14.0
    assert results[0]['Dias_Descanso_L'] == 14.0
    assert results[0]['Dias_Descanso_V'] == 14.0
    assert results[0]['Dif_Descanso'] == 0.0


def test_fatigue_calculator_fallback_and_diff():
    """
    Verifica que los equipos sin historial previo reciben el valor por defecto
    de 7.0 días y que su diferencia es de 0.0.
    """
    calculator = FatigueCalculator(max_days=14.0, default_days=7.0)

    # Equipos sin historial previo
    rows = [
        {'Fecha': '2023-10-01', 'Equipo_L': 'TeamNewA', 'Equipo_V': 'TeamNewB'}
    ]

    results = calculator.calculate_rest_days(rows)

    assert len(results) == 1
    # Deben recibir el valor por defecto de 7.0 días
    assert results[0]['Dias_Descanso_L'] == 7.0
    assert results[0]['Dias_Descanso_V'] == 7.0
    assert results[0]['Dif_Descanso'] == 0.0


def test_process_files(tmp_path):
    """
    Verifica que process_files lea correctamente los archivos temporales simulados,
    ejecute el cálculo de fatiga acumulando el estado y escriba los resultados correctos.
    """
    # Definición de rutas utilizando el fixture tmp_path
    hist_in = tmp_path / "hist_in.csv"
    curr_in = tmp_path / "curr_in.csv"
    hist_out = tmp_path / "hist_out.csv"
    curr_out = tmp_path / "curr_out.csv"

    # Crear datos simulados para el historial
    with open(hist_in, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Fecha', 'Equipo_L', 'Equipo_V'])
        writer.writeheader()
        writer.writerow({'Fecha': '2023-10-01', 'Equipo_L': 'Real Madrid', 'Equipo_V': 'Barcelona'})

    # Crear datos simulados para los partidos actuales
    # Real Madrid jugará 4 días después del partido anterior (01 Oct al 05 Oct)
    # Atletico no tiene historial previo (debería recibir fallback de 7 días)
    with open(curr_in, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Fecha', 'Equipo_L', 'Equipo_V'])
        writer.writeheader()
        writer.writerow({'Fecha': '2023-10-05', 'Equipo_L': 'Real Madrid', 'Equipo_V': 'Atletico'})

    calculator = FatigueCalculator(max_days=14.0, default_days=7.0)
    calculator.process_files(
        str(hist_in),
        str(curr_in),
        str(hist_out),
        str(curr_out)
    )

    # Validar que los archivos de salida existen
    assert hist_out.exists()
    assert curr_out.exists()

    # Comprobar salida del archivo histórico
    with open(hist_out, mode='r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        hist_rows = list(reader)
        assert len(hist_rows) == 1
        assert float(hist_rows[0]['Dias_Descanso_L']) == 7.0
        assert float(hist_rows[0]['Dias_Descanso_V']) == 7.0
        assert float(hist_rows[0]['Dif_Descanso']) == 0.0

    # Comprobar salida del archivo actual (arrastra el estado del histórico)
    with open(curr_out, mode='r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        curr_rows = list(reader)
        assert len(curr_rows) == 1
        # Real Madrid: de 01-Oct a 05-Oct son exactamente 4.0 días de descanso
        assert float(curr_rows[0]['Dias_Descanso_L']) == 4.0
        # Atletico: Sin historial previo, recibe por defecto 7.0 días
        assert float(curr_rows[0]['Dias_Descanso_V']) == 7.0
        # Diferencia de descanso: 4.0 - 7.0 = -3.0
        assert float(curr_rows[0]['Dif_Descanso']) == -3.0