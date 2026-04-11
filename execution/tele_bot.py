
import requests
from strategy.metadata import VERSION

class TelegramReporter:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_alert(self, symbol, side, params):
        """
        發送高質量的進場報告
        """
        message = (
            f"🚀 **【{VERSION} 交易信號】**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🔹 **幣種**: {symbol}\n"
            f"🔹 **方向**: {side}\n"
            f"🔹 **天氣**: {params.get('regime_desc', 'UNKNOWN')}\n"
            f"🔹 **Z-Score**: {params.get('z_score', 0):.2f}\n"
            f"🔹 **預期 TP**: {params.get('tp_price', 0)}\n"
            f"🔹 **止損 SL**: {params.get('sl_price', 0)}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📍 *系統目前處於實戰監控中*"
        )
        self._post(message)

    def _post(self, text):
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        requests.post(self.base_url, data=payload)
