from integrations.google.gsheets import get_sheet_values, write_sheet_values
from services.broker_bin.matcher_service import get_header_indices
import logging

logger = logging.getLogger(__name__)

# Maps Google Sheet headers to an internal field name (lowercase, underscores instead of spaces) for easier access.
REQUIRED_HEADERS = {
    "part number": "part_number",
    "price": "price",
    "brand": "brand_name",
    "company": "company_name",
    "contact": "contact_name",
    "contact email": "contact_email",
}


def get_intake_rows(sheet_id: str, range_name: str) -> tuple[list[str],list[list[str]]]:
    """
    Fetches raw rows from a Google Sheet using the service account credentials
    configured via GOOGLE_SERVICE_ACCOUNT_FILE.

    Args:
        sheet_id: The Google Sheet's spreadsheet ID (from its URL).
        range_name: The A1 notation range (e.g. sheet/tab name) to read from.
    Returns:
        A list of rows, each a list of cell values as strings. The first row
        is the header row. Empty if the range has no data.
    Raises:
        ValueError: If the sheet is empty (no header row or data rows).
    """

    intake_rows = get_sheet_values(sheet_id, range_name)
    if not intake_rows:
        raise ValueError(f"Intake sheet is empty; expected a header row plus data rows for range '{range_name}'")
    else:
        headers = intake_rows[0]
        intake_data_rows = intake_rows[1:]
        return headers, intake_data_rows


def get_non_duplicate_intake_parts_rows(
    headers_parts: list[str], existing_parts_rows: list[list[str]], broker_bin_records: list[list[str]]
) -> list[list[str]]:
    """
    Filters out BrokerBin hits whose part is already recorded in the intake parts sheet.

    Args:
        headers_parts: The header row of the intake parts Google Sheet.
        existing_parts_rows: Raw parts rows from the intake Google Sheet, header row excluded.
        broker_bin_records: Raw rows from the BrokerBin report, each a list of strings representing
            the part number, brand name, company name, contact name, and contact number.
    Returns:
        A list of new [part_number, brand_name, ''] rows to add to the intake parts sheet.
    """
    indices_parts = get_header_indices(headers_parts, required_headers=REQUIRED_HEADERS)
    existing_parts_rows_broken_bin_eq = [
        [row[indices_parts["part_number"]], row[indices_parts["brand_name"]]]
        for row in existing_parts_rows
    ]

    new_parts_rows = []
    for broker_bin_record in broker_bin_records:
        try:
            part_number, brand_name, _, _, _ = broker_bin_record
        except ValueError:
            logger.warning("Skipping malformed BrokerBin record (expected 5 fields): %s", broker_bin_record)
            continue
        if [part_number, brand_name] not in existing_parts_rows_broken_bin_eq:
            new_parts_rows.append([part_number, brand_name, ''])

    logger.info("Found %d new parts rows to add to the intake sheet", len(new_parts_rows))
    return new_parts_rows


def get_non_duplicate_intake_contacts_rows(
    headers_contacts: list[str], existing_contacts_rows: list[list[str]], broker_bin_records: list[list[str]]
) -> list[list[str]]:
    """
    Filters out BrokerBin hits whose contact is already recorded in the intake contacts sheet.

    Args:
        headers_contacts: The header row of the intake contacts Google Sheet.
        existing_contacts_rows: Raw contacts rows from the intake Google Sheet, header row excluded.
        broker_bin_records: Raw rows from the BrokerBin report, each a list of strings representing
            the part number, brand name, company name, contact name, and contact number.
    Returns:
        A list of new [company_name, contact_name, ''] rows to add to the intake contacts sheet.
    """
    indices_contacts = get_header_indices(headers_contacts, required_headers=REQUIRED_HEADERS)
    existing_contacts_rows_broken_bin_eq = [
        [row[indices_contacts["company_name"]], row[indices_contacts["contact_name"]]]
        for row in existing_contacts_rows
    ]

    new_contacts_rows = []
    for broker_bin_record in broker_bin_records:
        try:
            _, _, company_name, contact_name, _ = broker_bin_record
        except ValueError:
            logger.warning("Skipping malformed BrokerBin record (expected 5 fields): %s", broker_bin_record)
            continue
        if [company_name, contact_name] not in existing_contacts_rows_broken_bin_eq:
            new_contacts_rows.append([company_name, contact_name, ''])

    logger.info("Found %d new contacts rows to add to the intake sheet", len(new_contacts_rows))
    return new_contacts_rows


def update_intake_parts_sheet(sheet_id: str, range_name: str, broker_bin_records: list[list[str]]) -> None:
    """
    Writes values to a range of a Google Sheet using the service account
    credentials configured via GOOGLE_SERVICE_ACCOUNT_FILE.

    Args:
        sheet_id: The Google Sheet's spreadsheet ID (from its URL).
        range_name: The A1 notation range (e.g. sheet/tab name) to write to.
        broker_bin_records: Raw rows from the BrokerBin report, each a list of strings representing
            the part number, brand name, company name, contact name, and contact number.

    Raises:
        RuntimeError: If the Google Sheets API call fails (e.g. bad sheet_id,
            sheet not shared with the service account, network error).
    """
    headers_parts, existing_parts_rows = get_intake_rows(sheet_id, range_name)
    new_parts_rows = get_non_duplicate_intake_parts_rows(headers_parts, existing_parts_rows, broker_bin_records)

    if new_parts_rows:
        all_parts_rows = [headers_parts] + existing_parts_rows + new_parts_rows
        write_sheet_values(sheet_id, range_name, all_parts_rows)
        logger.info("Wrote %d new parts rows to the intake sheet", len(new_parts_rows))
    else:
        logger.info("No new parts rows to add to the intake sheet")


def update_intake_contacts_sheet(sheet_id: str, range_name: str, broker_bin_records: list[list[str]]) -> None:
    """
    Writes values to a range of a Google Sheet using the service account
    credentials configured via GOOGLE_SERVICE_ACCOUNT_FILE.

    Args:
        sheet_id: The Google Sheet's spreadsheet ID (from its URL).
        range_name: The A1 notation range (e.g. sheet/tab name) to write to.
        broker_bin_records: Raw rows from the BrokerBin report, each a list of strings representing
            the part number, brand name, company name, contact name, and contact number.

    Raises:
        RuntimeError: If the Google Sheets API call fails (e.g. bad sheet_id,
            sheet not shared with the service account, network error).
    """
    headers_contacts, existing_contacts_rows = get_intake_rows(sheet_id, range_name)
    new_contacts_rows = get_non_duplicate_intake_contacts_rows(headers_contacts, existing_contacts_rows, broker_bin_records)

    if new_contacts_rows:
        all_contacts_rows = [headers_contacts] + existing_contacts_rows + new_contacts_rows
        write_sheet_values(sheet_id, range_name, all_contacts_rows)
        logger.info("Wrote %d new contacts rows to the intake sheet", len(new_contacts_rows))
    else:
        logger.info("No new contacts rows to add to the intake sheet")



                                             
