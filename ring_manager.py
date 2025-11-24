"""
Ring Manager - Verwaltet Ring-Topologie
"""
import threading
from typing import Dict, List, Optional
from common.utils import setup_logging


class ServerInfo:
    """Info über einen Server im Ring"""
    
    def __init__(self, server_id: str, ip: str, port: int):
        self.server_id = server_id
        self.ip = ip
        self.port = port
        self.is_leader = False
        self.is_alive = True
        
    def __repr__(self):
        leader = "👑" if self.is_leader else ""
        return f"{leader}Server({self.server_id}, {self.ip}:{self.port})"
        
    def to_dict(self) -> Dict:
        """Konvertiert zu Dictionary"""
        return {
            'server_id': self.server_id,
            'ip': self.ip,
            'port': self.port,
            'is_leader': self.is_leader
        }


class RingManager:
    """
    Verwaltet die Ring-Topologie
    - Ring-Struktur
    - Nachbarn (left/right)
    - Ring-Updates bei Server-Changes
    """
    
    def __init__(self, own_server_id: str):
        self.own_server_id = own_server_id
        self.logger = setup_logging(f"Ring-{own_server_id}")
        
        # Ring Members (server_id -> ServerInfo)
        self.ring_members: Dict[str, ServerInfo] = {}
        
        # Ring als sortierte Liste (nach server_id sortiert für konsistente Reihenfolge)
        self.ring_order: List[str] = []
        
        # Nachbarn
        self.left_neighbor: Optional[ServerInfo] = None
        self.right_neighbor: Optional[ServerInfo] = None
        
        # Lock für Thread-Safety
        self.lock = threading.Lock()
        
    def add_server(self, server_id: str, ip: str, port: int, is_leader: bool = False):
        """
        Fügt Server zum Ring hinzu
        
        Args:
            server_id: Server ID
            ip: IP-Adresse
            port: Port
            is_leader: Ist dieser Server der Leader?
        """
        with self.lock:
            if server_id in self.ring_members:
                self.logger.debug(f"Server {server_id} already in ring")
                return
                
            server_info = ServerInfo(server_id, ip, port)
            server_info.is_leader = is_leader
            
            self.ring_members[server_id] = server_info
            self._rebuild_ring()
            
            self.logger.info(f"Added server {server_id} to ring. Ring size: {len(self.ring_members)}")
            
    def remove_server(self, server_id: str):
        """
        Entfernt Server aus Ring
        
        Args:
            server_id: Server ID
        """
        with self.lock:
            if server_id not in self.ring_members:
                self.logger.warning(f"Cannot remove {server_id} - not in ring")
                return
                
            del self.ring_members[server_id]
            self._rebuild_ring()
            
            self.logger.info(f"Removed server {server_id} from ring. Ring size: {len(self.ring_members)}")
            
    def _rebuild_ring(self):
        """Baut Ring-Reihenfolge neu auf"""
        # Sortiere Server-IDs für konsistente Ring-Reihenfolge
        self.ring_order = sorted(self.ring_members.keys())
        
        # Finde eigene Position
        if self.own_server_id not in self.ring_order:
            self.left_neighbor = None
            self.right_neighbor = None
            return
            
        own_index = self.ring_order.index(self.own_server_id)
        ring_size = len(self.ring_order)
        
        if ring_size == 1:
            # Nur wir alleine im Ring
            self.left_neighbor = None
            self.right_neighbor = None
        else:
            # Linker Nachbar (vorheriger in Liste, wrap around)
            left_index = (own_index - 1) % ring_size
            left_id = self.ring_order[left_index]
            self.left_neighbor = self.ring_members[left_id]
            
            # Rechter Nachbar (nächster in Liste, wrap around)
            right_index = (own_index + 1) % ring_size
            right_id = self.ring_order[right_index]
            self.right_neighbor = self.ring_members[right_id]
            
        self.logger.debug(f"Ring rebuilt. Left: {self.left_neighbor}, Right: {self.right_neighbor}")
        
    def get_ring_topology(self) -> List[Dict]:
        """
        Gibt komplette Ring-Topologie zurück
        
        Returns:
            Liste von Server-Infos
        """
        with self.lock:
            return [self.ring_members[sid].to_dict() for sid in self.ring_order]
            
    def get_all_servers(self) -> List[ServerInfo]:
        """Gibt alle Server im Ring zurück"""
        with self.lock:
            return list(self.ring_members.values())
            
    def get_server(self, server_id: str) -> Optional[ServerInfo]:
        """Gibt ServerInfo für eine ID zurück"""
        with self.lock:
            return self.ring_members.get(server_id)
            
    def set_leader(self, server_id: str):
        """Setzt einen Server als Leader"""
        with self.lock:
            # Entferne Leader-Status von allen
            for server in self.ring_members.values():
                server.is_leader = False
                
            # Setze neuen Leader
            if server_id in self.ring_members:
                self.ring_members[server_id].is_leader = True
                self.logger.info(f"Leader set to: {server_id}")
                
    def get_leader(self) -> Optional[ServerInfo]:
        """Gibt aktuellen Leader zurück"""
        with self.lock:
            for server in self.ring_members.values():
                if server.is_leader:
                    return server
            return None
            
    def is_leader(self, server_id: str) -> bool:
        """Prüft ob Server der Leader ist"""
        with self.lock:
            server = self.ring_members.get(server_id)
            return server.is_leader if server else False
            
    def ring_size(self) -> int:
        """Gibt Anzahl Server im Ring zurück"""
        with self.lock:
            return len(self.ring_members)
            
    def print_ring(self):
        """Debug: Gibt Ring-Struktur aus"""
        with self.lock:
            self.logger.info("=== Ring Topology ===")
            for i, sid in enumerate(self.ring_order):
                server = self.ring_members[sid]
                marker = "👑" if server.is_leader else "🔵"
                own = " (ME)" if sid == self.own_server_id else ""
                self.logger.info(f"  {i}: {marker} {server.server_id}{own}")
            self.logger.info(f"Left Neighbor: {self.left_neighbor}")
            self.logger.info(f"Right Neighbor: {self.right_neighbor}")
            self.logger.info("=" * 25)  