import time

from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException
from selenium.webdriver.chrome.options import Options


def ask_input_via_prompt(driver, message="Inserisci il tuo nome:"):
    # Send the prompt command to the browser
    driver.execute_script(f"window.userInput = prompt({repr(message)});")
    # Wait for the alert to appear (might be instantaneous)
    # Now block until the alert is present; the user must type and press OK
    while True:
        try:
            # If the alert is still present, sleep and retry
            _ = driver.switch_to.alert
            time.sleep(0.2)  # brief sleep to avoid busy-looping
            continue
        except NoAlertPresentException:
            break

    # At the end (the user has closed the prompt) retrieve the value
    nome = driver.execute_script("return window.userInput;")
    return nome


# Example usage
def test():
    options = Options()
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-notifications")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.get("https://example.com")
    print("Apparirà un prompt nel browser: digita qualcosa e premi OK.")
    nome = ask_input_via_prompt(driver, "Inserisci il tuo nome:")
    print("Hai inserito:", nome)
    driver.quit()
