"""Report generation."""

import itertools
import logging
from sqlmodel import select, func, or_
from opicrawler.orm import get_session, Site, FinalURL

logger = logging.getLogger(__name__)


# A wrapper function.
def _recurse_menu(menu, indent=4, initial_level=0, max_level=None):
    """Transform a MenuItem-based dict to a Markdown menu structure."""

    # An auxiliary function.
    def recurse(items, lines, level):
        """Recurse the menu."""
        if max_level and level >= max_level:
            return
        for item in items:
            if "link" in item:
                lines.append(" "*level*indent + f'* [{item["label"]}]({item["link"]})')
            else:
                lines.append(" "*level*indent + f'* {item["label"]}')
            if "subitems" in item:
                recurse(item["subitems"], lines, level + 1)

    lines = []
    recurse(menu, lines, initial_level)
    return lines


def _non_opiferum_sites():
    """Return a Markdown list of sites with non-Opiferum final URLs."""
    results = []
    with get_session() as session:
        sites = session.exec(
            select(Site)
            .join(FinalURL)
            .where(FinalURL.external_to_opiferum)
            .distinct()
        )
        for site in sites:
            results.append(f'* {site.id}')
            for final_url in site.final_urls:
                prefix = "NON-" if final_url.external_to_opiferum else ""
                start_urls = [start_url.url for start_url in final_url.start_urls]
                results.append(f'    * {prefix}OPIFERUM: {start_urls} -> {final_url.url}')
    return results


def _sites_with_multiple_final_urls():
    """Return a Markdown list of sites with multiple final URLs."""
    results = []
    with get_session() as session:
        sites = session.exec(
            select(Site)
            .join(FinalURL)
            .group_by(Site.id)
            .having(func.count(FinalURL.id) > 1)
        )
        for site in sites:
            results.append(f'* {site.id}')
            for final_url in site.final_urls:
                start_urls = [start_url.url for start_url in final_url.start_urls]
                results.append(f'    * {final_url.url} <- {start_urls}')
    return results


def _sites_with_url_resolution_errors():
    """Return a Markdown list of sites with URL resolution errors."""
    results = []
    with get_session() as session:
        sites = session.exec(
            select(Site).where(Site.url_resolution_errors.any())
        )
        for site in sites:
            results.append(f'* {site.id}')
            for error in site.url_resolution_errors:
                results.append(f'    * ERROR: {error.start_url}: {error.error}')
            for final_url in site.final_urls:
                start_urls = [start_url.url for start_url in final_url.start_urls]
                results.append(f'    * SUCCESS: {start_urls} -> {final_url.url}')
    return results


def _other_errors():
    """Return a Markdown list of other errors."""
    results = []
    with get_session() as session:
        final_urls = session.exec(
            select(FinalURL).where(
                or_(
                    FinalURL.html_fetch_error.is_not(None),
                    FinalURL.screenshot_error.is_not(None),
                )
            )
        )
        for final_url in final_urls:
            results.append(f"* {final_url.site_id} {final_url.url}")
            results.extend(
                f"    * {k}: {v}"
                for k, v
                in {"HTML FETCH ERROR: ": final_url.html_fetch_error,
                    "SCREENSHOT ERROR: ": final_url.screenshot_error}.items()
                if v
            )
    return results


def _site_extracts():
    """Return site extracts in Markdown format."""
    site_extracts = []
    with get_session() as session:
        final_urls = session.exec(
            select(FinalURL).where(FinalURL.ai_extracts != {})
        )
        for final_url in final_urls:
            extracts = final_url.ai_extracts
            site_extracts.extend([f'## {final_url.site_id} <{final_url.url}>', ""])
            if "main_menu" in extracts:
                site_extracts.extend(["### Main Menu:", ""])
                site_extracts.extend(
                    _recurse_menu(extracts["main_menu"], max_level=1)
                )
                site_extracts.append("")
            if "services" in extracts:
                site_extracts.extend(["### Services", ""])
                site_extracts.extend([extracts["services"]["description"], ""])
                site_extracts.extend(f'* {s}' for s in extracts["services"]["listing"])
                site_extracts.append("")
            if "contact_information" in extracts:
                site_extracts.extend(["### Contact Information", ""])
                site_extracts.extend(
                    f'* {k}: {v}'
                    for k, v in extracts["contact_information"].items()
                    if k not in ["social_profiles", "individuals"]
                )
                if "social_profiles" in extracts["contact_information"]:
                    site_extracts.append("* social_profiles:")
                    site_extracts.extend(
                        f'    * {item}' for item
                        in extracts["contact_information"]["social_profiles"]
                    )
                if "individuals" in extracts["contact_information"]:
                    site_extracts.append("* individuals:")
                    for individual in extracts["contact_information"]["individuals"]:
                        site_extracts.append(
                            "    * "
                            +  ", ".join(f"{k}: {v}" for k, v in individual.items())
                        )
                site_extracts.append("")
    return site_extracts

def write_report(output_path):
    """Create a human-readable report in Markdown format."""
    lines = itertools.chain.from_iterable(
        ["# " + title, ""] + (content or ["None."]) + [""]
        for title, content in (
            ("Sites with Non-Opiferum Final URLs", _non_opiferum_sites()),
            ("Sites with Multiple Final URLs", _sites_with_multiple_final_urls()),
            ("Sites with URL Resolution Errors", _sites_with_url_resolution_errors()),
            ("Other Errors", _other_errors()),
            ("Site Extracts", _site_extracts()),
        )
    )
    with open(output_path/"report.md", "w", encoding="utf-8",
              newline="\n") as report_file:
        report_file.writelines("\n".join(lines))
