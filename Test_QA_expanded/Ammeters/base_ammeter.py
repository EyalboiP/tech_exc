import logging
import random
import socket
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple

from Ammeters.faults import DROP, GARBAGE, FaultConfig, FaultInjector

NotImplementedErrorMsg = "Subclasses must implement this property."

logger = logging.getLogger(__name__)

CLIENT_SOCKET_TIMEOUT_S = 2.0


class AmmeterEmulatorBase(ABC):
    def __init__(self, port: int, host: str = "localhost", faults: Optional[FaultConfig] = None):
        self.port = port
        self.host = host
        random.seed(time.time())  # Seed the random number generator for each instance
        self._faults = FaultInjector(faults)
        self._stop_event = threading.Event()
        self.ready_event = threading.Event()   # set once the socket is listening (or failed)
        self.startup_error: Optional[BaseException] = None

    def start_server(self):
        """
        Starts the server to listen for client requests.
        Runs until stop() is called. Each client connection is handled in its own
        thread, so a slow/stuck client cannot block the others.
        """
        self._stop_event.clear()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                # Allows restarting right after a previous run (no "Address already in use").
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.host, self.port))
                s.listen()
                s.settimeout(0.2)  # lets the loop notice stop() quickly
                logger.info("%s is running on port %s", self.__class__.__name__, self.port)
                self.ready_event.set()
                while not self._stop_event.is_set():
                    try:
                        conn, addr = s.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
        except OSError as exc:
            self.startup_error = exc
            logger.error("%s failed to start on port %s: %s", self.__class__.__name__, self.port, exc)
            raise
        finally:
            self.ready_event.set()

    def stop(self):
        """Ask the server loop to exit."""
        self._stop_event.set()

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]):
        with conn:
            logger.debug("Connected by %s", addr)
            conn.settimeout(CLIENT_SOCKET_TIMEOUT_S)
            try:
                data = conn.recv(1024)
                if not data:
                    return
                if data.strip() != self.get_current_command:
                    logger.warning("%s received unknown command: %r", self.__class__.__name__, data)
                    conn.sendall(b"ERROR: unknown command")
                    return

                action, delay = self._faults.next_action()
                if delay:
                    time.sleep(delay)
                if action == DROP:
                    logger.debug("Fault injected: dropping connection")
                    return
                if action == GARBAGE:
                    logger.debug("Fault injected: garbage reply")
                    conn.sendall(b"#GARBAGE#")
                    return

                # Call the specific measure_current() method defined in subclasses
                current = self.measure_current()
                conn.sendall(str(current).encode('utf-8'))
            except OSError as exc:  # timeouts, resets, broken pipe: never kill the server
                logger.debug("Client connection error from %s: %s", addr, exc)

    @classmethod
    def expected_statistics(cls) -> Optional[Tuple[float, float]]:
        """
        Theoretical (mean, std) of the emulated current, derived from the documented
        random ranges. Used by the accuracy assessment. None if unknown.
        """
        return None

    @property
    @abstractmethod
    def get_current_command(self) -> bytes:
        """
        This property must be implemented by each subclass to provide the specific
        command to get the current measurement.
        """
        raise NotImplementedError(NotImplementedErrorMsg)

    @abstractmethod
    def measure_current(self) -> float:
        """
        This method must be implemented by each subclass to provide the specific
        logic for current measurement.
        """
        raise NotImplementedError(NotImplementedErrorMsg)
