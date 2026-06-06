import asyncio
import http.server
import os
import queue
import socketserver
import sys
import threading
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

from pythonxbox.authentication.manager import AuthenticationManager
from pythonxbox.authentication.models import OAuth2TokenResponse
from pythonxbox.common.signed_session import SignedSession
from pythonxbox.scripts import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, TOKENS_FILE

from xboxctl.auth import DEFAULT_AUTH_PORT, AuthPrompt
from xboxctl.typing_compat import override

AUTH_CODE_QUEUE: Final[queue.Queue[str]] = queue.Queue(1)


class AuthenticationFlowError(Exception):
    @override
    def __str__(self) -> str:
        return "Authentication finished without an OAuth token."


@dataclass(frozen=True, slots=True)
class AuthFlowConfig:
    tokens: str
    client_id: str
    client_secret: str
    redirect_uri: str
    port: int
    prompt: AuthPrompt


def authorization_url(
    auth_manager: AuthenticationManager,
    prompt: AuthPrompt,
) -> str:
    original_url = auth_manager.generate_authorization_url()
    parsed_url = urlparse(original_url)
    query_params = [
        item for item in parse_qsl(parsed_url.query) if item[0] != "prompt"
    ]
    query_params.append(("prompt", prompt.value))
    return urlunparse(parsed_url._replace(query=urlencode(query_params)))


class AuthCallbackRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        query_params = parse_qs(urlparse(self.path).query)
        if query_params.get("error"):
            _ = self.send_error(
                HTTPStatus.BAD_REQUEST,
                explain=(
                    "Auth callback failed: "
                    f"{query_params.get('error_description')}"
                ),
            )
            return

        auth_code = query_params.get("code", [])
        if not auth_code:
            _ = self.send_error(
                HTTPStatus.BAD_REQUEST,
                explain="Auth callback failed: no code received.",
            )
            return

        AUTH_CODE_QUEUE.put(auth_code[0])
        response_body = b"<script>window.close()</script>"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        _ = self.wfile.write(response_body)


async def authenticate(config: AuthFlowConfig) -> None:
    async with SignedSession() as session:
        auth_manager = AuthenticationManager(
            session,
            config.client_id,
            config.client_secret,
            config.redirect_uri,
        )
        auth_url = authorization_url(auth_manager, config.prompt)
        _ = webbrowser.open(auth_url)
        code = AUTH_CODE_QUEUE.get()
        await auth_manager.request_tokens(code)

        oauth = auth_manager.oauth
        if oauth is None:
            raise AuthenticationFlowError
        write_tokens(config.tokens, oauth)


def write_tokens(token_filepath: str, oauth: OAuth2TokenResponse) -> None:
    token_path = Path(token_filepath)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with token_path.open(mode="w", encoding="utf-8") as handle:
        _ = handle.write(oauth.model_dump_json())
    message = f"Finished authentication, writing tokens to {token_filepath}\n"
    _ = sys.stdout.write(message)


async def async_main(arguments: Sequence[str]) -> None:
    config = parse_args(arguments)
    with socketserver.TCPServer(
        ("127.0.0.1", config.port),
        AuthCallbackRequestHandler,
    ) as httpd:
        message = f"Serving HTTP Server for auth callback at port {config.port}\n"
        _ = sys.stdout.write(message)
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        await authenticate(config)


def parse_args(arguments: Sequence[str]) -> AuthFlowConfig:
    tokens = TOKENS_FILE
    client_id = os.environ.get("CLIENT_ID", CLIENT_ID)
    client_secret = os.environ.get("CLIENT_SECRET", CLIENT_SECRET)
    redirect_uri = os.environ.get("REDIRECT_URI", REDIRECT_URI)
    port = DEFAULT_AUTH_PORT
    prompt = AuthPrompt.SELECT_ACCOUNT

    index = 0
    while index < len(arguments):
        option = arguments[index]
        match option:
            case "--tokens" | "-t":
                tokens = option_value(arguments, index)
                index += 2
            case "--client-id" | "-cid":
                client_id = option_value(arguments, index)
                index += 2
            case "--client-secret" | "-cs":
                client_secret = option_value(arguments, index)
                index += 2
            case "--redirect-uri" | "-ru":
                redirect_uri = option_value(arguments, index)
                index += 2
            case "--port" | "-p":
                port = int(option_value(arguments, index))
                index += 2
            case "--prompt":
                prompt = AuthPrompt(option_value(arguments, index))
                index += 2
            case _:
                _ = sys.stderr.write(f"Unknown option: {option}\n")
                raise SystemExit(2)

    return AuthFlowConfig(
        tokens=tokens,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        port=port,
        prompt=prompt,
    )


def option_value(arguments: Sequence[str], index: int) -> str:
    value_index = index + 1
    if value_index >= len(arguments):
        _ = sys.stderr.write(f"Missing value for {arguments[index]}\n")
        raise SystemExit(2)
    return arguments[value_index]


def main() -> None:
    asyncio.run(async_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
