"""Indirizzi di rete utili per far aprire l'app agli amici sulla stessa rete (Wi-Fi/LAN)."""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import subprocess
from typing import Any

_IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")


def _default_route_ip() -> list[str]:
    """L'indirizzo dell'interfaccia che esce verso la rete (UDP connect: non invia nulla)."""
    found: list[str] = []
    for target in ("8.8.8.8", "192.168.1.1", "10.0.0.1", "172.16.0.1"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.2)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            if ip not in found:
                found.append(ip)
        except OSError:
            pass
        finally:
            s.close()
    return found


def _from_hostname() -> list[str]:
    try:
        return [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        return []


def _from_system_tools() -> list[str]:
    system = platform.system()
    cmds: list[list[str]]
    if system == "Windows":
        cmds = [["ipconfig"]]
    elif system == "Darwin":
        cmds = [["/sbin/ifconfig"], ["ifconfig"]]
    else:
        cmds = [["ip", "-4", "-o", "addr", "show"], ["hostname", "-I"], ["ifconfig"]]
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=3, errors="ignore").stdout
        except (OSError, subprocess.SubprocessError):
            continue
        ips: list[str] = []
        for line in out.splitlines():
            low = line.lower()
            if system == "Windows" and not ("ipv4" in low or "indirizzo" in low):
                continue
            if system == "Darwin" and "inet " not in low:
                continue
            for m in _IPV4.findall(line):
                if system == "Windows" and low.strip().startswith(("subnet", "maschera", "gateway")):
                    continue
                ips.append(m)
        if ips:
            return ips
    return []


def _score(ip: str, default_route: list[str]) -> tuple[int, str]:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return -999, ""
    if a.is_loopback or a.is_unspecified or a.is_multicast or a.is_link_local:
        return -999, ""
    score, note = 1, "altra rete"
    if a in ipaddress.ip_network("192.168.0.0/16"):
        score, note = 30, "rete locale"
    elif a in ipaddress.ip_network("10.0.0.0/8"):
        score, note = 25, "rete locale"
    elif a in ipaddress.ip_network("172.16.0.0/12"):
        score, note = 15, "rete locale"
    elif a in ipaddress.ip_network("100.64.0.0/10"):
        score, note = 8, "VPN / Tailscale"
    # adattatori virtuali comuni (VirtualBox, Docker, WSL, VMware): di solito NON sono il Wi-Fi
    if ip.startswith(("192.168.56.", "192.168.99.", "172.17.", "172.18.", "172.19.", "192.168.65.")):
        score -= 22
        note = "adattatore virtuale (probabilmente non è il Wi-Fi)"
    if ip in default_route:
        score += 50
        note = "rete principale del PC"
    return score, note


def lan_addresses() -> list[dict[str, Any]]:
    """Elenco ordinato degli indirizzi con cui gli altri dispositivi possono raggiungere questo PC."""
    default_route = _default_route_ip()
    seen: dict[str, tuple[int, str]] = {}
    for ip in default_route + _from_hostname() + _from_system_tools():
        if ip in seen:
            continue
        score, note = _score(ip, default_route)
        if score > -900:
            seen[ip] = (score, note)
    ordered = sorted(seen.items(), key=lambda kv: -kv[1][0])
    return [{"ip": ip, "note": note, "primary": i == 0} for i, (ip, (_s, note)) in enumerate(ordered)]


def local_hostname_url() -> str:
    """Nome '.local' (Bonjour/mDNS): comodo da iPhone e Mac, quando disponibile."""
    try:
        name = socket.gethostname()
    except OSError:
        return ""
    if name.endswith(".local") and re.fullmatch(r"[A-Za-z0-9.-]+", name):
        return name
    return ""
