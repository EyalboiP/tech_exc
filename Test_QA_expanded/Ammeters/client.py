from socket import socket, AF_INET, SOCK_STREAM
from typing import Optional


def request_current_from_ammeter(port: int, command: bytes, host: str = 'localhost',
                                 timeout: float = 5.0) -> Optional[str]:
    """
    Simple one-shot client used by main.py for a quick demo.
    Prints and returns the raw reply (None if nothing was received).
    The testing framework uses the stricter src.testing.ammeter_client.AmmeterClient.
    """
    with socket(AF_INET, SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect((host, port))
        s.sendall(command)
        data = s.recv(1024)
        if data:
            reply = data.decode('utf-8')
            print(f"Received current measurement from port {port}: {reply} A")
            return reply
        print("No data received.")
        return None
