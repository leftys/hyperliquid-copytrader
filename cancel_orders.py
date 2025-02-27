import asyncio
import os
from hyperliquid.info import Info
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from dotenv import load_dotenv

async def cancel_all_orders():
    # Load environment variables
    load_dotenv()

    # Initialize Hyperliquid
    account: LocalAccount = eth_account.Account.from_key(os.getenv("PRIVATE_KEY_API"))
    exchange = Exchange(account, constants.MAINNET_API_URL)
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    
    # Get trading address
    trading_address = os.getenv("TRADING_ADDRESS")
    
    print(f"Fetching open orders for {trading_address}...")
    
    # Get open orders
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: info.open_orders(trading_address)
        )
        
        if not response:
            print("No open orders found")
            return
            
        print(f"Found {len(response)} open orders")
        
        # Cancel each order
        cancelled = 0
        failed = 0
        
        for order in response:
            try:
                coin = order.get('coin')
                oid = order.get('oid')
                side = 'Buy' if order.get('side') == 'B' else 'Sell'
                price = float(order.get('limitPx', 0))
                size = float(order.get('sz', 0))
                
                print(f"Cancelling {side} {size} {coin} @ ${price}")
                
                cancel_result = exchange.cancel(coin, oid)
                if cancel_result["status"] == "ok":
                    cancelled += 1
                    print(f"✓ Cancelled order {oid}")
                else:
                    failed += 1
                    print(f"✗ Failed to cancel order {oid}: {cancel_result}")
                
            except Exception as e:
                failed += 1
                print(f"Error cancelling order: {e}")
                
        print(f"\nSummary:")
        print(f"Total orders: {len(response)}")
        print(f"Successfully cancelled: {cancelled}")
        print(f"Failed to cancel: {failed}")
        
    except Exception as e:
        print(f"Error fetching open orders: {e}")

async def main():
    try:
        await cancel_all_orders()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
