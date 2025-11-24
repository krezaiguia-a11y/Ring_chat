"""
Zentrale Konfiguration für GroupChat Ring Election
"""

# ===========================
# NETWORK CONFIGURATION
# ===========================

# UDP Multicast für Server Discovery
MULTICAST_GROUP = "239.255.0.1"
MULTICAST_PORT = 5000
DISCOVERY_INTERVAL = 3  # Sekunden

# TCP Server Ports
DEFAULT_SERVER_PORT_START = 8001

# ===========================
# TIMEOUTS & INTERVALS
# ===========================

# Heartbeat zwischen Servern
HEARTBEAT_INTERVAL = 2  # Sekunden zwischen Heartbeats
HEARTBEAT_TIMEOUT = 6   # Sekunden bis Server als tot gilt (3x Interval)

# Election
ELECTION_TIMEOUT = 10   # Sekunden für komplette Election
ELECTION_MESSAGE_DELAY = 0.5  # Delay beim Forwarding

# Client Reconnection
CLIENT_RECONNECT_INTERVAL = 2
CLIENT_RECONNECT_MAX_ATTEMPTS = 5

# ===========================
# MESSAGE TYPES
# ===========================

class MessageType:
    """Alle Message Types im System"""
    
    # Discovery (UDP)
    DISCOVERY_ANNOUNCE = "DISCOVERY_ANNOUNCE"
    JOIN_REQUEST = "JOIN_REQUEST"
    JOIN_RESPONSE = "JOIN_RESPONSE"
    
    # Election (TCP Ring)
    ELECTION = "ELECTION"
    LEADER_ANNOUNCEMENT = "LEADER_ANNOUNCEMENT"
    
    # Heartbeat (TCP)
    HEARTBEAT = "HEARTBEAT"
    HEARTBEAT_ACK = "HEARTBEAT_ACK"
    
    # Client-Server (TCP)
    CLIENT_JOIN = "CLIENT_JOIN"
    CLIENT_LEAVE = "CLIENT_LEAVE"
    CHAT_MESSAGE = "CHAT_MESSAGE"
    
    # Server-Server (TCP)
    FORWARD_MESSAGE = "FORWARD_MESSAGE"
    RING_UPDATE = "RING_UPDATE"
    
    # Notifications
    NOTIFICATION = "NOTIFICATION"
    MESSAGE_HISTORY = "MESSAGE_HISTORY"


class NotificationType:
    """Notification Types"""
    USER_JOINED = "USER_JOINED"
    USER_LEFT = "USER_LEFT"
    SERVER_JOINED = "SERVER_JOINED"
    SERVER_LEFT = "SERVER_LEFT"
    LEADER_CHANGED = "LEADER_CHANGED"


class ServerStatus:
    """Server Status States"""
    STARTING = "STARTING"
    DISCOVERING = "DISCOVERING"
    JOINING = "JOINING"
    ACTIVE = "ACTIVE"
    LEADER = "LEADER"
    ELECTION_IN_PROGRESS = "ELECTION_IN_PROGRESS"


# ===========================
# SYSTEM LIMITS
# ===========================

MAX_MESSAGE_SIZE = 4096
BUFFER_SIZE = 4096
MAX_MESSAGE_HISTORY = 1000
MAX_CLIENTS_PER_SERVER = 100

# ===========================
# LOGGING
# ===========================

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
LOG_DATE_FORMAT = '%H:%M:%S'