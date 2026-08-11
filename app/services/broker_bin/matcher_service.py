"""
Matches BrokerBin "Searched by" hits against the Google Sheet of parts/contacts,
resolving which contact email (primary or secondary) each quote should go to.
"""

import logging
from repository.parts_repository import get_last_24_hours_parts_requests

logger = logging.getLogger(__name__)

# Maps Google Sheet headers to an internal field name (lowercase, underscores instead of spaces) for easier access.
REQUIRED_HEADERS = {
    "part number": "part_number",
    "price": "price",
    "company": "company_name",
    "contact name": "contact_name",
    "primary email": "primary_contact",
    "secondary email": "secondary_contact",
}


def get_header_indices(headers: list[str],required_headers=REQUIRED_HEADERS) -> dict[str, int]:
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
        if field not in required_headers:
            raise ValueError(f"Google Sheet has unexpected column: '{field}'")
        field_mapping = required_headers[field]
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


def aggregate_matches_by_email(matches: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """
    Aggregates matches by the email address they will be sent to.

    Args:
        matches: List of match dicts as produced by `match_broker_bin_records`.

    Returns:
        A dict mapping each email address to a list of match dicts that will be
        sent to that address.
    """
    aggregated = {}
    for match in matches:
        email = match["email_sent_to"]
        if email not in aggregated:
            aggregated[email] = []
        aggregated[email].append(match)
    return aggregated


def aggregate_matches_by_company(matches: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """
    Aggregates matches by the company name they belong to.

    Args:
        matches: List of match dicts as produced by `match_broker_bin_records`.

    Returns:
        A dict mapping each company name to a list of match dicts that belong to that company.
    """
    aggregated = {}
    for match in matches:
        company_name = match["company_name"]
        if company_name not in aggregated:
            aggregated[company_name] = []
        aggregated[company_name].append(match)
    return aggregated


def filter_matches_already_sent_last_24_hours(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Filters out matches that have already been sent in the last 24 hours.

    Args:
        matches: List of match dicts as produced by `match_broker_bin_records`.
    Returns:
        A filtered list of match dicts that have not been sent in the last 24 hours
    """

    try:
        parts_requests_last_24_hours = get_last_24_hours_parts_requests()
    except RuntimeError as exc:
        logger.error("Failed to fetch last 24 hours parts requests: %s", exc)
        return matches  # If we can't fetch the last 24 hours, assume all matches are new

    filtered_matches = []
    if parts_requests_last_24_hours:
        logger.info("Fetched %d parts requests from the last 24 hours", len(parts_requests_last_24_hours))
        for part_request in parts_requests_last_24_hours:
            part_number_sent = part_request.get("part_number")
            part_brand_sent = part_request.get("brand_name")
            part_company_sent = part_request.get("company_name")
            part_contact_sent = part_request.get("contact_name")
            part_email_sent = part_request.get("email_sent_to")

            if part_number_sent and part_brand_sent and part_company_sent and part_contact_sent and part_email_sent:
                for match in matches:
                    if (match["part_number"] == part_number_sent and
                        match["brand_name"] == part_brand_sent and
                        match["company_name"] == part_company_sent and
                        match["contact_name"] == part_contact_sent and
                        match["email_sent_to"] == part_email_sent):
                        logger.info(
                            "Match for part %s / %s / %s already sent to %s in the last 24 hours; skipping",
                            part_number_sent, part_company_sent, part_contact_sent, part_email_sent
                        )
                        break
                else:
                    filtered_matches.append(match)
    else:
        logger.info("No parts requests found in the last 24 hours; all matches are new")
        filtered_matches = matches
        
    logger.info(
        "Filtered out %d matches already sent in the last 24 hours; %d remaining",
        len(matches) - len(filtered_matches), len(filtered_matches)
    )
    return filtered_matches