"""Data preprosessing."""

import re
import html2text


def parse_domains_file(file_object):
    """Process the domains input file."""
    id_domain_pairs = []
    for line in file_object.readlines():
        if results := re.search(r"(\d+)\s+([\w\.-]+)", line):
            id_domain_pairs.append(results.groups())
    return id_domain_pairs


def convert_html_to_text(page):
    """Convert HTML to plain text."""
    h = html2text.HTML2Text()
    h.body_width = 0  # to ensure that lines aren't chopped up
    h.ignore_links = False
    h.ignore_images = True
    h.single_line_break = True
    h.unicode_snob = True
    return {**page, "text": h.handle(page["html"] if "html" in page else "")}
