#!/usr/bin/env python3
"""
extract_brokerbin.py

Parses a BrokerBin "Match Your Hits" hourly report email and extracts,
for every "Searched by" hit, the following fields:

    Part Number
    Brand Name
    Company Name
    Company Contact Name
    Company Contact Number

The email has three repeating "rows" per hit:
    Row 1: Your inventory line, e.g.
        CXP-100G-SR10, NEW, qty 5, CALL, CISCO, 100GBASE-SR10 CXP Module for
    Row 2: The part# that was searched + the company that searched it, e.g.
        CXP-100G-SR10 Searched by: Server Supply.com, Inc.
    Row 3: The BrokerBin member (contact) who searched + their phone, e.g.
            Rick Mahmud P: 516-334-7718

Row 1 supplies the authoritative Part Number / Brand (Row 2's part number is
sometimes truncated/abbreviated in the source email, e.g. "4." instead of the
full Lenovo part number, so it is intentionally NOT used for the output).

INPUT FORMATS SUPPORTED (auto-detected):
  1. A dict (already-parsed JSON), e.g. {'contentType': 'html', 'content': '<html>...'}
  2. A list of such dicts (multiple fetched emails).
  3. A JSON string or Python-literal string of either of the above -- including
     text with a leading label, e.g. "Fetched Emails: {'contentType': ...}".
  4. A raw HTML string (uses <br>, &nbsp;, <a href="mailto:...">, etc).
  5. Plain text, already formatted like the row examples above.

  Real-world HTML→text conversions also tend to swallow random spaces
  (e.g. "Searchedby:", "GLC-FE-100EXSearched by:", "N/AP: 763-383-9920").
  The parsing below is deliberately tolerant of these missing spaces.

Usage:
    from extract_brokerbin import parse_brokerbin_report

    fetched = {'contentType': 'html', 'content': '<html>...'}
    rows = parse_brokerbin_report(fetched)
    # rows is a list of lists:
    #   [Part#, BrandName, CompanyName, CompanyContactName, CompanyContactNumber]

Run directly:
    python extract_brokerbin.py input.txt   # reads file, prints the list of lists
    cat input.txt | python extract_brokerbin.py   # reads from stdin
"""

import ast
import html
import json
import re

# Matches a section header like "---CISCO---"
SECTION_HEADER_RE = re.compile(r'^-{2,}\s*\S.*\S\s*-{2,}$')

# Matches a "Searched by" fragment anywhere in a line, tolerant of missing
# spaces around "Searched", "by" and ":" (e.g. "Searchedby:", "Searched by:IT").
SEARCHED_BY_RE = re.compile(r'Searched\s*by\s*:\s*(?P<company>.+?)\s*$', re.IGNORECASE)

# Matches the "P:" phone label anywhere in a contact line, tolerant of a
# missing space before it (e.g. "N/AP: 763-383-9920").
PHONE_LABEL_RE = re.compile(r'P\s*:\s*', re.IGNORECASE)


# --------------------------------------------------------------------------
# Raw-input normalization: unwrap API payloads and convert HTML to text
# --------------------------------------------------------------------------

def extract_email_content(data: dict | list | str) -> str | dict | list:
    """
    Pulls the HTML/text body out of a fetched-email payload. Accepts:
      - a dict, e.g. {'contentType': 'html', 'content': '<html>...'}
      - a list of such dicts (multiple fetched emails)
      - a JSON string or Python-literal string of either of the above,
        optionally with a leading label like "Fetched Emails: {...}"
      - plain text / raw HTML (returned unchanged)

    Args:
        data: The raw fetched-email payload, in any of the accepted forms above.

    Returns:
        The extracted email body content as a string, or the original value
        unchanged/unwrapped if no 'content' field could be found.
    """
    # Already a parsed dict -- e.g. {'contentType': 'html', 'content': '...'}
    if isinstance(data, dict):
        content = data.get('content')
        return content if content else data

    # Already a parsed list of dicts -- multiple fetched emails
    if isinstance(data, list):
        parts = [item.get('content') for item in data
                 if isinstance(item, dict) and item.get('content')]
        return '\n\n'.join(parts) if parts else data

    if not isinstance(data, str):
        return data

    text = data.strip()

    # Try it as straight JSON first (double-quoted keys/strings)
    try:
        return extract_email_content(json.loads(text))
    except (ValueError, TypeError):
        pass

    # Fall back to a trailing Python-dict/list literal, e.g. a string like
    # "Fetched Emails: {'contentType': 'html', 'content': '<html>...'}"
    m = re.search(r'(\{.*\}|\[.*\])\s*$', text, re.DOTALL)
    if m:
        try:
            return extract_email_content(ast.literal_eval(m.group(1)))
        except (ValueError, SyntaxError):
            pass

    return text


