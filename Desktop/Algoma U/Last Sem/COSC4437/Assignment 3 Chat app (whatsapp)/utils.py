# utils.py
import json
import time

# Pack a message into a JSON string before sending
def pack_message(sender, message):
    """
    Creates a JSON-encoded message with timestamp.
    """
    data = {
        "sender": sender,
        "timestamp": time.time(),
        "message": message
    }
    return json.dumps(data).encode('utf-8')  # Convert to bytes for socket send()


# Unpack a JSON message received from socket
def unpack_message(data):
    """
    Decodes JSON-encoded message from bytes to dict.
    """
    try:
        decoded = json.loads(data.decode('utf-8'))
        return decoded
    except json.JSONDecodeError:
        return {"error": "Invalid message format"}


# Optional: Convert timestamp to readable format
def format_time(timestamp):
    """
    Convert a timestamp (float) to human-readable HH:MM:SS.
    """
    return time.strftime('%H:%M:%S', time.localtime(timestamp))
