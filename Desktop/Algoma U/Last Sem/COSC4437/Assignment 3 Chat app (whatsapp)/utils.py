# utils.py
import json
import time

# --- Existing functions ---
def pack_message(sender, message):
    data = {
        "sender": sender,
        "timestamp": time.time(),
        "message": message
    }
    return json.dumps(data).encode('utf-8')


def unpack_message(data):
    try:
        decoded = json.loads(data.decode('utf-8'))
        return decoded
    except json.JSONDecodeError:
        return {"error": "Invalid message format"}


def format_time(timestamp):
    return time.strftime('%H:%M:%S', time.localtime(timestamp))


# --- Add these functions ---

def send_json(sock, msg_dict):
    """
    Send a Python dict as a JSON-encoded message over a socket.
    Appends a newline for delimiting messages.
    """
    try:
        json_str = json.dumps(msg_dict) + "\n"
        sock.sendall(json_str.encode('utf-8'))
    except Exception as e:
        print(f"[send_json] Error sending message: {e}")


def recv_json_from_file(sock_file):
    """
    Read a newline-delimited JSON message from a socket file (TextIOWrapper).
    Returns a Python dict or None if EOF is reached.
    """
    try:
        line = sock_file.readline()
        if not line:
            return None
        return json.loads(line.strip())
    except json.JSONDecodeError:
        print("[recv_json_from_file] Invalid JSON received")
        return None
    except Exception as e:
        print(f"[recv_json_from_file] Error reading message: {e}")
        return None


def now_ts():
    """Return current timestamp as float (time.time())."""
    return time.time()