def looks_like_html(text: str) -> bool:
    """
    Args:
        text: Candidate email body text.

    Returns:
        True if `text` contains recognizable HTML tags.
    """
    return bool(re.search(r'<(html|body|div|br|p|a)\b', text, re.IGNORECASE))


def html_to_text(markup: str) -> str:
    """
    Convert an HTML email body into plain text suitable for parsing.

    Args:
        markup: Raw HTML email body.

    Returns:
        Plain text with tags stripped and entities unescaped.
    """
    text = markup

    # Drop script/style blocks entirely
    text = re.sub(r'(?is)<(script|style)\b.*?</\1>', '', text)
    # Line/paragraph boundaries -> newline
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</(p|div|tr|li)>', '\n', text)
    # Strip all remaining tags but keep their inner text (e.g. link text)
    text = re.sub(r'<[^>]+>', '', text)
    # Unescape entities (&nbsp; -> \xa0, &amp; -> &, etc.) then normalize
    text = html.unescape(text)
    text = text.replace('\xa0', ' ')

    lines = [line.rstrip() for line in text.splitlines()]
    return '\n'.join(lines)


def normalize_input(data: dict | list | str) -> str:
    """
    Full pipeline: unwrap the fetched-email payload (dict/list/JSON string/
    Python-literal string), then HTML-to-text if the resulting body is HTML.

    Args:
        data: The raw fetched-email payload, in any form accepted by
            `extract_email_content`.

    Returns:
        Plain text ready for line-by-line parsing.
    """
    content = extract_email_content(data)
    if not isinstance(content, str):
        content = str(content)
    if looks_like_html(content):
        content = html_to_text(content)
    return content


def is_inventory_line(line: str) -> tuple[str, str] | None:
    """
    Row 1 lines look like:
        PART, CONDITION, qty N, CALL, BRAND, description...

    Args:
        line: A single stripped line of the report body.

    Returns:
        A (part, brand) tuple if the line matches the inventory-line shape,
        otherwise None.
    """
    parts = line.split(',', 5)
    if len(parts) < 5:
        return None

    part = parts[0].strip()
    condition = parts[1].strip()
    qty_field = parts[2].strip()
    call_field = parts[3].strip()
    brand = parts[4].strip()

    if not part or call_field != 'CALL' or not qty_field.lower().startswith('qty'):
        return None
    if not condition or not brand:
        return None

    return part, brand


def clean_company(name: str) -> str:
    """
    Strip a lone trailing period (e.g. 'Inc.' -> 'Inc'), keep internal ones.

    Args:
        name: Raw company name as captured from the "Searched by:" line.

    Returns:
        The cleaned company name.
    """
    name = name.strip()
    if name.endswith('.'):
        name = name[:-1]
    return name.strip()


def parse_contact_line(line: str) -> tuple[str, str]:
    """
    Split a contact line into (name, phone), tolerant of a missing space
    before the 'P:' label (e.g. 'N/AP: 763-383-9920').

    Args:
        line: The contact line following a "Searched by:" line.

    Returns:
        A (name, phone) tuple. phone is an empty string if no 'P:' label is found.
    """
    line = line.strip()
    m = PHONE_LABEL_RE.search(line)
    if not m:
        return line, ''
    name = line[:m.start()].strip()
    phone = line[m.end():].strip()
    return name, phone


def parse_brokerbin_report(data: dict | list | str) -> list[list[str]]:
    """
    Parse a BrokerBin report and return a list of lists:

        [Part#, BrandName, CompanyName, CompanyContactName, CompanyContactNumber]

    One inner list per "Searched by" hit.

    Args:
        data: The BrokerBin report email payload. Can be:
            - a dict, e.g. {'contentType': 'html', 'content': '<html>...'}
            - a list of such dicts
            - a JSON or Python-literal string of either of the above
            - a raw HTML string, or plain already-formatted text

    Returns:
        A list of [part_number, brand_name, company_name, contact_name,
        contact_number] rows, one per "Searched by" hit found. Empty if none
        are found or `data` does not contain parseable content.
    """
    text = normalize_input(data)
    records = []
    lines = text.splitlines()

    current_part = None
    current_brand = None

    i = 0
    n = len(lines)
    while i < n:
        raw_line = lines[i]
        line = raw_line.strip()

        if not line or SECTION_HEADER_RE.match(line):
            i += 1
            continue

        inv = is_inventory_line(line)
        if inv:
            current_part, current_brand = inv
            i += 1
            continue

        searched = SEARCHED_BY_RE.search(line)
        if searched and current_part:
            company = clean_company(searched.group('company'))

            contact_name, contact_phone = '', ''
            if i + 1 < n and lines[i + 1].strip():
                contact_name, contact_phone = parse_contact_line(lines[i + 1])
                i += 1  # consume the contact line too

            records.append([current_part, current_brand, company, contact_name, contact_phone])

        i += 1

    return records
