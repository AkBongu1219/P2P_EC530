import unittest
import socket
import time
import threading
import tempfile
import os
import datetime
from unittest.mock import patch, MagicMock

import sys
sys.path.append('.')  
from p2p import MessageDB, Peer, notify_user

class TestMessageDB(unittest.TestCase):
    """Test cases for the MessageDB class"""
    
    def setUp(self):
        # Create a temporary database file for testing
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.db = MessageDB(self.temp_db.name)
    
    def tearDown(self):
        # Close the database connection and remove the temporary file
        self.db.close()
        os.unlink(self.temp_db.name)
    
    def test_insert_and_get_message(self):
        """Test inserting a message and retrieving it as pending"""
        # Insert a test message
        self.db.insert_message("alice", "bob", "pending", "Hello Bob!")
        
        # Retrieve pending messages for bob
        pending_messages = self.db.get_pending_messages("bob")
        
        # Check if we got our message
        self.assertEqual(len(pending_messages), 1)
        _, sender, receiver, status, message = pending_messages[0]
        self.assertEqual(sender, "alice")
        self.assertEqual(receiver, "bob")
        self.assertEqual(status, "pending")
        self.assertEqual(message, "Hello Bob!")
    
    def test_update_message_status(self):
        """Test updating the status of a message"""
        # Insert a test message and get its ID
        msg_id = self.db.insert_message("alice", "bob", "pending", "Hello again!")
        
        # Update the status of the message
        self.db.update_message_status(msg_id, "sent")
        
        # Message should no longer be pending
        pending_messages = self.db.get_pending_messages("bob")
        self.assertEqual(len(pending_messages), 0)
    
    def test_scheduled_messages(self):
        """Test the scheduled messages functionality"""
        # Current time and a time in the past
        now = datetime.datetime.now()
        past_time = (now - datetime.timedelta(minutes=5)).isoformat(sep=' ', timespec='seconds')
        future_time = (now + datetime.timedelta(minutes=5)).isoformat(sep=' ', timespec='seconds')
        
        # Insert a scheduled message in the past
        self.db.insert_scheduled_message(
            "alice", "bob", "localhost", 8001, past_time, "Past message", "scheduled"
        )
        
        # Insert a scheduled message in the future
        self.db.insert_scheduled_message(
            "alice", "bob", "localhost", 8001, future_time, "Future message", "scheduled"
        )
        
        # Check due messages (should only get the past one)
        current_time = now.isoformat(sep=' ', timespec='seconds')
        due_messages = self.db.get_due_scheduled_messages(current_time)
        
        self.assertEqual(len(due_messages), 1)
        _, scheduled_time, sender, receiver, target_host, target_port, message, status = due_messages[0]
        self.assertEqual(scheduled_time, past_time)
        self.assertEqual(message, "Past message")


