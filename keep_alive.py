import time
from playwright.sync_api import sync_playwright

def wake_up_apps():
    apps = [
        "https://vendler.streamlit.app",
        "https://albura.streamlit.app"                   
    ]
    
    with sync_playwright() as p:
        # Abrimos un navegador real (Chromium)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0")
        page = context.new_page()
        
        for url in apps:
            try:
                print(f"Visitando: {url}")
                # Vamos a la página y esperamos a que cargue el JavaScript
                page.goto(url, wait_until="networkidle", timeout=60000)
                # Esperamos 15 segundos para que la conexión WebSocket se estabilice
                time.sleep(15) 
                print(f"Éxito: {url} está despierta.")
            except Exception as e:
                print(f"Error visitando {url}: {e}")
        
        browser.close()

if __name__ == "__main__":
    wake_up_apps()
