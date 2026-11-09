import time
import json
import os
import sys
import logging
import warnings
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.parse
import urllib.request
import threading
import yfinance as yf
from flask import Flask, jsonify, request, render_template

# Suppress all warnings to keep terminal output clean
warnings.filterwarnings("ignore")

app = Flask(__name__)

# Suppress the Flask development server warning message
cli = sys.modules.get('flask.cli', None)
if cli is not None:
    cli.show_server_banner = lambda *x: None

# Disable Werkzeug's default HTTP request logging in terminal
logging.getLogger('werkzeug').setLevel(logging.ERROR)

config_file = "config.json"
global_prices = {}
global_alert_states = {}

class StockAlert:
    def __init__(self, symbol, target_price, alert_type="above", last_price=None, last_checked=None):
        self.symbol = symbol
        self.target_price = target_price
        self.alert_type = alert_type
        self.last_price = last_price
        self.last_checked = last_checked

class EmailConfig:
    def __init__(self, enabled=False, smtp_server="smtp.gmail.com", smtp_port=587, sender_email="", sender_password="", recipient_email=""):
        self.enabled = enabled
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.recipient_email = recipient_email

class TelegramConfig:
    def __init__(self, enabled=False, bot_token="", chat_id=""):
        self.enabled = enabled
        self.bot_token = bot_token
        self.chat_id = chat_id

class StockPriceMonitor:
    def __init__(self, cfg_file="config.json"):
        self.config_file = cfg_file
        self.stocks = []
        self.email_config = None
        self.telegram_config = None
        self.check_interval = 60
        self.alert_states = global_alert_states
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                self.stocks = [StockAlert(**stock) for stock in config.get('stocks', [])]
                if 'email' in config:
                    self.email_config = EmailConfig(**config['email'])
                if 'telegram' in config:
                    self.telegram_config = TelegramConfig(**config['telegram'])
                self.check_interval = config.get('check_interval', 60)
            except Exception as e:
                print(f"Error loading config: {e}")
                self._create_default_config()
        else:
            self._create_default_config()

    def _create_default_config(self):
        default_config = {
            "stocks": [{"symbol": "INFY.NS", "target_price": 3000.0, "alert_type": "above"}],
            "check_interval": 60,
            "email": {"enabled": False, "smtp_server": "smtp.gmail.com", "smtp_port": 587, "sender_email": "", "sender_password": "", "recipient_email": ""},
            "telegram": {"enabled": False, "bot_token": "", "chat_id": ""}
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=4)
            self.load_config()
        except Exception as e:
            print(f"Error creating default config: {e}")

    def get_stock_price(self, symbol):
        try:
            stock = yf.Ticker(symbol)
            data = stock.history(period="1d", interval="1m")
            if data.empty:
                return None
            price = float(data["Close"].iloc[-1])
            global_prices[symbol] = price
            return price
        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            return None

    def check_alert(self, stock_alert):
        price = self.get_stock_price(stock_alert.symbol)
        if price is None:
            return False
        stock_alert.last_price = price
        stock_alert.last_checked = datetime.now().isoformat()
        if stock_alert.alert_type == "above":
            return price >= stock_alert.target_price
        return price <= stock_alert.target_price

    def send_email_alert(self, stock_alert, price):
        if not self.email_config or not self.email_config.enabled:
            return
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config.sender_email
            msg['To'] = self.email_config.recipient_email
            msg['Subject'] = f"Stock Alert: {stock_alert.symbol}"
            body = f"Stock Price Alert Triggered!\n\nSymbol: {stock_alert.symbol}\nCurrent Price: {price:.2f}\nTarget Price: {stock_alert.target_price:.2f}\nAlert Type: {stock_alert.alert_type}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            msg.attach(MIMEText(body, 'plain'))
            server = smtplib.SMTP(self.email_config.smtp_server, self.email_config.smtp_port)
            server.starttls()
            server.login(self.email_config.sender_email, self.email_config.sender_password)
            server.send_message(msg)
            server.quit()
            print(f"Email alert sent for {stock_alert.symbol}")
        except Exception as e:
            print(f"Error sending email: {e}")

    def send_telegram_alert(self, stock_alert, price):
        if not self.telegram_config or not self.telegram_config.enabled:
            return
        if not self.telegram_config.bot_token or not self.telegram_config.chat_id:
            return
        try:
            direction_symbol = "≥" if stock_alert.alert_type == "above" else "≤"
            message = (f"Stock Price Alert Triggered!\n\nSymbol: {stock_alert.symbol}\nCurrent Price: {price:.2f}\nTarget: {direction_symbol} {stock_alert.target_price:.2f}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            url = f"https://api.telegram.org/bot{self.telegram_config.bot_token}/sendMessage"
            payload = urllib.parse.urlencode({"chat_id": self.telegram_config.chat_id, "text": message}).encode("utf-8")
            request = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.getcode() == 200:
                    print(f"Telegram alert sent for {stock_alert.symbol}")
        except Exception as e:
            print(f"Error sending Telegram alert: {e}")

    def process_alerts(self):
        # Reload to capture any UI changes to config
        self.load_config()
        
        current_keys = {f"{s.symbol}|{s.alert_type}|{s.target_price}" for s in self.stocks}
        stale_keys = [k for k in self.alert_states.keys() if k not in current_keys]
        for k in stale_keys:
            del self.alert_states[k]

        for stock_alert in self.stocks:
            condition_met = self.check_alert(stock_alert)
            state_key = f"{stock_alert.symbol}|{stock_alert.alert_type}|{stock_alert.target_price}"
            was_condition_met = self.alert_states.get(state_key, False)

            if condition_met:
                price = stock_alert.last_price
                if not was_condition_met:
                    print(f"✅ ALERT: {stock_alert.symbol} = {price:.2f} (Target: {stock_alert.target_price:.2f})")
                    self.send_email_alert(stock_alert, price)
                    self.send_telegram_alert(stock_alert, price)
                self.alert_states[state_key] = True
            else:
                self.alert_states[state_key] = False

# Background Worker Thread
def background_monitor():
    monitor = StockPriceMonitor(config_file)
    while True:
        monitor.process_alerts()
        time.sleep(monitor.check_interval)

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    if not os.path.exists(config_file):
        return jsonify({"stocks": [], "prices": {}, "alert_states": {}})
    with open(config_file, 'r') as f:
        config = json.load(f)
    return jsonify({
        "stocks": config.get("stocks", []),
        "prices": global_prices,
        "alert_states": global_alert_states
    })

@app.route('/api/add', methods=['POST'])
def add_stock():
    data = request.json
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    if "stocks" not in config:
        config["stocks"] = []
        
    config["stocks"].append({
        "symbol": data["symbol"],
        "target_price": data["target_price"],
        "alert_type": data["alert_type"]
    })
    
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)
        
    return jsonify({"success": True})

@app.route('/api/remove/<int:idx>', methods=['POST'])
def remove_stock(idx):
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    if "stocks" in config and 0 <= idx < len(config["stocks"]):
        config["stocks"].pop(idx)
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
            
    return jsonify({"success": True})

if __name__ == "__main__":
    t = threading.Thread(target=background_monitor, daemon=True)
    t.start()
    print("🚀 Background monitoring started. Opening Web interface...")
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5000)
