"""Which addresses is a TCP port listening on? Used by `./village doctor` to confirm that the
Village is reachable from this PC only (127.0.0.1), never from the network.

Usage: python -m app.bindcheck <port> <configured-host>     prints "STATUS<TAB>message"
Reads /proc/net/tcp and /proc/net/tcp6 (Linux); nothing is opened or changed.
"""

from __future__ import annotations

import ipaddress
import sys
from pathlib import Path

_LISTEN = "0A"


def _address(hex_address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """/proc/net/tcp writes addresses as hex, each 32-bit word in host (little-endian) order."""
    raw = bytes.fromhex(hex_address)
    words = [raw[index : index + 4][::-1] for index in range(0, len(raw), 4)]
    return ipaddress.ip_address(b"".join(words))


def parse_listeners(table: str, port: int) -> list[str]:
    """The local addresses in LISTEN state on `port`, from the text of /proc/net/tcp[6]."""
    found = []
    for line in table.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or fields[3] != _LISTEN:
            continue
        hex_address, _, hex_port = fields[1].rpartition(":")
        if int(hex_port, 16) == port:
            found.append(str(_address(hex_address)))
    return found


def listening_addresses(port: int, proc: Path = Path("/proc/net")) -> list[str] | None:
    """Every address something listens on for `port`; None when the system cannot be inspected."""
    found: list[str] = []
    readable = False
    for name in ("tcp", "tcp6"):
        try:
            found += parse_listeners((proc / name).read_text(encoding="ascii"), port)
            readable = True
        except (OSError, ValueError):
            continue
    return sorted(set(found)) if readable else None


def is_loopback(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_loopback


def verdict(addresses: list[str] | None, port: int, configured_host: str) -> tuple[str, str]:
    """(PASS | WARN | FAIL, message) for the doctor."""
    if addresses is None:
        return "WARN", f"bind: cannot inspect listening sockets on this system; configured host is {configured_host}"
    if not addresses:
        return "PASS", f"bind: nothing is listening on port {port}; configured host is {configured_host} (loopback only)"
    exposed = [address for address in addresses if not is_loopback(address)]
    if exposed:
        return (
            "FAIL",
            f"bind: port {port} is listening on {', '.join(exposed)} — reachable from the network. "
            "The Village must listen on 127.0.0.1 only.",
        )
    return "PASS", f"bind: port {port} is listening on {', '.join(addresses)} only (not reachable from the network)"


def main(argv: list[str]) -> int:
    port = int(argv[1])
    configured_host = argv[2] if len(argv) > 2 else "127.0.0.1"
    status, message = verdict(listening_addresses(port), port, configured_host)
    print(f"{status}\t{message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
