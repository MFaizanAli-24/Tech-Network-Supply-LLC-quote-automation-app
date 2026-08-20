import logging
import os
import sys
import warnings

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from integrations.google.gsheets import get_sheet_values
from integrations.outlook.mail import get_emails_from_sender, send_email
from services.broker_bin.parser_service import parse_brokerbin_report
from services.broker_bin.matcher_service import match_broker_bin_records, aggregate_matches_by_email, filter_matches_already_sent_last_n_hours, aggregate_matches_by_company
from services.broker_bin.intake_service import update_intake_parts_sheet, update_intake_contacts_sheet
from templates.quote_email import get_reconciltion_report_template, get_quote_email_template
from repository.parts_repository import save_part_request

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

HEAD_RECORD_CNT = 5  # log the first HEAD_RECORD_CNT parsed broker bin records, for debugging
TAIL_RECORD_CNT = 5  # log the last TAIL_RECORD_CNT parsed broker bin records, for debugging

# -------------
# CONFIG SOURCE
# -------------

GOOGLE_PARTS_SHEET_ID = os.environ.get("GOOGLE_PARTS_SHEET_ID", "")
GOOGLE_PARTS_SHEET_NAME = os.environ.get("GOOGLE_PARTS_SHEET_NAME", "Sheet1")

GOOGLE_CONTACTS_SHEET_ID = os.environ.get("GOOGLE_CONTACTS_SHEET_ID", "")
GOOGLE_CONTACTS_SHEET_NAME = os.environ.get("GOOGLE_CONTACTS_SHEET_NAME", "Sheet1")

GOOGLE_CONFIG_SHEET_ID = os.environ.get("GOOGLE_CONFIG_SHEET_ID", "")
GOOGLE_CONFIG_SHEET_NAME = os.environ.get("GOOGLE_CONFIG_SHEET_NAME", "Sheet1")

INTAKE_PARTS_SHEET_ID = os.environ.get("GOOGLE_INTAKE_PARTS_SHEET_ID")
INTAKE_PARTS_SHEET_NAME = os.environ.get("GOOGLE_INTAKE_PARTS_SHEET_NAME")

INTAKE_CONTACTS_SHEET_ID = os.environ.get("GOOGLE_INTAKE_CONTACTS_SHEET_ID")
INTAKE_CONTACTS_SHEET_NAME = os.environ.get("GOOGLE_INTAKE_CONTACTS_SHEET_NAME")

BROKER_BIN_REPORT_MINS = int(os.environ.get("BROKER_BIN_REPORT_MINS", "60"))


def send_quote_email(matches: list[dict[str, str]]) -> None:
    """
    Sends a single quote email for all matched BrokerBin hit belonging to the same contact. 

    Args:
        matches: A list of match dicts as produced by `match_broker_bin_records` and aggregated by `aggregate_matches_by_email`,
        with keys part_number, brand_name, company_name, contact_name, contact_number,
        part_price, part_condition, email_sent_to, email_type.

    Returns:
        None

    Raises:
        requests.HTTPError: If the underlying Graph API call to send the email fails.
    """

    part_numbers = [match["part_number"] for match in matches]
    part_prices = [match["part_price"] for match in matches]
    part_conditions = [match["part_condition"] for match in matches]
    part_manufacturers = [match["brand_name"] for match in matches]
    recipient_name = list(set([match["contact_name"] for match in matches]))[0]
    recipient_email = list(set([match["email_sent_to"] for match in matches]))[0]
    recipient_email_type = list(set([match["email_type"] for match in matches]))[0]

    subject = f"Quote for Part Number: {', '.join(part_numbers)}"
    body = get_quote_email_template(
        part_names=part_numbers, part_prices=part_prices, part_conditions=part_conditions, part_manufacturers=part_manufacturers, to=recipient_name
    )
    send_email(to_address=recipient_email, subject=subject, body=body, body_type="HTML")
    logger.info(
        "Sent quote email to %s contact %s for part(s) %s (price(s) %s, condition(s) %s)",
        recipient_email_type, recipient_email, ','.join(part_numbers), ','.join(part_prices), ','.join(part_conditions)
    )


def send_reconciliation_report(matches: list[dict[str, str]], matches_agg_by_company: dict[str, list[dict[str, str]]],  recipient_email: str) -> None:
    """
    Sends a summary report of every quote email sent during this run.

    Args:
        matches: The full list of match dicts that quote emails were sent for.
        recipient_email: Address the reconciliation report should be sent to.

    Returns:
        None

    Raises:
        requests.HTTPError: If the underlying Graph API call to send the email fails.
    """
    subject = f"Reconciliation Report: {len(matches)} Quotes Sent"
    body = get_reconciltion_report_template(matches,matches_agg_by_company)
    send_email(
        to_address=recipient_email, subject=subject, body=body, body_type="HTML"
    )
    logger.info("Reconciliation report sent to %s", recipient_email)


