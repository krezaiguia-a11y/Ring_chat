"""
Message Handler - Routing und Distribution von Chat-Messages
"""
import threading
from queue import Queue
from typing import Dict, List, Callable, Optional
from common.config import MessageType
from common.protocol import create_forward_message, create_notification
from common.utils import setup_logging


class MessageHandler:
    """
    Verwaltet Chat-Messages
    - Leader: Empfängt Messages und verteilt sie an alle Server
    - Non-Leader: Forwarded Messages zum Leader
    - Alle: Verteilen Messages an verbundene Clients
    """
    
    def __init__(self, server_id: str, ring_manager):
        self.server_id = server_id
        self.ring_manager = ring_manager
        self.logger = setup_logging(f"MessageHandler-{server_id}")
        
        # Message History (für neue Clients)
        self.message_history: List[Dict] = []
        self.history_lock = threading.Lock()
        
        # Message Queue für Processing
        self.message_queue = Queue()
        
        # Callbacks
        self.on_message_to_clients: Optional[Callable] = None  # Sende zu lokalen Clients
        self.on_forward_to_leader: Optional[Callable] = None   # Forward zum Leader
        self.on_broadcast_to_servers: Optional[Callable] = None  # Leader broadcast zu Servern
        
        # Processing Thread
        self.running = False
        self.process_thread = None
        
    def start(self):
        """Startet Message Processing"""
        self.logger.info("Starting Message Handler")
        self.running = True
        
        self.process_thread = threading.Thread(target=self._process_messages, daemon=True)
        self.process_thread.start()
        
    def stop(self):
        """Stoppt Message Handler"""
        self.logger.info("Stopping Message Handler")
        self.running = False
        
    def handle_client_message(self, message: Dict, from_client_id: str):
        """
        Verarbeitet Message von einem Client
        
        Args:
            message: Chat Message
            from_client_id: ID des sendenden Clients
        """
        self.logger.debug(f"Received message from client {from_client_id}: {message.get('content', '')[:50]}")
        
        # Prüfe ob wir Leader sind
        am_i_leader = self.ring_manager.is_leader(self.server_id)
        
        if am_i_leader:
            # Wir sind Leader - verteile an alle Server
            self._distribute_message(message)
        else:
            # Wir sind nicht Leader - forward zum Leader
            self._forward_to_leader(message)
            
    def handle_forwarded_message(self, message: Dict):
        """
        Verarbeitet Message die von anderem Server weitergeleitet wurde
        (Leader empfängt diese und verteilt sie)
        
        Args:
            message: Forwarded Message
        """
        original_message = message.get('original_message')
        origin_server = message.get('origin_server_id')
        
        self.logger.debug(f"Received forwarded message from server {origin_server}")
        
        # Leader verteilt an alle Server
        if self.ring_manager.is_leader(self.server_id):
            self._distribute_message(original_message)
        else:
            self.logger.warning("Received forwarded message but I'm not the leader")
            
    def handle_distributed_message(self, message: Dict):
        """
        Verarbeitet Message die vom Leader verteilt wurde
        -> Sende an lokale Clients
        
        Args:
            message: Chat Message vom Leader
        """
        # Speichere in History
        self._add_to_history(message)
        
        # Sende an lokale Clients
        if self.on_message_to_clients:
            self.on_message_to_clients(message)
            
    def _distribute_message(self, message: Dict):
        """
        Leader: Verteilt Message an alle Server im Ring
        
        Args:
            message: Chat Message
        """
        self.logger.debug(f"Distributing message to all servers")
        
        # Speichere in eigener History
        self._add_to_history(message)
        
        # Sende an eigene Clients
        if self.on_message_to_clients:
            self.on_message_to_clients(message)
        
        # Broadcast an alle anderen Server
        if self.on_broadcast_to_servers:
            forward_msg = create_forward_message(message, self.server_id)
            self.on_broadcast_to_servers(forward_msg)
            
    def _forward_to_leader(self, message: Dict):
        """
        Non-Leader: Forwarded Message zum Leader
        
        Args:
            message: Chat Message
        """
        leader = self.ring_manager.get_leader()
        
        if not leader:
            self.logger.error("Cannot forward message - no leader known")
            return
            
        if leader.server_id == self.server_id:
            self.logger.warning("I am the leader, shouldn't forward to myself")
            return
            
        self.logger.debug(f"Forwarding message to leader {leader.server_id}")
        
        if self.on_forward_to_leader:
            forward_msg = create_forward_message(message, self.server_id)
            self.on_forward_to_leader(leader, forward_msg)
            
    def _add_to_history(self, message: Dict):
        """Fügt Message zur History hinzu"""
        with self.history_lock:
            self.message_history.append(message)
            
            # Limit History size
            if len(self.message_history) > 1000:
                self.message_history = self.message_history[-1000:]
                
    def get_message_history(self) -> List[Dict]:
        """Gibt Message History zurück"""
        with self.history_lock:
            return self.message_history.copy()
            
    def _process_messages(self):
        """Background Thread für Message Processing"""
        while self.running:
            try:
                # Hier könnten wir Messages aus Queue verarbeiten
                # Aktuell: Direkte Verarbeitung in handle_* Methods
                pass
            except Exception as e:
                self.logger.error(f"Error processing messages: {e}")
                
    def set_callbacks(self, 
                     to_clients: Callable = None,
                     to_leader: Callable = None, 
                     to_servers: Callable = None):
        """
        Setzt Callbacks für Message Distribution
        
        Args:
            to_clients: Callback(message) - Sende zu lokalen Clients
            to_leader: Callback(leader_info, message) - Forward zum Leader
            to_servers: Callback(message) - Broadcast zu allen Servern
        """
        if to_clients:
            self.on_message_to_clients = to_clients
        if to_leader:
            self.on_forward_to_leader = to_leader
        if to_servers:
            self.on_broadcast_to_servers = to_servers