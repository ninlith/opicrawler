"""AI-assisted web page data extraction."""

import asyncio
import json
import logging
from typing import Optional
import openai
import pydantic_core
import stamina
from openai import AsyncOpenAI
from pydantic import BaseModel
from opicrawler.logging import OpenAILogMonitor

logger = logging.getLogger(__name__)


class MenuItem(BaseModel):
    """Represents a menu item that allows nested submenus."""
    label: str
    link: Optional[str] = None
    subitems: Optional[list['MenuItem']] = None

class Services(BaseModel):
    """Represents services provided by an entity."""
    description: str
    listing: list[str]

class IndividualContact(BaseModel):
    """Represents an individual contact."""
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class ContactInformation(BaseModel):
    """Represents contact details for an entity."""
    entity_name: Optional[str] = None
    main_email: Optional[str] = None
    main_phone: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    social_profiles: Optional[list[str]] = None
    individuals: Optional[list[IndividualContact]] = None
    additional_info: Optional[dict] = None

class Extracts(BaseModel):
    """Schema for Structured Outputs."""
    main_menu: Optional[list[MenuItem]] = None
    services: Optional[Services] = None
    contact_information: Optional[ContactInformation] = None


def _error_to_retry(exc: Exception) -> bool:
    """Return True if Exception is of specified type."""
    # Retry with warning.
    # BUG: https://github.com/openai/openai-python/issues/1763
    if isinstance(exc, pydantic_core._pydantic_core.ValidationError):
        logger.warning(exc)
        return True

    # Otherwise retry silently on all of the following errors.
    return isinstance(exc, (openai.RateLimitError, openai.APIError, asyncio.TimeoutError))


async def _extract_data(*, client, model, page, counter, callback):
    """Extract structured information from a web page content."""
    callback(advance_secondary=1)
    page_content = json.dumps(page["text"])

    @stamina.retry(
        on=_error_to_retry,
        attempts=6,
        timeout=60,
        wait_initial=1,
        wait_max=20,
        wait_jitter=5,
    )
    async def completion_with_backoff(**kwargs):
        """Exponential backoff with jitter between retries."""
        return await client.beta.chat.completions.parse(**kwargs)

    completion = await completion_with_backoff(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are an assistant specializing in extracting "
                           "structured information from text."
            },
            {
                "role": "user",
                "content": f"""
Here is a plain-text Markdown representation of a web page, wrapped in JSON:

{page_content}

Please identify and extract the following:

- The main menu navigation items, excluding any entry point label (e.g., 'Menu', 'Valikko', or similar).
- The key services offered by the entity behind the page, as a concise description and a list, both in Finnish.
- Contact information.
""",
            },
        ],
        response_format=Extracts,
    )
    logger.debug(f'x-request-id: {completion._request_id}, final_url: {page["final_url"]}')

    # Get the structured output from the response.
    content = completion.choices[0].message.content

    # Validate and parse the structured output into the Pydantic Extracts model.
    extracts = Extracts.model_validate_json(content)

    # Clean the data by excluding unset and None values.
    cleaned_data = extracts.model_dump(exclude_unset=True, exclude_none=True)

    page["ai_extracts"] = cleaned_data
    callback(advance=1)
    return page


async def _extract_data_with_semaphore(semaphore, **kwargs):
    """Limit concurrency with a semaphore and handle specific exceptions."""
    async with semaphore:
        try:
            return await _extract_data(**kwargs)  # pylint: disable=missing-kwoa
        except (openai.RateLimitError, openai.APIError, asyncio.TimeoutError) as exc:
            logger.error(exc)
        except pydantic_core._pydantic_core.ValidationError as exc:
            logger.error(exc)
            logger.debug(kwargs)
        return kwargs["page"]


async def gather_extracts(
        pages,
        concurrency_limit,
        tasks_per_second,
        openai_model,
        callback,
) -> list[dict]:
    """Send concurrent OpenAI API requests and collect results."""
    semaphore = asyncio.Semaphore(concurrency_limit)
    client = AsyncOpenAI()
    n = len(pages)
    callback(total=n)
    olm = OpenAILogMonitor(total=n)
    tasks = []
    async with asyncio.TaskGroup() as tg:
        for i, page in enumerate(pages, 1):
            task = tg.create_task(
                _extract_data_with_semaphore(
                    semaphore,
                    client=client,
                    model=openai_model,
                    page=page,
                    counter=(i, n),
                    callback=callback,
                )
            )
            tasks.append(task)
            await asyncio.sleep(1/tasks_per_second)
    responses = [task.result() for task in tasks]
    return responses
