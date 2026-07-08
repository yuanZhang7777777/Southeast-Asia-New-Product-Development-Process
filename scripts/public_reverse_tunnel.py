from __future__ import annotations

import select
import socket
import threading
import time
from pathlib import Path

import paramiko

TUNNELS = ((15173, "127.0.0.1", 5173), (18000, "127.0.0.1", 8000))


def main() -> None:
    env = read_env(Path(__file__).resolve().parents[1] / ".env")
    threads = []
    for remote_port, local_host, local_port in TUNNELS:
        thread = threading.Thread(target=serve_tunnel, args=(env, remote_port, local_host, local_port), daemon=False)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#") and "=" in text:
            key, value = text.split("=", 1)
            values[key] = value
    return values


def serve_tunnel(env: dict[str, str], remote_port: int, local_host: str, local_port: int) -> None:
    while True:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                env["CLOUD_SERVER_HOST"],
                port=int(env["CLOUD_SERVER_SSH_PORT"]),
                username=env["CLOUD_SERVER_SSH_USER"],
                password=env["CLOUD_SERVER_SSH_PASSWORD"],
                timeout=15,
                banner_timeout=15,
                auth_timeout=15,
            )
            transport = client.get_transport()
            if transport is None:
                raise RuntimeError("SSH transport unavailable")
            transport.set_keepalive(30)
            transport.request_port_forward("127.0.0.1", remote_port)
            print(f"remote 127.0.0.1:{remote_port} -> {local_host}:{local_port}", flush=True)
            while transport.is_active():
                channel = transport.accept(10)
                if channel is None:
                    continue
                threading.Thread(target=forward, args=(channel, local_host, local_port), daemon=True).start()
        except Exception as exc:
            print(f"tunnel {remote_port} reconnecting after error: {exc}", flush=True)
            time.sleep(5)


def forward(channel, local_host: str, local_port: int) -> None:
    try:
        sock = socket.create_connection((local_host, local_port), timeout=10)
    except OSError:
        channel.close()
        return
    with sock, channel:
        while True:
            readable, _, _ = select.select([sock, channel], [], [], 30)
            if not readable:
                continue
            if sock in readable:
                data = sock.recv(65536)
                if not data:
                    return
                channel.sendall(data)
            if channel in readable:
                data = channel.recv(65536)
                if not data:
                    return
                sock.sendall(data)


if __name__ == "__main__":
    main()
