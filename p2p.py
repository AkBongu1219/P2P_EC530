import socket
import threading
import argparse
import sqlite3
import datetime
import time
import platform
import subprocess

# Modified notify_user function to work on macOS using osascript.
def notify_user(title, message):
    if platform.system() == "Darwin":
        script = f'display notification "{message}" with title "{title}"'
        subprocess.call(["osascript", "-e", script])
    else:
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="P2P Chat",
                timeout=5  # Notification stays for 5 seconds
            )
        except Exception as e:
            print("Notification error:", e)

class MessageDB:
    def __init__(self, db_file="messages.db"):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.create_table()
        self.create_scheduled_table()

    def create_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            sender TEXT,
            receiver TEXT,
            status TEXT,
            message TEXT
        )
        """
        self.conn.execute(query)
        self.conn.commit()

    def create_scheduled_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS scheduled_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheduled_timestamp TEXT,
            sender TEXT,
            receiver TEXT,
            target_host TEXT,
            target_port INTEGER,
            message TEXT,
            status TEXT
        )
        """
        self.conn.execute(query)
        self.conn.commit()

    def insert_message(self, sender, receiver, status, message):
        timestamp = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
        query = """
        INSERT INTO messages (timestamp, sender, receiver, status, message)
        VALUES (?, ?, ?, ?, ?)
        """
        cur = self.conn.cursor()
        cur.execute(query, (timestamp, sender, receiver, status, message))
        self.conn.commit()
        return cur.lastrowid

    def get_pending_messages(self, receiver):
        query = """
        SELECT id, sender, receiver, status, message FROM messages
        WHERE receiver = ? AND (status = 'pending' OR status = 'failed')
        """
        cur = self.conn.cursor()
        cur.execute(query, (receiver,))
        return cur.fetchall()

    def update_message_status(self, message_id, status):
        query = "UPDATE messages SET status = ? WHERE id = ?"
        self.conn.execute(query, (status, message_id))
        self.conn.commit()

    # Methods for scheduled messages.
    def insert_scheduled_message(self, sender, receiver, target_host, target_port, scheduled_timestamp, message, status):
        query = """
        INSERT INTO scheduled_messages (scheduled_timestamp, sender, receiver, target_host, target_port, message, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cur = self.conn.cursor()
        cur.execute(query, (scheduled_timestamp, sender, receiver, target_host, target_port, message, status))
        self.conn.commit()
        return cur.lastrowid

    def get_due_scheduled_messages(self, current_time):
        query = """
        SELECT id, scheduled_timestamp, sender, receiver, target_host, target_port, message, status
        FROM scheduled_messages
        WHERE scheduled_timestamp <= ? AND status = 'scheduled'
        """
        cur = self.conn.cursor()
        cur.execute(query, (current_time,))
        return cur.fetchall()

    def update_scheduled_message_status(self, message_id, status):
        query = "UPDATE scheduled_messages SET status = ? WHERE id = ?"
        self.conn.execute(query, (status, message_id))
        self.conn.commit()

    def close(self):
        self.conn.close()

class Peer:
    def __init__(self, host, port, nickname):
        self.host = host
        self.port = port  # If port is 0, the OS will auto-assign a free port.
        self.nickname = nickname
        self.running = True
        self.db = MessageDB()

    def start(self):
        threading.Thread(target=self.server_thread, daemon=True).start()
        threading.Thread(target=self.check_scheduled_messages, daemon=True).start()

    def server_thread(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((self.host, self.port))
                self.port = s.getsockname()[1]
            except OSError as e:
                print(f"[Server] Failed to bind to {self.host}:{self.port}. Error: {e}")
                return
            s.listen()
            print(f"[Server] Listening on {self.host}:{self.port}")
            while self.running:
                try:
                    conn, addr = s.accept()
                    threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
                except Exception as e:
                    print(f"[Server] Exception: {e}")
                    break

    def handle_client(self, conn, addr):
        with conn:
            print(f"[Server] Connected by {addr}")
            try:
                data = conn.recv(1024)
                if not data:
                    return
                message = data.decode()
                print(message)
                # Trigger desktop notification.
                notify_user("New Message", message)
                # Auto acknowledgment if the message is not already an ACK.
                if not message.startswith("ACK:"):
                    ack_message = "ACK: Message received"
                    try:
                        conn.sendall(ack_message.encode())
                    except Exception as e:
                        print(f"[Server] Failed to send ack: {e}")
                # Store the received message.
                if ": " in message:
                    sender, actual_text = message.split(": ", 1)
                else:
                    sender = "Unknown"
                    actual_text = message
                self.db.insert_message(sender, self.nickname, "received", actual_text)
            except Exception as e:
                print(f"[Server] Error handling client {addr}: {e}")

    def send_message(self, target_host, target_port, message_text, receiver_nickname):
        full_message = f"{self.nickname}: {message_text}"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((target_host, target_port))
                s.sendall(full_message.encode())
                # Wait for acknowledgment.
                ack = s.recv(1024)
                if ack:
                    ack_message = ack.decode()
                    print(f"[Client] Received acknowledgment: {ack_message}")
            print(f"[Client] Message sent to {target_host}:{target_port}")
            self.db.insert_message(self.nickname, receiver_nickname, "sent", message_text)
            return True
        except Exception as e:
            print(f"[Client] Error sending message to {target_host}:{target_port}: {e}")
            self.db.insert_message(self.nickname, receiver_nickname, "pending", message_text)
            return False

    def resend_pending_messages(self, target_host, target_port, target_nickname):
        pending_messages = self.db.get_pending_messages(target_nickname)
        if pending_messages:
            print(f"[Offline] Attempting to resend {len(pending_messages)} pending message(s) to {target_nickname}...")
        for msg in pending_messages:
            msg_id, sender, receiver, status, message_text = msg
            full_message = f"{self.nickname}: {message_text}"
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((target_host, target_port))
                    s.sendall(full_message.encode())
                    ack = s.recv(1024)
                    if ack:
                        ack_message = ack.decode()
                        print(f"[Offline] Received acknowledgment for message ID {msg_id}: {ack_message}")
                print(f"[Offline] Resent message ID {msg_id} successfully.")
                self.db.update_message_status(msg_id, "sent")
            except Exception as e:
                print(f"[Offline] Failed to resend message ID {msg_id}: {e}")

    def schedule_message(self, target_host, target_port, target_nickname, scheduled_timestamp, message_text):
        self.db.insert_scheduled_message(self.nickname, target_nickname, target_host, target_port, scheduled_timestamp, message_text, "scheduled")

    def check_scheduled_messages(self):
        while self.running:
            current_time = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
            due_messages = self.db.get_due_scheduled_messages(current_time)
            for msg in due_messages:
                msg_id, scheduled_timestamp, sender, receiver, target_host, target_port, message_text, status = msg
                print(f"[Scheduled] Attempting to send scheduled message ID {msg_id} to {receiver} (scheduled at {scheduled_timestamp})")
                success = self.send_message(target_host, target_port, message_text, receiver)
                if success:
                    self.db.update_scheduled_message_status(msg_id, "sent")
            time.sleep(10)

    def stop(self):
        self.running = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.host, self.port))
                s.close()
        except Exception:
            pass
        self.db.close()

def main():
    parser = argparse.ArgumentParser(description="P2P Chat Application with Notifications, Auto Ack, and Scheduled Messages")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP to bind the peer server (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0, help="Port to bind the peer server (default: auto-assigned)")
    args = parser.parse_args()

    nickname = input("Enter your nickname: ").strip()
    if not nickname:
        print("You must provide a nickname. Exiting.")
        return

    peer = Peer(args.host, args.port, nickname)
    peer.start()

    print("Commands:")
    print("  connect <target_host> <target_port>         - Connect to a peer for messaging")
    print("  disconnect                                  - Disconnect current connection")
    print("  schedule <target_host> <target_port> <target_nickname> <YYYY-MM-DD HH:MM:SS> <message>")
    print("                                              - Schedule a message for future delivery")
    print("  myport                                      - Display this peer's port")
    print("  quit                                        - Exit the application")
    print("Once connected, simply type your message and press Enter to send it.")

    current_target = None
    current_target_nickname = None

    try:
        while True:
            user_input = input(">> ").strip()
            if user_input.lower() == "quit":
                break
            if user_input.lower() == "myport":
                print(f"My port is: {peer.port}")
                continue
            parts = user_input.split()
            if parts and parts[0].lower() == "connect":
                if len(parts) != 3:
                    print("Invalid command. Usage: connect <target_host> <target_port>")
                    continue
                target_host = parts[1]
                try:
                    target_port = int(parts[2])
                except ValueError:
                    print("Invalid port number. Please provide a numeric value.")
                    continue
                target_nickname = input("Enter target's nickname: ").strip()
                current_target = (target_host, target_port)
                current_target_nickname = target_nickname
                print(f"Connected to {target_host}:{target_port} ({target_nickname}). Now type your messages directly.")
                peer.resend_pending_messages(target_host, target_port, target_nickname)
                continue
            if parts and parts[0].lower() == "disconnect":
                current_target = None
                current_target_nickname = None
                print("Disconnected from the current peer.")
                continue
            if parts and parts[0].lower() == "schedule":
                # Expected format: schedule <target_host> <target_port> <target_nickname> <YYYY-MM-DD HH:MM:SS> <message>
                if len(parts) < 6:
                    print("Invalid command. Usage: schedule <target_host> <target_port> <target_nickname> <YYYY-MM-DD HH:MM:SS> <message>")
                    continue
                target_host = parts[1]
                try:
                    target_port = int(parts[2])
                except ValueError:
                    print("Invalid port number. Please provide a numeric value.")
                    continue
                target_nickname = parts[3]
                scheduled_time_str = parts[4]
                message_text = " ".join(parts[5:])
                try:
                    scheduled_time = datetime.datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M:%S")
                    scheduled_time_str = scheduled_time.isoformat(sep=' ', timespec='seconds')
                except Exception as e:
                    print("Invalid scheduled time format. Please use YYYY-MM-DD HH:MM:SS")
                    continue
                peer.schedule_message(target_host, target_port, target_nickname, scheduled_time_str, message_text)
                print(f"Scheduled message for {target_nickname} at {scheduled_time_str}")
                continue
            if current_target:
                peer.send_message(current_target[0], current_target[1], user_input, current_target_nickname)
            else:
                print("No active connection. Use 'connect <target_host> <target_port>' to connect to a peer.")
    except KeyboardInterrupt:
        print("\nExiting...")

    peer.stop()
    print("Peer stopped.")

if __name__ == "__main__":
    main()