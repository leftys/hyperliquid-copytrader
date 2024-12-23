import asyncio
import os
import datetime
from hyperliquid.info import Info
import requests
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import json
from dotenv import load_dotenv


class OrderBot:
    def __init__(self):
        self.should_run = True
        # Load environment variables from .env file
        load_dotenv()

        # Initialize Hyperliquid
        self.account: LocalAccount = eth_account.Account.from_key(os.getenv("PRIVATE_KEY_API"))
        self.exchange = Exchange(self.account, constants.MAINNET_API_URL)
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)

        # Configuration from environment variables
        self.ACCOUNT_TO_COPY = os.getenv("ACCOUNT_TO_COPY")
        self.TRADING_ADDRESS = os.getenv("TRADING_ADDRESS")
        self.LEVERAGE = float(os.getenv("LEVERAGE", "5"))
        self.TRADE_LIMIT = 10
        self.MINI_ALLOC_OF_PF = 0

        # Get exchange metadata
        meta = self.info.meta()
        
        # Create szDecimals map
        self.sz_decimals = {}
        for asset_info in meta["universe"]:
            self.sz_decimals[asset_info["name"]] = asset_info["szDecimals"]

    async def get_account_value(self, address):
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    'https://api.hyperliquid.xyz/info',
                    json={"type": "clearinghouseState", "user": address},
                    timeout=10
                )
            )
            data = response.json()
            return float(data['crossMarginSummary']['accountValue'])
        except Exception as e:
            print(f"Error fetching account value: {e}")
            return 0

    async def get_open_orders(self, address):
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    'https://api.hyperliquid.xyz/info',
                    json={"type": "openOrders", "user": address},
                    timeout=10
                )
            )
            return response.json()
        except Exception as e:
            print(f"Error fetching open orders: {e}")
            return []

    async def cancel_order(self, coin, oid):
        try:
            cancel_result = self.exchange.cancel(coin, oid)
            if cancel_result["status"] == "ok":
                return True
            print(f"Failed to cancel order: {cancel_result}")
            return False
        except Exception as e:
            print(f"Error cancelling order: {e}")
            return False

    async def place_limit_order(self, coin, is_buy, size, price, reduce_only=False):
        try:
            order_result = self.exchange.order(
                coin,
                is_buy,
                size,
                price,
                {"limit": {"tif": "Gtc"}},
                reduce_only=reduce_only
            )
            if order_result["status"] == "ok":
                status = order_result["response"]["data"]["statuses"][0]
                if "error" in status:
                    return False
                return True
            print(f"Error placing limit order: {order_result}")
            return False
        except Exception as e:
            print(f"Exception in place_limit_order: {e}")
            return False

    def print_order_summary(self, orders, title):
        if not orders:
            print(f"\n{title}: No active orders")
            return
            
        print(f"\n{title}:")
        order_summary = {}
        total_value = 0
        
        for order in orders:
            coin = order['coin']
            if coin not in order_summary:
                order_summary[coin] = []
                
            order_value = float(order['sz']) * float(order['limitPx'])
            total_value += abs(order_value)
            
            order_summary[coin].append({
                'side': 'Buy' if order['side'] == 'B' else 'Sell',
                'price': float(order['limitPx']),
                'size': float(order['sz']),
                'value': order_value,
                'reduceOnly': order.get('reduceOnly', False)
            })

    async def check_and_copy_orders(self):
        try:
            berlinTime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\nChecking orders at {berlinTime}")
            
            # Get account values
            copy_trade_account_value = await self.get_account_value(self.ACCOUNT_TO_COPY)
            my_account_value = (await self.get_account_value(self.TRADING_ADDRESS)) * self.LEVERAGE
            
            if copy_trade_account_value == 0 or my_account_value == 0:
                print("Failed to get account values, skipping this iteration")
                return
            
            print(f"\nCopy trade account value: ${copy_trade_account_value:,.2f}")
            print(f"My account value (with {self.LEVERAGE}x leverage): ${my_account_value:,.2f}")
            
            # Get orders
            copy_trade_orders = await self.get_open_orders(self.ACCOUNT_TO_COPY)
            my_orders = await self.get_open_orders(self.TRADING_ADDRESS)
            
            self.print_order_summary(copy_trade_orders, "Copy Trade Account Orders")
            self.print_order_summary(my_orders, "My Open Orders")
            
            # Create maps
            my_order_map = {}
            copy_trade_map = {}
            
            for order in my_orders:
                key = f"{order['coin']}-{order['side']}-{order['limitPx']}"
                my_order_map[key] = order
                
            for order in copy_trade_orders:
                key = f"{order['coin']}-{order['side']}-{order['limitPx']}"
                copy_trade_map[key] = order

            # Cancel unmatched orders
            cancelled_orders = 0
            for my_order in my_orders:
                key = f"{my_order['coin']}-{my_order['side']}-{my_order['limitPx']}"
                if key not in copy_trade_map:
                    if await self.cancel_order(my_order['coin'], my_order['oid']):
                        cancelled_orders += 1
                        my_order_map.pop(key, None)

            # Process copy trade orders
            processed_orders = 0
            for order in copy_trade_orders:
                try:
                    key = f"{order['coin']}-{order['side']}-{order['limitPx']}"
                    existing_order = my_order_map.get(key)
                    
                    order_size = float(order['sz'])
                    order_price = float(order['limitPx'])
                    scaled_size = (order_size * my_account_value) / copy_trade_account_value
                    scaled_size = round(scaled_size, self.sz_decimals[order['coin']])
                    
                    if scaled_size == 0:
                        min_size = 1 / (10 ** self.sz_decimals[order['coin']])
                        scaled_size = min_size
                        
                    reduce_only = 'reduceOnly' in order and order['reduceOnly'] is True

                    if not existing_order:
                        success = await self.place_limit_order(
                            order['coin'],
                            order['side'] == 'B',
                            scaled_size,
                            float(order['limitPx']),
                            reduce_only=reduce_only
                        )
                        if success:
                            processed_orders += 1
                    
                    else:
                        current_size = float(existing_order['sz'])
                        size_diff = abs(current_size - scaled_size)
                        
                        if size_diff / current_size > 0.01:  # 1% threshold
                            if await self.cancel_order(existing_order['coin'], existing_order['oid']):
                                success = await self.place_limit_order(
                                    order['coin'],
                                    order['side'] == 'B',
                                    scaled_size,
                                    float(order['limitPx']),
                                    reduce_only=reduce_only
                                )
                                if success:
                                    processed_orders += 1

                except Exception as e:
                    print(f"Error processing order: {e}")
                    continue

            print(f"\nOrder sync summary:")
            print(f"Copy trade orders: {len(copy_trade_orders)}")
            print(f"My orders: {len(my_orders)}")
            print(f"Orders processed: {processed_orders}")
            print(f"Orders cancelled: {cancelled_orders}")

        except asyncio.CancelledError:
            print("Order check cancelled, shutting down gracefully...")
            self.should_run = False
        except Exception as e:
            print(f"Error in check_and_copy_orders: {e}")

    async def run(self):
        print("Starting order copy bot...")
        print(f"Copying from: {self.ACCOUNT_TO_COPY}")
        print(f"Trading with: {self.TRADING_ADDRESS}")
        print(f"Leverage: {self.LEVERAGE}x")
        print(f"Minimum trade size: ${self.TRADE_LIMIT}")
        
        while self.should_run:
            try:
                await self.check_and_copy_orders()
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                print("Bot operation cancelled, shutting down...")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

async def main():
    bot = OrderBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("Received shutdown signal, stopping bot...")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        print("Bot shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Application terminated by user")
    except Exception as e:
        print(f"Application error: {e}")