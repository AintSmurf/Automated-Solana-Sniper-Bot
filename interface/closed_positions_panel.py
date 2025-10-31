import tkinter as tk
from tkinter import ttk
from interface.styling import *
from interface.ui_popup_helper import UIPopupHelper


class ClosedPositionsPanel(tk.Frame):
    def __init__(self, parent, ctx, **kwargs):
        super().__init__(parent, **kwargs)
        self.ctx = ctx
        self.settings = ctx.settings
        
        
        kwargs.setdefault("bg", BG_COLOR)

        style = ttk.Style()
        style.theme_use("default")

        style.configure("Custom.Treeview",
                        background=BG_COLOR,
                        fieldbackground=BG_COLOR,
                        foreground=FG_COLOR_WHITE,
                        rowheight=24,
                        font=GLOBAL_FONT)

        style.configure("Custom.Treeview.Heading",
                        background=BG_COLOR_2,
                        foreground=FG_COLOR_WHITE,
                        font=("Calibri", 11, "bold"))

        style.map("Custom.Treeview.Heading",
                background=[("active", BG_COLOR_2), ("pressed", BG_COLOR_2)],
                foreground=[("active", FG_COLOR_WHITE), ("pressed", FG_COLOR_WHITE)])

        self.columns = ["Buy_Timestamp","Sell_Timestamp", "Token Address","Entry_USD", "Exit_USD", "PnL (%)", "Trigger"]
        self.tree = ttk.Treeview(self, columns=self.columns, show="headings", style="Custom.Treeview")

        for col in self.columns:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_by(c, False))
            self.tree.column(col, anchor="center", width=120)

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self._on_double_click)


        self._sort_descending = {}

    def update_table(self, data):
        rows = data if (isinstance(data, list) and data and isinstance(data[0], (list, tuple))) else [data]
        self.tree.delete(*self.tree.get_children())
        self.tree.tag_configure("profit", foreground="lightgreen")
        self.tree.tag_configure("loss", foreground="red")

        for row in rows:
            try:
                entry_usd = float(row[3]) if row[3] is not None else 0.0
            except (ValueError, TypeError):
                entry_usd = 0.0

            try:
                exit_usd = float(row[4]) if row[4] is not None else 0.0
            except (ValueError, TypeError):
                exit_usd = 0.0

            try:
                pnl_value = float(row[5]) if row[5] is not None else 0.0
            except (ValueError, TypeError):
                pnl_value = 0.0

            tag = "profit" if pnl_value >= 0 else "loss"

            pnl_display = f"{pnl_value:.2f}%" if row[5] is not None else "—"

            self.tree.insert(
                "",
                "end",
                values=(
                    row[1] or "",         # buy_signature
                    row[2] or "",         # sell_signature
                    row[0] or "",         # id / token address
                    f"{entry_usd:.6f}",
                    f"{exit_usd:.6f}",
                    pnl_display,
                    row[6] or "",         # trigger_reason
                ),
                tags=(tag,)
            )

    def sort_by(self, col, descending):
        """Sort tree contents when a column header is clicked."""
        data = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]

        # try to parse numbers (esp for PnL, Entry, Exit)
        def convert(val):
            try:
                return float(val.replace("%", ""))  # handle % column
            except:
                return val

        data = [(convert(v), k) for v, k in data]

        # sort
        data.sort(reverse=descending)

        # rearrange items in sorted positions
        for idx, (val, k) in enumerate(data):
            self.tree.move(k, '', idx)

        # flip sort order for next click
        self._sort_descending[col] = not descending
        self.tree.heading(col, command=lambda c=col: self.sort_by(c, self._sort_descending[col]))

    def refresh(self):
        try:
            df = self.ctx.get("token_dao").get_closed_poisitons()
            self.update_table(df)
        except Exception as e:
            print(f"⚠️ Failed to refresh closed positions: {e}")

    def _on_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        values = self.tree.item(item_id, "values")
        headers = self.columns
        token_address = values[2] if len(values) > 2 else None

        UIPopupHelper.show_detail_popup("💹 Closed Trade Details", headers, values, token_address, master=self)

