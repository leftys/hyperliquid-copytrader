import os
import shutil
from pathlib import Path

def build_mac_app():
    # Get current directory
    current_dir = Path().absolute()
    print(f"Current directory: {current_dir}")
    
    # Create resources directory if it doesn't exist
    resources_dir = current_dir / "resources"
    resources_dir.mkdir(exist_ok=True)
    print(f"Resources directory: {resources_dir}")

    # First remove any existing files in resources
    for existing_file in resources_dir.glob('*'):
        existing_file.unlink()
    
    # Copy bot files to resources
    bot_files = ["position_bot.py", "order_bot.py"]
    for bot_file in bot_files:
        source = current_dir / bot_file
        destination = resources_dir / bot_file
        if source.exists():
            shutil.copy2(source, destination)
            print(f"Copied {bot_file} to resources")
        else:
            raise FileNotFoundError(f"Required file {bot_file} not found!")

    # Define PyInstaller configuration
    import PyInstaller.__main__
    PyInstaller.__main__.run([
        'trading_bot_app.py',
        '--windowed',
        '--name=HyperliquidCopyTrader',
        '--add-data=resources:.',  # Changed this line
        '--clean',
        '--icon=icon.icns',
        '--osx-bundle-identifier=com.hyperliquid.copytrader',
        '--hidden-import=tkinter',
        '--hidden-import=paramiko',
        '--hidden-import=eth_account',
        '--hidden-import=dotenv',
        '--hidden-import=hyperliquid',
        '--hidden-import=cryptography',
        '--hidden-import=requests',
        '--hidden-import=asyncio',
        '--hidden-import=eth_account.signers.local',
        '--hidden-import=hyperliquid.exchange',
        '--hidden-import=hyperliquid.info',
        '--hidden-import=hyperliquid.utils',
        '--hidden-import=keyring',
        '--hidden-import=keyring.backends',
        '--hidden-import=keyring.backends.OS_X',
        '--collect-all=keyring',
    ])

if __name__ == "__main__":
    build_mac_app()