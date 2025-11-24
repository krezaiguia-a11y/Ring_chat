"""
Connection Manager - Verwaltet Verbindung zum Server
"""
import socket
import threading
from typing import Optional, Callable
from queue import Queue
from common.config import BUFFER_SIZE, MessageType
from common.protocol import serialize_message, deserialize_message
from common.utils import setup_logging


class ConnectionManager:
    """
    Verwaltet TCP-Verbindung zum Server
    - Verbindung aufbauen
    - Messages senden/empfangen
    - Auto-Reconnect bei Disconnect
    """
    
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.logger = setup_logging(f"Connection-{client_id}")
        
        # Connection
        self.socket: Optional[socket.socket] = None
        self.server_address: tuple = None
        self.connected = False
        
        # Threads
        self.receive_thread = None
        self.running = False
        
        # Callbacks
        self.on_message_received: Optional[Callable] = None
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        
        # Send Queue
        self.send_queue = Queue()
        self.send_thread = None
        
    def connect(self, server_ip: str, server_port: int) -> bool:
        """
        Verbindet zum Server
        
        Args:
            server_ip: Server IP
            server_port: Server Port
            
        Returns:
            True wenn erfolgreich
        """
        try:
            self.logger.info(f"Connecting to server {server_ip}:{server_port}...")
            
            # Create Socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            
            # Connect
            self.socket.connect((server_ip, server_port))
            self.server_address = (server_ip, server_port)
            self.connected = True
            
            self.logger.info("✅ Connected to server!")
            
            # Start Threads
            self.running = True
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            
            self.receive_thread.start()
            self.send_thread.start()
            
            # Callback
            if self.on_connected:
                self.on_connected()
                
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            self.connected = False
            return False
            
    def disconnect(self):
        """Trennt Verbindung"""
        self.logger.info("Disconnecting from server...")
        self.running = False
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            
        # Callback
        if self.on_disconnected:
            self.on_disconnected()
            
    def send_message(self, message: dict):
        """
        Sendet Message zum Server
        
        Args:
            message: Message Dictionary
        """
        if not self.connected:
            self.logger.warning("Not connected - cannot send message")
            return
            
        # Add to send queue
        self.send_queue.put(message)
        
    def _send_loop(self):
        """Send Thread - Sendet Messages aus Queue"""
        while self.running:
            try:
                # Get message from queue (blocking with timeout)
                message = self.send_queue.get(timeout=1.0)
                
                if not self.connected:
                    continue
                    
                # Serialize and send
                data = serialize_message(message)
                self.socket.sendall(data + b'\n')
                
                self.logger.debug(f"Sent: {message.get('type')}")
                
            except Exception as e:
                if self.running and self.connected:
                    self.logger.error(f"Error sending message: {e}")
                    self._handle_disconnect()
                    
    def _receive_loop(self):
        """Receive Thread - Empfängt Messages vom Server"""
        buffer = b''
        
        while self.running and self.connected:
            try:
                # Receive data
                chunk = self.socket.recv(BUFFER_SIZE)
                
                if not chunk:
                    # Server closed connection
                    self.logger.warning("Server closed connection")
                    self._handle_disconnect()
                    break
                    
                buffer += chunk
                
                # Process complete messages (separated by \n)
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    
                    if line:
                        message = deserialize_message(line)
                        if message:
                            self._handle_received_message(message)
                            
            except socket.timeout:
                continue
            except Exception as e:
                if self.running and self.connected:
                    self.logger.error(f"Error receiving: {e}")
                    self._handle_disconnect()
                break
                
    def _handle_received_message(self, message: dict):
        """
        Verarbeitet empfangene Message
        
        Args:
            message: Empfangene Message
        """
        msg_type = message.get('type')
        self.logger.debug(f"Received: {msg_type}")
        
        # Callback
        if self.on_message_received:
            self.on_message_received(message)
            
    def _handle_disconnect(self):
        """Behandelt Disconnect"""
        if not self.connected:
            return
            
        self.logger.warning("Connection lost!")
        self.connected = False
        
        # Close socket
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            
        # Callback
        if self.on_disconnected:
            self.on_disconnected()
            
    def is_connected(self) -> bool:
        """Gibt Connection-Status zurück"""
        return self.connected
        
    def set_callbacks(self,
                     on_message: Callable = None,
                     on_connected: Callable = None,
                     on_disconnected: Callable = None):
        """
        Setzt Callbacks
        
        Args:
            on_message: Callback(message) wenn Message empfangen
            on_connected: Callback() wenn verbunden
            on_disconnected: Callback() wenn getrennt
        """
        if on_message:
            self.on_message_received = on_message
        if on_connected:
            self.on_connected = on_connected
        if on_disconnected:
            self.on_disconnected = on_disconnected