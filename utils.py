"""
Utility Functions
"""
import socket
import logging
from typing import Tuple


def get_local_ip() -> str:
    """
    Ermittelt die lokale IP-Adresse des Systems
    
    Returns:
        IP-Adresse als String (z.B. "192.168.1.100")
    """
    try:
        # Trick: Verbinde zu Google DNS (8.8.8.8) um eigene IP zu finden
        # Es wird keine echte Verbindung aufgebaut
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def parse_address(address: str) -> Tuple[str, int]:
    """
    Parst einen Address-String zu IP und Port
    
    Args:
        address: Format "ip:port" (z.B. "192.168.1.100:8001")
        
    Returns:
        Tuple (ip, port)
    """
    parts = address.split(":")
    ip = parts[0]
    port = int(parts[1])
    return ip, port


def setup_logging(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Richtet Logging für ein Modul ein
    
    Args:
        name: Name des Loggers
        level: Log-Level (default: INFO)
        
    Returns:
        Konfigurierter Logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Console Handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    ch.setFormatter(formatter)
    
    logger.addHandler(ch)
    return logger


def generate_server_id(port: int = None) -> str:
    """
    Generiert eine eindeutige Server-ID
    
    Args:
        port: Optional port number
        
    Returns:
        Server ID als String
    """
    import uuid
    if port:
        return f"server-{port}"
    return f"server-{uuid.uuid4().hex[:8]}"


def format_server_info(server_id: str, ip: str, port: int, is_leader: bool = False) -> str:
    """
    Formatiert Server-Info für Ausgabe
    
    Returns:
        Formatierter String
    """
    leader_marker = "👑 " if is_leader else ""
    return f"{leader_marker}{server_id} ({ip}:{port})"