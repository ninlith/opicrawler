"""Report generation."""

import itertools
import logging

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


def write_report(sites, screenshot_errors, output_path):  # XXX
    """Create a human-readable report in Markdown format."""
    lines = []
    non_opiferum_sites = []
    sites_with_errors = []
    sites_with_multiple_final_urls = []
    site_extracts = []
    for site_id, site in sites["site_ids"].items():
        if "final_urls" in site:
            if any(
                v["external_to_opiferum"]
                for v in site["final_urls"].values()
            ):
                non_opiferum_sites.append(f'* {site_id}')
                non_opiferum_sites.extend(
                    f'    * NON-OPIFERUM: {v["start_urls"]} -> {k}'
                    for k, v in site["final_urls"].items()
                    if v["external_to_opiferum"]
                )
                non_opiferum_sites.extend(
                    f'    * OPIFERUM: {v["start_urls"]} -> {k}'
                    for k, v in site["final_urls"].items()
                    if not v["external_to_opiferum"]
                )
            if len(site["final_urls"]) > 1:
                sites_with_multiple_final_urls.append(f'* {site_id}')
                sites_with_multiple_final_urls.extend(
                    f'    * {k} <- {site["final_urls"][k]["start_urls"]}'
                    for k in site["final_urls"].keys()
                )
            for final_url, v in site["final_urls"].items():
                if "ai_extracts" in v:
                    extracts = v["ai_extracts"]
                    site_extracts.extend([f'## {site_id} <{final_url}>', ""])
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
        if "url_resolution_errors" in site or any(
                    True
                    for v in site["final_urls"].values()
                    if "html_fetch_error" in v
                ):
            sites_with_errors.append(f'* {site_id}')
            if "url_resolution_errors" in site:
                sites_with_errors.extend(
                    f'    * RESOLUTION ERROR: {error["start_url"]}: {error["error"]}'
                    for error in site["url_resolution_errors"]
                )
            if "final_urls" in site:
                sites_with_errors.extend(
                    f'    * RESOLUTION SUCCESS: {v["start_urls"]} -> {k}'
                    for k, v in site["final_urls"].items()
                )
                sites_with_errors.extend(
                    f'    * HTML FETCH ERROR: {k}: {v["html_fetch_error"]}'
                    for k, v in site["final_urls"].items()
                    if "html_fetch_error" in v
                )
    screenshot_error_lines = [
        f"* {identifier}, {url}: {error_message}"
        for identifier, url, error_message in screenshot_errors
    ]
    lines = itertools.chain.from_iterable(
        ["# " + title, ""] + (content or ["None."]) + [""]
        for title, content in (
            ("Sites with Non-Opiferum Final URLs", non_opiferum_sites),
            ("Sites with Multiple Final URLs", sites_with_multiple_final_urls),
            ("Site Request Errors", sites_with_errors),
            ("Screenshot Errors", screenshot_error_lines),
            ("Site Extracts", site_extracts),
        )
    )
    with open(output_path/"report.md", "w", encoding="utf-8",
              newline="\n") as report_file:
        report_file.writelines("\n".join(lines))
