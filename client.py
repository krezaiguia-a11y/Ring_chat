"""
Main Client - Chat Client Application
"""
import uuid
import time
import argparse
from common.config import MessageType, NotificationType
from common.protocol import create_client_join, create_client_leave, create_chat_message
from common.utils import setup_logging
from client.connection import ConnectionManager
from client.ui import TerminalUI


class Client:
    """
    Chat Client
    
    - Verbindet zu Server
    - Sendet/Empfängt Messages
    - Terminal UI
    """
    
    def __init__(self, username: str):
        self.username = username
        self.client_id = str(uuid.uuid4())
        self.logger = setup_logging(f"Client-{username}")
        
        # Komponenten
        self.connection = ConnectionManager(self.client_id)
        self.ui = TerminalUI(username)
        
        # State
        self.running = False
        self.joined_chat = False
        
        # Setup Callbacks
        self._setup_callbacks()
        
    def _setup_callbacks(self):
        """Richtet Callbacks ein"""
        self.connection.set_callbacks(
            on_message=self._on_message_received,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected
        )
        
    def start(self, server_ip: str = "127.0.0.1", server_port: int = 8001):
        """
        Startet Client und verbindet zu Server
        
        Args:
            server_ip: Server IP
            server_port: Server Port
        """
        self.logger.info(f"Starting client for user: {self.username}")
        self.running = True
        
        # Start UI
        self.ui.start()
        
        # Connect to Server
        if not self.connection.connect(server_ip, server_port):
            self.ui.display_error("Failed to connect to server!")
            return
            
        # Send JOIN Message
        self._send_join()
        
        # Wait a bit for connection to establish
        time.sleep(0.5)
        
        # Main Input Loop
        self._input_loop()
        
    def stop(self):
        """Stoppt Client"""
        self.logger.info("Stopping client...")
        self.running = False
        
        # Send LEAVE Message
        if self.joined_chat:
            self._send_leave()
            time.sleep(0.5)  # Wait for message to send
            
        # Disconnect
        self.connection.disconnect()
        
        # Stop UI
        self.ui.stop()
        
        print("\n👋 Goodbye!\n")
        
    def _send_join(self):
        """Sendet JOIN Message"""
        join_msg = create_client_join(self.client_id, self.username)
        self.connection.send_message(join_msg)
        self.logger.info("Sent JOIN message")
        
    def _send_leave(self):
        """Sendet LEAVE Message"""
        leave_msg = create_client_leave(self.client_id, self.username)
        self.connection.send_message(leave_msg)
        self.logger.info("Sent LEAVE message")
        
    def _send_chat_message(self, content: str):
        """
        Sendet Chat Message
        
        Args:
            content: Message Content
        """
        if not content:
            return
            
        chat_msg = create_chat_message(
            username=self.username,
            content=content,
            client_id=self.client_id
        )
        self.connection.send_message(chat_msg)
        
    def _input_loop(self):
        """Main Input Loop"""
        while self.running:
            try:
                # Read user input
                user_input = self.ui.read_input()
                
                if not user_input:
                    continue
                    
                # Handle Commands
                if user_input.startswith('/'):
                    self._handle_command(user_input)
                else:
                    # Send as chat message
                    self._send_chat_message(user_input)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Error in input loop: {e}")
                
        self.stop()
        
    def _handle_command(self, command: str):
        """
        Verarbeitet Commands
        
        Args:
            command: Command String (z.B. "/quit")
        """
        cmd = command.lower().strip()
        
        if cmd == "/quit" or cmd == "/exit":
            self.running = False
            
        elif cmd == "/help":
            self.ui.display_help()
            
        elif cmd == "/users":
            self.ui.display_notification("User list not yet implemented", "INFO")
            
        else:
            self.ui.display_error(f"Unknown command: {command}")
            self.ui.display_notification("Type /help for available commands", "INFO")
            
    # ============================================
    # CALLBACKS
    # ============================================
    
    def _on_connected(self):
        """Callback: Verbunden mit Server"""
        self.logger.info("Connected callback")
        
    def _on_disconnected(self):
        """Callback: Verbindung getrennt"""
        self.ui.display_connection_status(False)
        self.logger.warning("Disconnected from server")
        
        # Exit input loop
        self.running = False
        
    def _on_message_received(self, message: dict):
        """
        Callback: Message vom Server empfangen
        
        Args:
            message: Empfangene Message
        """
        msg_type = message.get('type')
        
        if msg_type == "WELCOME":
            # Welcome Message vom Server
            self.joined_chat = True
            welcome_text = message.get('message', 'Welcome!')
            self.ui.display_notification(welcome_text, "SUCCESS")
            
        elif msg_type == MessageType.CHAT_MESSAGE:
            # Chat Message
            username = message.get('username')
            content = message.get('content')
            timestamp = message.get('timestamp')
            
            self.ui.display_message(username, content, timestamp)
            
        elif msg_type == MessageType.NOTIFICATION:
            # Notification
            self._handle_notification(message)
            
        elif msg_type == MessageType.MESSAGE_HISTORY:
            # Message History
            messages = message.get('messages', [])
            self.ui.display_history(messages)
            
        else:
            self.logger.debug(f"Received unknown message type: {msg_type}")
            
    def _handle_notification(self, message: dict):
        """
        Verarbeitet Notifications
        
        Args:
            message: Notification Message
        """
        notif_type = message.get('notification_type')
        
        if notif_type == NotificationType.USER_JOINED:
            username = message.get('username')
            self.ui.display_user_joined(username)
            
        elif notif_type == NotificationType.USER_LEFT:
            username = message.get('username')
            self.ui.display_user_left(username)
            
        elif notif_type == NotificationType.LEADER_CHANGED:
            leader_id = message.get('leader_id')
            self.ui.display_leader_changed(leader_id)
            
        else:
            # Generic notification
            msg = message.get('message', 'Notification')
            self.ui.display_notification(msg, "INFO")


# ============================================
# MAIN ENTRY POINT
# ============================================

def main():
    """Main Entry Point"""
    parser = argparse.ArgumentParser(description='GroupChat Ring Election Client')
    parser.add_argument('--username', type=str, help='Your username', required=True)
    parser.add_argument('--server', type=str, help='Server IP', default='127.0.0.1')
    parser.add_argument('--port', type=int, help='Server Port', default=8001)
    
    args = parser.parse_args()
    
    # Erstelle und starte Client
    client = Client(username=args.username)
    
    try:
        client.start(server_ip=args.server, server_port=args.port)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        client.stop()


if __name__ == "__main__":
    main()