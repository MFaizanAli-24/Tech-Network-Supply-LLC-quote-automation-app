def get_quote_email_template(part_names: list[str], part_prices: list[str], part_conditions: list[str], to: str, from_company_name: str = "Black Merlin LLC") -> str:
    """
    Builds the HTML body for part(s) quote email.

    Args:
        part_names: A list of part names/numbers being quoted.
        part_prices: A list of the quoted prices, as displayed text.
        part_conditions: A list of the quoted part conditions, as displayed text.
        to: Name of the contact the email is addressed to.
        from_company_name: Company name used in the closing signature.

    Returns:
        An HTML string suitable for use as an email body.
    """

    rows = ""
    for part_name, part_price, part_condition in zip(part_names, part_prices, part_conditions):
        if not part_name or not part_price:
            raise ValueError(f"Part name and price must be non-empty: {part_name}, {part_price}")
        try:
            part_price = f"${part_price} each"
            rows += f"""
                <tr>
                    <td>{part_name}</td>
                    <td>{part_price}</td>
                    td>{part_condition}</td>
                </tr>
            """
        except Exception as exc:
            raise ValueError(f"Failed to format part name and price into HTML: {part_name}, {part_price}") from exc
        
    return f"""
    <html>
        <body>
            <p>Hi {to},</p>
            <p>We currently have competitive pricing on the following part(s)</p>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr>
                    <th>Part Name</th>
                    <th>Price</th>
                    <th>Condition</th>
                </tr>
                {rows}
            </table>
            <p>If you are interested in any of these items or have additional requirements, simply reply with your part numbers, and we will be happy to provide our best pricing</p>
            <p>Best regards,<br>{from_company_name}</p>
        </body>
    </html>
    """


def get_reconciltion_report_template(records: list[dict[str, str]], company_records: dict[str, list[dict[str, str]]], from_company_name: str = "Black Merlin LLC") -> str:
    """
    Builds the HTML body for the reconciliation report email summarizing all
    quote emails sent during a run.

    Args:
        records: Match dicts, each expected to contain part_number, brand_name,
            company_name, contact_name, and contact_number.
        from_company_name: Company name used in the closing signature.

    Returns:
        An HTML string suitable for use as an email body.

    Raises:
        KeyError: If a record is missing one of the required fields.
    """
    rows = ""
    for record in records:
        try:
            rows += f"""
        <tr style="background-color: #ccffcc;">
            <td>{record['part_number']}</td>
            <td>{record['part_price']}</td>
            <td>{record['brand_name']}</td>
            <td>{record['company_name']}</td>
            <td>{record['contact_name']}</td>
            <td>{record['contact_number']}</td>
            <td>{record['email_sent_to']}</td>
            <td>{record['email_type']}</td>
        </tr>
        """
        except KeyError as exc:
            raise KeyError(f"Reconciliation record missing required field {exc}: {record}") from exc
    company_rows = ""

    for company_name, company_records_list in company_records.items():
        company_rows += f"""
                <tr style="background-color: #ccffcc;">
                    <td>{company_name}</td>
                    <td>{len(company_records_list)}</td>
                </tr>
                """

    return f"""
    <html>
        <body>
            <p>Dear Team,</p>
            <p>Please find below the reconciliation report:</p>
            <p>Summary of Quotes Sent by Company:</p>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr>
                    <th>Company Name</th>
                    <th>Number of Quotes Sent</th>
                </tr>
                {company_rows}
            </table>
            <p>Detailed Quote Records:</p>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr>
                    <th>Part Number</th>
                    <th>Price</th>
                    <th>Brand Name</th>
                    <th>Company Name</th>
                    <th>Contact Name</th>
                    <th>Contact Number</th>
                    <th>Email Sent To</th>
                    <th>Email Type</th>
                </tr>
                {rows}
            </table>
            <p>Best regards,<br>{from_company_name}</p>
        </body>
    </html>
    """