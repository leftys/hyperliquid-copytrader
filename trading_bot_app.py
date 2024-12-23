import sys
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import paramiko
import threading
import json
from pathlib import Path
import time
from datetime import datetime
import keyring
import pickle

class TradingBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HyperLiquid Copy Trader")
        self.root.geometry("600x300")

        # Create app data directory for storing credentials and logs
        self.app_data_dir = Path.home() / '.hyperliquid_copytrader'
        self.app_data_dir.mkdir(exist_ok=True)
        self.log_file = self.app_data_dir / 'bot_logs.txt'
        self.config_file = self.app_data_dir / 'config.json'
        
        # Variables
        self.server_var = tk.StringVar(value="your-server.com")
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.copy_account_var = tk.StringVar()
        self.trading_address_var = tk.StringVar()
        self.private_key_var = tk.StringVar()
        self.leverage_var = tk.StringVar(value="1")

        # Load saved credentials and trading config
        self.load_saved_config()
        
        # Setup UI (this will create the log frame)
        self.setup_ui()
        
        # SSH client
        self.ssh = None
        self.connected = False
        self.bots_running = False

        # Load previous logs
        self.load_logs()

        # Add a timer for batched log saving
        self.last_log_save = time.time()
        self.log_save_interval = 5  # Save logs every 5 seconds
        
        # Schedule periodic log saving
        self.root.after(5000, self.periodic_save_logs)

        # Set up closing handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initially show only server connection tab and hide trading configuration
        self.notebook.select(0)  # Select server connection tab
        self.notebook.hide(1)    # Hide trading configuration tab

    def setup_ui(self):
            # Main container
            main_frame = ttk.Frame(self.root, padding="10")
            main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
            
            # Top container for tabs
            top_frame = ttk.Frame(main_frame)
            top_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=5)
            
            # Create and configure style for notebook
            style = ttk.Style()
            style.layout('CustomNotebook.TNotebook.Tab', [])  # Remove the default tab layout
            style.configure('CustomNotebook.TNotebook', tabposition='n')
            style.configure('CustomNotebook.TNotebook.Tab', 
                        padding=[10, 5],
                        font=('Helvetica', '12', 'bold'),
                        borderwidth=0,     # Remove border
                        background='white' # Match background
            )
            
            # Configure tab strip to be borderless
            style.layout('CustomNotebook', [('Notebook.client', {'sticky': 'nswe'})])
            
            # Create notebook with custom style
            self.notebook = ttk.Notebook(top_frame, style='CustomNotebook.TNotebook')
            self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E))
            
            # Server connection frame
            connection_frame = ttk.Frame(self.notebook, padding="5")
            self.notebook.add(connection_frame, text="Server Connection")
            
            # Connection UI elements
            ttk.Label(connection_frame, text="Server:").grid(row=0, column=0, sticky=tk.W)
            ttk.Entry(connection_frame, textvariable=self.server_var).grid(row=0, column=1, sticky=(tk.W, tk.E))
            
            ttk.Label(connection_frame, text="Username:").grid(row=1, column=0, sticky=tk.W)
            ttk.Entry(connection_frame, textvariable=self.username_var).grid(row=1, column=1, sticky=(tk.W, tk.E))
            
            ttk.Label(connection_frame, text="Password:").grid(row=2, column=0, sticky=tk.W)
            ttk.Entry(connection_frame, textvariable=self.password_var, show="*").grid(row=2, column=1, sticky=(tk.W, tk.E))
            
            self.connect_button = ttk.Button(connection_frame, text="Connect", command=self.connect_to_server)
            self.connect_button.grid(row=3, column=0, columnspan=2, pady=5)
            
            # Trading configuration frame
            config_frame = ttk.Frame(self.notebook, padding="5")
            self.notebook.add(config_frame, text="Trading Configuration")
            
            # Account to Copy
            ttk.Label(config_frame, text="Address to Copytrade:").grid(row=0, column=0, sticky=tk.W)
            ttk.Entry(config_frame, textvariable=self.copy_account_var).grid(row=0, column=1, sticky=(tk.W, tk.E))
            
            # Trading Address
            ttk.Label(config_frame, text="Web3 Wallet Address:").grid(row=1, column=0, sticky=tk.W)
            ttk.Entry(config_frame, textvariable=self.trading_address_var).grid(row=1, column=1, sticky=(tk.W, tk.E))
            
            # API Private Key
            ttk.Label(config_frame, text="Private Key from API:").grid(row=2, column=0, sticky=tk.W)
            ttk.Entry(config_frame, textvariable=self.private_key_var, show="*").grid(row=2, column=1, sticky=(tk.W, tk.E))
            ttk.Label(config_frame, justify=tk.LEFT).grid(row=2, column=2, sticky=tk.W, padx=5)
            
            # Multiplier
            ttk.Label(config_frame, text="Position Multiplier:").grid(row=3, column=0, sticky=tk.W)
            ttk.Entry(config_frame, textvariable=self.leverage_var).grid(row=3, column=1, sticky=(tk.W, tk.E))
            ttk.Label(config_frame, justify=tk.LEFT).grid(row=3, column=2, sticky=tk.W, padx=5)
            
            # Buttons frame
            buttons_frame = ttk.Frame(config_frame)
            buttons_frame.grid(row=4, column=0, columnspan=2, pady=5)
            
            self.start_button = ttk.Button(buttons_frame, text="Start Trading", command=self.start_trading, state=tk.DISABLED)
            self.start_button.grid(row=0, column=0, padx=5)
            
            self.stop_button = ttk.Button(buttons_frame, text="Stop Trading", command=self.stop_trading, state=tk.DISABLED)
            self.stop_button.grid(row=0, column=1, padx=5)

            # Bottom container for logs
            bottom_frame = ttk.Frame(main_frame)
            bottom_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.S), pady=5)
            
            # Log frame
            self.log_frame = CollapsibleFrame(bottom_frame, text="Logs")
            self.log_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5)
            self.log_frame.toggle()  # Collapse the logs frame on startup

            # Add status indicator in connection frame
            status_frame = ttk.Frame(connection_frame)
            status_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5,0))
            
            self.status_label = ttk.Label(
                status_frame, 
                text="Not Connected",
                foreground='red'
            )
            self.status_label.grid(row=0, column=0, sticky=tk.W)
            
            # Update status methods
            def update_status(connected):
                if connected:
                    self.status_label.configure(
                        text="Connected",
                        foreground='green'
                    )
                else:
                    self.status_label.configure(
                        text="Not Connected",
                        foreground='red'
                    )
            
            self.update_connection_status = update_status
            
            # Configure grid weights
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(0, weight=0)  # Don't expand top frame
            
            main_frame.columnconfigure(0, weight=1)
            main_frame.rowconfigure(0, weight=0)  # Don't expand top frame
            main_frame.rowconfigure(1, weight=1)  # Allow bottom frame to expand
            
            top_frame.columnconfigure(0, weight=1)
            bottom_frame.columnconfigure(0, weight=1)
            
            connection_frame.columnconfigure(1, weight=1)
            config_frame.columnconfigure(1, weight=1)

    def load_saved_config(self):
        """Load saved configuration"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    
                    # Load non-sensitive data
                    self.server_var.set(config.get('server', ''))
                    self.username_var.set(config.get('username', ''))
                    self.copy_account_var.set(config.get('copy_account', ''))
                    self.trading_address_var.set(config.get('trading_address', ''))
                    self.leverage_var.set(config.get('leverage', '1'))
                    
                    # Load sensitive data from keyring
                    if config.get('username'):
                        password = keyring.get_password(
                            'hyperliquid_copytrader',
                            f"{config.get('username')}@{config.get('server')}_password"
                        )
                        if password:
                            self.password_var.set(password)
                            
                    if config.get('trading_address'):
                        private_key = keyring.get_password(
                            'hyperliquid_copytrader',
                            f"{config.get('trading_address')}_private_key"
                        )
                        if private_key:
                            self.private_key_var.set(private_key)
                            
        except Exception as e:
            print(f"Error loading configuration: {str(e)}")

    def periodic_save_logs(self):
        """Periodically save logs to file"""
        try:
            current_time = time.time()
            if current_time - self.last_log_save >= self.log_save_interval:
                self.save_logs()
                self.last_log_save = current_time
        finally:
            # Schedule next check
            self.root.after(5000, self.periodic_save_logs)

    def save_config(self):
        """Save configuration securely"""
        try:
            # Save non-sensitive data
            config = {
                'server': self.server_var.get(),
                'username': self.username_var.get(),
                'copy_account': self.copy_account_var.get(),
                'trading_address': self.trading_address_var.get(),
                'leverage': self.leverage_var.get()
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
            
            # Save sensitive data securely
            if self.password_var.get():
                keyring.set_password(
                    'hyperliquid_copytrader',
                    f"{self.username_var.get()}@{self.server_var.get()}_password",
                    self.password_var.get()
                )
            
            if self.private_key_var.get():
                keyring.set_password(
                    'hyperliquid_copytrader',
                    f"{self.trading_address_var.get()}_private_key",
                    self.private_key_var.get()
                )
            
            print("Configuration saved successfully")
        except Exception as e:
            print(f"Error saving configuration: {str(e)}")

    def handle_successful_connection(self):
            """Handle UI updates after successful connection"""
            # Update connection status
            self.update_connection_status(True)
            
            # Add tabs back if they were hidden
            if len(self.notebook.tabs()) < 2:
                self.notebook.add(self.notebook.tabs()[0], text="Server Connection")
                self.notebook.add(self.notebook.tabs()[1], text="Trading Configuration")

            # Select trading configuration tab
            self.notebook.select(1)
            # Hide server connection tab
            self.notebook.hide(0)
            
            # Reset connect button
            self.connect_button.configure(
                state=tk.NORMAL,
                text="Connect"
            )

    def log(self, message, log_type='info'):
        """Add log message with appropriate styling"""
        try:
            self.log_frame.append_log(message, log_type)
            # Don't save on every log message
        except Exception as e:
            print(f"Error logging message: {str(e)}")
            print(f"[{datetime.now()}] {message}")
        
    def connect_to_server(self):

        self.connect_button.configure(state=tk.DISABLED)
        self.connect_button.configure(text="Connecting...")


        def connect_thread():
            try:
                self.log("Connecting to server...", 'info')
                
                # Create SSH client with keepalive
                self.ssh = paramiko.SSHClient()
                self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Connect to server with timeout
                try:
                    self.ssh.connect(
                        self.server_var.get(),
                        username=self.username_var.get(),
                        password=self.password_var.get(),
                        timeout=10  # Add timeout
                    )
                except (paramiko.SSHException, TimeoutError) as e:
                    raise Exception(f"Failed to connect: {str(e)}")
                
                # Enable keepalive to prevent timeouts
                self.ssh.get_transport().set_keepalive(60)
                
                self.log("Connected successfully!", 'success')
                self.log("Checking existing environment...")

                # Batch check all requirements in a single command
                check_command = " && ".join([
                    "which node >/dev/null 2>&1 || echo 'need:nodejs'",
                    "which npm >/dev/null 2>&1 || echo 'need:npm'",
                    "which pm2 >/dev/null 2>&1 || echo 'need:pm2'",
                    "which python3 >/dev/null 2>&1 || echo 'need:python3'",
                    "pip3 show hyperliquid-python-sdk >/dev/null 2>&1 || echo 'need:sdk'",
                    "pip3 show eth_account >/dev/null 2>&1 || echo 'need:eth_account'",
                    "test -d ~/trading_bots || echo 'need:trading_bots_dir'"
                ])
                
                success, output = self.execute_ssh_command(check_command, check_exit=False)
                missing_packages = [pkg.split(':')[1] for pkg in output.split('\n') if pkg.startswith('need:')]

                if missing_packages:
                    self.log("Installing missing components...")
                    install_commands = []
                    
                    if 'nodejs' in missing_packages:
                        install_commands.extend([
                            "curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -",
                            "sudo apt-get install -y nodejs"
                        ])
                    if 'npm' in missing_packages:
                        install_commands.append("sudo apt-get install -y npm")
                    if 'pm2' in missing_packages:
                        install_commands.append("sudo npm install pm2 -g")
                    if 'python3' in missing_packages:
                        install_commands.append("sudo apt-get install -y python3 python3-pip python3-requests python3-dotenv")
                    if any(pkg in missing_packages for pkg in ['sdk', 'eth_account']):
                        install_commands.append("sudo python3 -m pip install --break-system-packages hyperliquid-python-sdk eth_account")
                    if 'trading_bots_dir' in missing_packages:
                        install_commands.append("mkdir -p ~/trading_bots")

                    if install_commands:
                        combined_command = " && ".join(install_commands)
                        success, output = self.execute_ssh_command(combined_command)
                        if not success:
                            raise Exception(f"Failed to install components: {output}")

                # Transfer bot files efficiently
                self.log("Updating bot files...")
                if getattr(sys, 'frozen', False):
                    resource_dir = os.path.join(sys._MEIPASS)
                else:
                    current_file = os.path.abspath(__file__)
                    resource_dir = os.path.join(os.path.dirname(current_file), "resources")

                with self.ssh.open_sftp() as sftp:
                    for script_name in ["position_bot.py", "order_bot.py"]:
                        local_path = os.path.join(resource_dir, script_name)
                        remote_path = f"/root/trading_bots/{script_name}"
                        
                        if not os.path.exists(local_path):
                            raise FileNotFoundError(f"Missing required file: {script_name}")
                        
                        self.log(f"Transferring {script_name}...")
                        sftp.put(local_path, remote_path)
                        self.log(f"Successfully transferred {script_name}")

                # Check if bots are running
                success, output = self.execute_ssh_command("pm2 jlist")
                if success and output:
                    try:
                        pm2_processes = json.loads(output)
                        running_bots = [p for p in pm2_processes if p['name'] in ['position_bot', 'order_bot'] and p['pm2_env']['status'] == 'online']
                        
                        if running_bots:
                            self.log("Found running trading bots!")
                            self.bots_running = True
                            self.start_button.configure(state=tk.DISABLED)
                            self.stop_button.configure(state=tk.NORMAL)
                            self.monitor_logs()
                        else:
                            self.start_button.configure(state=tk.NORMAL)
                            self.stop_button.configure(state=tk.DISABLED)
                    except json.JSONDecodeError:
                        self.log("No running PM2 processes found")
                        self.start_button.configure(state=tk.NORMAL)
                        self.stop_button.configure(state=tk.DISABLED)

                self.log("Environment setup complete!")
                self.connected = True
                self.root.after(0, self.handle_successful_connection)
                
            except Exception as e:
                self.log(f"Connection error: {str(e)}", 'error')
                messagebox.showerror("Connection Error", str(e))
                # Reset button state
                self.root.after(0, lambda: self.connect_button.configure(
                    state=tk.NORMAL,
                    text="Connect"
                ))
                return
            finally:
                # Ensure button is always reset if process fails
                if not self.connected:
                    self.root.after(0, lambda: self.connect_button.configure(
                        state=tk.NORMAL,
                        text="Connect"
                    ))
        
        # Start connection thread
        thread = threading.Thread(target=connect_thread)
        thread.daemon = True  # Make thread daemon so it doesn't block app exit
        thread.start()


    def save_logs(self):
        """Save logs to file"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(self.log_frame.get_all_logs())
        except Exception as e:
            print(f"Error saving logs: {str(e)}")

    def load_logs(self):
        """Load previous logs"""
        try:
            if self.log_file.exists():
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    logs = f.read()
                    if logs:
                        self.log_frame.set_logs(logs)
        except Exception as e:
            print(f"Error loading logs: {str(e)}")

    def stop_trading(self):
        def stop_thread():
            try:
                self.log("Stopping trading bots...")
                self.bots_running = False
                
                # Stop PM2 processes
                stop_commands = [
                    "pm2 stop position_bot",
                    "pm2 stop order_bot",
                    "pm2 delete position_bot",
                    "pm2 delete order_bot"
                ]
                
                for cmd in stop_commands:
                    stdin, stdout, stderr = self.ssh.exec_command(cmd)
                    exit_status = stdout.channel.recv_exit_status()
                    
                    if exit_status != 0:
                        error = stderr.read().decode()
                        self.log(f"Warning during bot shutdown: {error}")
                
                self.log("Trading bots stopped successfully")
                self.stop_button.configure(state=tk.DISABLED)
                self.start_button.configure(state=tk.NORMAL)
                
            except Exception as e:
                self.log(f"Error stopping trading bots: {str(e)}")
                messagebox.showerror("Error", f"Failed to stop trading bots: {str(e)}")
        
        thread = threading.Thread(target=stop_thread)
        thread.start()
        
    def start_trading(self):
        if not all([self.copy_account_var.get(), self.trading_address_var.get(), self.private_key_var.get()]):
            messagebox.showerror("Error", "Please fill in all trading configuration fields")
            return
                
        def start_thread():
            try:
                self.start_button.configure(state=tk.DISABLED)
                self.bots_running = True
                
                # Create .env file more efficiently
                env_content = f"""PRIVATE_KEY_API={self.private_key_var.get()}
ACCOUNT_TO_COPY={self.copy_account_var.get()}
TRADING_ADDRESS={self.trading_address_var.get()}
LEVERAGE={self.leverage_var.get()}"""

                with self.ssh.open_sftp() as sftp:
                    with sftp.file("/root/trading_bots/.env", 'w') as f:
                        f.write(env_content)
                
                # Start bots with batched commands
                success, output = self.execute_ssh_command(
                    "cd /root/trading_bots && "
                    "pm2 start position_bot.py --name position_bot --interpreter python3 && "
                    "pm2 start order_bot.py --name order_bot --interpreter python3"
                )
                
                if not success:
                    self.log(f"Error starting bots: {output}", 'error')
                    return
                
                self.log("Trading bots started successfully!", 'success')
                self.stop_button.configure(state=tk.NORMAL)
                
                # Start log monitoring
                self.monitor_logs()
                
            except Exception as e:
                self.log(f"Error starting trading: {str(e)}", 'error')
                messagebox.showerror("Error", f"Failed to start trading: {str(e)}")
                self.start_button.configure(state=tk.NORMAL)
        
        thread = threading.Thread(target=start_thread)
        thread.start()

    def on_closing(self):
        """Handle application closing"""
        try:
            if self.bots_running:
                if messagebox.askyesno("Quit", "Trading bots are running. Stop them before closing?"):
                    self.stop_trading()
                    self.root.after(1000, self.on_closing)  # Check again in 1 second
                    return
                    
            if self.ssh and self.connected:
                self.ssh.close()
                self.connected = False
                self.update_connection_status(False)
            
            self.save_config()
            self.save_logs()
            self.root.destroy()
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")
            self.root.destroy()

    def execute_ssh_command(self, command, check_exit=True):
            """Execute SSH command with optimized handling"""
            try:
                stdin, stdout, stderr = self.ssh.exec_command(command)
                if check_exit:
                    exit_status = stdout.channel.recv_exit_status()
                    if exit_status != 0:
                        error = stderr.read().decode().strip()
                        if error:
                            return False, error
                return True, stdout.read().decode().strip()
            except Exception as e:
                return False, str(e)

    def monitor_logs(self):
            def monitor_thread():
                last_log_time = {}  # Store last log time for each bot
                
                while self.connected and self.bots_running:
                    try:
                        # Batch check for both bots
                        stdin, stdout, stderr = self.ssh.exec_command(
                            "pm2 jlist && pm2 logs --nostream --timestamp --lines 50"
                        )
                        output = stdout.read().decode()
                        
                        # Split output into PM2 status and logs
                        parts = output.split('\n', 1)
                        if len(parts) < 2:
                            time.sleep(5)
                            continue
                            
                        pm2_output, logs = parts
                        
                        # Process PM2 status
                        try:
                            pm2_processes = json.loads(pm2_output)
                            running_bots = [p for p in pm2_processes if p['name'] in ['position_bot', 'order_bot'] and p['pm2_env']['status'] == 'online']
                            
                            if not running_bots:
                                self.log("Warning: Trading bots have stopped!", 'warning')
                                self.bots_running = False
                                self.root.after(0, lambda: self.start_button.configure(state=tk.NORMAL))
                                self.root.after(0, lambda: self.stop_button.configure(state=tk.DISABLED))
                                break
                        except json.JSONDecodeError:
                            pass
                        
                        # Process logs with batching
                        for line in logs.split('\n'):
                            if not line.strip():
                                continue
                                
                            try:
                                # Extract bot name
                                if 'position_bot' in line:
                                    bot_name = 'position_bot'
                                elif 'order_bot' in line:
                                    bot_name = 'order_bot'
                                else:
                                    continue
                                    
                                # Extract timestamp
                                timestamp_str = line.split('T')[0] + ' ' + line.split('T')[1].split('|')[0]
                                log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                                log_time = log_time.timestamp()
                                
                                # Only process new logs
                                last_time = last_log_time.get(bot_name, 0)
                                if log_time > last_time:
                                    self.log(f"[{bot_name}] {line}")
                                    last_log_time[bot_name] = log_time
                            except (ValueError, IndexError):
                                continue
                        
                        time.sleep(5)  # Check every 5 seconds
                        
                    except Exception as e:
                        self.log(f"Error monitoring logs: {str(e)}", 'error')
                        time.sleep(5)
                            
            thread = threading.Thread(target=monitor_thread)
            thread.daemon = True
            thread.start()

