"""
Protocol Definitions - Message Serialization/Deserialization
"""
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional


def create_message(msg_type: str, **kwargs) -> Dict[str, Any]:
    """
    Erstellt eine standardisierte Message mit Metadata
    
    Args:
        msg_type: Type der Message (siehe MessageType in config)
        **kwargs: Zusätzliche Felder für die Message
        
    Returns:
        Dictionary mit Message-Daten
    """
    message = {
        "type": msg_type,
        "message_id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        **kwargs
    }
    return message


def serialize_message(message: Dict[str, Any]) -> bytes:
    """
    Konvertiert Message Dict zu JSON bytes für Netzwerk-Übertragung
    
    Args:
        message: Message Dictionary
        
    Returns:
        UTF-8 encoded JSON bytes
    """
    json_str = json.dumps(message)
    return json_str.encode('utf-8')


def deserialize_message(data: bytes) -> Optional[Dict[str, Any]]:
    """
    Konvertiert empfangene bytes zu Message Dict
    
    Args:
        data: Empfangene bytes
        
    Returns:
        Message Dictionary oder None bei Fehler
    """
    try:
        json_str = data.decode('utf-8')
        return json.loads(json_str)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"Error deserializing message: {e}")
        return None


# ===========================
# DISCOVERY MESSAGES
# ===========================

def create_discovery_announce(server_id: str, ip: str, port: int) -> Dict:
    """Server announces its presence via UDP multicast"""
    return create_message(
        "DISCOVERY_ANNOUNCE",
        server_id=server_id,
        ip=ip,
        port=port
    )


def create_join_request(server_id: str, ip: str, port: int) -> Dict:
    """New server requests to join the ring"""
    return create_message(
        "JOIN_REQUEST",
        server_id=server_id,
        ip=ip,
        port=port
    )


def create_join_response(server_id: str, ring_info: list) -> Dict:
    """Existing server responds with ring topology"""
    return create_message(
        "JOIN_RESPONSE",
        server_id=server_id,
        ring_info=ring_info
    )


# ===========================
# ELECTION MESSAGES
# ===========================

def create_election_message(candidate_id: str, originator_id: str, hop_count: int = 0) -> Dict:
    """
    Election message für Chang-Roberts Algorithm
    
    Args:
        candidate_id: ID des aktuellen Kandidaten
        originator_id: ID des Servers der die Election gestartet hat
        hop_count: Anzahl der Hops im Ring
    """
    return create_message(
        "ELECTION",
        candidate_id=candidate_id,
        originator_id=originator_id,
        hop_count=hop_count
    )


def create_leader_announcement(leader_id: str, ring_topology: list = None) -> Dict:
    """
    Announcement des neuen Leaders
    
    Args:
        leader_id: ID des neuen Leaders
        ring_topology: Optional: Aktuelle Ring-Struktur
    """
    return create_message(
        "LEADER_ANNOUNCEMENT",
        leader_id=leader_id,
        ring_topology=ring_topology or []
    )


# ===========================
# CLIENT MESSAGES
# ===========================

def create_client_join(client_id: str, username: str) -> Dict:
    """Client joins the chat"""
    return create_message(
        "CLIENT_JOIN",
        client_id=client_id,
        username=username
    )


def create_client_leave(client_id: str, username: str) -> Dict:
    """Client leaves the chat"""
    return create_message(
        "CLIENT_LEAVE",
        client_id=client_id,
        username=username
    )


def create_chat_message(username: str, content: str, client_id: str = None) -> Dict:
    """User sends a chat message"""
    return create_message(
        "CHAT_MESSAGE",
        username=username,
        content=content,
        client_id=client_id
    )


# ===========================
# SERVER-SERVER MESSAGES
# ===========================

def create_forward_message(message: Dict, origin_server_id: str) -> Dict:
    """Leader forwards client message to other servers"""
    return create_message(
        "FORWARD_MESSAGE",
        original_message=message,
        origin_server_id=origin_server_id
    )


def create_heartbeat(server_id: str, is_leader: bool) -> Dict:
    """Server heartbeat message"""
    return create_message(
        "HEARTBEAT",
        server_id=server_id,
        is_leader=is_leader
    )


# ===========================
# NOTIFICATIONS
# ===========================

def create_notification(notification_type: str, **kwargs) -> Dict:
    """
    Generic notification message
    
    Args:
        notification_type: Type from NotificationType
        **kwargs: Additional notification data
    """
    return create_message(
        "NOTIFICATION",
        notification_type=notification_type,
        **kwargs
    )