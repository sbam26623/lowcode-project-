"""Shared helpers for list pages, exports and form parsing."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Response, request

from .extensions import db

PAGE_SIZES = (25, 50, 100)


@dataclass
class Page:
    items: list
    page: int
    per_page: int
    total: int

    @property
    def pages(self) -> int:
        return max((self.total + self.per_page - 1) // self.per_page, 1)


def paginate(stmt) -> Page:
    """Server-side pagination (FR-AST-05) using ?page= and ?per_page=."""
    per_page = request.args.get("per_page", 25, type=int)
    per_page = per_page if per_page in PAGE_SIZES else 25
    page = max(request.args.get("page", 1, type=int), 1)
    result = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    return Page(items=list(result.items), page=page, per_page=per_page, total=result.total)


def csv_response(filename: str, header: list[str], rows) -> Response:
    buf = io.StringIO()
    buf.write("﻿")  # BOM so Excel opens UTF-8 (umlauts, €) correctly
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_decimal(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None
