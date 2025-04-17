import socket
import threading
import argparse
import sqlite3
import datetime
import time
import platform
import subprocess
import redis
import json

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
    def __init__(self, host, port, nickname, redis_host, redis_port):
        self.host = host
        self.port = port
        self.nickname = nickname
        self.running = True
        self.db = MessageDB()

        # Redis setup for pub/sub (use redis_host and redis_port to allow cross-laptop communication)
        self.redis = redis.Redis(host=redis_host, port=redis_port, db=0)
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.subscribed_topics = set()
        
        # For handling legacy P2P messages
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((host, port))
        self.port = self.socket.getsockname()[1]  # Get the actual port if port=0 was used
        self.socket.listen(5)

    def start(self):
        threading.Thread(target=self.server_thread, daemon=True).start()
        threading.Thread(target=self.check_scheduled_messages, daemon=True).start()
        threading.Thread(target=self.redis_listener_thread, daemon=True).start()

    def redis_listener_thread(self):
        print(f"Redis listener started for {self.nickname}")
        while self.running:
            message = self.pubsub.get_message()
            if message and message['type'] == 'message':
                channel = message['channel'].decode()
                try:
                    data = json.loads(message['data'].decode())
                    if data.get('type') == 'publish' and data.get('from') != self.nickname:
                        sender = data.get('from')
                        text = data.get('message')
                        print(f"\n[Redis] ({channel}) {sender}: {text}")
                        notify_user(f"New message on {channel}", f"{sender}: {text}")
                        self.db.insert_message(sender, channel, 'received', text)
                        print(">> ", end="", flush=True)  # Restore prompt
                except Exception as e:
                    print(f"Error processing Redis message: {e}")
            time.sleep(0.1)  # Small sleep to prevent CPU hogging

    def subscribe_topic(self, topic):
        if topic not in self.subscribed_topics:
            self.pubsub.subscribe(topic)
            self.subscribed_topics.add(topic)
            cmd = json.dumps({'type':'subscribe','topic':topic,'from':self.nickname})
            self.redis.publish(topic, cmd)
            print(f"Subscribed to topic: {topic}")

    def publish_topic(self, topic, message):
        cmd = json.dumps({'type':'publish','topic':topic,'from':self.nickname,'message':message})
        self.redis.publish(topic, cmd)
        self.db.insert_message(self.nickname, topic, 'sent', message)
        print(f"Published message to {topic}")

    def list_topics(self):
        channels = self.redis.execute_command('PUBSUB CHANNELS') or []
        print("Active topics:")
        for ch in channels:
            print(f" - {ch.decode()}")

    def list_listeners(self, topic):
        num = self.redis.execute_command('PUBSUB NUMSUB', topic)[1]
        print(f"Subscribers on {topic}: {num}")

    def server_thread(self):
        print(f"P2P server started on port {self.port}")
        while self.running:
            try:
                client, addr = self.socket.accept()
                threading.Thread(target=self.handle_client, args=(client, addr), daemon=True).start()
            except Exception as e:
                if self.running:  # Only log if we're still supposed to be running
                    print(f"Server error: {e}")
                break
        
    def handle_client(self, client_socket, address):
        try:
            data = client_socket.recv(4096).decode('utf-8')
            if data:
                try:
                    message_data = json.loads(data)
                    sender = message_data.get('sender')
                    message = message_data.get('message')
                    print(f"\n[P2P] Message from {sender}: {message}")
                    notify_user(f"Message from {sender}", message)
                    self.db.insert_message(sender, self.nickname, 'received', message)
                    
                    # Acknowledge receipt
                    client_socket.send(json.dumps({'status': 'delivered'}).encode('utf-8'))
                    print(">> ", end="", flush=True)  # Restore prompt
                except json.JSONDecodeError:
                    print(f"Received malformed data: {data}")
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()

    def send_message(self, host, port, message, receiver):
        try:
            # Store message in DB first
            msg_id = self.db.insert_message(self.nickname, receiver, 'pending', message)
            
            # Then try to send it
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)  # 5 second timeout
                s.connect((host, int(port)))
                
                # Prepare and send the message
                msg_data = json.dumps({
                    'sender': self.nickname,
                    'receiver': receiver,
                    'message': message,
                    'timestamp': datetime.datetime.now().isoformat()
                })
                s.send(msg_data.encode('utf-8'))
                
                # Wait for acknowledgment
                response = s.recv(1024).decode('utf-8')
                resp_data = json.loads(response)
                if resp_data.get('status') == 'delivered':
                    self.db.update_message_status(msg_id, 'delivered')
                    print(f"Message delivered to {receiver}")
                    return True
                else:
                    self.db.update_message_status(msg_id, 'failed')
                    print(f"Message delivery failed: {resp_data.get('error', 'Unknown error')}")
                    return False
                    
        except Exception as e:
            self.db.update_message_status(msg_id, 'failed')
            print(f"Failed to send message: {e}")
            return False

    def schedule_message(self, host, port, receiver, scheduled_time, message):
        self.db.insert_scheduled_message(
            self.nickname, receiver, host, port, scheduled_time, message, 'scheduled'
        )
        print(f"Message scheduled for {scheduled_time}")

    def resend_pending_messages(self, host, port, receiver):
        pending = self.db.get_pending_messages(receiver)
        if not pending:
            print(f"No pending messages for {receiver}")
            return
            
        print(f"Attempting to resend {len(pending)} pending messages to {receiver}")
        for msg_id, sender, recv, status, message in pending:
            if self.send_message(host, port, message, receiver):
                self.db.update_message_status(msg_id, 'delivered')

    def check_scheduled_messages(self):
        while self.running:
            current_time = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
            due = self.db.get_due_scheduled_messages(current_time)
            for msg in due:
                msg_id, sched_ts, sender, recv, host, port, txt, status = msg
                print(f"[Scheduled] Sending ID {msg_id} to {recv} (scheduled at {sched_ts})")
                success = self.send_message(host, port, txt, recv)
                if success:
                    self.db.update_scheduled_message_status(msg_id, 'sent')
            time.sleep(10)

    def stop(self):
        self.running = False
        # Clean up Redis subscriptions
        for topic in self.subscribed_topics:
            try:
                self.pubsub.unsubscribe(topic)
            except:
                pass
        self.pubsub.close()
        
        # Close socket
        try:
            self.socket.close()
        except:
            pass
            
        self.db.close()

