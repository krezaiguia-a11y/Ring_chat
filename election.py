"""
Election Service - Chang-Roberts Ring Election Algorithm
"""
import threading
import time
from typing import Optional, Callable
from common.config import MessageType, ELECTION_TIMEOUT, ELECTION_MESSAGE_DELAY
from common.protocol import create_election_message, create_leader_announcement
from common.utils import setup_logging


class ElectionService:
    """
    Implementiert Chang-Roberts Election Algorithm
    
    Ablauf:
    1. Server startet Election mit eigener ID als Kandidat
    2. Election-Message wird im Ring weitergegeben
    3. Jeder Server vergleicht: Ist empfangene ID > eigene ID?
       - JA: Forward mit höherer ID
       - NEIN: Forward mit eigener ID
    4. Wenn Message zurück zum Originator kommt:
       - Höchste ID im Ring wird Leader
    """
    
    def __init__(self, server_id: str, ring_manager):
        self.server_id = server_id
        self.ring_manager = ring_manager
        self.logger = setup_logging(f"Election-{server_id}")
        
        # Election State
        self.election_in_progress = False
        self.election_lock = threading.Lock()
        
        # Aktuelle Election Info
        self.current_election_id = None
        self.current_candidate_id = None
        self.election_originator = None
        
        # Callbacks
        self.on_leader_elected: Optional[Callable] = None
        self.send_to_neighbor: Optional[Callable] = None  # Callback zum Senden an rechten Nachbar
        
        # Election Timeout Thread
        self.election_timer = None
        
    def start_election(self, reason: str = "Manual trigger"):
        """
        Startet eine neue Election
        
        Args:
            reason: Grund für die Election (für Logging)
        """
        # ========== FIX 1: Prüfe ob wir Nachbarn haben ==========
        if self.ring_manager.right_neighbor is None:
            self.logger.info("🤷 Cannot start election - no neighbors in ring")
            self.logger.info("👑 Declaring myself as leader")
            self.ring_manager.set_leader(self.server_id)
            if self.on_leader_elected:
                self.on_leader_elected(self.server_id)
            return
        # ========== ENDE FIX 1 ==========
        
        with self.election_lock:
            if self.election_in_progress:
                self.logger.warning("Election already in progress, ignoring start request")
                return
                
            self.logger.info(f"🗳️  Starting election - Reason: {reason}")
            self.election_in_progress = True
            
            # Generiere Election ID (timestamp)
            self.current_election_id = int(time.time() * 1000)
            self.current_candidate_id = self.server_id
            self.election_originator = self.server_id
            
            # Starte Election Timeout
            self._start_election_timer()
            
            # Sende Election Message an rechten Nachbar
            self._send_election_message(
                candidate_id=self.server_id,
                originator_id=self.server_id,
                hop_count=0
            )
            
    def handle_election_message(self, message: dict):
        """
        Verarbeitet empfangene Election Message
        
        Args:
            message: Election Message Dictionary
        """
        candidate_id = message.get('candidate_id')
        originator_id = message.get('originator_id')
        hop_count = message.get('hop_count', 0)
        
        self.logger.debug(f"Received ELECTION: candidate={candidate_id}, originator={originator_id}, hops={hop_count}")
        
        # Professional Fallback: Prüfe ob Ring bereit ist
        if self.ring_manager.right_neighbor is None:
            self.logger.warning("Ring not ready yet (no right neighbor), buffering election message")
            # Versuche es später nochmal
            def retry_election():
                time.sleep(2)
                if self.ring_manager.right_neighbor is not None:
                    self.logger.info("Ring now ready, re-processing election message")
                    self.handle_election_message(message)
                else:
                    self.logger.error("Ring still not ready after 2s, dropping election message")
            threading.Thread(target=retry_election, daemon=True).start()
            return
        
        with self.election_lock:
            # Wenn wir noch keine Election haben, starten wir eine
            if not self.election_in_progress:
                self.logger.info("Received election message, joining election")
                self.election_in_progress = True
                self.current_election_id = message.get('message_id')
                self._start_election_timer()
            
            # Prüfe: Ist Message zurück zum Originator?
            if originator_id == self.server_id:
                # Election ist komplett durch den Ring gelaufen
                self.logger.info(f"🎉 Election complete! Winner: {candidate_id}")
                self._complete_election(candidate_id)
                return
                
            # Chang-Roberts Logic: Vergleiche IDs
            if candidate_id > self.server_id:
                # Empfangener Kandidat ist besser, forward ihn
                self.logger.debug(f"Forwarding {candidate_id} (better than {self.server_id})")
                self._send_election_message(candidate_id, originator_id, hop_count + 1)
                
            elif candidate_id < self.server_id:
                # Wir sind besser, ersetze Kandidaten
                self.logger.debug(f"Replacing {candidate_id} with {self.server_id} (we're better)")
                self._send_election_message(self.server_id, originator_id, hop_count + 1)
                
            else:
                # Gleiche ID (sollte nicht passieren)
                self.logger.warning(f"Same candidate ID: {candidate_id}")
                self._send_election_message(candidate_id, originator_id, hop_count + 1)
                
    def handle_leader_announcement(self, message: dict):
        """
        Verarbeitet Leader Announcement
        
        Args:
            message: Leader Announcement Message
        """
        leader_id = message.get('leader_id')
        self.logger.info(f"👑 New leader announced: {leader_id}")
        
        with self.election_lock:
            # Setze Leader im Ring Manager
            self.ring_manager.set_leader(leader_id)
            
            # Beende Election
            self.election_in_progress = False
            self._cancel_election_timer()
            
            # Callback
            if self.on_leader_elected:
                self.on_leader_elected(leader_id)
                
            # Forward Announcement weiter (damit alle Server es bekommen)
            if leader_id != self.server_id:
                # Nur forwarden wenn wir nicht der Leader sind
                # (Leader sendet initial, dann einmal rum)
                time.sleep(ELECTION_MESSAGE_DELAY)
                self._forward_leader_announcement(leader_id)
                
    def _complete_election(self, winner_id: str):
        """
        Schließt Election ab - Winner wird Leader
        
        Args:
            winner_id: ID des Gewinners
        """
        self.logger.info(f"Election completed. Winner: {winner_id}")
        
        # Setze Leader
        self.ring_manager.set_leader(winner_id)
        
        # Sende Leader Announcement durch den Ring
        self._announce_leader(winner_id)
        
        # Election beendet
        self.election_in_progress = False
        self._cancel_election_timer()
        
        # Callback
        if self.on_leader_elected:
            self.on_leader_elected(winner_id)
            
    def _send_election_message(self, candidate_id: str, originator_id: str, hop_count: int):
        """Sendet Election Message an rechten Nachbar"""
        if not self.ring_manager.right_neighbor:
            self.logger.warning("No right neighbor to send election message")
            return
            
        message = create_election_message(
            candidate_id=candidate_id,
            originator_id=originator_id,
            hop_count=hop_count
        )
        
        # Kleines Delay um Race Conditions zu vermeiden
        time.sleep(ELECTION_MESSAGE_DELAY)
        
        if self.send_to_neighbor:
            self.send_to_neighbor(self.ring_manager.right_neighbor, message)
            
    def _announce_leader(self, leader_id: str):
        """Sendet Leader Announcement an rechten Nachbar"""
        if not self.ring_manager.right_neighbor:
            self.logger.warning("No right neighbor for leader announcement")
            return
            
        message = create_leader_announcement(
            leader_id=leader_id,
            ring_topology=self.ring_manager.get_ring_topology()
        )
        
        if self.send_to_neighbor:
            self.send_to_neighbor(self.ring_manager.right_neighbor, message)
            
    def _forward_leader_announcement(self, leader_id: str):
        """Forwarded Leader Announcement weiter"""
        self._announce_leader(leader_id)
        
    def _start_election_timer(self):
        """Startet Election Timeout Timer"""
        self._cancel_election_timer()
        
        def timeout_handler():
            self.logger.error("⏰ Election timeout!")
            with self.election_lock:
                self.election_in_progress = False
                
            # ========== FIX 2: Prüfe ob wir Nachbarn haben ==========
            if self.ring_manager.right_neighbor is None:
                self.logger.warning("No neighbors - canceling election restart")
                self.ring_manager.set_leader(self.server_id)
                if self.on_leader_elected:
                    self.on_leader_elected(self.server_id)
                return
            # ========== ENDE FIX 2 ==========
                
            # Starte neue Election
            self.logger.info("Restarting election...")
            time.sleep(1)
            self.start_election("Election timeout")
            
        self.election_timer = threading.Timer(ELECTION_TIMEOUT, timeout_handler)
        self.election_timer.daemon = True
        self.election_timer.start()
        
    def _cancel_election_timer(self):
        """Bricht Election Timer ab"""
        if self.election_timer:
            self.election_timer.cancel()
            self.election_timer = None
            
    def set_send_callback(self, callback: Callable):
        """
        Setzt Callback zum Senden von Messages an Nachbarn
        
        Args:
            callback: Funktion(server_info, message)
        """
        self.send_to_neighbor = callback
        
    def set_leader_elected_callback(self, callback: Callable):
        """
        Setzt Callback für Leader-Wahl
        
        Args:
            callback: Funktion(leader_id)
        """
        self.on_leader_elected = callback
        
    def is_election_in_progress(self) -> bool:
        """Gibt zurück ob Election läuft"""
        with self.election_lock:
            return self.election_in_progress