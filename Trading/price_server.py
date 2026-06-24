"""
한국주식 실시간 시세 로컬 서버.
KIS OpenAPI를 통해 현재가를 조회하고 index.html에 JSON으로 제공한다.

실행:  python price_server.py
접속:  http://localhost:8765/api/prices?codes=005930,000660
"""
import json
import time
import sys
import io
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import kis_api

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)

PORT      = 8765
CACHE_TTL = 30       # 초 — 동일 종목 30초 이내 재요청은 캐시 반환
_cache: dict = {}


def _fetch(code: str) -> dict | None:
    try:
        return kis_api.get_current_price(code)
    except Exception as e:
        print(f"[price_server] {code} 조회 실패: {e}")
        return None


class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # ── ping ──────────────────────────────────
        if parsed.path == '/api/ping':
            self._json({"ok": True})
            return

        # ── prices ────────────────────────────────
        if parsed.path != '/api/prices':
            self.send_error(404)
            return

        raw = params.get('codes', [''])[0]
        codes = [c.strip() for c in raw.split(',') if c.strip()]
        result = {}
        now = time.time()

        for code in codes:
            cached = _cache.get(code)
            if cached and now - cached.get('_ts', 0) < CACHE_TTL:
                result[code] = {k: v for k, v in cached.items() if k != '_ts'}
            else:
                data = _fetch(code)
                if data:
                    data['_ts'] = now
                    _cache[code] = data
                    result[code] = {k: v for k, v in data.items() if k != '_ts'}
                else:
                    result[code] = None

        self._json(result)

    # ── helpers ───────────────────────────────────

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, *args):
        pass   # HTTP 접속 로그 숨김


if __name__ == '__main__':
    print("[price_server] KIS 토큰 초기화 중...")
    kis_api.init_token()
    server = HTTPServer(('localhost', PORT), Handler)
    print(f"[price_server] 서버 시작 ─ http://localhost:{PORT}")
    print(f"[price_server] index.html에서 자동 감지됩니다. Ctrl+C 로 종료.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[price_server] 종료")
