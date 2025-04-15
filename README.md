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
├── Dockerfile              # Docker configuration
├── .dockerignore          # Docker ignore rules
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

Glad it worked! Here's a clean, copy-paste-ready **Docker section** for your `README.md`:

---

## Dockerization

This project can be run inside a Docker container for portability and ease of setup.

### 🔧 Build the Docker Image

From the root of the project directory (where the `Dockerfile` is located), run:

```bash
docker build -t p2p-messenger .
```

### Run the Application

To run the P2P messaging app interactively:

```bash
docker run -it --rm p2p-messenger
```

You will be prompted to enter your nickname and can begin interacting with other peers.

### Run Unit Tests

To run the included unit tests inside Docker:

```bash
docker run --rm p2p-messenger python3 test_p2p.py
```





