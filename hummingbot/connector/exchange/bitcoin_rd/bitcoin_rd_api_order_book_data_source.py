import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.bitcoin_rd import bitcoin_rd_constants as CONSTANTS, bitcoin_rd_web_utils as web_utils
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger
import time

if TYPE_CHECKING:
    from hummingbot.connector.exchange.bitcoin_rd.bitcoin_rd_exchange import BitcoinRdExchange


class BitcoinRDAPIOrderBookDataSource(OrderBookTrackerDataSource):
    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        trading_pairs: List[str],
        connector: "BitcoinRdExchange",
        api_factory: Optional[WebAssistantsFactory] = None,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._trade_messages_queue_key = CONSTANTS.TRADE_TOPIC_ID
        self._diff_messages_queue_key = CONSTANTS.DIFF_TOPIC_ID
        self._api_factory = api_factory

    async def get_last_traded_prices(self, trading_pairs: List[str], domain: Optional[str] = None) -> Dict[str, float]:
        return await self._connector.get_last_traded_prices(trading_pairs=trading_pairs)

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Retrieves a copy of the full order book from the exchange, for a particular trading pair.

        :param trading_pair: the trading pair for which the order book will be retrieved

        :return: the response from the exchange (JSON dictionary)
        """
        self.logger().info("trading pair books: ")
        self.logger().info(trading_pair)
       
        self.logger().info("params")
        self.logger().info(params)
        params = {
            "symbol": await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        }
        data = await self._connector._api_request(path_url=CONSTANTS.ORDERBOOK_PATH,
                                                  method=RESTMethod.GET,
                                                  params=params)
        self.logger().info("data snapshot:") 
        self.logger().info(data)
        return data

    async def _subscribe_channels(self, ws: WSAssistant):
        """
        Subscribes to the trade events and diff orders events through the provided websocket connection.
        :param ws: the websocket assistant used to connect to the exchange
        """
        try:
            for trading_pair in self._trading_pairs:
                self.logger().info("trading pair")
                self.logger().info(self._trading_pairs)
                trading_symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
                for topic in [CONSTANTS.DIFF_TOPIC_ID, CONSTANTS.TRADE_TOPIC_ID]:
                    payload = {"op": CONSTANTS.SUB_ENDPOINT_NAME, "args": f"{topic}:{trading_symbol}"}
                    await ws.send(WSJSONRequest(payload=payload))

            self.logger().info("Subscribed to public order book and trade channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().error(
                "Unexpected error occurred subscribing to order book trading and delta streams...", exc_info=True
            )
            raise

    async def _connected_websocket_assistant(self) -> WSAssistant:
        self.logger().info("WS: ==")
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=f"{CONSTANTS.WS_URL}")
        return ws

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        self.logger().info("orderbook")
        snapshot_response: Dict[str, Any] = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp =time.time()
        self.logger().info(snapshot_response)
        order_book_message_content = {
            "trading_pair": trading_pair,
            "update_id": snapshot_timestamp,
            "bids": snapshot_response[trading_pair]["bids"],
            "asks": snapshot_response[trading_pair]["asks"],
        }
        snapshot_msg: OrderBookMessage = OrderBookMessage(
            OrderBookMessageType.SNAPSHOT, order_book_message_content, snapshot_timestamp
        )
        return snapshot_msg

    async def _parse_trade_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        self.logger().info("TRADE MESSAGE")
        trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=raw_message["symbol"])
        for trade_data in raw_message["data"]:
            timestamp: float = time.time()
            message_content = {
                "trade_id": timestamp,  # trade id isn't provided so using timestamp instead
                "trading_pair": trading_pair,
                "trade_type": float(TradeType.BUY.value) if trade_data["bm"] else float(TradeType.SELL.value),
                "amount": Decimal(trade_data["q"]),
                "price": Decimal(trade_data["p"]),
            }
            trade_message: Optional[OrderBookMessage] = OrderBookMessage(
                message_type=OrderBookMessageType.TRADE, content=message_content, timestamp=timestamp
            )
            message_queue.put_nowait(trade_message)

    async def _parse_order_book_diff_message(self, raw_message: Dict[str, Any], message_queue: asyncio.Queue):
        self.logger().info("TRADE MESSAGE 2 ")
        diff_data: Dict[str, Any] = raw_message[trading_pair]
        timestamp: float = time.time()
        trading_pair = await self._connector.trading_pair_associated_to_exchange_symbol(symbol=raw_message["symbol"])
        message_content = {
            "trading_pair": trading_pair,
            "update_id": timestamp,
            "bids": diff_data["bids"],
            "asks": diff_data["asks"],
        }
        diff_message: OrderBookMessage = OrderBookMessage(OrderBookMessageType.DIFF, message_content, timestamp)
        message_queue.put_nowait(diff_message)

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        self.logger().info("TRADE MESSAGE 3")
        channel = ""
        if "data" in event_message:
            self.logger().info("event")
            self.logger().info(event_message)
            event_channel = event_message.get("message")
            if event_channel == CONSTANTS.TRADE_TOPIC_ID:
                channel = self._trade_messages_queue_key
            if event_channel == CONSTANTS.DIFF_TOPIC_ID:
                channel = self._diff_messages_queue_key
        return channel

    async def _process_message_for_unknown_channel(
        self, event_message: Dict[str, Any], websocket_assistant: WSAssistant
    ):
        """
        Processes a message coming from a not identified channel.
        Does nothing by default but allows subclasses to reimplement

        :param event_message: the event received through the websocket connection
        :param websocket_assistant: the websocket connection to use to interact with the exchange
        """
        self.logger().info("CH MESSAGE")
        if event_message.get("message") == "ping":
            pong_payloads = {"op": "pong"}
            pong_request = WSJSONRequest(payload=pong_payloads)
            await websocket_assistant.send(request=pong_request)
