import tkinter as tk
from interface.styling import *
import time

class UIPopupHelper:
    """Shared popup window for displaying trade or token details."""

    @staticmethod
    def show_detail_popup(title: str, headers: list[str], values: list[str], token_mint: str = None, master=None):
        top = tk.Toplevel(master)
        top.title(title)
        top.configure(bg=BG_COLOR)
        top.wm_attributes("-alpha", 0.0)  # start transparent for fade-in

        # === Fixed Size ===
        FIXED_WIDTH = 420
        FIXED_HEIGHT = 360
        top.minsize(FIXED_WIDTH, FIXED_HEIGHT)
        top.maxsize(FIXED_WIDTH, FIXED_HEIGHT)
        top.resizable(False, False)

        # === Title ===
        tk.Label(
            top,
            text=title,
            fg=TITLE_FG,
            bg=BG_COLOR,
            font=GLOBAL_FONT2,
        ).pack(padx=10, pady=(10, 5))

        # === Token Address (single display) ===
        if token_mint:
            tk.Label(
                top,
                text=token_mint,
                fg=FG_COLOR_STEEL_BLUE,
                bg=BG_COLOR,
                font=("Consolas", 10),
                wraplength=380,
                justify="left"
            ).pack(padx=10, pady=(0, 5), anchor="w")

        # === Separator ===
        tk.Frame(top, bg=BG_COLOR_2, height=2).pack(fill="x", padx=10, pady=(0, 5))

        # === Details Table ===
        frame = tk.Frame(top, bg=BG_COLOR)
        frame.pack(padx=15, pady=5, anchor="w")

        for h, v in zip(headers, values):
            # Skip duplicate Token Address line
            if "Token Address" in h:
                continue

            color = FG_COLOR_WHITE
            if "PnL" in h and "%" in str(v):
                try:
                    val = float(v.replace("%", ""))
                    color = "#2ecc71" if val >= 0 else "#e74c3c"
                except:
                    pass

            row = tk.Frame(frame, bg=BG_COLOR)
            row.pack(anchor="w", pady=1)

            tk.Label(
                row, text=f"{h}:", fg=FG_COLOR_STEEL_BLUE, bg=BG_COLOR, font=GLOBAL_FONT, width=16, anchor="w"
            ).pack(side="left")
            tk.Label(
                row, text=v, fg=color, bg=BG_COLOR, font=GLOBAL_FONT, anchor="w"
            ).pack(side="left")

        # === Separator ===
        tk.Frame(top, bg=BG_COLOR_2, height=2).pack(fill="x", padx=10, pady=(8, 5))

        # === Buttons ===
        btn_frame = tk.Frame(top, bg=BG_COLOR)
        btn_frame.pack(pady=(0, 10))

        if token_mint:
            def copy_address():
                top.clipboard_clear()
                top.clipboard_append(token_mint)
                top.title("✅ Copied to clipboard")

            tk.Button(
                btn_frame,
                text="📋 Copy Address",
                bg=BTN_COLOR,
                fg=FG_COLOR_WHITE,
                activebackground="#2a2a2a",
                relief="flat",
                font=GLOBAL_FONT,
                command=copy_address,
                width=15,
            ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="Close",
            bg=STOP_BTN_COLOR,
            fg=FG_COLOR_WHITE,
            activebackground="#2a2a2a",
            relief="flat",
            font=GLOBAL_FONT,
            command=top.destroy,
            width=10,
        ).pack(side="left", padx=5)

        # === Center Popup ===
        top.update_idletasks()
        if master:
            master_x = master.winfo_rootx()
            master_y = master.winfo_rooty()
            master_w = master.winfo_width()
            master_h = master.winfo_height()
            x = master_x + (master_w - FIXED_WIDTH) // 2
            y = master_y + (master_h - FIXED_HEIGHT) // 2
            top.geometry(f"{FIXED_WIDTH}x{FIXED_HEIGHT}+{x}+{y}")

        # === Fade-in Animation ===
        def fade_in(step=0.05):
            alpha = top.attributes("-alpha")
            if alpha < 1.0:
                alpha = min(alpha + step, 1.0)
                top.attributes("-alpha", alpha)
                top.after(20, fade_in)
        fade_in()
