"""
Terminal UI für Chat Client
"""
import sys
import threading
from datetime import datetime
from common.utils import setup_logging


class TerminalUI:
    """
    Einfache Terminal-basierte Chat-UI
    - Zeigt Messages an
    - Zeigt Notifications
    - Input-Handler
    """
    
    def __init__(self, username: str):
        self.username = username
        self.logger = setup_logging(f"UI-{username}", level=40)  # Nur ERROR
        
        # UI State
        self.running = False
        self.input_thread = None
        
        # Callbacks
        self.on_user_input = None
        
    def start(self):
        """Startet UI"""
        self.running = True
        self.print_welcome()
        
    def stop(self):
        """Stoppt UI"""
        self.running = False
        
    def print_welcome(self):
        """Zeigt Welcome Message"""
        print("=" * 60)
        print(f"   Welcome to GroupChat, {self.username}!")
        print("=" * 60)
        print("Commands:")
        print("  /help    - Show help")
        print("  /users   - Show connected users")
        print("  /quit    - Leave chat")
        print("=" * 60)
        print()
        
    def display_message(self, username: str, content: str, timestamp: str = None):
        """
        Zeigt Chat-Message an
        
        Args:
            username: Sender
            content: Message Content
            timestamp: Optional timestamp
        """
        if not timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
            
        # Eigene Messages anders formatieren
        if username == self.username:
            print(f"[{timestamp}] You: {content}")
        else:
            print(f"[{timestamp}] {username}: {content}")
        sys.stdout.flush()
        
    def display_notification(self, message: str, notification_type: str = "INFO"):
        """
        Zeigt System-Notification
        
        Args:
            message: Notification Message
            notification_type: Type (INFO, WARNING, ERROR)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if notification_type == "ERROR":
            print(f"[{timestamp}] ❌ {message}")
        elif notification_type == "WARNING":
            print(f"[{timestamp}] ⚠️  {message}")
        elif notification_type == "SUCCESS":
            print(f"[{timestamp}] ✅ {message}")
        else:
            print(f"[{timestamp}] ℹ️  {message}")
            
        sys.stdout.flush()
        
    def display_user_joined(self, username: str):
        """Zeigt User-Join-Notification"""
        self.display_notification(f"{username} joined the chat", "INFO")
        
    def display_user_left(self, username: str):
        """Zeigt User-Leave-Notification"""
        self.display_notification(f"{username} left the chat", "INFO")
        
    def display_leader_changed(self, leader_id: str):
        """Zeigt Leader-Change-Notification"""
        self.display_notification(f"New leader: {leader_id}", "INFO")
        
    def display_connection_status(self, connected: bool, server: str = None):
        """Zeigt Connection-Status"""
        if connected:
            self.display_notification(f"Connected to server: {server}", "SUCCESS")
        else:
            self.display_notification("Disconnected from server", "ERROR")
            
    def display_history(self, messages: list):
        """
        Zeigt Message History
        
        Args:
            messages: Liste von Messages
        """
        if not messages:
            return
            
        print("\n" + "=" * 60)
        print("   MESSAGE HISTORY")
        print("=" * 60)
        
        for msg in messages:
            username = msg.get('username', 'Unknown')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            
            # Parse timestamp
            try:
                dt = datetime.fromisoformat(timestamp)
                ts_str = dt.strftime("%H:%M:%S")
            except:
                ts_str = "??:??:??"
                
            self.display_message(username, content, ts_str)
            
        print("=" * 60)
        print()
        
    def display_error(self, error_msg: str):
        """Zeigt Error"""
        self.display_notification(error_msg, "ERROR")
        
    def display_help(self):
        """Zeigt Help"""
        print("\n" + "=" * 60)
        print("   HELP")
        print("=" * 60)
        print("Commands:")
        print("  /help    - Show this help")
        print("  /users   - Show connected users (not implemented)")
        print("  /quit    - Leave chat")
        print("\nJust type your message and press Enter to send!")
        print("=" * 60)
        print()
        
    def get_input_prompt(self) -> str:
        """Gibt Input-Prompt zurück"""
        return f"{self.username}> "
        
    def read_input(self):
        """
        Liest User-Input (blocking)
        
        Returns:
            User-Input String
        """
        try:
            prompt = self.get_input_prompt()
            user_input = input(prompt)
            return user_input.strip()
        except (EOFError, KeyboardInterrupt):
            return "/quit"
        except Exception as e:
            self.logger.error(f"Error reading input: {e}")
            return ""