import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def attach_to_browser():
    with open("browser_endpoint.txt", "r") as file:
        debug_port = file.read().strip()

    chrome_options = Options()
    chrome_options.debugger_address = debug_port

    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://dexscreener.com/page-2")

    print("Attached to Puppeteer-launched browser!")
    input("Press Enter to exit...")
    driver.quit()


if __name__ == "__main__":
    attach_to_browser()
