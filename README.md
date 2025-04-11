# Peer-to-Peer Messaging System

This Python project implements a local Peer-to-Peer (P2P) messaging system with integrated offline handling and automation features. Each peer can send, receive, and schedule messages seamlessly over a local network.

## Features

- **P2P Communication:**  
  Real-time messaging between multiple peers running locally.

- **SQLite Database Integration:**  
  Messages are persistently stored in a local SQLite database with details such as timestamps, sender, receiver, status, and message content.

- **Offline Support:**  
  Messages sent to offline peers are automatically queued and delivered once the peer reconnects.

- **Message Automation and Scheduling:**  
  Schedule messages for future delivery at specific dates and times.

- **Notification Support:**  
  Desktop notifications for incoming messages (macOS and cross-platform via plyer).

## Files and Structure
```bash
├── p2p.py              # Main P2P messaging implementation
├── test_p2p.py         # Unit tests for the messaging system
├── requirements.txt         # Dependencies
├── messages.db         # SQLite database file (generated automatically)
├── setup.py         # Allows for local pip installation
```
## Getting started

- Python 3.7+
- pip install -r requirements.txt

## Usage

 - python p2p.py
 - Follow terminal instructions

## Install via PIP (Local)

You can also install the package locally:

```bash
python -m build
pip install dist/p2p_ec530-0.1.0-py3-none-any.whl
```

Then run the CLI with:

```bash
p2p-cli
```
Follow terminal instructions




