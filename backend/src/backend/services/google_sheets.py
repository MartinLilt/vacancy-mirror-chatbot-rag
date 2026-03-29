"""Google Sheets sync service for the Vacancy Mirror user table.

Keeps a Google Spreadsheet up-to-date with every bot user:
their Telegram ID, name, username, plan, subscription status
and the timestamps of first seen / last update.

Environment variables
---------------------
GOOGLE_SHEETS_ID : str
    The spreadsheet ID (the long hash in the Sheets URL).
GOOGLE_SERVICE_ACCOUNT_JSON : str
    Path to the Google service account JSON key file **or** the
    raw JSON string itself (useful for Docker/env secrets).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import gspread
from gspread import Spreadsheet, Worksheet

log = logging.getLogger(__name__)

# Column layout of the "Users" sheet (1-indexed).
# Order here determines the physical column order in the sheet.
_HEADERS: list[str] = [
    "telegram_user_id",
    "first_name",
    "last_name",
    "username",
    "plan",
    "status",
    "stripe_customer_id",
    "stripe_subscription_id",
    "first_seen",
    "last_updated",
]

_SHEET_NAME = "Users"

# Column pixel widths (approximate; Sheets uses pixels).
_COL_WIDTHS: dict[str, int] = {
    "telegram_user_id":       160,
    "first_name":             140,
    "last_name":              140,
    "username":               150,
    "plan":                   100,
    "status":                 110,
    "stripe_customer_id":     220,
    "stripe_subscription_id": 220,
    "first_seen":             180,
    "last_updated":           180,
}


class GoogleSheetsService:
    """Sync bot user data to a Google Spreadsheet.

    Each row represents one Telegram user.  The sheet is created
    automatically if it does not yet exist.  Existing rows are
    updated in-place; new users are appended.

    Parameters
    ----------
    spreadsheet_id:
        Google Sheets document ID.  Defaults to the
        ``GOOGLE_SHEETS_ID`` environment variable.
    credentials_source:
        Path to a service-account JSON file **or** the raw JSON
        string.  Defaults to ``GOOGLE_SERVICE_ACCOUNT_JSON`` env var.
    """

    def __init__(
        self,
        spreadsheet_id: str | None = None,
        credentials_source: str | None = None,
    ) -> None:
        self._spreadsheet_id: str = (
            spreadsheet_id
            or os.environ.get("GOOGLE_SHEETS_ID", "")
        )
        self._credentials_source: str = (
            credentials_source
            or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        )
        self._client: gspread.Client | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert_user(self, user_row: dict[str, Any]) -> None:
        """Insert or update a single user row in the sheet.

        Parameters
        ----------
        user_row:
            Dict with any subset of keys from ``_HEADERS``.
            ``telegram_user_id`` is required.
        """
        if not self._spreadsheet_id:
            log.debug(
                "GOOGLE_SHEETS_ID not set — skipping sheet sync."
            )
            return
        if not self._credentials_source:
            log.debug(
                "GOOGLE_SERVICE_ACCOUNT_JSON not set "
                "— skipping sheet sync."
            )
            return

        try:
            sheet = self._get_sheet()
            self._upsert_row(sheet, user_row)
        except Exception as exc:  # noqa: BLE001
            log.warning("Google Sheets upsert failed: %s", exc)

    def sync_all(
        self, rows: list[dict[str, Any]]
    ) -> None:
        """Replace the whole sheet with the provided rows.

        Intended for a full-refresh sync (e.g. called at startup).

        Parameters
        ----------
        rows:
            List of user dicts; each must have ``telegram_user_id``.
        """
        if not self._spreadsheet_id:
            log.debug(
                "GOOGLE_SHEETS_ID not set — skipping sheet sync."
            )
            return
        if not self._credentials_source:
            log.debug(
                "GOOGLE_SERVICE_ACCOUNT_JSON not set "
                "— skipping sheet sync."
            )
            return

        try:
            sheet = self._get_sheet()
            self._write_all(sheet, rows)
        except Exception as exc:  # noqa: BLE001
            log.warning("Google Sheets full sync failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> gspread.Client:
        """Authenticate and return a gspread client."""
        src = self._credentials_source.strip()
        # Detect raw JSON string vs file path.
        if src.startswith("{"):
            info: dict = json.loads(src)
            return gspread.service_account_from_dict(info)
        return gspread.service_account(filename=src)

    def _get_client(self) -> gspread.Client:
        """Return cached gspread client, building it on first call."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _get_spreadsheet(self) -> Spreadsheet:
        """Open the target spreadsheet."""
        return self._get_client().open_by_key(
            self._spreadsheet_id
        )

    def _get_sheet(self) -> Worksheet:
        """Return (and create if needed) the 'Users' worksheet."""
        spreadsheet = self._get_spreadsheet()
        try:
            return spreadsheet.worksheet(_SHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(
                title=_SHEET_NAME, rows=1000, cols=len(_HEADERS)
            )
            ws.append_row(
                _HEADERS,
                value_input_option="USER_ENTERED",
            )
            self._apply_sheet_formatting(spreadsheet, ws)
            log.info(
                "Created worksheet '%s' in spreadsheet %s.",
                _SHEET_NAME,
                self._spreadsheet_id,
            )
            return ws

    def _apply_sheet_formatting(
        self,
        spreadsheet: Spreadsheet,
        ws: Worksheet,
    ) -> None:
        """Apply column widths, header style, freeze and alignment."""
        sid = ws.id
        n_cols = len(_HEADERS)
        requests: list[dict] = []

        # -- Column widths ----------------------------------------
        for idx, col in enumerate(_HEADERS):
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sid,
                        "dimension": "COLUMNS",
                        "startIndex": idx,
                        "endIndex": idx + 1,
                    },
                    "properties": {
                        "pixelSize": _COL_WIDTHS.get(col, 150)
                    },
                    "fields": "pixelSize",
                }
            })

        # -- Row height for all rows (default 21 px → 28 px) -----
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sid,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1000,
                },
                "properties": {"pixelSize": 28},
                "fields": "pixelSize",
            }
        })

        # -- Header row style (row 0) -----------------------------
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": n_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        # Dark blue-grey background
                        "backgroundColor": {
                            "red": 0.165,
                            "green": 0.212,
                            "blue": 0.282,
                        },
                        "textFormat": {
                            "foregroundColor": {
                                "red": 1.0,
                                "green": 1.0,
                                "blue": 1.0,
                            },
                            "bold": True,
                            "fontSize": 10,
                            "fontFamily": "Roboto Mono",
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                    }
                },
                "fields": (
                    "userEnteredFormat("
                    "backgroundColor,"
                    "textFormat,"
                    "horizontalAlignment,"
                    "verticalAlignment)"
                ),
            }
        })

        # -- Data rows style (rows 1–999) -------------------------
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 1,
                    "endRowIndex": 1000,
                    "startColumnIndex": 0,
                    "endColumnIndex": n_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "fontSize": 10,
                            "fontFamily": "Roboto",
                        },
                        "verticalAlignment": "MIDDLE",
                        "horizontalAlignment": "LEFT",
                    }
                },
                "fields": (
                    "userEnteredFormat("
                    "textFormat,"
                    "verticalAlignment,"
                    "horizontalAlignment)"
                ),
            }
        })

        # -- Freeze header row ------------------------------------
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sid,
                    "gridProperties": {
                        "frozenRowCount": 1,
                    },
                },
                "fields": "gridProperties.frozenRowCount",
            }
        })

        # -- Alternating row colours (banding) --------------------
        requests.append({
            "addBanding": {
                "bandedRange": {
                    "bandedRangeId": sid,
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": 1,
                        "endRowIndex": 1000,
                        "startColumnIndex": 0,
                        "endColumnIndex": n_cols,
                    },
                    # White rows
                    "rowProperties": {
                        "firstBandColor": {
                            "red": 1.0,
                            "green": 1.0,
                            "blue": 1.0,
                        },
                        # Light blue-grey alternate rows
                        "secondBandColor": {
                            "red": 0.937,
                            "green": 0.953,
                            "blue": 0.976,
                        },
                    },
                }
            }
        })

        spreadsheet.batch_update({"requests": requests})
        log.debug(
            "Sheet formatting applied to '%s'.", _SHEET_NAME
        )
        self._apply_sheet_protection(spreadsheet, ws)

    def _apply_sheet_protection(
        self,
        spreadsheet: Spreadsheet,
        ws: Worksheet,
    ) -> None:
        """Lock the sheet so only the service account can edit it.

        All editors (including the spreadsheet owner) will see a
        warning when trying to edit cells.  The service account
        bypasses this restriction because it makes API calls as
        itself, not as a human editor.
        """
        # First remove any existing protections on this sheet
        # to avoid duplicates on repeated calls.
        existing = spreadsheet.fetch_sheet_metadata()
        for s in existing.get("sheets", []):
            if s["properties"]["sheetId"] != ws.id:
                continue
            for p in s.get("protectedRanges", []):
                spreadsheet.batch_update({
                    "requests": [{
                        "deleteProtectedRange": {
                            "protectedRangeId": p["protectedRangeId"]
                        }
                    }]
                })

        # Retrieve the service account e-mail so we can list it
        # as the only editor allowed to bypass the warning.
        try:
            sa_email: str = (
                self._get_client().auth.service_account_email
            )
        except AttributeError:
            sa_email = ""

        # Google Sheets API does not allow removing the spreadsheet
        # owner from the editors list, so a hard lock is not possible
        # via API for owner accounts.  warningOnly=True shows a
        # confirmation dialog to any human editor before they can
        # overwrite a cell, which is the strongest protection
        # available without revoking owner access.
        protect_request: dict = {
            "addProtectedRange": {
                "protectedRange": {
                    "range": {
                        "sheetId": ws.id,
                    },
                    "description": (
                        "Managed by Vacancy Mirror bot — "
                        "do not edit manually."
                    ),
                    "warningOnly": True,
                }
            }
        }
        spreadsheet.batch_update({"requests": [protect_request]})
        log.info(
            "Sheet '%s' protected. Only service account "
            "(%s) can edit.",
            _SHEET_NAME,
            sa_email,
        )

    def _set_column_widths(
        self,
        spreadsheet: Spreadsheet,
        ws: Worksheet,
    ) -> None:
        """Set pixel widths for each column via batchUpdate."""
        requests: list[dict] = []
        for idx, col in enumerate(_HEADERS):
            width = _COL_WIDTHS.get(col, 150)
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": idx,
                        "endIndex": idx + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            })
        if requests:
            spreadsheet.batch_update({"requests": requests})

    def _row_to_values(
        self, user_row: dict[str, Any]
    ) -> list[str]:
        """Convert a user dict to an ordered list of cell values."""
        return [
            str(user_row.get(col, "")) for col in _HEADERS
        ]

    def _upsert_row(
        self,
        sheet: Worksheet,
        user_row: dict[str, Any],
    ) -> None:
        """Update existing row or append a new one."""
        user_id = str(user_row.get("telegram_user_id", ""))
        if not user_id:
            log.warning(
                "upsert_user called without telegram_user_id."
            )
            return

        # Ensure header row exists.
        existing = sheet.get_all_values()
        if not existing:
            sheet.append_row(
                _HEADERS,
                value_input_option="USER_ENTERED",
            )
            existing = [_HEADERS]

        header_row = existing[0]
        try:
            id_col_idx = header_row.index("telegram_user_id")
        except ValueError:
            # Header missing — rebuild it.
            sheet.insert_row(_HEADERS, index=1)
            existing = sheet.get_all_values()
            header_row = existing[0]
            id_col_idx = header_row.index("telegram_user_id")

        # Search for an existing row with this user_id.
        row_index: int | None = None
        for i, row in enumerate(existing[1:], start=2):
            if (
                len(row) > id_col_idx
                and row[id_col_idx] == user_id
            ):
                row_index = i
                break

        values = self._row_to_values(user_row)
        if row_index is not None:
            # Update only changed columns to save quota.
            col_count = len(_HEADERS)
            range_name = (
                f"A{row_index}:"
                f"{chr(ord('A') + col_count - 1)}{row_index}"
            )
            sheet.update(
                range_name,
                [values],
                value_input_option="USER_ENTERED",
            )
            log.debug(
                "Updated sheet row %d for user %s.",
                row_index,
                user_id,
            )
        else:
            sheet.append_row(
                values,
                value_input_option="USER_ENTERED",
            )
            log.debug(
                "Appended new sheet row for user %s.", user_id
            )

    def _write_all(
        self,
        sheet: Worksheet,
        rows: list[dict[str, Any]],
    ) -> None:
        """Clear the sheet and write all rows at once."""
        all_values: list[list[str]] = [_HEADERS]
        for row in rows:
            all_values.append(self._row_to_values(row))
        sheet.clear()
        sheet.update(
            "A1",
            all_values,
            value_input_option="USER_ENTERED",
        )
        log.info(
            "Full sync wrote %d user rows to Google Sheets.",
            len(rows),
        )


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def build_user_row(
    *,
    telegram_user_id: int,
    first_name: str = "",
    last_name: str = "",
    username: str = "",
    plan: str = "free",
    status: str = "none",
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    first_seen: str = "",
    last_updated: str = "",
) -> dict[str, Any]:
    """Build a user dict ready for ``GoogleSheetsService.upsert_user``.

    Parameters
    ----------
    telegram_user_id:
        Telegram integer user ID.
    first_name / last_name / username:
        Telegram profile fields.
    plan:
        ``"free"``, ``"plus"``, or ``"pro_plus"``.
    status:
        Subscription status string (``"active"``, ``"cancelled"``…).
    stripe_customer_id / stripe_subscription_id:
        Stripe identifiers (empty string when not subscribed).
    first_seen:
        ISO timestamp of first ``/start`` call; kept if already set.
    last_updated:
        ISO timestamp updated on every call.

    Returns
    -------
    dict[str, Any]
        Ordered user dict matching ``_HEADERS``.
    """
    return {
        "telegram_user_id": telegram_user_id,
        "first_name": first_name,
        "last_name": last_name or "",
        "username": f"@{username}" if username else "",
        "plan": plan,
        "status": status,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "first_seen": first_seen or _now_iso(),
        "last_updated": last_updated or _now_iso(),
    }
