import os
import time
import threading
from playwright.sync_api import sync_playwright

def run_server():
    import http.server
    import socketserver
    os.chdir("static")
    handler = http.server.SimpleHTTPRequestHandler
    httpd = socketserver.TCPServer(("", 8123), handler)
    print("Serving at port 8123")
    httpd.serve_forever()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    time.sleep(2)  # Give server time to start

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", args=["--no-sandbox", "--disable-setuid-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
            page.goto("http://localhost:8123/preview.html")
            page.wait_for_timeout(2500) # Wait for transitions
            page.screenshot(path="ghazali-preview.png")
            browser.close()
            print("Screenshot saved to ghazali-preview.png")
    except Exception as e:
        print("Error capturing screenshot:", e)
