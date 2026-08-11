"""
Persists BrokerBin quote matches to Supabase and reads back recent part
requests for reporting.
"""

import logging
from datetime import datetime, timedelta, timezone

from postgrest.exceptions import APIError

from repository.supabase_client import supabase_client

logger = logging.getLogger(__name__)


def save_part_request(
    part_number: str,
    brand_name: str,
    company_name: str,
    contact_name: str,
    contact_number: str,
    part_price: str,
    to_email: str,
    to_email_type: str,
) -> dict:
    """
    Inserts a single matched BrokerBin hit into the parts_requests table.

    Args:
        part_number: The quoted part number.
        brand_name: The part's brand/manufacturer.
        company_name: Name of the company that searched for the part.
        contact_name: Name of the contact at that company.
        contact_number: Phone number of the contact.
        part_price: The quoted price, as displayed text.
        to_email: Email address the quote was sent to.
        to_email_type: "primary" or "secondary", per the matched contact column.

    Returns:
        The inserted row, as returned by Supabase.

    Raises:
        RuntimeError: If the insert fails (e.g. missing table, bad credentials).
    """
    data = {
        "part_number": part_number,
        "brand_name": brand_name,
        "company_name": company_name,
        "contact_name": contact_name,
        "contact_number": contact_number,
        "part_price": part_price,
        "email_sent_to": to_email,
        "email_type": to_email_type,
    }

    try:
        response = supabase_client.table("parts_requests").insert(data).execute()
    except APIError as exc:
        raise RuntimeError(f"Failed to save part request for part {part_number}: {exc}") from exc

    logger.info("Saved part request for part %s / %s", part_number, company_name)
    return response.data


def get_last_24_hours_parts_requests() -> list[dict]:
    """
    Fetches all part requests recorded in the last 24 hours, most recent first.

    Returns:
        A list of parts_requests rows.

    Raises:
        RuntimeError: If the query fails (e.g. missing table, bad credentials).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        response = (
            supabase_client
            .table("parts_requests")
            .select("*")
            .gte("created_at", cutoff.isoformat())
            .order("created_at", desc=True)
            .execute()
        )
    except APIError as exc:
        raise RuntimeError(f"Failed to fetch parts requests from the last 24 hours: {exc}") from exc

    return response.data
