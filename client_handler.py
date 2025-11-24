"""
Client Handler - Verwaltet Client-Verbindungen zum Server
"""
import socket
import threading
import json
from typing import Dict, Optional, Callable
from common.config import MessageType, BUFFER_SIZE
from common.protocol import deserialize_message, serialize_message, create_notification
from common.utils import setup_logging


class ClientConnection:
    """Repräsentiert eine Client-Verbindung"""
    
    def __init__(self, client_socket: socket.socket, address: tuple, client_id: str, username: str):
        self.socket = client_socket
        self.address = address
        self.client_id = client_id
        self.username = username
        self.connected = True
        
    def send(self, message: Dict):
        """Sendet Message an Client"""
        try:
            data = serialize_message(message)
            self.socket.sendall(data + b'\n')
            return True
        except Exception as e:
            print(f"Error sending to client {self.username}: {e}")
            self.connected = False
            return False
            
    def close(self):
        """Schließt Verbindung"""
        self.connected = False
        try:
            self.socket.close()
        except:
            pass


class ClientHandler:
    """
    Verwaltet alle Client-Verbindungen
    - Akzeptiert neue Clients
    - Empfängt Messages von Clients
    - Sendet Messages an Clients
    - Join/Leave Notifications
    """
    
    def __init__(self, server_id: str):
        self.server_id = server_id
        self.logger = setup_logging(f"ClientHandler-{server_id}")
        
        # Connected Clients (client_id -> ClientConnection)
        self.clients: Dict[str, ClientConnection] = {}
        self.clients_lock = threading.Lock()
        
        # Callbacks
        self.on_client_message: Optional[Callable] = None
        self.on_client_joined: Optional[Callable] = None
        self.on_client_left: Optional[Callable] = None
        
    def add_client(self, client_socket: socket.socket, address: tuple):
        """
        Fügt neuen Client hinzu
        
        Args:
            client_socket: Socket des Clients
            address: Client-Adresse
        """
        # Starte Thread für diesen Client
        thread = threading.Thread(
            target=self._handle_client,
            args=(client_socket, address),
            daemon=True
        )
        thread.start()
        
    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """
        Verarbeitet einen einzelnen Client
        
        Args:
            client_socket: Socket des Clients
            address: Client-Adresse
        """
        client_conn = None
        client_id = None
        username = None
        
        try:
            self.logger.info(f"New client connection from {address}")
            
            # Warte auf JOIN Message
            client_socket.settimeout(10.0)  # 10 Sekunden Timeout für JOIN
            data = client_socket.recv(BUFFER_SIZE)
            
            if not data:
                self.logger.warning("Client disconnected before sending JOIN")
                client_socket.close()
                return
                
            # Parse JOIN Message
            message = deserialize_message(data)
            if not message or message.get('type') != MessageType.CLIENT_JOIN:
                self.logger.warning("First message was not CLIENT_JOIN")
                client_socket.close()
                return
                
            client_id = message.get('client_id')
            username = message.get('username')
            
            self.logger.info(f"Client joined: {username} (ID: {client_id})")
            
            # Erstelle ClientConnection
            client_conn = ClientConnection(client_socket, address, client_id, username)
            
            # Speichere Client
            with self.clients_lock:
                self.clients[client_id] = client_conn
                
            # Callback: Client joined
            if self.on_client_joined:
                self.on_client_joined(client_id, username)
                
            # Sende Bestätigung
            welcome_msg = {
                'type': 'WELCOME',
                'message': f'Welcome to the chat, {username}!',
                'server_id': self.server_id
            }
            client_conn.send(welcome_msg)
            
            # Entferne Timeout
            client_socket.settimeout(None)
            
            # Empfange Messages von Client
            buffer = b''
            while client_conn.connected:
                try:
                    chunk = client_socket.recv(BUFFER_SIZE)
                    if not chunk:
                        # Client hat Verbindung geschlossen
                        break
                        
                    buffer += chunk
                    
                    # Verarbeite komplette Messages (getrennt durch \n)
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        
                        if line:
                            message = deserialize_message(line)
                            if message:
                                self._handle_client_message(client_id, message)
                                
                except socket.timeout:
                    continue
                except Exception as e:
                    self.logger.error(f"Error receiving from client {username}: {e}")
                    break
                    
        except Exception as e:
            self.logger.error(f"Error handling client: {e}")
            
        finally:
            # Client Cleanup
            if client_id:
                self.logger.info(f"Client disconnected: {username} (ID: {client_id})")
                
                with self.clients_lock:
                    if client_id in self.clients:
                        del self.clients[client_id]
                        
                # Callback: Client left
                if self.on_client_left:
                    self.on_client_left(client_id, username)
                    
            if client_conn:
                client_conn.close()
            else:
                try:
                    client_socket.close()
                except:
                    pass
                    
    def _handle_client_message(self, client_id: str, message: Dict):
        """
        Verarbeitet Message von Client
        
        Args:
            client_id: Client ID
            message: Empfangene Message
        """
        msg_type = message.get('type')
        
        if msg_type == MessageType.CHAT_MESSAGE:
            # Chat Message -> An Message Handler weiterleiten
            if self.on_client_message:
                self.on_client_message(message, client_id)
                
        elif msg_type == MessageType.CLIENT_LEAVE:
            # Client will explizit disconnecten
            with self.clients_lock:
                if client_id in self.clients:
                    self.clients[client_id].close()
                    
    def broadcast_to_all_clients(self, message: Dict):
        """
        Sendet Message an alle verbundenen Clients
        
        Args:
            message: Message zum Senden
        """
        with self.clients_lock:
            disconnected = []
            
            for client_id, client_conn in self.clients.items():
                if not client_conn.send(message):
                    disconnected.append(client_id)
                    
            # Entferne disconnected Clients
            for client_id in disconnected:
                del self.clients[client_id]
                
    def send_to_client(self, client_id: str, message: Dict) -> bool:
        """
        Sendet Message an spezifischen Client
        
        Args:
            client_id: Client ID
            message: Message
            
        Returns:
            True wenn erfolgreich
        """
        with self.clients_lock:
            if client_id in self.clients:
                return self.clients[client_id].send(message)
        return False
        
    def get_connected_clients(self) -> list:
        """Gibt Liste verbundener Clients zurück"""
        with self.clients_lock:
            return [
                {
                    'client_id': cid,
                    'username': conn.username,
                    'address': conn.address
                }
                for cid, conn in self.clients.items()
            ]
            
    def client_count(self) -> int:
        """Gibt Anzahl verbundener Clients zurück"""
        with self.clients_lock:
            return len(self.clients)
            
    def set_callbacks(self,
                     on_message: Callable = None,
                     on_joined: Callable = None,
                     on_left: Callable = None):
        """
        Setzt Callbacks
        
        Args:
            on_message: Callback(message, client_id) wenn Client Message sendet
            on_joined: Callback(client_id, username) wenn Client joint
            on_left: Callback(client_id, username) wenn Client leavt
        """
        if on_message:
            self.on_client_message = on_message
        if on_joined:
            self.on_client_joined = on_joined
        if on_left:
            self.on_client_left = on_left