def main():
    parser = argparse.ArgumentParser(description="P2P Chat with Redis Pub/Sub")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP to bind the peer server")
    parser.add_argument("--port", type=int, default=0, help="Port to bind the peer server")
    parser.add_argument("--redis-host", default="127.0.0.1", help="Redis server host (accessible to all peers)")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis server port")
    args = parser.parse_args()

    nickname = input("Enter your nickname: ").strip()
    if not nickname:
        print("You must provide a nickname. Exiting.")
        return

    peer = Peer(args.host, args.port, nickname, args.redis_host, args.redis_port)
    peer.start()

    print("Commands:")
    print("  subscribe <topic>                    - Subscribe to a Redis topic")
    print("  publish <topic> <message>           - Publish to a Redis topic")
    print("  topics                              - List active Redis topics")
    print("  listeners <topic>                   - Show subscriber count for a topic")
    print("  connect <host> <port>               - Legacy P2P connect")
    print("  schedule <host> <port> <nick> <time> <msg> - Schedule a message")
    print("  myport                              - Show this peer's listening port")
    print("  quit                                - Exit the app")

    current_target = None
    current_nick = None

    try:
        while True:
            line = input(">> ").strip()
            parts = line.split()
            if not parts: continue
            cmd = parts[0].lower()
            if cmd == 'quit': break
            elif cmd == 'subscribe' and len(parts)==2:
                peer.subscribe_topic(parts[1])
            elif cmd == 'publish' and len(parts)>=3:
                peer.publish_topic(parts[1], ' '.join(parts[2:]))
            elif cmd == 'topics':
                peer.list_topics()
            elif cmd == 'listeners' and len(parts)==2:
                peer.list_listeners(parts[1])
            elif cmd == 'myport':
                print(f"My port: {peer.port}")
            elif cmd == 'connect' and len(parts)==3:
                host, port = parts[1], int(parts[2])
                nick = input("Enter target's nickname: ").strip()
                current_target = (host, port)
                current_nick = nick
                peer.resend_pending_messages(host, port, nick)
            elif cmd == 'schedule' and len(parts)>=6:
                host, port_str, nick, sched = parts[1], parts[2], parts[3], parts[4]
                msg = ' '.join(parts[5:])
                try:
                    dt = datetime.datetime.strptime(sched, "%Y-%m-%d %H:%M:%S")
                    peer.schedule_message(host, int(port_str), nick, dt.isoformat(sep=' ', timespec='seconds'), msg)
                except Exception as e:
                    print("Invalid schedule command.", e)
            elif current_target:
                peer.send_message(current_target[0], current_target[1], line, current_nick)
            else:
                print("Unknown command or no active P2P connection.")
    except KeyboardInterrupt:
        pass

    peer.stop()
    print("Peer stopped.")

if __name__ == "__main__":
    main()