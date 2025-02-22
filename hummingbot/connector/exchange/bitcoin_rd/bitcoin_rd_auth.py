
import hashlib
import hmac
import json
from collections import OrderedDict
from typing import Any, Dict
from urllib.parse import urlencode
import time

from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, RESTRequest, WSRequest


class BitcoinRDAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """
        print("REQUEST")
        print(request)
        _path = request.throttler_limit_id
        _method = ""
        if request.method == RESTMethod.GET:
            _method = "GET"
        elif request.method == RESTMethod.POST:
            _method = "POST"
        elif request.method == RESTMethod.PUT:
            _method = "PUT"
        elif request.method == RESTMethod.DELETE:
            _method = "DELETE"
        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        if _method == "POST" or _method == "DELETE":
             headers.update(self.auth_me(_path, _method, params=request.params))
        else:
            headers.update(self.auth_me(_path, _method))
        request.headers = headers
        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        This method is intended to configure a websocket request to be authenticated. BitcoinRD does not use this
        functionality
        """
        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        
        headers.update(self.auth_me("ok", "ok", is_ws=True))
        request.headers = headers
        return request

    def get_api_expires(self):
        return str(int(time.time() + 60))
    

    def generate_signature(self, PATH_URL, METHOD, api_expires, is_ws, params=None):
        method, path, api_expires = self.init_signature(PATH_URL, METHOD, is_ws)
        string_to_encode = method + path + api_expires
        if params != None:
            string_to_encode += json.dumps(params, separators=(',', ':'))
        signature = hmac.new(self.secret_key.encode(),string_to_encode.encode(),hashlib.sha256).hexdigest()
        return signature

    def init_signature(self, PATH_URL, METHOD, is_ws):
        if is_ws:
            method = "CONNECT"
            path = '/stream'
            api_expires = self.get_api_expires()
            return method, path, api_expires
        else:   
            method = METHOD
            path = f"/v2{PATH_URL}"
            api_expires = self.get_api_expires()
            return method, path, api_expires

    def auth_me(self, PATH_URL, METHOD, is_ws=False, params=None):
        method, path, api_expires = self.init_signature(PATH_URL, METHOD, is_ws)
        api_expires = self.get_api_expires()
        signature = self.generate_signature(PATH_URL, METHOD, api_expires, is_ws, params=None)
        headers = {
            "api-key": self.api_key,
            "api-signature": signature,
            "api-expires": api_expires
        }
        return headers
