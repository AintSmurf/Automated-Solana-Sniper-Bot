import time, json, websocket
from config.network import HELIUS_WS
from helpers.framework_utils import get_payload
from config.dex_detection_rules import DEX_DETECTION_RULES

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

    def start_ws(self):
        self.logger.info(f"🌐 Connecting WS: {self.wss_url}")
        self.logger.info(f"trades count:{self.ctx.settings['MAXIMUM_TRADES']}, dollars per trade:{self.ctx.settings['TRADE_AMOUNT']}")
        self.ws = websocket.WebSocketApp(
            self.wss_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        while not self.stop_ws.is_set():
            try:
                self.ws.run_forever()
            except Exception as e:
                self.logger.error(f"❌ WebSocket error: {e}")

            if not self.stop_ws.is_set():
                self.logger.warning("🔄 Reconnecting in 5s...")
                time.sleep(5)

    def on_open(self, ws):
        self.dex_payload["id"] = self.id; self.id += 1
        ws.send(json.dumps(self.dex_payload))
        self.logger.info("✅ Subscribed to AMM logs.")

    def on_message(self, ws, message):
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
