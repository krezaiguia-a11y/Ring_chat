"""
Discovery Service - UDP Multicast für automatisches Server-Finding
"""
import socket
import threading
import time
import struct
from typing import Callable, Dict, List
from common.config import MULTICAST_GROUP, MULTICAST_PORT, DISCOVERY_INTERVAL, MessageType
from common.protocol import create_discovery_announce, deserialize_message, serialize_message
from common.utils import setup_logging


class DiscoveryService:
    """
    UDP Multicast Service für Server Discovery
    - Sendet periodisch Announcements
    - Empfängt Announcements von anderen Servern
    """
    
    def __init__(self, server_id: str, ip: str, port: int):
        self.server_id = server_id
        self.ip = ip
        self.port = port
        
        self.logger = setup_logging(f"Discovery-{server_id}")
        
        # UDP Sockets
        self.send_socket = None
        self.recv_socket = None
        
        # Thread Control
        self.running = False
        self.announce_thread = None
        self.listen_thread = None
        
        # Callback für gefundene Server
        self.on_server_discovered: Callable = None
        
        # Discovered Servers (server_id -> {ip, port, last_seen})
        self.discovered_servers: Dict[str, Dict] = {}
        
    def start(self):
        """Startet Discovery Service"""
        self.logger.info("Starting Discovery Service...")
        self.running = True
        
        # Setup Sockets
        self._setup_sockets()
        
        # Start Threads
        self.announce_thread = threading.Thread(target=self._announce_loop, daemon=True)
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        
        self.announce_thread.start()
        self.listen_thread.start()
        
        self.logger.info(f"Discovery Service started on {MULTICAST_GROUP}:{MULTICAST_PORT}")
        
    def stop(self):
        """Stoppt Discovery Service"""
        self.logger.info("Stopping Discovery Service...")
        self.running = False
        
        if self.send_socket:
            self.send_socket.close()
        if self.recv_socket:
            self.recv_socket.close()
            
    def _setup_sockets(self):
        """Richtet UDP Multicast Sockets ein"""
        
        # Send Socket
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        
        # Receive Socket
        self.recv_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Bind to multicast port
        self.recv_socket.bind(('', MULTICAST_PORT))
        
        # Join multicast group
        mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
        self.recv_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        self.logger.debug("UDP Multicast sockets configured")
        
    def _announce_loop(self):
        """Sendet periodisch Discovery Announcements"""
        while self.running:
            try:
                # Erstelle Announcement Message
                message = create_discovery_announce(
                    server_id=self.server_id,
                    ip=self.ip,
                    port=self.port
                )
                
                # Serialize und sende
                data = serialize_message(message)
                self.send_socket.sendto(data, (MULTICAST_GROUP, MULTICAST_PORT))
                
                self.logger.debug(f"Sent discovery announcement")
                
            except Exception as e:
                self.logger.error(f"Error sending announcement: {e}")
                
            time.sleep(DISCOVERY_INTERVAL)
            
    def _listen_loop(self):
        """Empfängt Discovery Messages von anderen Servern"""
        self.recv_socket.settimeout(1.0)  # Timeout für sauberes Beenden
        
        while self.running:
            try:
                data, addr = self.recv_socket.recvfrom(4096)
                
                # Deserialize Message
                message = deserialize_message(data)
                if not message:
                    continue
                    
                # Ignoriere eigene Messages
                if message.get('server_id') == self.server_id:
                    continue
                    
                # Verarbeite Discovery Message
                self._handle_discovery_message(message, addr)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error receiving discovery: {e}")
                    
    def _handle_discovery_message(self, message: Dict, addr: tuple):
        """Verarbeitet empfangene Discovery Messages"""
        msg_type = message.get('type')
        
        if msg_type == MessageType.DISCOVERY_ANNOUNCE:
            server_id = message.get('server_id')
            ip = message.get('ip')
            port = message.get('port')
            
            # Speichere/Update Server Info
            is_new = server_id not in self.discovered_servers
            
            self.discovered_servers[server_id] = {
                'server_id': server_id,
                'ip': ip,
                'port': port,
                'last_seen': time.time()
            }
            
            if is_new:
                self.logger.info(f"Discovered new server: {server_id} at {ip}:{port}")
                
                # Callback für neuen Server
                if self.on_server_discovered:
                    self.on_server_discovered(server_id, ip, port)
                    
    def get_discovered_servers(self) -> List[Dict]:
        """
        Gibt Liste aller entdeckten Server zurück
        
        Returns:
            Liste von Server-Infos
        """
        return list(self.discovered_servers.values())
        
    def set_server_discovered_callback(self, callback: Callable):
        """
        Setzt Callback für neu entdeckte Server
        
        Args:
            callback: Funktion(server_id, ip, port)
        """
        self.on_server_discovered = callback