def get_broker_bin_sender_email(configuration_records: list[list[str]]) -> str:
    """
    Looks up the BrokerBin report sender email from the configuration sheet.

    Args:
        configuration_records: Raw rows from the config Google Sheet, header row first.

    Returns:
        The configured "Broker Bin Report Sender Email" value.

    Raises:
        ValueError: If no row's first column matches "broker bin report sender email".
    """
    for row in configuration_records[1:]:  # skip header row
        if row[0].lower() == "broker bin report sender email":
            return row[1]
    raise ValueError("Could not find 'Broker Bin Report Sender Email' in configuration sheet")


def get_reconciliation_report_recipient_email(configuration_records: list[list[str]]) -> str:
    """
    Looks up the reconciliation report recipient email from the configuration sheet.

    Args:
        configuration_records: Raw rows from the config Google Sheet, header row first.

    Returns:
        The configured "Reconciliation Report Recipient Email" value.

    Raises:
        ValueError: If no row's first column matches "reconciliation report recipient email".
    """
    for row in configuration_records[1:]:  # skip header row
        if row[0].lower() == "reconciliation report recipient email":
            return row[1]
    raise ValueError("Could not find 'Reconciliation Report Recipient Email' in configuration sheet")


def main() -> None:
    """
    Runs one end-to-end quoting cycle: fetches config and parts/contact data from
    Google Sheets, pulls the latest BrokerBin report email, matches hits against
    contacts, sends quote emails, and sends a reconciliation report.

    Returns:
        None

    Raises:
        ValueError: If required configuration values or sheet columns are missing.
        requests.HTTPError: If a Microsoft Graph API call fails.
    """
    parts_records = get_sheet_values(GOOGLE_PARTS_SHEET_ID,GOOGLE_PARTS_SHEET_NAME)
    contacts_records = get_sheet_values(GOOGLE_CONTACTS_SHEET_ID,GOOGLE_CONTACTS_SHEET_NAME)
    configuration_records = get_sheet_values(GOOGLE_CONFIG_SHEET_ID, GOOGLE_CONFIG_SHEET_NAME)

    broker_bin_sender_email = get_broker_bin_sender_email(configuration_records)
    reconciliation_report_recipient_email = get_reconciliation_report_recipient_email(configuration_records)

    emails = get_emails_from_sender(broker_bin_sender_email, minutes=BROKER_BIN_REPORT_MINS, top=1)
    logger.info("==================== BROKERBIN MATCH REPORT STATS ====================")
    if not emails:
        logger.info("No BrokerBin emails found.")
        return

    logger.info("Fetched %d email(s); most recent received %s UTC", len(emails), emails[0]["receivedDateTime"])

    broker_bin_records = parse_brokerbin_report(emails[0]["body"]["content"])
    logger.info("Parsed %d BrokerBin records", len(broker_bin_records))
    logger.debug("Sample head records: %s", broker_bin_records[:HEAD_RECORD_CNT])
    logger.debug("Sample tail records: %s", broker_bin_records[-TAIL_RECORD_CNT:])

    logger.info("==================== UPDATE INTAKE SHEETS ====================")

    logger.info("--"*30)
    update_intake_parts_sheet(INTAKE_PARTS_SHEET_ID, INTAKE_PARTS_SHEET_NAME, broker_bin_records)
    update_intake_contacts_sheet(INTAKE_CONTACTS_SHEET_ID, INTAKE_CONTACTS_SHEET_NAME, broker_bin_records)
    logger.info("--"*30)

    logger.info("==================== MATCH LOGS ====================")

    matches = match_broker_bin_records(broker_bin_records, parts_records, contacts_records)
    matches_filtered = filter_matches_already_sent_last_n_hours(matches, 24) 
    aggregated_matches_by_email = aggregate_matches_by_email(matches_filtered)
    aggregated_matches_by_company = aggregate_matches_by_company(matches_filtered)
    

    logger.info("==================== INDIVIDUAL QUOTE EMAILS ====================")
    for _,match in aggregated_matches_by_email.items():
        logger.info("--"*30)
        send_quote_email(match)
        logger.info("--"*30)

    logger.info("==================== RECONCILIATION REPORT ====================")
    logger.info("--"*30)
    send_reconciliation_report(matches_filtered, aggregated_matches_by_company, reconciliation_report_recipient_email)
    logger.info("--"*30)

    logger.info("==================== SAVE PART REQUESTS - SUPABASE ====================")
    logger.info("--"*30)
    for match in matches_filtered:
        save_part_request(
            part_number=match["part_number"],
            brand_name=match["brand_name"],
            company_name=match["company_name"],
            contact_name=match["contact_name"],
            contact_number=match["contact_number"],
            part_price=match["part_price"],
            to_email=match["email_sent_to"],
            to_email_type=match["email_type"],
        )
    logger.info("--"*30)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Quote automation run failed")
        sys.exit(1)
