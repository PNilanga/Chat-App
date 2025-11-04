import socket
import threading
import time
import tkinter as tk
from tkinter import simpledialog
from utils import send_json, recv_json_from_file, now_ts, format_time

HOST = '127.0.0.1'
PORT = 5000
SYNC_INTERVAL_MS = 15000 # Request sync every 15 seconds

class ChatClientGUI:
    def __init__(self, master, username):
        self.master = master
        self.username = username
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sync_offset = 0.0
        self.running = True

        # --- GUI Styling ---
        master.title(f"WhatsApp Chat - {username}")
        master.configure(bg="#ECE5DD")
        master.geometry("500x600")

        # Chat display frame
        self.chat_frame = tk.Frame(master, bg="#ECE5DD")
        self.chat_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollable chat area
        self.canvas = tk.Canvas(self.chat_frame, bg="#ECE5DD", highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.chat_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#ECE5DD")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Input frame
        self.input_frame = tk.Frame(master, bg="#DDDDDD", pady=5)
        self.input_frame.pack(fill=tk.X)

        self.entry = tk.Entry(self.input_frame, font=("Helvetica", 12))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.entry.bind("<Return>", self.send_message)

        self.send_button = tk.Button(self.input_frame, text="Send", command=self.send_message, bg="#075E54", fg="white")
        self.send_button.pack(side=tk.RIGHT, padx=5)

        # Clock labels
        self.clock_frame = tk.Frame(master, bg="#ECE5DD", pady=5)
        self.clock_frame.pack(fill=tk.X)
        self.local_time_label = tk.Label(self.clock_frame, text="Local: --:--:--", bg="#ECE5DD")
        self.local_time_label.pack(side=tk.LEFT, padx=10)
        self.server_time_label = tk.Label(self.clock_frame, text="Synced: --:--:--", bg="#ECE5DD")
        self.server_time_label.pack(side=tk.RIGHT, padx=10)

        # --- Connect to server ---
        try:
            self.sock.connect((HOST, PORT))
        except Exception as e:
            self.add_system_message(f"[!] Could not connect: {e}")
            self.running = False
            return

        send_json(self.sock, {"type":"register", "name": username})
        self.sock_file = self.sock.makefile('r', encoding='utf-8')

        threading.Thread(target=self.listen_server, daemon=True).start()
        self.update_clocks()
        # Start the periodic sync loop
        self.request_sync()

    # --- Message display functions ---
    def add_message_bubble(self, text, sender="You", timestamp=None, sent_by_me=True, is_private=False):
        frame = tk.Frame(self.scrollable_frame, bg="#ECE5DD", pady=2)
        frame.pack(fill=tk.X, anchor='e' if sent_by_me else 'w', padx=10)

        # Sender name
        if is_private:
            name_color = "#CC0000" # Red for private
        else:
            name_color = "#075E54" if sent_by_me else "#128C7E"
            
        sender_label = tk.Label(frame, text=sender, font=("Helvetica", 10, "bold"), bg="#ECE5DD", fg=name_color)
        sender_label.pack(anchor='e' if sent_by_me else 'w')

        # Message bubble
        bg_color = "#DCF8C6" if sent_by_me else "#FFFFFF"
        bubble = tk.Label(frame, text=f"{text}\n{timestamp}", bg=bg_color, wraplength=300,
                          justify='left', anchor='w', padx=10, pady=5, font=("Helvetica", 12), bd=0, relief="ridge")
        bubble.pack(anchor='e' if sent_by_me else 'w')

        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def add_system_message(self, text):
        frame = tk.Frame(self.scrollable_frame, bg="#ECE5DD", pady=2)
        frame.pack(fill=tk.X)
        label = tk.Label(frame, text=text, bg="#ECE5DD", fg="#888888", font=("Helvetica", 10, "italic"))
        label.pack()
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    # --- Sending & receiving ---
    def send_message(self, event=None):
        if not self.running:
            return
            
        msg_text = self.entry.get().strip()
        if not msg_text:
            return
        self.entry.delete(0, tk.END)
        
        msg_dict = None
        local_display_time = format_time(now_ts() + self.sync_offset)

        # Check for private message command
        if msg_text.startswith("/w "):
            parts = msg_text.split(" ", 2)
            if len(parts) < 3:
                self.add_system_message(f"[!] Invalid PM format. Use: /w <username> <message>")
                return
            
            target_user = parts[1]
            payload = parts[2]
            
            msg_dict = {
                "type": "private_msg", 
                "sender": self.username, 
                "target": target_user,
                "payload": payload, 
                "ts_local": now_ts()
            }
            # Display your own private message locally
            self.add_message_bubble(payload, sender=f"[To {target_user}]", timestamp=local_display_time, sent_by_me=True, is_private=True)

        else:
            # This is a normal broadcast message
            msg_dict = {
                "type": "msg", 
                "sender": self.username, 
                "payload": msg_text, 
                "ts_local": now_ts()
            }
            # Display your own broadcast message locally
            self.add_message_bubble(msg_text, sender=self.username, timestamp=local_display_time, sent_by_me=True, is_private=False)

        # Send the dictionary (either PM or broadcast)
        try:
            send_json(self.sock, msg_dict)
        except Exception as e:
            self.add_system_message(f"[!] Failed to send message: {e}")

    def listen_server(self):
        while self.running:
            try:
                msg = recv_json_from_file(self.sock_file)
            except Exception:
                # This can happen if the socket is closed abruptly
                msg = None

            if msg is None:
                if self.running:
                    self.add_system_message("[!] Disconnected from server.")
                    self.running = False
                break
                
            mtype = msg.get("type")
            sender = msg.get("sender", "SERVER")
            payload = msg.get("payload", "")

            # Determine the correct timestamp.
            # Server-sent timestamps are authoritative.
            ts = msg.get("server_receive_time") or msg.get("server_time")
            if ts:
                timestamp = format_time(ts) # Use server time directly
            else:
                # Fallback for sync replies or older messages
                ts = msg.get("ts_local", now_ts())
                timestamp = format_time(ts + self.sync_offset) # Use offset

            if mtype == "msg":
                if sender != self.username:
                    self.add_message_bubble(payload, sender=sender, timestamp=timestamp, sent_by_me=False, is_private=False)
            
            elif mtype == "private_msg":
                if sender != self.username:
                    self.add_message_bubble(payload, sender=f"[Private from {sender}]", timestamp=timestamp, sent_by_me=False, is_private=True)
            
            elif mtype == "system" or mtype == "error":
                self.add_system_message(f"[{sender}] {payload}")
            
            elif mtype == "sync_reply":
                server_time = msg.get("server_time")
                if server_time:
                    # This is Cristian's algorithm (simplified, without RTT)
                    self.sync_offset = server_time - now_ts()
                    print(f"[Sync] New offset: {self.sync_offset}") # For debugging
            
            else:
                self.add_system_message(str(msg))

    # --- Clocks ---
    def update_clocks(self):
        if not self.running:
            return
            
        local_time = now_ts()
        synced_time = local_time + self.sync_offset
        
        self.local_time_label.config(text=f"Local: {format_time(local_time)}")
        self.server_time_label.config(text=f"Synced: {format_time(synced_time)}")
        
        self.master.after(1000, self.update_clocks)

    def request_sync(self):
        """Periodically send a sync request to the server."""
        if not self.running:
            return
        
        try:
            send_json(self.sock, {"type": "sync_request", "ts_local": now_ts()})
        except Exception as e:
            print(f"[Sync] Failed to send sync request: {e}")
        
        # Schedule the *next* sync request
        self.master.after(SYNC_INTERVAL_MS, self.request_sync)

# --- Start GUI after username input ---
def start_chat():
    root = tk.Tk()
    root.withdraw()  # hide main window while asking username
    username = simpledialog.askstring("Username", "Enter your username:")
    if not username:
        return
        
    username = username.replace(" ", "_") # Sanitize username
    
    root.deiconify()  # show main chat window
    app = ChatClientGUI(root, username)
    root.mainloop()
    
    # When main window closes, stop client threads
    app.running = False
    try:
        app.sock.close()
    except Exception:
        pass

if __name__ == "__main__":
    start_chat()
