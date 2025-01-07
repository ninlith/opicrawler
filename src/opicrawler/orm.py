"""Object–relational mapping."""

from datetime import datetime
from collections import defaultdict
from typing import Optional, Any
from sqlmodel import (
    Field,
    JSON,
    Relationship,
    Session,
    SQLModel,
    create_engine,
    delete,
    select,
    update,
)

engine = None


class OpiferumIP(SQLModel, table=True):
    """Represents an IP address belonging to Opiferum."""
    __tablename__ = "opiferum_ip"
    id: int | None = Field(default=None, primary_key=True)
    ip_address: str = Field(unique=True, index=True)


class Site(SQLModel, table=True):
    """Represents a site."""
    id: int = Field(primary_key=True)
    row_creation_datetime: str

    url_resolution_errors: Optional[list["URLResolutionError"]] = Relationship(
        back_populates="site", cascade_delete=True)
    final_urls: Optional[list["FinalURL"]] = Relationship(
        back_populates="site", cascade_delete=True)


class URLResolutionError(SQLModel, table=True):
    """Represents an URL resolution error."""
    __tablename__ = "url_resolution_error"
    id: int | None = Field(default=None, primary_key=True)
    start_url: str
    error: str

    site_id: int | None = Field(default=None, foreign_key="site.id", ondelete="CASCADE")
    site: Optional[Site] = Relationship(back_populates="url_resolution_errors")


class FinalURL(SQLModel, table=True):
    """Represents data associated with a final URL."""
    __tablename__ = "final_url"
    id: int | None = Field(default=None, primary_key=True)
    url: str
    external_to_opiferum: bool
    html_fetch_error: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    ai_extracts: Optional[dict[str, Any]] = Field(default={}, sa_type=JSON)
    screenshot_error: Optional[str] = None

    site_id: int | None = Field(default=None, foreign_key="site.id", ondelete="CASCADE")
    site: Optional[Site] = Relationship(back_populates="final_urls")

    start_urls: list["StartURL"] = Relationship(back_populates="final_url", cascade_delete=True)
    ip_addresses: list["IPAddress"] = Relationship(back_populates="final_url", cascade_delete=True)


class IPAddress(SQLModel, table=True):
    """Represents an IP address associated with a final URL."""
    __tablename__ = "ip_address"
    id: int | None = Field(default=None, primary_key=True)
    ip: str

    final_url_id: int | None = Field(default=None, foreign_key="final_url.id", ondelete="CASCADE")
    final_url: Optional[FinalURL] = Relationship(back_populates="ip_addresses")


class StartURL(SQLModel, table=True):
    """Represents a start URL associated with a final URL."""
    __tablename__ = "start_url"
    id: int | None = Field(default=None, primary_key=True)
    url: str

    final_url_id: int | None = Field(default=None, foreign_key="final_url.id", ondelete="CASCADE")
    final_url: Optional[FinalURL] = Relationship(back_populates="start_urls")


def setup_engine(path):
    """Initialize the SQLAlchemy engine with the given path."""
    sqlite_path = path
    sqlite_url = f"sqlite:///{sqlite_path}"
    global engine
    engine = create_engine(sqlite_url)


def get_session():
    """Return a new database session."""
    if engine is None:
        raise RuntimeError("Engine not initialized. Call setup_engine first.")
    return Session(engine)


def create_db_and_tables():
    """Create all database tables."""
    SQLModel.metadata.create_all(engine)


def create_or_replace_opiferum_ips(opiferum_ip_addresses):
    """Create or replace IP addresses belonging to Opiferum."""
    with Session(engine) as session:
        existing_ips = set(
            ip.ip_address for ip in session.exec(select(OpiferumIP)).all()
        )
        if opiferum_ip_addresses != existing_ips:
            session.exec(delete(OpiferumIP))
            session.add_all(OpiferumIP(ip_address=ip) for ip in opiferum_ip_addresses)
            session.commit()


def _structuralize_responses(responses) -> defaultdict:
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
    return sites


def create_or_replace_structured_responses(responses):
    """Create or replace structured responses."""
    with Session(engine) as session:
        sites = _structuralize_responses(responses)
        for site_id, site_data in sites.items():
            existing_site = session.exec(select(Site).where(Site.id == site_id)).first()
            if existing_site:
                session.delete(existing_site)
                session.commit()

            new_site = Site(
                id=site_id,
                row_creation_datetime=datetime.now().isoformat(),
            )
            new_site.url_resolution_errors = [
                URLResolutionError(**x) for x in site_data["url_resolution_errors"]
            ]
            new_site.final_urls = [
                FinalURL(
                    url=k,
                    external_to_opiferum=v["external_to_opiferum"],
                    html_fetch_error=v["html_fetch_error"] if "html_fetch_error" in v else None,
                    html=v["html"] if "html" in v else None,
                    start_urls=[
                        StartURL(url=url) for url in v["start_urls"]
                    ],
                    ip_addresses=[
                        IPAddress(ip=ip) for ip in v["ip_addresses"]
                    ],
                )
                for k, v
                in site_data["final_urls"].items()
            ]
            session.add(new_site)
        session.commit()


def select_pages() -> list[dict]:
    """Retrieve all pages with non-empty HTML content."""
    with Session(engine) as session:
        pages = session.exec(
            select(
                FinalURL.id,
                FinalURL.site_id,
                FinalURL.url,
                FinalURL.html,
            ).where(
                FinalURL.html.is_not(None)
            )
        )
    return [
        {"id": page.id, "site_id": page.site_id, "url": page.url, "html": page.html}
        for page in pages
    ]


def update_pages(pages):
    """Update FinalURL entries with the given list of page data."""
    if not pages:
        return
    with Session(engine) as session:
        for page in pages:
            page_id = page.pop("id")
            session.exec(
                update(FinalURL)
                .where(FinalURL.id == page_id)
                .values(**page)
            )
        session.commit()
