"""
Matches BrokerBin "Searched by" hits against the Google Sheet of parts/contacts,
resolving which contact email (primary or secondary) each quote should go to.
"""

import logging

logger = logging.getLogger(__name__)

# Maps Google Sheet headers to an internal field name (lowercase, underscores instead of spaces) for easier access.
REQUIRED_HEADERS = {
    "part number": "part_number",
    "price": "price",
    "company": "company_name",
    "contact name": "contact_name",
    "contact person email": "primary_contact",
    "email": "secondary_contact",
}


def get_header_indices(headers: list[str]) -> dict[str, int]:
    """
    Maps REQUIRED_HEADERS field names to their column index in `headers`.

    Args:
        headers: The header row of the parts/contact Google Sheet.

    Returns:
        A dict mapping each field name in REQUIRED_HEADERS to its column index.

    Raises:
        ValueError: If any required column is missing from `headers`.
    """
    lowered = [h.lower() for h in headers]
    indices = {}
    for field in lowered:
        if field not in REQUIRED_HEADERS:
            raise ValueError(f"Google Sheet has unexpected column: '{field}'")
        field_mapping = REQUIRED_HEADERS[field]
        indices[field_mapping] = lowered.index(field)
    return indices


def get_all_parts_prices(parts_data: list[list[str]]) -> dict[str, str]:
    """
    Builds a mapping of part_number -> price from the parts/contact Google Sheet.

    Args:
        parts_data: Raw rows from the parts/contact Google Sheet, header row first.
    Returns:
        A dict mapping part_number to price, for every row that has a non-empty part_number and price.
    """
    if not parts_data:
        raise ValueError("parts_data is empty; expected a header row plus data rows")

    headers = parts_data[0]
    indices = get_header_indices(headers)
    part_number_idx = indices["part_number"]
    price_idx = indices["price"]

    records = {}
    for row in parts_data[1:]:
        part_number = row[part_number_idx].strip()
        price = row[price_idx].strip()
        if part_number and price:
            records[part_number] = price
    return records


def get_all_company_emails(contacts_data: list[list[str]]) -> dict[str,list[str]]:
    """
    Builds a mapping of company_name -> [email, email_type] from the parts/contact Google Sheet,
    preferring the primary contact email and falling back to the secondary contact email.

    Args:
        contacts_data: Raw rows from the parts/contact Google Sheet, header row first.
    Returns:
        A dict mapping each company_name to a [email, email_type] pair, where email_type
        is "primary" or "secondary", for every row that has a usable contact email.
    """
    if not contacts_data:
        raise ValueError("contacts_data is empty; expected a header row plus data rows")

    headers = contacts_data[0]
    indices = get_header_indices(headers)
    primary_idx = indices["primary_contact"]
    secondary_idx = indices["secondary_contact"]
    company_idx = indices["company_name"]

    company_emails = {}
    for row in contacts_data[1:]:
        company_name = row[company_idx].strip()
        primary_email = row[primary_idx].strip()
        secondary_email = row[secondary_idx].strip()
        if '@' in primary_email:
            company_emails[company_name] = [primary_email,"primary"]
        elif '@' in secondary_email:
            company_emails[company_name] = [secondary_email,"secondary"]

    return company_emails


def match_broker_bin_records(
    broker_bin_records: list[list[str]], parts_records: list[list[str]], contacts_records: list[list[str]]
) -> list[dict[str, str]]:
    """
    Matches BrokerBin hits against the Google Sheet parts/contact data by part
    number, company name, and contact name.

    Args:
        broker_bin_records: Parsed BrokerBin rows, each
            [part_number, brand_name, company_name, contact_name, contact_number].
        parts_records: Raw rows from the parts Google Sheet, header row first.
        contacts_records: Raw rows from the contacts Google Sheet, header row first.

    Returns:
        A list of dicts, one per hit that matched a non-empty price and a usable
        contact email:
            {part_number, brand_name, company_name, contact_name, contact_number,
             part_price, email_sent_to, email_type}

    Raises:
        ValueError: If `parts_records` or `contacts_records` is empty or missing a
            required column.
    """

    parts_info = get_all_parts_prices(parts_records)
    contacts_info = get_all_company_emails(contacts_records)

    matches = []
    for broker_bin_record in broker_bin_records:
        try:
            part_number, brand_name, company_name, contact_name, contact_number = broker_bin_record
        except ValueError:
            logger.warning("Skipping malformed BrokerBin record (expected 5 fields): %s", broker_bin_record)
            continue

        if part_number in parts_info:
            part_price = parts_info[part_number]
            if part_price != "":
                if company_name in contacts_info:
                    to_email, to_email_type = contacts_info[company_name]
                    matches.append({
                        "part_number": part_number,
                        "brand_name": brand_name,
                        "company_name": company_name,
                        "contact_name": contact_name,
                        "contact_number": contact_number,
                        "part_price": part_price,
                        "email_sent_to": to_email,
                        "email_type": to_email_type,
                    })
                    logger.info("--"*30)
                    logger.info(
                        "Match found for part %s / %s / %s: sending quote to %s (%s)",
                        part_number, company_name, contact_name, to_email, to_email_type
                    )
                    logger.info("--"*30)

    return matches
