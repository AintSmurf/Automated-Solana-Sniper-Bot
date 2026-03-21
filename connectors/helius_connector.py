import time, json, websocket, threading
from config.network import HELIUS_WS
from helpers.framework_utils import get_payload
from config.dex_detection_rules import DEX_DETECTION_RULES
import os


class HeliusConnector:
    def __init__(self, ctx, stop_ws,):
        self.ctx = ctx
        self.logger = ctx.get("logger")

        self.stop_ws = stop_ws

        self.api_key = ctx.api_keys["helius"]
        self.network = ctx.settings["NETWORK"]
        self.wss_url = HELIUS_WS[self.network] + self.api_key

        self.dex_name = ctx.api_keys["dex"]
        self.dex_payload = get_payload(self.dex_name)
        self.id = 1

        # shared pipes
        self.queue = ctx.get("signature_queue")
        self.sig_seen = ctx.get("signature_seen")
        self.sig_to_mint = ctx.get("sig_to_mint")
        self.ws = None
        self.last_message_ts = time.time()
        self.last_message_lock = threading.Lock()
        self.restart_requested = threading.Event()

    def start_ws(self):
        self.logger.info(f"🌐 Connecting WS: {self.wss_url}")
        self.logger.info(
            f"trades count:{self.ctx.settings['MAXIMUM_TRADES']}, "
            f"dollars per trade:{self.ctx.settings['TRADE_AMOUNT']}"
        )

        self.restart_requested.clear()
        self._mark_alive()

        self.ws = websocket.WebSocketApp(
            self.wss_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_pong=self.on_pong,
        )

        current_ws = self.ws

        watchdog = threading.Thread(
            target=self._watchdog,
            args=(current_ws,),
            daemon=True,
            name="HeliusWsWatchdog"
        )
        watchdog.start()

        try:
            self.ws.run_forever(
                ping_interval=10,
                ping_timeout=5,
                ping_payload="ping"
            )

            self.logger.warning(
                f"⚠️ WebSocket run_forever() returned. "
                f"restart_requested={self.restart_requested.is_set()}, "
                f"stop_ws={self.stop_ws.is_set()}"
            )

        except Exception as e:
            self.logger.error(f"❌ WebSocket error: {e}", exc_info=True)

        finally:
            try:
                if self.ws:
                    self.ws.keep_running = False
                    self.ws.close()
            except Exception:
                pass

        return

    def _mark_alive(self):
        with self.last_message_lock:
            self.last_message_ts = time.time()

    def _watchdog(self, ws):
        stale_limit = 25

        while not self.stop_ws.is_set() and ws is self.ws:
            time.sleep(5)

            with self.last_message_lock:
                age = time.time() - self.last_message_ts

            if age > stale_limit:
                self.logger.error(
                    f"🚨 WebSocket stale: no message/pong for {age:.0f}s. Requesting restart."
                )

                self.restart_requested.set()

                try:
                    ws.keep_running = False
                    ws.close()
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to close stale WebSocket: {e}")

                time.sleep(8)

                if self.restart_requested.is_set() and not self.stop_ws.is_set() and ws is self.ws:
                    self.logger.critical(
                        "💥 WebSocket did not return after stale close. Exiting for systemd restart."
                    )
                    os._exit(1)

                return

    def on_pong(self, ws, message):
        self._mark_alive()
        self.logger.debug("🏓 WebSocket pong received.")
    
    def on_open(self, ws):
        self._mark_alive()

        self.dex_payload["id"] = self.id
        self.id += 1

        ws.send(json.dumps(self.dex_payload))
        self.logger.info("✅ Subscribed to AMM logs.")

    def on_message(self, ws, message):
        self._mark_alive()
        try:
            data = json.loads(message)
            self.logger.debug(f"ws response:{data}")
            value = data.get("params", {}).get("result", {}).get("value", {})
            if not value:
                return
            signature = value.get("signature")
            logs = value.get("logs", [])
            if not signature:
                return

            # quick filter with rules
            rules = DEX_DETECTION_RULES.get(self.dex_name, [])
            if rules and not any(any(rule in log for rule in rules) for log in logs):
                return

            # de-dupe
            with self.ctx.get("signature_seen_lock"):
                if signature in self.sig_seen:
                    return
                self.sig_seen.add(signature)
            self.queue.put((signature, None, None, "LIVE"))
        except Exception as e:
            self.logger.error(f"❌ on_message error: {e}", exc_info=True)

    def on_error(self, ws, error):
        self.logger.error(f"WS error: {error}")

    def on_close(self, ws, code, msg):
        if self.stop_ws.is_set():
            self.logger.info("🛑 WS closed due to shutdown.")
            return
        self.logger.warning(f"WS closed (code={code}) {msg}")

    def close(self):
        self.stop_ws.set()
        try:
            self.ws.close()
        except Exception:
            pass
  