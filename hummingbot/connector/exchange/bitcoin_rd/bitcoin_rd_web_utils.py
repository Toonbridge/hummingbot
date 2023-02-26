import time
from typing import Any, Dict, Optional

from hummingbot.connector.exchange.bitcoin_rd import bitcoin_rd_constants as CONSTANTS
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest
from hummingbot.core.web_assistant.rest_pre_processors import RESTPreProcessorBase
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory


class BitcoinRDRESTPreProcessor(RESTPreProcessorBase):
    async def pre_process(self, request: RESTRequest) -> RESTRequest:
        if request.headers is None:
            request.headers = {}
        # Generates generic headers required by BitcoinRD
        headers_generic = {}
        headers_generic["Accept"] = "application/json"
        headers_generic["Content-Type"] = "application/json"
        # Headers signature to identify user as an HB liquidity provider.
        request.headers = dict(
            list(request.headers.items()) + list(headers_generic.items()) + list(get_hb_id_headers().items())
        )
        return request


def get_hb_id_headers() -> Dict[str, Any]:
    """
    Headers signature to identify user as an HB liquidity provider.

    :return: a custom HB signature header
    """
    return {
        "request-source": "hummingbot-liq-mining",
    }


def public_rest_url(path_url: str) -> str:
    """
    Creates a full URL for provided private REST endpoint
    :param path_url: a private REST endpoint
    :param domain: domain to connect to
    :return: the full URL to the endpoint
    """
    return CONSTANTS.REST_URL + path_url


def private_rest_url(path_url: str) -> str:
    """
    Creates a full URL for provided private REST endpoint
    :param path_url: a private REST endpoint
    :param domain: the domain to connect to
    :return: None, we use overwrite_url instead
    """
    return CONSTANTS.REST_URL + path_url


def build_api_factory(
    throttler: Optional[AsyncThrottler] = None,
    domain: str = CONSTANTS.DEFAULT_DOMAIN,
    auth: Optional[AuthBase] = None,
) -> WebAssistantsFactory:
    throttler = throttler or create_throttler()
    api_factory = WebAssistantsFactory(throttler=throttler, auth=auth, rest_pre_processors=[BitcoinRDRESTPreProcessor()])
    return api_factory

