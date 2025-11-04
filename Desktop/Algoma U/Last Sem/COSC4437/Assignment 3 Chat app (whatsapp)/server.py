
import socket
import threading
import argparse
from utils import send_json, recv_json_from_file, now_ts
from typing import Dict, Tuple

HOST = '0.0.0.0'
PORT = 5000
MAX_BACKLOG = 10

# Thread-safe mapping from socket -> (addr, name)
clients_lock = threading.Lock()
clients: Dict[socket.socket, Tuple[Tuple[str,int], str]] = {}

def broadcast(msg_dict, exclude_conn=None):
    """Send msg_dict (a Python dict) to all connected clients except exclude_conn."""
    with clients_lock:
        conns = list(clients.keys())
    for conn in conns:
        if conn is exclude_conn:
            continue
        try:
            send_json(conn, msg_dict)
        except Exception as e:
            # Sending failed; handle cleanup on that connection in its thread
            print(f"[broadcast] failed to send to {conn}: {e}")

def handle_client(conn: socket.socket, addr):
    """
    Per-client thread. Reads newline-delimited JSON messages using conn.makefile('r').
    Expects a register message first to identify the client name.
    """
    print(f"[+] Connection from {addr}")
    sock_file = conn.makefile('r', encoding='utf-8')
    name = None
    try:
        # First, expect a register message
        msg = recv_json_from_file(sock_file)
        if msg is None:
            print(f"[-] {addr} closed before registering")
            return

        if msg.get('type') == 'register' and msg.get('name'):
            name = msg['name']
            with clients_lock:
                clients[conn] = (addr, name)
            print(f"[+] Registered {name} @ {addr}")
            # Notify others user joined
            join_msg = {
                "type": "system",
                "payload": f"{name} has joined the chat.",
                "sender": "SERVER",
                "server_time": now_ts()
            }
            broadcast(join_msg, exclude_conn=conn)
        else:
            # If the client didn't register, assign a fallback name
            name = f"{addr[0]}:{addr[1]}"
            with clients_lock:
                clients[conn] = (addr, name)
            print(f"[!] No register message; using fallback name {name}")

        # Main loop: handle incoming messages
        while True:
            msg = recv_json_from_file(sock_file)
            if msg is None:
                print(f"[-] {name} disconnected")
                break

            mtype = msg.get('type')
            if mtype == 'msg':
                # Optionally enrich with server receipt time
                msg['server_receive_time'] = now_ts()
                print(f"[msg] {name}: {msg.get('payload')}")
                broadcast(msg, exclude_conn=conn)

            elif mtype == 'sync_request':
                # Cristian algorithm: reply immediately with server time
                # Client is expected to calculate offset.
                reply = {
                    "type": "sync_reply",
                    "server_time": now_ts()
                }
                try:
                    send_json(conn, reply)
                except Exception as e:
                    print(f"[sync] failed to send sync_reply to {name}: {e}")

            else:
                # Unknown message type; log and optionally ignore
                print(f"[?] Unknown msg type from {name}: {mtype}")

    except Exception as e:
        print(f"[!] Exception in handle_client for {addr}: {e}")
    finally:
        # Cleanup
        try:
            with clients_lock:
                if conn in clients:
                    _, departed_name = clients.pop(conn)
                else:
                    departed_name = name or str(addr)
        except Exception:
            departed_name = name or str(addr)

        try:
            sock_file.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

        # Broadcast leave notification
        leave_msg = {
            "type": "system",
            "payload": f"{departed_name} has left the chat.",
            "sender": "SERVER",
            "server_time": now_ts()
        }
        broadcast(leave_msg, exclude_conn=None)
        print(f"[x] Cleaned up connection for {departed_name} @ {addr}")


def run_server(host: str = HOST, port: int = PORT):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(MAX_BACKLOG)
    print(f"[i] Server listening on {host}:{port}")

    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[i] Server shutting down (KeyboardInterrupt).")
    finally:
        with clients_lock:
            conns = list(clients.keys())
        for c in conns:
            try:
                c.close()
            except Exception:
                pass
        srv.close()
        print("[i] Server socket closed.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Threaded chat server with Cristian sync reply.")
    parser.add_argument('--host', default=HOST, help='Host to bind (default 0.0.0.0)')
    parser.add_argument('--port', type=int, default=PORT, help='Port to bind (default 5000)')
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)