def get_quote_email_template(part_name: str, part_price: str, to: str, from_company_name: str = "Black Merlin LLC") -> str:
    """
    Builds the HTML body for a single-part quote email.

    Args:
        part_name: The part number/name being quoted.
        part_price: The quoted price, as displayed text.
        to: Name of the contact the email is addressed to.
        from_company_name: Company name used in the closing signature.

    Returns:
        An HTML string suitable for use as an email body.
    """
    return f"""
    <html>
        <body>
            <p>Dear {to},</p>
            <p>We are pleased to provide you with a quote for the part you requested:</p>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr>
                    <th>Part Name</th>
                    <th>Price</th>
                </tr>
                <tr>
                    <td>{part_name}</td>
                    <td>{part_price}</td>
                </tr>
            </table>
            <p>If you have any questions or would like to proceed with the order, please feel free to contact us.</p>
            <p>Best regards,<br>{from_company_name}</p>
        </body>
    </html>
    """


def get_reconciltion_report_template(records: list[dict[str, str]], from_company_name: str = "Black Merlin LLC") -> str:
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

    return f"""
    <html>
        <body>
            <p>Dear Team,</p>
            <p>Please find below the reconciliation report:</p>
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