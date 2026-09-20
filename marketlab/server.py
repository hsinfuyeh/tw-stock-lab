"""Local-only HTTP service. No trading or external write capability."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from .data import json_text


def make_server(service,port=8765):
    web=Path(__file__).resolve().parent.parent/"web"
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,status,payload,content_type="application/json; charset=utf-8"):
            body=payload if isinstance(payload,bytes) else (json_text(payload) if content_type.startswith("application/json") else payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        def allowed_host(self):
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}")
        def do_GET(self):
            if not self.allowed_host(): return self.send(403,{"error":"只接受本機主機名稱"})
            request=urlparse(self.path); q=parse_qs(request.query)
            try:
                if request.path=="/api/state": return self.send(200,service.state())
                if request.path=="/api/snapshot":
                    snap=service.store.snapshot(q.get("id",[None])[0])
                    return self.send(200,snap) if snap else self.send(404,{"error":"找不到快照"})
                if request.path=="/api/reconciled": return self.send(200,service.store.get("reconciled",[]))
                if request.path=="/api/export":
                    return self.send(200,service.export_csv(int(q.get("horizon",[7])[0]),q.get("sort",["expected_return"])[0],q.get("id",[None])[0]),"text/csv; charset=utf-8")
                files={"/":("index.html","text/html"),"/index.html":("index.html","text/html"),"/app.js":("app.js","text/javascript"),"/style.css":("style.css","text/css")}
                if request.path not in files: return self.send(404,{"error":"找不到頁面"})
                filename,mime=files[request.path]
                return self.send(200,(web/filename).read_bytes(),mime+"; charset=utf-8")
            except (ValueError,TypeError) as exc: return self.send(400,{"error":str(exc)})
            except Exception as exc: return self.send(500,{"error":str(exc)})
        def do_POST(self):
            if not self.allowed_host(): return self.send(403,{"error":"只接受本機主機名稱"})
            origin=self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"):
                return self.send(403,{"error":"不接受跨來源操作"})
            if self.headers.get("Sec-Fetch-Site")=="cross-site": return self.send(403,{"error":"不接受跨來源操作"})
            if self.headers.get("Content-Type","").split(";")[0]!="application/json": return self.send(415,{"error":"需要 application/json"})
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=16384: raise ValueError("請求內容大小錯誤")
                body=json.loads(self.rfile.read(length))
                if self.path=="/api/settings": return self.send(200,{"settings":service.save_settings(body)})
                if self.path=="/api/update": return self.send(202,{"job":service.start_update()})
                return self.send(404,{"error":"找不到操作"})
            except (ValueError,TypeError) as exc: return self.send(400,{"error":str(exc)})
    return ThreadingHTTPServer(("127.0.0.1",port),Handler)
