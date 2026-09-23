import csv
import io
from dataclasses import dataclass
from datetime import datetime

from app.importing.schemas import ImportError, ImportOptions

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_REQUESTS = 1000
REQUIRED_COLUMNS = {
    "Заявка",
    "Тип заявки BK",
    "Тип заявки HD",
    "Начало",
    "Окончание",
    "Район",
    "Адрес",
}


@dataclass
class ParsedRequest:
    line: int
    values: dict
    engineer_name: str | None


@dataclass
class ParsedFile:
    requests: list[ParsedRequest]
    office_address: str
    blank_rows: int


def parse_datetime(value: str, line: int, column: str) -> datetime:
    """CSV local wall time -> PostgreSQL TIMESTAMP WITHOUT TIME ZONE."""
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        raise ImportError(f"Строка {line}, {column}: ожидается дата ДД.ММ.ГГГГ ЧЧ:ММ") from None


def normalize_request(row: dict[str, str], line: int, options: ImportOptions) -> ParsedRequest:
    limits = {
        "Заявка": 32,
        "Тип заявки BK": 48,
        "Тип заявки HD": 128,
        "Район": 128,
        "Адрес": 2000,
        "Статус BK": 32,
        "Бригада": 128,
    }
    for column, limit in limits.items():
        if len(row.get(column, "")) > limit:
            raise ImportError(f"Строка {line}, {column}: максимум {limit} символов")
    for column in ("Заявка", "Тип заявки BK", "Адрес"):
        if not row[column]:
            raise ImportError(f"Строка {line}: не заполнено поле {column}")

    start = parse_datetime(row["Начало"], line, "Начало")
    end = parse_datetime(row["Окончание"], line, "Окончание")
    if end <= start:
        raise ImportError(f"Строка {line}: конец окна должен быть позже начала")
    if start.date() != end.date():
        raise ImportError(f"Строка {line}: планировщик не поддерживает окно через полночь")
    rule = options.work_rules.get(row["Тип заявки BK"])
    if rule is None:
        raise ImportError(f"Строка {line}: для типа заявки BK не задано правило work_rules")
    gigabit = row.get("Гигабитное подключение", "").casefold()
    if gigabit not in ("", "да", "нет"):
        raise ImportError(f"Строка {line}: Гигабитное подключение должно быть Да или Нет")
    equipment = {}
    if gigabit:
        equipment["gigabit"] = gigabit == "да"
    if row.get("Подключение"):
        equipment["connection"] = row["Подключение"]
    return ParsedRequest(
        line=line,
        engineer_name=row.get("Бригада") or None,
        values={
            "external_id": row["Заявка"],
            "address": row["Адрес"],
            "district": row["Район"] or None,
            "work_type": row["Тип заявки BK"],
            "hd_type": row["Тип заявки HD"] or None,
            "window_start": start,
            "window_end": end,
            "skill": rule.skill,
            "duration_min": rule.duration_min,
            "priority": rule.priority,
            "required_transport": None,
            "equipment": equipment,
            "status": row.get("Статус BK") or None,
        },
    )


def parse_csv(content: bytes, options: ImportOptions) -> ParsedFile:
    """Parse semicolon CSV independently of the database and geocoding services."""
    if len(content) > MAX_FILE_BYTES:
        raise ImportError("Размер CSV превышает 5 МиБ")
    try:
        decoded = content.decode(options.encoding)
    except UnicodeDecodeError:
        raise ImportError("Неверная кодировка CSV; доступны utf-8-sig и cp1251") from None
    if "\x00" in decoded:
        raise ImportError("CSV содержит нулевые байты")
    reader = csv.reader(io.StringIO(decoded, newline=""), delimiter=";", strict=True)
    requests = []
    office = None
    blank_rows = 0
    seen = set()
    try:
        header = [cell.strip() for cell in next(reader, [])]
        if len(header) != len(set(header)):
            raise ImportError("Заголовок CSV содержит повторяющиеся колонки")
        missing = REQUIRED_COLUMNS - set(header)
        if missing:
            raise ImportError(f"В CSV отсутствуют колонки: {', '.join(sorted(missing))}")
        is_control = "Бригада" in header or "Статус BK" in header
        if is_control != (options.dataset == "control"):
            raise ImportError("dataset не соответствует CSV: контроль содержит Бригада/Статус BK")
        for cells in reader:
            line = reader.line_num
            cells = [cell.strip() for cell in cells]
            if not any(cells):
                blank_rows += 1
                continue
            if cells[0].casefold() == "адрес офиса":
                if office is not None or len(cells) < 2 or not cells[1] or any(cells[2:]):
                    raise ImportError(f"Строка {line}: некорректная или повторная строка офиса")
                office = cells[1]
                if len(office) > 2000:
                    raise ImportError(f"Строка {line}: адрес офиса слишком длинный")
                continue
            if len(cells) != len(header):
                raise ImportError(f"Строка {line}: число полей не совпадает с заголовком")
            request = normalize_request(dict(zip(header, cells)), line, options)
            key = (request.values["external_id"], request.values["window_start"])
            if key in seen:
                raise ImportError(f"Строка {line}: повтор заявки с тем же началом окна")
            seen.add(key)
            requests.append(request)
            if len(requests) > MAX_REQUESTS:
                raise ImportError(f"В одном файле допускается не более {MAX_REQUESTS} заявок")
    except csv.Error:
        raise ImportError(f"Строка {reader.line_num}: некорректный формат CSV") from None
    if not requests:
        raise ImportError("В CSV нет заявок")
    if office and options.office_address and office != options.office_address:
        raise ImportError("Адрес офиса в options отличается от адреса в CSV")
    office = options.office_address or office
    if not office:
        raise ImportError("Укажите office_address: в CSV нет адреса офиса")
    return ParsedFile(requests, office, blank_rows)
