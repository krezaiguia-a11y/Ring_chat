"""
Main Server - Orchestriert alle Server-Komponenten
"""
import socket
import threading
import time
import argparse
from typing import Optional, Dict
from common.config import (
    DEFAULT_SERVER_PORT_START, 
    MessageType, 
    ServerStatus,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT
)
from common.protocol import serialize_message, deserialize_message
from common.utils import setup_logging, get_local_ip, generate_server_id
from server.discovery import DiscoveryService
from server.ring_manager import RingManager, ServerInfo
from server.election import ElectionService
from server.message_handler import MessageHandler
from server.client_handler import ClientHandler


class Server:
    """
    Haupt-Server-Klasse
    
    Integriert:
    - Discovery Service (UDP Multicast)
    - Ring Manager (Ring-Topologie)
    - Election Service (Leader-Wahl)
    - Message Handler (Chat-Messages)
    - Client Handler (Client-Verbindungen)
    """
    
    def __init__(self, server_id: str = None, port: int = None):
        # Server ID
        self.server_id = server_id or generate_server_id(port)
        self.port = port or DEFAULT_SERVER_PORT_START
        self.ip = get_local_ip()
        
        self.logger = setup_logging(f"Server-{self.server_id}")
        self.logger.info(f"Initializing server {self.server_id} on {self.ip}:{self.port}")
        
        # Server Status
        self.status = ServerStatus.STARTING
        self.running = False
        
        # TCP Server Socket (für Clients und Server-to-Server)
        self.server_socket: Optional[socket.socket] = None
        
        # Komponenten
        self.discovery = DiscoveryService(self.server_id, self.ip, self.port)
        self.ring_manager = RingManager(self.server_id)
        self.election = ElectionService(self.server_id, self.ring_manager)
        self.message_handler = MessageHandler(self.server_id, self.ring_manager)
        self.client_handler = ClientHandler(self.server_id)
        
        # Server-to-Server Connections (server_id -> socket)
        self.server_connections: Dict[str, socket.socket] = {}
        self.connections_lock = threading.Lock()
        
        # Heartbeat
        self.heartbeat_thread = None
        self.last_heartbeat_received: Dict[str, float] = {}
        
        # Setup Callbacks
        self._setup_callbacks()
        
    def _setup_callbacks(self):
        """Richtet Callbacks zwischen Komponenten ein"""
        
        # Discovery -> Neuer Server gefunden
        self.discovery.set_server_discovered_callback(self._on_server_discovered)
        
        # Election -> Leader gewählt
        self.election.set_leader_elected_callback(self._on_leader_elected)
        self.election.set_send_callback(self._send_to_server)
        
        # Message Handler -> Messages verteilen
        self.message_handler.set_callbacks(
            to_clients=self._broadcast_to_local_clients,
            to_leader=self._forward_to_leader,
            to_servers=self._broadcast_to_all_servers
        )
        
        # Client Handler -> Client Events
        self.client_handler.set_callbacks(
            on_message=self._on_client_message,
            on_joined=self._on_client_joined,
            on_left=self._on_client_left
        )
        
    def start(self):
        """Startet den Server"""
        try:
            self.logger.info("=" * 50)
            self.logger.info(f"🚀 Starting Server: {self.server_id}")
            self.logger.info(f"   Address: {self.ip}:{self.port}")
            self.logger.info("=" * 50)
            
            self.running = True
            
            # 1. TCP Server Socket starten
            self._start_tcp_server()
            
            # 2. Füge eigenen Server zum Ring hinzu
            self.ring_manager.add_server(self.server_id, self.ip, self.port, is_leader=False)
            
            # 3. Starte Discovery Service
            self.discovery.start()
            self.status = ServerStatus.DISCOVERING
            
            # 4. Warte kurz auf Discovery
            self.logger.info("Discovering other servers...")
            time.sleep(5)
            
            # 5. Initialisiere Ring
            self._initialize_ring()
            
            # 5.5. Warte bis Ring wirklich bereit ist (State-Based, nicht Time-Based!)
            if not self._wait_for_ring_ready(timeout=10):
                self.logger.error("Ring not ready in time, but proceeding...")
            
            # 6. Starte Election (nur wenn noch kein Leader existiert)
            current_leader = self.ring_manager.get_leader()
            
            if current_leader is not None:
                # Es gibt bereits einen Leader (durch Discovery-Election)
                self.logger.info(f"✅ Leader already exists: {current_leader.server_id} - skipping initial election")
                if current_leader.server_id == self.server_id:
                    self.status = ServerStatus.LEADER
                    self.logger.info("👑 I am the leader!")
                else:
                    self.status = ServerStatus.ACTIVE
                    self.logger.info(f"Following leader: {current_leader.server_id}")
            elif self.ring_manager.ring_size() > 1:
                # Kein Leader, aber andere Server da → Election starten!
                self.logger.info("Starting initial election...")
                time.sleep(2)
                self.election.start_election("Initial election")
            else:
                # Wir sind alleine (ring_size = 1, nur wir) → Ich bin Leader
                self.logger.info("No other servers found - I am the leader!")
                self.ring_manager.set_leader(self.server_id)
                self.status = ServerStatus.LEADER
                
            # 7. Starte Message Handler
            self.message_handler.start()
            
            # 8. Starte Heartbeat
            self._start_heartbeat()
            
            self.status = ServerStatus.ACTIVE
            self.logger.info(f"✅ Server {self.server_id} is running!")
            
            # Keep running
            self._run()
            
        except Exception as e:
            self.logger.error(f"Error starting server: {e}", exc_info=True)
            self.stop()
            
    def stop(self):
        """Stoppt den Server"""
        self.logger.info(f"Stopping server {self.server_id}...")
        self.running = False
        
        # Stop Komponenten
        if self.discovery:
            self.discovery.stop()
        if self.message_handler:
            self.message_handler.stop()
            
        # Close Connections
        with self.connections_lock:
            for sock in self.server_connections.values():
                try:
                    sock.close()
                except:
                    pass
            self.server_connections.clear()
            
        # Close Server Socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
                
        self.logger.info("Server stopped")
    # ============================================
    # TCP SERVER & CONNECTION HANDLING
    # ============================================
    
    def _start_tcp_server(self):
        """Startet TCP Server für Clients und Server-to-Server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.ip, self.port))
        self.server_socket.listen(10)
        
        self.logger.info(f"TCP Server listening on {self.ip}:{self.port}")
        
        # Accept Thread
        accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
        accept_thread.start()
        
    def _accept_connections(self):
        """Akzeptiert eingehende TCP Verbindungen"""
        self.server_socket.settimeout(1.0)
        
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                self.logger.debug(f"New connection from {address}")
                
                # Thread für Connection-Typ-Erkennung
                thread = threading.Thread(
                    target=self._handle_new_connection,
                    args=(client_socket, address),
                    daemon=True
                )
                thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error accepting connection: {e}")
                    
    def _handle_new_connection(self, conn_socket: socket.socket, address: tuple):
        """
        Bestimmt ob Connection von Client oder Server kommt
        """
        try:
            # Erste Message bestimmt Connection-Typ
            conn_socket.settimeout(5.0)
            data = conn_socket.recv(4096)
            
            if not data:
                conn_socket.close()
                return
                
            message = deserialize_message(data)
            if not message:
                conn_socket.close()
                return
                
            msg_type = message.get('type')
            
            # Client Connection (CLIENT_JOIN)
            if msg_type == MessageType.CLIENT_JOIN:
                self.logger.info(f"Client connection from {address}")
                # Sende Message zurück für Processing
                conn_socket.sendall(data)
                # Übergebe an Client Handler
                self.client_handler.add_client(conn_socket, address)
                
            # Server Connection (HEARTBEAT, ELECTION, etc.)
            elif msg_type in [MessageType.HEARTBEAT, MessageType.ELECTION, 
                            MessageType.LEADER_ANNOUNCEMENT, MessageType.FORWARD_MESSAGE]:
                self.logger.info(f"Server connection from {address}")
                # Verarbeite Server Message
                self._handle_server_message(message, conn_socket)
                # Keep connection für weitere Messages
                self._handle_persistent_server_connection(conn_socket, address)
                
            else:
                self.logger.warning(f"Unknown connection type: {msg_type}")
                conn_socket.close()
                
        except Exception as e:
            self.logger.error(f"Error handling new connection: {e}")
            try:
                conn_socket.close()
            except:
                pass
                
    def _handle_persistent_server_connection(self, conn_socket: socket.socket, address: tuple):
        """Hält Server-Connection offen für weitere Messages"""
        buffer = b''
        
        while self.running:
            try:
                chunk = conn_socket.recv(4096)
                if not chunk:
                    break
                    
                buffer += chunk
                
                # Verarbeite Messages (getrennt durch \n)
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line:
                        message = deserialize_message(line)
                        if message:
                            self._handle_server_message(message, conn_socket)
                            
            except Exception as e:
                self.logger.error(f"Error in persistent server connection: {e}")
                break
                
        try:
            conn_socket.close()
        except:
            pass
            
    # ============================================
    # SERVER-TO-SERVER COMMUNICATION
    # ============================================
    
    def _connect_to_server(self, server_info: ServerInfo) -> Optional[socket.socket]:
        """
        Verbindet zu einem anderen Server
        
        Args:
            server_info: Server Info
            
        Returns:
            Socket oder None bei Fehler
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((server_info.ip, server_info.port))
            
            self.logger.debug(f"Connected to server {server_info.server_id}")
            
            with self.connections_lock:
                self.server_connections[server_info.server_id] = sock
                
            return sock
            
        except Exception as e:
            self.logger.error(f"Error connecting to {server_info.server_id}: {e}")
            return None
            
    def _send_to_server(self, server_info: ServerInfo, message: Dict):
        """
        Sendet Message zu einem Server
        
        Args:
            server_info: Ziel-Server
            message: Message
        """
        try:
            # Hole oder erstelle Connection
            with self.connections_lock:
                sock = self.server_connections.get(server_info.server_id)
                
            if not sock:
                sock = self._connect_to_server(server_info)
                
            if not sock:
                self.logger.error(f"Cannot send to {server_info.server_id} - no connection")
                return
                
            # Sende Message
            data = serialize_message(message)
            sock.sendall(data + b'\n')
            
            self.logger.debug(f"Sent {message.get('type')} to {server_info.server_id}")
            
        except Exception as e:
            self.logger.error(f"Error sending to {server_info.server_id}: {e}")
            
            # Remove broken connection
            with self.connections_lock:
                if server_info.server_id in self.server_connections:
                    del self.server_connections[server_info.server_id]
                    
    def _broadcast_to_all_servers(self, message: Dict):
        """
        Broadcast Message an alle Server im Ring (außer uns selbst)
        
        Args:
            message: Message
        """
        servers = self.ring_manager.get_all_servers()
        
        for server in servers:
            if server.server_id != self.server_id:
                self._send_to_server(server, message)
                
    def _handle_server_message(self, message: Dict, sender_socket: socket.socket = None):
        """
        Verarbeitet Message von anderem Server
        
        Args:
            message: Empfangene Message
            sender_socket: Socket des Senders (optional)
        """
        msg_type = message.get('type')
        
        if msg_type == MessageType.ELECTION:
            self.election.handle_election_message(message)
            
        elif msg_type == MessageType.LEADER_ANNOUNCEMENT:
            self.election.handle_leader_announcement(message)
            
        elif msg_type == MessageType.HEARTBEAT:
            self._handle_heartbeat(message)
            
        elif msg_type == MessageType.FORWARD_MESSAGE:
            # Message vom Non-Leader zum Leader
            self.message_handler.handle_forwarded_message(message)
            
        elif msg_type in [MessageType.FORWARD_MESSAGE, MessageType.CHAT_MESSAGE]:
            # Message vom Leader zu uns (Distribution)
            original_msg = message.get('original_message', message)
            self.message_handler.handle_distributed_message(original_msg)
            
        else:
            self.logger.warning(f"Unknown server message type: {msg_type}")
            
    # ============================================
    # RING INITIALIZATION
    # ============================================
    
    def _initialize_ring(self):
        """Initialisiert Ring mit entdeckten Servern"""
        discovered = self.discovery.get_discovered_servers()
        
        self.logger.info(f"Discovered {len(discovered)} other servers")
        
        for server in discovered:
            self.ring_manager.add_server(
                server['server_id'],
                server['ip'],
                server['port']
            )
            
        self.ring_manager.print_ring()
        
    def _wait_for_ring_ready(self, timeout: int = 10) -> bool:
        """
        Wartet bis Ring vollständig aufgebaut ist (State-Based Synchronisation)
        
        Professional Solution: Aktives Warten statt blindes time.sleep()
        
        Args:
            timeout: Maximale Wartezeit in Sekunden
            
        Returns:
            True wenn Ring bereit, False bei Timeout
        """
        start_time = time.time()
        discovered_count = len(self.discovery.get_discovered_servers())
        
        self.logger.info(f"⏳ Waiting for ring to be ready (discovered {discovered_count} servers)...")
        
        while time.time() - start_time < timeout:
            ring_size = self.ring_manager.ring_size()
            
            # Ring ist bereit wenn:
            # 1. Wir alleine sind (ring_size = 1) ODER
            # 2. Alle entdeckten Server sind im Ring UND Nachbarn sind konfiguriert
            
            if ring_size == 1:
                # Solo-Mode: Keine anderen Server
                self.logger.info("✅ Ring ready (solo mode)")
                return True
            elif ring_size == discovered_count + 1:
                # Multi-Server-Mode: Alle Server im Ring
                if self.ring_manager.right_neighbor is not None and self.ring_manager.left_neighbor is not None:
                    self.logger.info(f"✅ Ring is ready! Size: {ring_size}, Neighbors configured")
                    return True
                else:
                    self.logger.debug(f"Ring size correct ({ring_size}), waiting for neighbors...")
            else:
                self.logger.debug(f"Waiting... Ring size: {ring_size}/{discovered_count + 1}")
                
            # Kurz warten bevor nächster Check
            time.sleep(0.5)
            
        # Timeout erreicht
        self.logger.warning(f"⏰ Ring ready timeout after {timeout}s (ring_size={self.ring_manager.ring_size()})")
        self.logger.warning(f"   Proceeding anyway, but system may be unstable")
        return False
        
    def _on_server_discovered(self, server_id: str, ip: str, port: int):
        """
        Callback: Neuer Server wurde entdeckt
        
        Args:
            server_id: Server ID
            ip: IP-Adresse
            port: Port
        """
        self.logger.info(f"New server discovered during runtime: {server_id}")
        
        # Füge zu Ring hinzu
        self.ring_manager.add_server(server_id, ip, port)
        
        # Wenn wir Leader sind, starte neue Election
        if self.ring_manager.is_leader(self.server_id):
            self.logger.info("Leader detected new server - starting re-election")
            time.sleep(1)
            self.election.start_election("New server joined")
            
    # ============================================
    # ELECTION CALLBACKS
    # ============================================
    
    def _on_leader_elected(self, leader_id: str):
        """
        Callback: Neuer Leader wurde gewählt
        
        Args:
            leader_id: ID des neuen Leaders
        """
        am_i_leader = (leader_id == self.server_id)
        
        if am_i_leader:
            self.logger.info("👑 I AM THE LEADER!")
            self.status = ServerStatus.LEADER
        else:
            self.logger.info(f"Leader is: {leader_id}")
            self.status = ServerStatus.ACTIVE
            
        # Benachrichtige alle Clients
        notification = {
            'type': MessageType.NOTIFICATION,
            'notification_type': 'LEADER_CHANGED',
            'leader_id': leader_id,
            'message': f"New leader elected: {leader_id}"
        }
        self._broadcast_to_local_clients(notification)
        
    # ============================================
    # CLIENT CALLBACKS
    # ============================================
    
    def _on_client_joined(self, client_id: str, username: str):
        """Callback: Client ist beigetreten"""
        self.logger.info(f"👤 Client joined: {username}")
        
        # Sende Notification an alle Clients
        notification = {
            'type': MessageType.NOTIFICATION,
            'notification_type': 'USER_JOINED',
            'username': username,
            'message': f"{username} joined the chat"
        }
        self._broadcast_to_local_clients(notification)
        
        # Sende Message History an neuen Client
        history = self.message_handler.get_message_history()
        if history:
            history_msg = {
                'type': MessageType.MESSAGE_HISTORY,
                'messages': history[-50:]  # Letzte 50 Messages
            }
            self.client_handler.send_to_client(client_id, history_msg)
            
    def _on_client_left(self, client_id: str, username: str):
        """Callback: Client hat Chat verlassen"""
        self.logger.info(f"👤 Client left: {username}")
        
        # Sende Notification
        notification = {
            'type': MessageType.NOTIFICATION,
            'notification_type': 'USER_LEFT',
            'username': username,
            'message': f"{username} left the chat"
        }
        self._broadcast_to_local_clients(notification)
        
    def _on_client_message(self, message: Dict, client_id: str):
        """Callback: Client hat Message gesendet"""
        username = message.get('username', 'Unknown')
        content = message.get('content', '')
        
        self.logger.info(f"💬 {username}: {content[:50]}")
        
        # Weiterleiten an Message Handler
        self.message_handler.handle_client_message(message, client_id)
        
    def _broadcast_to_local_clients(self, message: Dict):
        """Sendet Message an alle lokalen Clients"""
        self.client_handler.broadcast_to_all_clients(message)
        
    def _forward_to_leader(self, leader_info: ServerInfo, message: Dict):
        """Forwarded Message zum Leader"""
        self._send_to_server(leader_info, message)
        
    # ============================================
    # HEARTBEAT
    # ============================================
    
    def _start_heartbeat(self):
        """Startet Heartbeat System"""
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
    def _heartbeat_loop(self):
        """Sendet periodisch Heartbeats zu Nachbarn"""
        while self.running:
            try:
                # Sende Heartbeat an rechten Nachbar
                if self.ring_manager.right_neighbor:
                    heartbeat_msg = {
                        'type': MessageType.HEARTBEAT,
                        'server_id': self.server_id,
                        'is_leader': self.ring_manager.is_leader(self.server_id)
                    }
                    self._send_to_server(self.ring_manager.right_neighbor, heartbeat_msg)
                    
                # Prüfe Timeouts
                self._check_heartbeat_timeouts()
                
            except Exception as e:
                self.logger.error(f"Error in heartbeat: {e}")
                
            time.sleep(HEARTBEAT_INTERVAL)
            
    def _handle_heartbeat(self, message: Dict):
        """Verarbeitet empfangenen Heartbeat"""
        server_id = message.get('server_id')
        
        # Update last seen
        self.last_heartbeat_received[server_id] = time.time()
        
    def _check_heartbeat_timeouts(self):
        """Prüft ob Server nicht mehr antworten (crashed)"""
        current_time = time.time()
        crashed_servers = []
        
        for server in self.ring_manager.get_all_servers():
            if server.server_id == self.server_id:
                continue
                
            last_seen = self.last_heartbeat_received.get(server.server_id, 0)
            
            if last_seen == 0:
                # Noch kein Heartbeat empfangen (neuer Server)
                self.last_heartbeat_received[server.server_id] = current_time
                continue
                
            if current_time - last_seen > HEARTBEAT_TIMEOUT:
                crashed_servers.append(server)
                
        # Handle Crashes
        for server in crashed_servers:
            self._handle_server_crash(server)
            
    def _handle_server_crash(self, server: ServerInfo):
        """
        Reagiert auf Server-Crash
        
        Args:
            server: Gecraschter Server
        """
        self.logger.warning(f"⚠️  Server crashed: {server.server_id}")
        
        # Entferne aus Ring
        self.ring_manager.remove_server(server.server_id)
        
        # Entferne Connection
        with self.connections_lock:
            if server.server_id in self.server_connections:
                try:
                    self.server_connections[server.server_id].close()
                except:
                    pass
                del self.server_connections[server.server_id]
                
        # Wenn Leader gecrasht ist -> Neue Election
        if server.is_leader:
            self.logger.warning("💥 LEADER CRASHED! Starting new election...")
            time.sleep(1)
            self.election.start_election("Leader crashed")
            
    # ============================================
    # MAIN LOOP
    # ============================================
    
    def _run(self):
        """Main Server Loop"""
        try:
            while self.running:
                time.sleep(1)
                
                # Status Output alle 30 Sekunden
                if int(time.time()) % 30 == 0:
                    self._print_status()
                    
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
            self.stop()
            
    def _print_status(self):
        """Gibt Server-Status aus"""
        is_leader = self.ring_manager.is_leader(self.server_id)
        status_emoji = "👑" if is_leader else "🔵"
        
        self.logger.info("=" * 50)
        self.logger.info(f"{status_emoji} Server: {self.server_id}")
        self.logger.info(f"   Status: {self.status}")
        self.logger.info(f"   Ring Size: {self.ring_manager.ring_size()}")
        self.logger.info(f"   Clients: {self.client_handler.client_count()}")
        self.logger.info(f"   Leader: {self.ring_manager.get_leader()}")
        self.logger.info("=" * 50)


# ============================================
# MAIN ENTRY POINT
# ============================================

def main():
    """Main Entry Point"""
    parser = argparse.ArgumentParser(description='GroupChat Ring Election Server')
    parser.add_argument('--id', type=str, help='Server ID', default=None)
    parser.add_argument('--port', type=int, help='Server Port', default=DEFAULT_SERVER_PORT_START)
    
    args = parser.parse_args()
    
    # Erstelle und starte Server
    server = Server(server_id=args.id, port=args.port)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        server.stop()


if __name__ == "__main__":
    main()