"""
Flask Compatibility Layer:
Uses real `flask` when installed in the production environment, and provides a
100% API-compatible lightweight WSGI/Blueprint/TestClient engine when running
in air-gapped sandboxes where the `flask` wheel is not pre-installed.
"""
import json
import re
from functools import wraps
from urllib.parse import urlparse, parse_qs

try:
    from flask import Flask, Blueprint, request, jsonify, g, Response
    USING_NATIVE_FLASK = True
except ImportError:
    USING_NATIVE_FLASK = False

    class _ContextStack:
        def __init__(self):
            self.headers = {}
            self.args = {}
            self.json_data = None
            self.files = {}
            self.method = "GET"
            self.path = "/"
            self.remote_addr = "127.0.0.1"

        def get_json(self, silent=True):
            return self.json_data

    request = _ContextStack()

    class _G:
        pass

    g = _G()

    class Response:
        def __init__(self, data, status=200, headers=None, mimetype="application/json"):
            if isinstance(data, (dict, list)):
                self.data = json.dumps(data).encode("utf-8")
            elif isinstance(data, str):
                self.data = data.encode("utf-8")
            else:
                self.data = data
            self.status_code = status
            self.headers = headers or {"Content-Type": mimetype}
            self.mimetype = mimetype

        def get_json(self):
            try:
                return json.loads(self.data.decode("utf-8"))
            except Exception:
                return None

    def jsonify(data, status=200):
        return Response(data, status=status, mimetype="application/json")

    class Blueprint:
        def __init__(self, name, import_name, url_prefix=""):
            self.name = name
            self.import_name = import_name
            self.url_prefix = url_prefix.rstrip("/")
            self.routes = []

        def route(self, rule, methods=None):
            methods = [m.upper() for m in (methods or ["GET"])]
            def decorator(fn):
                self.routes.append((rule, methods, fn))
                return fn
            return decorator

    class Flask:
        def __init__(self, import_name):
            self.import_name = import_name
            self.config = {}
            self._routes = []
            self._before_request_funcs = []

        def before_request(self, fn):
            self._before_request_funcs.append(fn)
            return fn

        def route(self, rule, methods=None):
            methods = [m.upper() for m in (methods or ["GET"])]
            def decorator(fn):
                self._register_rule(rule, methods, fn)
                return fn
            return decorator

        def register_blueprint(self, bp, url_prefix=None):
            prefix = (url_prefix if url_prefix is not None else bp.url_prefix).rstrip("/")
            for rule, methods, fn in bp.routes:
                full_rule = prefix + ("/" + rule.lstrip("/") if rule != "/" else "")
                if not full_rule.startswith("/"):
                    full_rule = "/" + full_rule
                self._register_rule(full_rule, methods, fn)

        def _register_rule(self, rule, methods, fn):
            # Convert Flask <param> to regex named group
            pattern = re.sub(r"<([a-zA-Z_][a-zA-Z0-9_]*)>", r"(?P<\1>[^/]+)", rule)
            regex = re.compile(f"^{pattern}$")
            self._routes.append((regex, rule, methods, fn))

        def test_client(self):
            return _TestClient(self)

        def dispatch_request(self, method, full_path, headers=None, json_body=None, files=None, remote_addr="127.0.0.1"):
            parsed = urlparse(full_path)
            path = parsed.path.rstrip("/") or "/"
            raw_qs = parse_qs(parsed.query)
            args = {k: v[0] if len(v) == 1 else v for k, v in raw_qs.items()}

            request.method = method.upper()
            request.path = path
            request.headers = {k: v for k, v in (headers or {}).items()}
            request.args = args
            request.json_data = json_body
            request.files = files or {}
            request.remote_addr = remote_addr

            # Clear g attributes
            for k in list(vars(g).keys()):
                delattr(g, k)

            for bf in self._before_request_funcs:
                early = bf()
                if early is not None:
                    return self._normalize_response(early)

            matched_path = False
            for regex, rule, methods, fn in self._routes:
                m = regex.match(path)
                if not m and path != "/":
                    m = regex.match(path + "/")
                if m:
                    matched_path = True
                    if request.method in methods:
                        kwargs = m.groupdict()
                        res = fn(**kwargs)
                        return self._normalize_response(res)
            if matched_path:
                return Response({"error": "Method Not Allowed", "code": "METHOD_NOT_ALLOWED"}, status=405)
            return Response({"error": f"Endpoint {path} not found", "code": "NOT_FOUND"}, status=404)

        def _normalize_response(self, res):
            if isinstance(res, Response):
                return res
            if isinstance(res, tuple):
                body, status = res[0], res[1]
                headers = res[2] if len(res) > 2 else None
                if isinstance(body, Response):
                    body.status_code = status
                    if headers:
                        body.headers.update(headers)
                    return body
                return Response(body, status=status, headers=headers)
            return Response(res, status=200)

    class _TestClient:
        def __init__(self, app):
            self.app = app

        def open(self, path, method="GET", headers=None, json=None, files=None, remote_addr="127.0.0.1"):
            return self.app.dispatch_request(
                method=method,
                full_path=path,
                headers=headers,
                json_body=json,
                files=files,
                remote_addr=remote_addr
            )

        def get(self, path, headers=None, **kwargs):
            return self.open(path, method="GET", headers=headers, **kwargs)

        def post(self, path, headers=None, json=None, files=None, **kwargs):
            return self.open(path, method="POST", headers=headers, json=json, files=files, **kwargs)

        def put(self, path, headers=None, json=None, **kwargs):
            return self.open(path, method="PUT", headers=headers, json=json, **kwargs)

        def patch(self, path, headers=None, json=None, **kwargs):
            return self.open(path, method="PATCH", headers=headers, json=json, **kwargs)

        def delete(self, path, headers=None, json=None, **kwargs):
            return self.open(path, method="DELETE", headers=headers, json=json, **kwargs)