class CollapsibleFrame(ttk.Frame):
    def __init__(self, parent, text="", *args, **kwargs):
        ttk.Frame.__init__(self, parent, *args, **kwargs)

        # Configure style for the frame
        style = ttk.Style()
        style.configure('Header.TLabel', font=('Helvetica', '12', 'bold'))
        style.configure('Logs.TFrame', background='white')

        # Initialize the toggle functionality before binding
        self.show = tk.BooleanVar(value=False)  # Start expanded
        
        # Main container
        self.main_container = ttk.Frame(self, style='Logs.TFrame', padding="2")
        self.main_container.grid(row=0, column=0, sticky="nsew")
        
        # Header frame with background
        self.header_frame = ttk.Frame(self.main_container, style='Logs.TFrame')
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        
        # Toggle button/label
        self.toggle_button = ttk.Label(
            self.header_frame, 
            text="▼ " + text, 
            style='Header.TLabel',
            padding=(5, 5)
        )
        self.toggle_button.grid(row=0, column=0, sticky="w")
        
        # Content frame with fixed height
        self.content_frame = ttk.Frame(self.main_container, padding="5", height=200)
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
        self.content_frame.grid_propagate(False)  # Maintain fixed height
        
        # Create log text widget with optimized settings
        self.log_text = scrolledtext.ScrolledText(
            self.content_frame,
            height=10,  # Reduced height for better performance
            width=80,   # Fixed width for better performance
            background='white',
            font=('Consolas', '10'),
            wrap=tk.WORD,
            undo=False,     # Disable undo for better performance
            maxundo=0,      # No undo history
            setgrid=True    # Better scroll performance
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        
        # Log buffer for batching updates
        self.log_buffer = []
        self.max_lines = 1000  # Maximum number of log lines to keep
        
        # Configure tags for different message types
        self.log_text.tag_configure('timestamp', foreground='#666666')
        self.log_text.tag_configure('error', foreground='#ff0000')
        self.log_text.tag_configure('warning', foreground='#ffa500')
        self.log_text.tag_configure('success', foreground='#008000')
        self.log_text.tag_configure('info', foreground='#000000')
        
        # Configure weights for proper expansion
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)  # Don't let log frame expand vertically
        self.main_container.columnconfigure(0, weight=1)
        self.main_container.rowconfigure(1, weight=0)  # Fixed height for log frame
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=0)  # Don't let text widget expand
        
        # Define toggle method
        def toggle(event=None):
            if self.show.get():
                self.content_frame.grid_remove()
                self.toggle_button.configure(text="▶ " + self.toggle_button.cget("text")[2:])
            else:
                self.content_frame.grid()
                self.toggle_button.configure(text="▼ " + self.toggle_button.cget("text")[2:])
            self.show.set(not self.show.get())
        
        # Store the toggle method
        self.toggle = toggle
        
        # Bind click event after toggle method is defined
        self.toggle_button.bind('<Button-1>', self.toggle)
        self.header_frame.bind('<Button-1>', self.toggle)

        # Schedule periodic updates
        self._schedule_update()

    def _schedule_update(self):
        if hasattr(self, 'content_frame'):
            self.content_frame.after(100, self._process_buffer)

    def _process_buffer(self):
        try:
            if self.log_buffer:
                self.log_text.configure(state='normal')
                
                # Process all buffered messages
                for timestamp, message, log_type in self.log_buffer:
                    self.log_text.insert(tk.END, f"[{timestamp}] ", 'timestamp')
                    self.log_text.insert(tk.END, f"{message}\n", log_type)
                
                # Clear buffer
                self.log_buffer.clear()
                
                # Limit number of lines
                self._limit_lines()
                
                self.log_text.configure(state='disabled')
                self.log_text.see(tk.END)
        finally:
            self._schedule_update()

    def _limit_lines(self):
        """Limit the number of lines to prevent memory issues"""
        line_count = int(self.log_text.index('end-1c').split('.')[0])
        if line_count > self.max_lines:
            self.log_text.delete('1.0', f'{line_count - self.max_lines}.0')

    def append_log(self, message, log_type='info'):
        """Add log message to buffer"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_buffer.append((timestamp, message, log_type))

    def get_all_logs(self):
        """Get all logs"""
        return self.log_text.get("1.0", tk.END)

    def clear_logs(self):
        """Clear all logs"""
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state='disabled')
        self.log_buffer.clear()
        
    def set_logs(self, logs):
        """Set log content"""
        self.clear_logs()
        if logs:
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, logs)
            self.log_text.configure(state='disabled')
            self.log_text.see(tk.END)



def main():
    root = tk.Tk()
    app = TradingBotApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()