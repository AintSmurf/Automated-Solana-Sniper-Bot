import tkinter as tk
from interface.logging_panel import LoggingPanel
from interface.closed_positions_panel import ClosedPositionsPanel
from interface.realtime_stats_panel import RealTimeStatsPanel
from interface.styling import *
from helpers.trade_counter import TradeCounter
from helpers.logging_manager import LoggingHandler
from interface.ui_log_hanlder import UILogHandler
from utilities.excel_utility import ExcelUtility
from config.settings import load_settings
from helpers.bot_orchestrator import BotOrchestrator
from datetime import datetime
import threading
from interface.settings_window import SettingsConfigUI






class SniperBotUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.title("Solana Sniper Bot")
        self.configure(bg=BG_COLOR)
        self.geometry("1100x700")
        self.excel_utility = ExcelUtility()
        self.settings = load_settings()
        self.orchestrator: BotOrchestrator | None = None

        #start loop
        self.after_id = self.after(5000, self.refresh_stats)

        # === Master Layout ===
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=3)  # left area
        self.grid_columnconfigure(1, weight=1)  # right sidebar

        # === LEFT SIDE ===
        left_frame = tk.Frame(self, bg=BG_COLOR)
        left_frame.grid(row=0, column=0, sticky="nsew")

        # Split left into top (logs) + bottom (closed positions)
        left_frame.grid_rowconfigure(0, weight=2)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # Live Tracking (LabelFrame + LoggingPanel as Treeview)
        live_frame = tk.LabelFrame(
            left_frame, text=" Live Tracking Panel",
            font=("Arial", 12, "bold"), fg="cyan", bg=BG_COLOR, labelanchor="nw"
        )
        live_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self._logging_frame = LoggingPanel(live_frame,bg=BG_COLOR,   close_trade_callback=self.close_trade)
        self._logging_frame.pack(fill="both", expand=True)
        #pull messages
        ui_log_handler = UILogHandler(self._logging_frame)
        tracker_logger = LoggingHandler.get_named_logger("tracker")
        tracker_logger.addHandler(ui_log_handler)

        # Closed Positions (LabelFrame + ClosedPositionsPanel)
        closed_frame = tk.LabelFrame(
            left_frame, text="Closed Positions",
            font=("Arial", 12, "bold"), fg="cyan", bg=BG_COLOR, labelanchor="nw"
        )
        closed_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.closed_positions = ClosedPositionsPanel(closed_frame, excel_utility=self.excel_utility, bg=BG_COLOR)
        self.closed_positions.pack(fill="both", expand=True)


        # Adjust row weights so top grows more
        left_frame.grid_rowconfigure(1, weight=2)  # Live tracking grows
        left_frame.grid_rowconfigure(3, weight=1)  # Closed positions smaller
        
        #=== Right SIDE ===
        self.right_frame = tk.Frame(self, bg=BG_COLOR)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self._build_sidebar()
      
    def start_bot_ui(self):
        trade_counter = TradeCounter(self.settings["MAXIMUM_TRADES"])
        self.orchestrator = BotOrchestrator(trade_counter, self.settings)
        self.orchestrator.start()

        # Keep reference for later updates
        self.trade_counter = trade_counter  

        # Update Total Trades immediately
        self.update_total_trades()

        # Update UI
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="🟢 Bot Status: Running", fg="green")

    def stop_bot_ui(self):
        if self.orchestrator:
            threading.Thread(target=self.orchestrator.shutdown, daemon=True).start()
            self.orchestrator = None

        # Cancel scheduled refresh until bot restarts
        self.safe_after_cancel()
        self.after_id = self.after(5000, self.refresh_stats)  # restart clean loop

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="🔴 Bot Status: Stopped", fg="red")

    def update_wallet_balance(self):
        """Fetch balances and update wallet label."""
        try:
            balances = self.orchestrator.tracker.solana_manager.get_account_balances()

            sol_balance = 0.0
            usdc_balance = 0.0

            for entry in balances:
                if entry["token_mint"] == "SOL":
                    sol_balance = entry["balance"]
                elif entry["token_mint"].startswith("EPjFWdd5Auf"):  # USDC mint
                    usdc_balance = entry["balance"]

            self.wallet_label.config(
                text=f"{sol_balance:.2f} SOL | ${usdc_balance:.2f} USDC"
            )

        except Exception as e:
            print(f"Wallet update failed: {e}")

    def update_api_calls(self):
        stats = self.orchestrator.get_api_stats()
        self.helius_label.config(text=f"Helius: {stats['helius']['total_requests']}")
        self.jupiter_label.config(text=f"Jupiter: {stats['jupiter']['total_requests']}")

    def update_total_trades(self):
        """Update Total Trades count in the sidebar"""
        if hasattr(self, "trade_counter"):
            count = self.trade_counter.get_trades_count()
            self.total_trades_label.config(text=f"Total Trades: {count}")

    def refresh_stats(self):
        """Auto-refresh stats every 5 seconds."""
        if not hasattr(self, "_refreshing") or not self._refreshing:
            self._refreshing = True
            threading.Thread(target=self._refresh_stats_worker, daemon=True).start()
        
        # run again every 5 sec
        self.after_id = self.after(5000, self.refresh_stats)
    
    def _refresh_stats_worker(self):
        try:
            if not self.orchestrator:
                # Bot not running → placeholders
                balances = [
                    {"token_mint": "SOL", "balance": 0.0},
                    {"token_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "balance": 0.0}
                ]
                stats = {"helius": {"total_requests": 0}, "jupiter": {"total_requests": 0}}
                trades = 0
            else:
                balances = self.orchestrator.tracker.solana_manager.get_account_balances()
                stats = self.orchestrator.get_api_stats()
                trades = self.trade_counter.get_trades_count() if hasattr(self, "trade_counter") else 0

            self.after(0, lambda: self._update_stats_ui(balances, stats, trades))

        except Exception as e:
            print(f"⚠️ Stats worker failed: {e}")
            # fallback placeholders
            self.after(0, lambda: self._update_stats_ui([], {"helius": {"total_requests": 0}, "jupiter": {"total_requests": 0}}, 0))
        finally:
            self._refreshing = False

    def _update_stats_ui(self, balances, stats, trades):
        sol_balance = 0.0
        usdc_balance = 0.0
        for entry in balances:
            mint = entry.get("token_mint")
            if mint == "SOL":
                sol_balance = entry["balance"]
            elif mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":  # USDC
                usdc_balance = entry["balance"]

        self.wallet_label.config(text=f"{sol_balance:.2f} SOL | ${usdc_balance:.2f} USDC")
        self.helius_label.config(text=f"Helius: {stats.get('helius', {}).get('total_requests', 0)}")
        self.jupiter_label.config(text=f"Jupiter: {stats.get('jupiter', {}).get('total_requests', 0)}")
        self.total_trades_label.config(text=f"Total Trades: {trades}")
        self.last_update_label.config(text=f"Last update: {datetime.now():%H:%M:%S}")

    def manual_refresh(self):
        """Manual refresh button → refresh closed positions only."""
        try:
            self.closed_positions.refresh()
        except Exception as e:
            print(f"⚠️ Manual refresh failed: {e}")
    
    def open_settings(self):
        config_window = SettingsConfigUI(self, on_save=self.refresh_ui_from_settings)
        config_window.grab_set()

    def safe_after_cancel(self):
        """Cancel scheduled after() loops safely."""
        if hasattr(self, "after_id") and self.after_id:
            try:
                self.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def on_close(self):
        # cancel LoggingPanel loop
        if hasattr(self, "_logging_frame"):
            self._logging_frame.stop_polling()
        
        """Called when the window is closed."""
        self.safe_after_cancel()
        if self.orchestrator:
            try:
                self.orchestrator.shutdown()
            except Exception:
                pass
        self.destroy()
    
    def refresh_ui_from_settings(self):
        """Reload settings and refresh only dynamic sections."""
        self.settings = load_settings()

        helius_val = getattr(self, "helius_label", None).cget("text") if hasattr(self, "helius_label") else "Helius: 0"
        jupiter_val = getattr(self, "jupiter_label", None).cget("text") if hasattr(self, "jupiter_label") else "Jupiter: 0"
        trades_val = getattr(self, "total_trades_label", None).cget("text") if hasattr(self, "total_trades_label") else "Total Trades: 0"

        # Clear widgets inside each dynamic frame
        for frame in (self.api_frame, self.settings_frame, self.exit_rules_frame, self.notify_frame):
            for widget in frame.winfo_children():
                widget.destroy()

        # Rebuild them
        self._build_dynamic_sidebar(helius_val, jupiter_val, trades_val)

    def _build_sidebar(self):
        """Build static + dynamic sidebar sections (called once at init)."""
        # clear old sidebar widgets
        for widget in self.right_frame.winfo_children():
            widget.destroy()

        self.right_frame.grid_rowconfigure(99, weight=1)

        # last update
        self.last_update_label = tk.Label(
            self.right_frame, text="Last update: --", bg=BG_COLOR, fg="gray"
        )
        self.last_update_label.pack(fill="x", pady=5)

        # Bot Status
        self.status_label = tk.Label(
            self.right_frame,
            text="🟡 Bot Status: Idle",
            font=("Arial", 12, "bold"),
            bg=BG_COLOR,
            fg="orange",
        )
        self.status_label.pack(fill="x", pady=(0, 10))

        # Total Trades
        self.total_trades_label = tk.Label(
            self.right_frame,
            text="Total Trades: 0",
            font=("Arial", 11, "bold"),
            bg=BG_COLOR,
            fg="white",
        )
        self.total_trades_label.pack(fill="x", pady=(0, 10))

        # Wallet (static)
        wallet_frame = tk.LabelFrame(self.right_frame, text="💰 Wallet Balance", bg=BG_COLOR, fg="white")
        wallet_frame.pack(fill="x", pady=5)
        self.wallet_label = tk.Label(wallet_frame, text="SOL: -- | USDC: --", font=("Arial", 10, "bold"),
                                    bg=BG_COLOR, fg="cyan")
        self.wallet_label.pack(anchor="w", padx=10, pady=2)

        # === Dynamic sections (saved refs so we can rebuild) ===
        self.api_frame = tk.LabelFrame(self.right_frame, text="🌐 API Usage", bg=BG_COLOR, fg="white")
        self.api_frame.pack(fill="x", pady=5)

        self.settings_frame = tk.LabelFrame(self.right_frame, text="⚙️ Settings", bg=BG_COLOR, fg="white")
        self.settings_frame.pack(fill="x", pady=5)

        self.exit_rules_frame = tk.LabelFrame(self.right_frame, text="🚪 Exit Rules", bg=BG_COLOR, fg="white")
        self.exit_rules_frame.pack(fill="x", pady=5)

        self.notify_frame = tk.LabelFrame(self.right_frame, text="🔔 Notifications", bg=BG_COLOR, fg="white")
        self.notify_frame.pack(fill="x", pady=5)

        # Build them first time
        self._build_dynamic_sidebar()

        # Controls (static)
        controls_frame = tk.Frame(self.right_frame, bg=BG_COLOR)
        controls_frame.pack(fill="x", pady=10)

        # Row 1 (Start + Stop)
        row1 = tk.Frame(controls_frame, bg=BG_COLOR)
        row1.pack(fill="x", pady=2)
        self.start_button = tk.Button(
            row1, text="▶ Start Bot", bg="#2ecc71", fg="white",
            font=("Arial", 12, "bold"), relief=tk.RAISED, command=self.start_bot_ui
        )
        self.start_button.pack(side="left", expand=True, fill="x", padx=5)
        self.stop_button = tk.Button(
            row1, text="⏹ Stop Bot", bg="#e74c3c", fg="white",
            font=("Arial", 12, "bold"), relief=tk.RAISED, command=self.stop_bot_ui, state=tk.DISABLED
        )
        self.stop_button.pack(side="left", expand=True, fill="x", padx=5)

        # Row 2 (Refresh + Settings)
        row2 = tk.Frame(controls_frame, bg=BG_COLOR)
        row2.pack(fill="x", pady=2)
        self.refresh_button = tk.Button(
            row2, text="🔄 Refresh", bg="#3498db", fg="white",
            font=("Arial", 12, "bold"), relief=tk.RAISED, command=self.manual_refresh
        )
        self.refresh_button.pack(side="left", expand=True, fill="x", padx=5)

        self.settings_button = tk.Button(
            row2, text="⚙ Settings", bg="#9b59b6", fg="white",
            font=("Arial", 12, "bold"), relief=tk.RAISED, command=self.open_settings
        )
        self.settings_button.pack(side="left", expand=True, fill="x", padx=5)

    def _build_dynamic_sidebar(self, helius_val="Helius: 0", jupiter_val="Jupiter: 0", trades_val="Total Trades: 0"):
        """Builds/rebuilds only the dynamic sections (API, Settings, Exit Rules, Notifications)."""

        # API Usage (use preserved values)
        self.helius_label = tk.Label(self.api_frame, text=helius_val, bg=BG_COLOR, fg="lightblue")
        self.helius_label.pack(anchor="w", padx=10, pady=2)

        self.jupiter_label = tk.Label(self.api_frame, text=jupiter_val, bg=BG_COLOR, fg="lightgreen")
        self.jupiter_label.pack(anchor="w", padx=10, pady=2)

        # Settings
        rows = {
            "Mode": "SIM" if self.settings["SIM_MODE"] else "REAL",
            "SLIPPAGE":f"{self.settings['SLPG']}",
            "TP": f"{self.settings['TP']}",
            "SL": self.settings["SL"],
            "TSL": self.settings["TRAILING_STOP"],
            "Timeout": f"{self.settings['TIMEOUT_SECONDS']}",
        }
        for k, v in rows.items():
            row = tk.Frame(self.settings_frame, bg=BG_COLOR)
            row.pack(fill="x", padx=5, pady=1)
            tk.Label(row, text=f"{k}:", fg="white", bg=BG_COLOR).pack(side="left")
            tk.Label(row, text=v, fg="cyan", bg=BG_COLOR).pack(side="right")

        # Exit Rules
        for rule, enabled in self.settings["EXIT_RULES"].items():
            lbl = tk.Label(
                self.exit_rules_frame,
                text=f"{rule}",
                fg="white",
                bg="green" if enabled else "red"
            )
            lbl.pack(fill="x", padx=5, pady=2)

        # Notifications
        for service, enabled in self.settings["NOTIFY"].items():
            if isinstance(enabled, bool) and enabled:
                lbl = tk.Label(self.notify_frame, text=f"{service}", bg="green", fg="white", font=("Arial", 9, "bold"))
                lbl.pack(fill="x", padx=5, pady=2)

        # Rebuild trades count label too
        self.total_trades_label.config(text=trades_val)

    def close_trade(self, token_mint):
        if self.orchestrator:
            try:
                self.orchestrator.close_trade(token_mint)
                self._logging_frame.add_log({
                    "token_mint": token_mint,
                    "event": "sell"
                })
            except Exception as e:
                print(f"⚠️ Failed to close trade: {e}")
