from .exceptions import SolverError
from .. import chrome
from queue import Queue
import requests
import json
import time

class CapMonsterClient:
    _base_url = "https://api.capmonster.cloud"

    def __init__(self,
        key,
        public_key,
        service_url,
        page_url,
        data={}
    ):
        self._rs = requests.Session()
        self._token_queue = Queue()
        self._key = key + "__nocache"
        self._public_key = public_key
        self._service_url = service_url
        self._page_url = page_url
        self._data = data

    def put_token(self, token):
        self._token_queue.put(token)
    
    def get_token(self, timeout=120, interval=0.5):
        try: return self._token_queue.get(False)
        except: pass

        task_id = self._request("/createTask", {
            "task": {
                "type": "FunCaptchaTaskProxyless",
                "websiteURL": self._page_url,
                "funcaptchaApiJSSubdomain": self._service_url.replace("https://", ""),
                "data": json.dumps(self._data, separators=(",", ":")),
                "websitePublicKey": self._public_key,
                "userAgent": chrome.user_agent
            }
        })["taskId"]
        start_time = time.time()

        while timeout > (time.time() - start_time):
            time.sleep(interval)
            state = self._request("/getTaskResult", {
                "taskId": task_id
            })
            if state["status"] == "ready":
                return state["solution"]["token"]
        
        raise SolverError("ERROR_CAPTCHA_UNSOLVABLE")

    def _request(self, path, payload={}):
        response = self._rs.request(
            method="POST",
            url=self._base_url + path,
            json={"clientKey": self._key, **payload}
        )
        response.raise_for_status()
        data = response.json()
        
        if data["errorId"] != 0:
            raise SolverError(data["errorCode"])
        
        del data["errorId"]
        return data
