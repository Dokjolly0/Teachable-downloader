from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader


def ask_input_modal(
    self: "TeachableDownloader",
    title="Enter your name:",
    placeholder="Digit here the pin...",
    confirm_button_name="Confirm",
):
    escaped_message = title.replace("'", "\\'")

    javascript_code = f"""
    (function(){{
        // 1. Prevents the recreation of the modal
        if (document.getElementById('__selenium_overlay')) return;

        // 2. Creates the overlay (for the dark background)
        const overlay = document.createElement('div');
        overlay.id = '__selenium_overlay';
        overlay.style.cssText = 'position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); z-index:9999998;';
        document.body.appendChild(overlay);

        // 3. Creates the modal container
        const modal = document.createElement('div');
        modal.id = '__selenium_modal';
        modal.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #ffffff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
            z-index: 9999999;
            width: 90%;
            max-width: 400px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
        `;

        // 4. Inserts the improved HTML content
        modal.innerHTML = `
            <p style="font-size: 18px; color: #333; margin-bottom: 20px; font-weight: 500;">{escaped_message}</p>
            <input id="__selenium_input" type="text" placeholder="{placeholder}" style="
                padding: 10px;
                font-size: 16px;
                width: calc(100% - 20px);
                margin-bottom: 20px;
                border: 1px solid #ccc;
                border-radius: 4px;
                box-sizing: content-box;
                transition: border-color 0.3s;
            " onfocus="this.style.borderColor='#007bff';" onblur="this.style.borderColor='#ccc';">
            <button id="__selenium_ok" style="
                padding: 10px 20px;
                font-size: 16px;
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                transition: background-color 0.3s;
                float: right;
            " onmouseover="this.style.backgroundColor='#0056b3';" onmouseout="this.style.backgroundColor='#007bff';">
                {confirm_button_name}
            </button>
            <div style="clear: both;"></div> `;
        document.body.appendChild(modal);

        // 5. Event management (removal of modal and saving of input)
        const okButton = document.getElementById('__selenium_ok');
        const inputField = document.getElementById('__selenium_input');

        const handleInput = () => {{
            window.userInput = inputField.value;
            modal.remove();
            overlay.remove();
        }};

        okButton.onclick = handleInput;

        // Allow submission by pressing Enter in the input field
        inputField.addEventListener('keypress', function (e) {{
            if (e.key === 'Enter') {{
                handleInput();
            }}
        }});

        // Focus automatico sul campo di input
        inputField.focus();

    }})();
    """
    self.driver.execute_script(javascript_code)

    while True:
        val = self.driver.execute_script(
            "return window.userInput !== undefined ? window.userInput : null;"
        )
        if val is not None:
            # Rimuovi la variabile temporanea dopo l'uso
            self.driver.execute_script("delete window.userInput;")
            return val
        time.sleep(0.2)


# Usage:
# self.driver.get("https://www.example.com")
# name = ask_input_modal(self, "Enter your name")
# print(f"Hello, {name}!")
