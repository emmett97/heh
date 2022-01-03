from .exceptions import SolverError
from flask import Flask, request
from queue import Queue, Empty
import threading
import subprocess
import logging
import os

os.environ["WERKZEUG_RUN_MAIN"] = "true"
logging.getLogger("werkzeug").disabled = True

class ArkoseSelfSolver:
    def __init__(self,
        public_key: str,
        service_url: str,
        page_url: str = None,
        page_title: str = None,
        history_length: int = 1,
        port: int = 5532
    ):
        self._public_key = public_key
        self._service_url = service_url
        self._page_url = page_url
        self._page_title = page_title
        self._history_length = history_length
        self._port_num = port
        self._token_queue = Queue()
        self._start_server()

    def launch_browser(self):
        subprocess.Popen([
            'start',
            "",
            f'{self.get_url()}/'],
            shell=True)

    def get_url(self):
        return f"http://127.0.0.1:{self._port_num}"

    def put_token(self, token):
        self._token_queue.put(token)

    def get_token(self):
        try:
            token = self._token_queue.get(True, timeout=30)
            return token
        except Empty:
            raise SolverError

    def _start_server(self):
        app = Flask("SelfSolver")

        @app.route("/")
        def present_captcha():
            return """
                <div id="CAPTCHA"></div>
                <iframe
                    src="/empty"
                    sandbox="allow-scripts allow-forms allow-same-origin allow-popups"
                    style="display: none"
                    id="enforcementFrame"
                    title="Making sure you're human"
                ></iframe>
                <br/>
                <button onclick="reloadCaptcha()">Reload</button>

                <script>
                    let f = document.getElementById("enforcementFrame")

                    f.addEventListener("load", () => {
                        for (let i = 0; i < 3; i++) {
                            f.contentWindow.history.pushState(null, "", "/empty")
                        }
                        f.src = "https://iframe.arkoselabs.com/{public_key}/index.html?mkt=en"
                    })
                
                    function reloadCaptcha() {
                        location.replace("/")
                    }

                    async function submitToken(token) {
                        await fetch("/send-token", {
                            method: "POST",
                            headers: {"content-type": "application/json"},
                            body: JSON.stringify({token: token})
                        })
                        reloadCaptcha()
                    }
                    
                    function changeFrameSize(data) {
                        f.style = `height: ${data.frameHeight}px; width: ${data.frameWidth}px; border: none;`
                    }
                    
                    window.addEventListener("message", e => {
                        let data = JSON.parse(e.data)
                        if (data.eventId == "challenge-complete") {
                            submitToken(data.payload.sessionToken)
                        } else if (data.eventId == "challenge-loaded") {
                            changeFrameSize(data.payload)
                        } else if (data.eventId == "challenge-iframeSize") {
                            changeFrameSize(data.payload)
                        }
                    }, false)
                </script>
                """ \
                .replace("{public_key}", self._public_key) \
                .replace("{service_url}", self._service_url) \
                .replace("{page_url}", self._page_url or self._service_url) \
                .replace("{page_title}", self._page_title) \
                .replace("{history_length}", str(self._history_length)) \
                .replace("{solve_url}", self.get_url())

        @app.route("/empty")
        def empty():
            return ""

        @app.route("/send-token", methods=["POST"])
        def submit_token():
            token = request.get_json()["token"]
            self._token_queue.put(token)
            return ""

        threading.Thread(
            target=app.run,
            kwargs={"port": self._port_num}
            ).start()