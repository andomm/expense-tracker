import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import TextIOWrapper


class CSVError(ValueError):
    def __init__(self, message: str, *, row: int | None = None):
        super().__init__(f"Row {row}: {message}" if row is not None else message)
        self.row = row


@dataclass(frozen=True)
class ParsedExpenseRow:
    date: date
    category: str
    description: str
    receiver: str
    amount: Decimal


class BaseExpenseImporter:
    date_column: str
    amount_column: str
    category_column: str
    description_column: str
    receiver_column: str
    decimal_separator = "."
    date_format = "YYYY-MM-DD"

    def rows(self, uploaded_file) -> Iterator[tuple[int, ParsedExpenseRow]]:
        with TextIOWrapper(
            uploaded_file.file, encoding="utf-8-sig", newline=""
        ) as stream:
            reader = csv.reader(stream, delimiter=";", strict=True)
            line = 1
            try:
                header = next(reader, [])
                if len(set(header)) != len(header) or not {
                    self.date_column,
                    self.amount_column,
                }.issubset(header):
                    raise CSVError(
                        f"Expected a header with {self.date_column} and {self.amount_column}. "
                        "Check the selected file format.",
                        row=line,
                    )
                while True:
                    # Report the start of the record, including after a multiline field.
                    line = reader.line_num + 1
                    values = next(reader, None)
                    if values is None:
                        break
                    if not values:
                        continue
                    if len(values) != len(header):
                        raise CSVError(
                            "The number of columns does not match the header.", row=line
                        )
                    yield (
                        line,
                        self.parse_row(dict(zip(header, values, strict=True)), line),
                    )
            except UnicodeDecodeError:
                # TextIOWrapper can decode ahead of the current record.
                raise CSVError(
                    "Save the file with UTF-8 encoding and try again."
                ) from None
            except csv.Error:
                raise CSVError(
                    "Invalid CSV quoting or a field is too long.", row=line
                ) from None

    def parse_date(self, value: str) -> date:
        return date.fromisoformat(value)

    def parse_row(self, values: dict[str, str], line: int) -> ParsedExpenseRow:
        try:
            day = self.parse_date(values[self.date_column].strip())
        except ValueError:
            raise CSVError(
                f"Enter a valid date in {self.date_column} ({self.date_format}).",
                row=line,
            ) from None
        amount = values[self.amount_column].strip().replace(self.decimal_separator, ".")
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", amount):
            raise CSVError(f"Enter a valid amount in {self.amount_column}.", row=line)
        return ParsedExpenseRow(
            date=day,
            category=values.get(self.category_column, ""),
            description=values.get(self.description_column, ""),
            receiver=values.get(self.receiver_column, ""),
            amount=Decimal(amount),
        )


class FinnishBankCSVImporter(BaseExpenseImporter):
    date_column = "Arvopäivä"
    amount_column = "Määrä EUROA"
    category_column = "Selitys"
    description_column = "Viesti"
    receiver_column = "Saaja/Maksaja"
    decimal_separator = ","


class SpiirCSVImporter(BaseExpenseImporter):
    date_column = "Date"
    amount_column = "Amount"
    category_column = "Category"
    description_column = "Note"
    receiver_column = "Text"
    date_format = "DD-MM-YYYY"

    def parse_date(self, value: str) -> date:
        return datetime.strptime(value, "%d-%m-%Y").date()


def get_importer(import_format: str) -> BaseExpenseImporter:
    if import_format == "osuuspankki_csv":
        return FinnishBankCSVImporter()
    if import_format == "spiir_csv":
        return SpiirCSVImporter()
    raise ValueError("Unsupported import format.")
