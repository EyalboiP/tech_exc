"""Unified client: one way to read a current value from any ammeter."""
import logging
import math
import socket
from typing import Union

logger = logging.getLogger(__name__)


class AmmeterError(Exception):
    """Base class for every ammeter communication failure."""


class AmmeterConnectionError(AmmeterError):
    """The ammeter could not be reached (refused, reset, timed out)."""


class AmmeterProtocolError(AmmeterError):
    """The ammeter answered, but not with a valid measurement."""


class AmmeterClient:
    def __init__(self, name: str, port: int, command: Union[str, bytes], host: str = "localhost",
                 timeout: float = 2.0, retries: int = 0):
        self.name = name
        self.port = port
        self.command = command.encode("utf-8") if isinstance(command, str) else command
        self.host = host
        self.timeout = timeout
        self.retries = retries

    def read(self) -> float:
        """Return one current measurement in amperes, or raise an AmmeterError."""
        last_error: AmmeterError = AmmeterError("no attempt made")
        for attempt in range(self.retries + 1):
            try:
                return self._read_once()
            except AmmeterError as exc:
                last_error = exc
                logger.debug("%s attempt %d/%d failed: %s", self.name, attempt + 1, self.retries + 1, exc)
        raise last_error

    def _read_once(self) -> float:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect((self.host, self.port))
                s.sendall(self.command)
                chunks = []
                while True:  # the emulator closes the connection after replying
                    chunk = s.recv(1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
        except socket.timeout as exc:
            raise AmmeterConnectionError(f"timeout after {self.timeout}s talking to {self.name} on port {self.port}") from exc
        except OSError as exc:
            raise AmmeterConnectionError(f"cannot talk to {self.name} on port {self.port}: {exc}") from exc

        payload = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if not payload:
            raise AmmeterProtocolError(f"{self.name} closed the connection without a reply")
        if payload.upper().startswith("ERROR"):
            raise AmmeterProtocolError(f"{self.name} reported an error: {payload}")
        try:
            value = float(payload)
        except ValueError as exc:
            raise AmmeterProtocolError(f"{self.name} returned a non-numeric reply: {payload[:40]!r}") from exc
        if not math.isfinite(value):
            raise AmmeterProtocolError(f"{self.name} returned a non-finite value: {payload!r}")
        return value
