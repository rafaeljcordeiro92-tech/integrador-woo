from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import json
import time

URL = "https://portal.juntossomosimbativeis.com.br"

options = Options()
options.add_argument("--start-maximized")

driver = webdriver.Chrome(options=options)

driver.get(URL)

print("🔐 FAÇA LOGIN MANUALMENTE...")
time.sleep(60)  # tempo pra você logar

cookies = driver.get_cookies()

with open("cookies.json", "w") as f:
    json.dump(cookies, f, indent=2)

print("✅ cookies salvos!")

driver.quit()