class TestPeer(unittest.TestCase):
    """Test cases for the Peer class"""
    
    # Disable this test since we have issues with notify_user on MacOS
    @patch('p2p.notify_user')  # Mock the notify_user function
    def test_peer_to_peer_communication(self, mock_notify):
        """Test basic peer-to-peer communication"""
        # Create two peers with new temporary databases
        temp_db1 = tempfile.NamedTemporaryFile(delete=False)
        temp_db1.close()
        temp_db2 = tempfile.NamedTemporaryFile(delete=False)
        temp_db2.close()
        
        peer1 = Peer("127.0.0.1", 0, "Alice")
        peer1.db = MessageDB(temp_db1.name)
        peer2 = Peer("127.0.0.1", 0, "Bob")
        peer2.db = MessageDB(temp_db2.name)
        
        try:
            # Start both peers
            peer1.start()
            peer2.start()
            
            # Give some time for the servers to start
            time.sleep(0.5)
            
            # Send a message from peer1 to peer2
            test_message = "Hello, this is a test message!"
            success = peer1.send_message("127.0.0.1", peer2.port, test_message, "Bob")
            
            # Check if the message was sent successfully
            self.assertTrue(success)
            
            # Give some time for message processing
            time.sleep(0.5)
            
            # Verify that notify_user was called (notification was shown)
            mock_notify.assert_called()
            
        finally:
            # Stop both peers properly
            peer1.running = False
            peer2.running = False
            
            # Clean up database files
            os.unlink(temp_db1.name)
            os.unlink(temp_db2.name)
    
    @patch('p2p.socket.socket')
    def test_offline_messaging(self, mock_socket):
        """Test offline messaging capability using mocked sockets"""
        # Setup mock socket to simulate connection refused
        mock_instance = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_instance
        # Simulate connection refused with an exception
        mock_instance.connect.side_effect = ConnectionRefusedError("[Errno 61] Connection refused")
        
        # Create a peer with a fresh database
        temp_db = tempfile.NamedTemporaryFile(delete=False)
        temp_db.close()
        
        peer = Peer("127.0.0.1", 0, "Alice")
        peer.db = MessageDB(temp_db.name)
        
        try:
            # Initialize the peer but don't start threads
            peer.running = True
            
            # Try to send a message (should fail due to mocked connection refused)
            test_message = "This is an offline message"
            success = peer.send_message("127.0.0.1", 8989, test_message, "Bob")
            
            # Message should not be delivered
            self.assertFalse(success)
            
            # Verify connect was attempted with correct parameters
            mock_instance.connect.assert_called_with(("127.0.0.1", 8989))
            
            # Check if the message was stored as pending
            pending_messages = peer.db.get_pending_messages("Bob")
            self.assertEqual(len(pending_messages), 1)
            _, sender, receiver, status, message = pending_messages[0]
            self.assertEqual(sender, "Alice")
            self.assertEqual(receiver, "Bob")
            self.assertEqual(status, "pending")
            self.assertEqual(message, test_message)
            
        finally:
            # Clean up
            peer.running = False
            os.unlink(temp_db.name)
    
    @patch('p2p.socket.socket')
    def test_scheduled_message(self, mock_socket):
        """Test scheduled message functionality with mocked socket"""
        # Setup mock socket
        mock_instance = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_instance
        
        # Create a peer with a fresh database
        temp_db = tempfile.NamedTemporaryFile(delete=False)
        temp_db.close()
        
        peer = Peer("127.0.0.1", 0, "Alice")
        peer.db = MessageDB(temp_db.name)
        
        try:
            # Don't start threading, directly test the scheduling method
            now = datetime.datetime.now()
            schedule_time = (now - datetime.timedelta(seconds=1)).isoformat(sep=' ', timespec='seconds')
            
            # Insert the scheduled message directly into the database
            peer.db.insert_scheduled_message("Alice", "Bob", "127.0.0.1", 8001, 
                                            schedule_time, "Scheduled hello!", "scheduled")
            
            # Manually trigger the check for scheduled messages
            with patch.object(peer, 'send_message', return_value=True) as mock_send:
                current_time = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
                due_messages = peer.db.get_due_scheduled_messages(current_time)
                
                # Process each due message
                for msg in due_messages:
                    msg_id, scheduled_timestamp, sender, receiver, target_host, target_port, message_text, status = msg
                    peer.send_message(target_host, target_port, message_text, receiver)
                    peer.db.update_scheduled_message_status(msg_id, "sent")
                
                # Check if send_message was called with correct parameters
                mock_send.assert_called_with("127.0.0.1", 8001, "Scheduled hello!", "Bob")
            
        finally:
            # Clean up
            os.unlink(temp_db.name)


class TestNotifications(unittest.TestCase):
    """Test cases for notification functionality"""
    
    @patch('p2p.platform.system', return_value="Darwin")
    @patch('p2p.subprocess.call')
    def test_macos_notification(self, mock_subprocess, mock_platform):
        """Test macOS notification"""
        notify_user("Test Title", "Test Message")
        
        # Check if subprocess.call was called with the correct osascript command
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0][0]
        self.assertEqual(args[0], "osascript")
        self.assertEqual(args[1], "-e")
        self.assertIn("display notification", args[2])
        self.assertIn("Test Message", args[2])
        self.assertIn("Test Title", args[2])
    
@patch('p2p.platform.system', return_value="Linux")
def test_other_platform_notification(self, mock_platform):
    """Test notification on other platforms"""
    try:
        notify_user("Test Title", "Test Message")
    except Exception as e:
        self.fail(f"notify_user raised an exception: {e}")

if __name__ == '__main__':
    unittest.main()