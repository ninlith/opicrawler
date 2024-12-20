"""JSON structure."""

from collections import defaultdict
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from opicrawler.async_ai_extraction import Extracts


class URLResolutionError(BaseModel):
    """Represents an URL resolution error."""
    start_url: str
    error: str

class FinalUrlData(BaseModel):
    """Represents data for a final URL."""
    start_urls: list[str]
    ip_addresses: list[str]
    external_to_opiferum: bool
    html_fetch_error: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    ai_extracts: Optional[Extracts] = None

class SiteData(BaseModel):
    """Represents site data."""
    final_urls: Optional[dict[str, FinalUrlData]] = None
    url_resolution_errors: Optional[list[URLResolutionError]] = None

class Sites(BaseModel):
    """The main Pydantic model."""
    datetime: str
    opiferum_ip_addresses: list[str]
    site_ids: dict[str, SiteData]


def validate_json(json_data):
    """Validate the given JSON data against the main Pydantic model."""
    return Sites.model_validate_json(json_data)


def structuralize_responses(responses, opiferum_ip_addresses) -> defaultdict:
    """Structuralize responses to an associative array."""
    sites = defaultdict(lambda: defaultdict(dict))
    for response in responses:
        site = sites[response["identifier"]]
        if "url_resolution_errors" in response:
            if "url_resolution_errors" in site:
                site["url_resolution_errors"].extend(response["url_resolution_errors"])
            else:
                site["url_resolution_errors"] = response["url_resolution_errors"]
        if "final_url" in response:
            if response["final_url"] in site["final_urls"]:
                site["final_urls"][response["final_url"]]["start_urls"].append(
                    response["start_url"])
            else:
                site["final_urls"][response["final_url"]] = {
                    "start_urls": [response["start_url"]],
                    "ip_addresses": response["ip_addresses"],
                    "external_to_opiferum": response["external_to_opiferum"],
                }
                final_url_data = site["final_urls"][response["final_url"]]
                if "html" in response:
                    final_url_data["html"] = response["html"]
                if "html_fetch_error" in response:
                    final_url_data["html_fetch_error"] = response["html_fetch_error"]
    sites = {
        "datetime": datetime.now().isoformat(),
        "opiferum_ip_addresses": opiferum_ip_addresses,
        "site_ids": sites,
    }
    return sites
