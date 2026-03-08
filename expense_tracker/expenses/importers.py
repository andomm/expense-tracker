import csv
from dataclasses import dataclass
from decimal import Decimal
from io import TextIOWrapper
from typing import Iterable


@dataclass(frozen=True)
class ParsedExpenseRow:
    date: str
    category: str
    description: str
    receiver: str
    amount: Decimal


class BaseExpenseImporter:
    delimiter = ";"
    encoding = "utf-8"

    def read_rows(self, uploaded_file) -> Iterable[dict[str, str]]:
        csv_file = TextIOWrapper(uploaded_file.file, encoding=self.encoding)
        return csv.DictReader(csv_file, delimiter=self.delimiter)

    def parse_row(self, row: dict[str, str]) -> ParsedExpenseRow:
        raise NotImplementedError


class FinnishBankCSVImporter(BaseExpenseImporter):
    def parse_row(self, row: dict[str, str]) -> ParsedExpenseRow:
        amount = Decimal(row["Määrä EUROA"].replace(",", "."))

        return ParsedExpenseRow(
            date=row.get("Arvopäivä", ""),
            category=row.get("Selitys", ""),
            description=row.get("Viesti", ""),
            receiver=row.get("Saaja/Maksaja", ""),
            amount=amount,
        )


def get_importer(import_format: str) -> BaseExpenseImporter:
    if import_format == "osuuspankki_csv":
        return FinnishBankCSVImporter()
    raise ValueError(f"Unsupported import format: {import_format}")
