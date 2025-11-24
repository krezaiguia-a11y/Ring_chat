# GroupChat Ring Election - Distributed Chat System

Ein verteiltes Gruppen-Chat-System mit Ring-Topologie und automatischer Leader-Wahl basierend auf dem Chang-Roberts Algorithmus.

## 🎯 Features

- 🔄 **Ring-Topologie**: Server organisieren sich automatisch in einem Ring
- 👑 **Leader Election**: Chang-Roberts Algorithmus für automatische Leader-Wahl
- 🔍 **Auto-Discovery**: UDP Multicast für automatisches Server-Finding
- 💪 **Fault Tolerance**: Automatische Re-Election bei Server-Crash
- 💬 **Group Chat**: Multi-Client Chat über verteilte Server
- 📡 **Dynamic Join**: Server können zur Laufzeit beitreten

## 📁 Projektstruktur
```
groupchat-ring-election/
├── server/              # Server-Komponenten
│   ├── server.py        # Haupt-Server
│   ├── discovery.py     # UDP Multicast Discovery
│   ├── election.py      # Chang-Roberts Election
│   ├── ring_manager.py  # Ring-Topologie Management
│   ├── message_handler.py  # Message Routing
│   └── client_handler.py   # Client Connections
├── client/              # Client-Komponenten
│   ├── client.py        # Haupt-Client
│   ├── connection.py    # Server Connection
│   └── ui.py           # Terminal UI
├── common/              # Gemeinsame Module
│   ├── config.py        # Konfiguration
│   ├── protocol.py      # Message Protokoll
│   └── utils.py         # Hilfsfunktionen
└── tests/               # Unit Tests
```

## 🚀 Installation
```bash
# Python 3.10+ erforderlich
cd groupchat-ring-election

# Optional: Virtual Environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Dependencies installieren (optional)
pip install -r requirements.txt
```

## 💻 Quick Start

### Variante 1: Manuell (empfohlen für Testing)

**Terminal 1: Server 1**
```bash
python -m server.server --id server1 --port 8001
```

**Terminal 2: Server 2**
```bash
python -m server.server --id server2 --port 8002
```

**Terminal 3: Server 3**
```bash
python -m server.server --id server3 --port 8003
```

**Terminal 4: Client Alice**
```bash
python -m client.client --username Alice --server 127.0.0.1 --port 8001
```

**Terminal 5: Client Bob**
```bash
python -m client.client --username Bob --server 127.0.0.1 --port 8002
```

### Variante 2: Automatisch (noch zu implementieren)
```bash
./scripts/start_demo.sh
```

## 🧪 Testing

### Leader Crash testen

1. Starte 3 Server + 2 Clients
2. Identifiziere Leader (👑 im Log)
3. Drücke `Ctrl+C` im Leader-Terminal
4. Beobachte:
   - Automatische Election
   - Neuer Leader wird gewählt
   - Chat läuft weiter!

### Server zur Laufzeit hinzufügen

1. Starte 2 Server + Clients
2. Starte 3. Server während Chat läuft
3. Beobachte:
   - Server wird automatisch entdeckt
   - Ring wird erweitert
   - Neue Election wird gestartet

## 🏗️ Architektur

### System-Übersicht
```
Clients → TCP → Leader Server → Ring (TCP) → All Servers → Local Clients
                     ↓
              UDP Multicast (Discovery)
```

### Komponenten

#### Server
- **Discovery Service**: UDP Multicast für Server-Finding
- **Ring Manager**: Verwaltet Ring-Topologie und Nachbarn
- **Election Service**: Chang-Roberts Election Algorithm
- **Message Handler**: Routing und Distribution von Chat-Messages
- **Client Handler**: Verwaltet Client-Verbindungen

#### Client
- **Connection Manager**: TCP-Verbindung zum Server
- **Terminal UI**: Einfache Chat-Interface
- **Message Handler**: Verarbeitet empfangene Messages

### Protokoll

#### Discovery (UDP Multicast)
```json
{
  "type": "DISCOVERY_ANNOUNCE",
  "server_id": "server-8001",
  "ip": "192.168.1.100",
  "port": 8001
}
```

#### Election (TCP Ring)
```json
{
  "type": "ELECTION",
  "candidate_id": "server-8003",
  "originator_id": "server-8001",
  "hop_count": 2
}
```

#### Chat Message
```json
{
  "type": "CHAT_MESSAGE",
  "username": "Alice",
  "content": "Hello World!",
  "timestamp": "2025-11-15T10:30:00Z"
}
```

## ⚙️ Konfiguration

Siehe `common/config.py` für alle Einstellungen:

- **MULTICAST_GROUP**: `239.255.0.1`
- **MULTICAST_PORT**: `5000`
- **HEARTBEAT_INTERVAL**: `2` Sekunden
- **ELECTION_TIMEOUT**: `10` Sekunden

## 📊 Implementierungs-Status

- [x] Phase 1: Basis Server/Client
- [x] Phase 2: UDP Discovery
- [x] Phase 3: Ring Topology
- [x] Phase 4: Election Algorithm
- [x] Phase 5: Message Distribution
- [x] Phase 6: Fault Tolerance
- [ ] Phase 7: Testing & Polish
- [ ] Phase 8: Dokumentation

## 👥 Team

- Mustafa Atas
- Haben Welday
- Karim Rezaiguia
- Nihat Özbek

**Gruppe 22 - Semester 1**

## 📝 Lizenz

Hochschulprojekt - Keine öffentliche Lizenz