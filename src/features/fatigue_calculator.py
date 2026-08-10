import csv
import datetime

__all__ = ['FatigueCalculator']


class FatigueCalculator:
    def __init__(self, max_days: float = 14.0, default_days: float = 7.0) -> None:
        self.max_days: float = max_days
        self.default_days: float = default_days

    def _parse_date(self, date_str: str) -> datetime.datetime:
        if isinstance(date_str, datetime.datetime):
            return date_str
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        raise ValueError(f"Unknown date format: {date_str}")

    def calculate_rest_days(self, rows: list, initial_state: dict | None = None) -> list:
        if not rows:
            return []

        state = {}
        if initial_state is not None:
            for team, date_val in initial_state.items():
                try:
                    state[team] = self._parse_date(date_val)
                except ValueError:
                    state[team] = date_val

        sorted_rows = sorted(rows, key=lambda r: self._parse_date(r['Fecha']))
        enriched_rows = []

        for row in sorted_rows:
            fecha_actual = self._parse_date(row['Fecha'])
            eq_l = row['Equipo_L']
            eq_v = row['Equipo_V']

            # Local Team
            if eq_l in state:
                diff_l = (fecha_actual - state[eq_l]).total_seconds() / 86400.0
                days_l = min(diff_l, self.max_days)
            else:
                days_l = self.default_days

            # Visitor Team
            if eq_v in state:
                diff_v = (fecha_actual - state[eq_v]).total_seconds() / 86400.0
                days_v = min(diff_v, self.max_days)
            else:
                days_v = self.default_days

            dif = days_l - days_v

            state[eq_l] = fecha_actual
            state[eq_v] = fecha_actual

            new_row = dict(row)
            new_row['Dias_Descanso_L'] = float(days_l)
            new_row['Dias_Descanso_V'] = float(days_v)
            new_row['Dif_Descanso'] = float(dif)
            enriched_rows.append(new_row)

        if initial_state is not None:
            initial_state.clear()
            initial_state.update(state)

        return enriched_rows

    def process_files(self, hist_in: str, curr_in: str, hist_out: str, curr_out: str) -> None:
        # Read history
        hist_rows = []
        hist_fieldnames = []
        try:
            with open(hist_in, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                hist_fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                for row in reader:
                    hist_rows.append(row)
        except FileNotFoundError:
            pass

        new_cols = ['Dias_Descanso_L', 'Dias_Descanso_V', 'Dif_Descanso']
        for col in new_cols:
            if col not in hist_fieldnames:
                hist_fieldnames.append(col)

        state = {}
        hist_enriched = self.calculate_rest_days(hist_rows, state)

        with open(hist_out, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=hist_fieldnames)
            writer.writeheader()
            writer.writerows(hist_enriched)

        # Read current
        curr_rows = []
        curr_fieldnames = []
        try:
            with open(curr_in, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                curr_fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                for row in reader:
                    curr_rows.append(row)
        except FileNotFoundError:
            pass

        for col in new_cols:
            if col not in curr_fieldnames:
                curr_fieldnames.append(col)

        curr_enriched = self.calculate_rest_days(curr_rows, state)

        with open(curr_out, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=curr_fieldnames)
            writer.writeheader()
            writer.writerows(curr_enriched)