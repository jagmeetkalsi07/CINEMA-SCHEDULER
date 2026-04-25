import sys
import os
import shutil
import subprocess
import threading
import socket
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler


import json

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress server logs

    def do_POST(self):
        if self.path == '/api/send-email':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            try:
                # Use powershell to interact with Outlook COM object to send email
                to = data.get('to', '')
                cc = data.get('cc', '')
                bcc = data.get('bcc', '')
                subject = data.get('subject', '')
                body = data.get('body', '')

                # Escape single quotes and dollar signs for powershell
                escaped_body = body.replace("'", "''").replace("$", "`$")
                escaped_subject = subject.replace("'", "''").replace("$", "`$")
                
                ps_script = f"""
                $Outlook = New-Object -ComObject Outlook.Application
                $Mail = $Outlook.CreateItem(0)
                $Mail.To = '{to}'
                $Mail.CC = '{cc}'
                $Mail.BCC = '{bcc}'
                $Mail.Subject = '{escaped_subject}'
                $Mail.HTMLBody = '{escaped_body}'
                $Mail.Send()
                """
                
                subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
        else:
            self.send_error(404, "Endpoint not found")


def get_fixed_port():
    return 49213


def get_html_path():
    app_data = os.path.join(os.environ.get('APPDATA', ''), 'ShowtimeManager')
    html_path = os.path.join(app_data, 'index.html')

    if not os.path.exists(app_data):
        os.makedirs(app_data)

    # Always copy the bundled HTML to AppData (ensures latest version)
    if hasattr(sys, '_MEIPASS'):
        source = os.path.join(sys._MEIPASS, 'Showtime-Manager-v29.html')
    else:
        source = os.path.join(os.path.dirname(__file__), 'Showtime-Manager-v29.html')

    shutil.copy2(source, html_path)
    return app_data


def main():
    app_data = get_html_path()
    port = get_fixed_port()

    os.chdir(app_data)

    try:
        server = HTTPServer(('127.0.0.1', port), QuietHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
    except OSError:
        # Port is already in use, which means the python backend is already running
        # in the background from a previous launch. We can just reuse it!
        pass

    url = f'http://127.0.0.1:{port}/index.html'

    # Try to launch in Chrome/Edge app mode for a native feel
    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    chrome_x86_path = r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
    edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

    browser = None
    for path in [chrome_path, chrome_x86_path, edge_path]:
        if os.path.exists(path):
            browser = path
            break

    try:
        if browser:
            profile_dir = os.path.join(app_data, "BrowserProfile")
            process = subprocess.Popen(
                [browser, f'--app={url}', f'--user-data-dir={profile_dir}', '--no-first-run', '--disable-sync'],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            process.wait()
            # If the process exited quickly, it likely handed off to an existing Chrome background instance.
            # We must keep the server thread alive so the backend doesn't mysteriously crash on 127.0.0.1.
            import time
            time.sleep(3) # ensure handoff succeeds
            while True:
                time.sleep(3600)
        else:
            os.startfile(url)
            while True:
                time.sleep(3600)  # Keep server alive
    except Exception as e:
        # Write crash log
        f = open(os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop', 'SM_CrashLog.txt'), 'w')
        f.write(str(e))
        f.close()


if __name__ == '__main__':
    main()
