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
        # Load environment variables from .env file
        load_dotenv(override=True)

        # Initialize Hyperliquid
        self.account: LocalAccount = eth_account.Account.from_key(os.getenv("PRIVATE_KEY_API"))
        self.exchange = Exchange(
            self.account, 
            constants.MAINNET_API_URL, 
            vault_address=os.getenv("VAULT_ADDRESS", "") or None, 
            account_address=os.getenv("ACCOUNT_ADDRESS", "") or None
        )
        self.info = Info(constants.MAINNET_API_URL, skip_ws=False)  # Enable WebSocket
        self.info2 = Info(constants.MAINNET_API_URL, skip_ws=False)  # Enable WebSocket

        # Configuration from environment variables
        self.ACCOUNT_TO_COPY = os.getenv("ACCOUNT_TO_COPY")
        self.TRADING_ADDRESS = os.getenv("TRADING_ADDRESS")
        self.LEVERAGE = float(os.getenv("LEVERAGE", "5"))
        self.TRADE_LIMIT = 10
        self.MINI_ALLOC_OF_PF = 0
        self.SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "5"))

        # Get exchange metadata
        meta = self.info.meta()
        
        # Create szDecimals map
        self.sz_decimals = {}
        for asset_info in meta["universe"]:
            self.sz_decimals[asset_info["name"]] = asset_info["szDecimals"]
            
        # Store copy account orders and my orders
        self.copy_account_orders = {}
        self.my_orders = {}
        
        # Account values
        self.copy_account_value = 0
        self.my_account_value = 0
        
        # Last sync time
        self.last_sync_time = 0

        self.loop = asyncio.get_running_loop()

    async def get_account_value(self, address):
        try:
            response = await self.loop.run_in_executor(
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
            response = await self.loop.run_in_executor(
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
                # print(f"Successfully cancelled order {oid} for {coin}")
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
                    print(f"Error in order response: {status['error']}")
                    return False
                print(f"Successfully placed {'buy' if is_buy else 'sell'} order for {size} {coin} @ ${price}")
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
            
        # Print summary by coin
        for coin, orders in order_summary.items():
            print(f"  {coin}: {len(orders)} orders")
            for order in orders:
                print(f"    {order['side']} {order['size']} @ ${order['price']} (${abs(order['value']):.2f})")
                
        print(f"  Total order value: ${total_value:.2f}")

    def handle_copy_account_order_update(self, order_msg):
        """Handle order updates from the account we're copying"""
        data = order_msg.get('data', [])
        if not data:
            return
            
        for update in data:
            order = update.get('order', {})
            status = update.get('status', '')
            
            if not order or not status:
                continue
                
            coin = order.get('coin')
            oid = order.get('oid')
            side = order.get('side')  # 'B' for buy, 'A' for sell
            limit_price = order.get('limitPx')
            size = order.get('sz')
            reduce_only = order.get('reduceOnly', False)
            
            if not all([coin, oid, side, limit_price, size]):
                continue
            
            key = f"{coin}-{side}-{limit_price}"

            if len(self.loop._ready) > 20:
                print("Too many orders pending, skipping...")
                return
            
            # Store the order and status for processing in the main event loop
            asyncio.run_coroutine_threadsafe(
                self.process_copy_account_order(order, status, key),
                self.loop
            )

    async def process_copy_account_order(self, order, status, key):
        """Process order updates from the copy account in the main event loop"""
        try:
            # Handle different order statuses
            if status == 'open':
                # New or modified order
                self.copy_account_orders[key] = order
                await self.sync_order(order)
            elif status in ['canceled', 'rejected']:
                # Order is no longer active
                if key in self.copy_account_orders:
                    del self.copy_account_orders[key]
                    await self.cancel_my_matching_order(key)
            elif status == 'filled':
                if float(order['sz']) == 0:
                    # Order is fully filled
                    if key in self.copy_account_orders:
                        del self.copy_account_orders[key]
            
            # Periodically update account values (not on every order update)
            current_time = datetime.datetime.now().timestamp()
            if current_time - self.last_sync_time > 10*60:  # Update every 10 minutes
                await self.update_account_values()
                self.last_sync_time = current_time
        except Exception as e:
            print(f"Error processing copy account order: {e}")

    def handle_my_order_update(self, order_msg):
        """Handle order updates from our trading account"""
        data = order_msg.get('data', [])
        if not data:
            return
            
        for update in data:
            order = update.get('order', {})
            status = update.get('status', '')
            
            if not order or not status:
                continue
                
            coin = order.get('coin')
            oid = order.get('oid')
            side = order.get('side')
            limit_price = order.get('limitPx')
            
            if not all([coin, oid, side, limit_price]):
                continue
            
            key = f"{coin}-{side}-{limit_price}"
            
            # Store the order and status for processing in the main event loop
            asyncio.run_coroutine_threadsafe(
                self.process_my_order(order, status, key),
                self.loop
            )

    async def process_my_order(self, order, status, key):
        """Process order updates from our trading account in the main event loop"""
        try:
            # Update our order tracking
            if status == 'open':
                self.my_orders[key] = order
            elif status in ['canceled', 'rejected']:
                if key in self.my_orders:
                    del self.my_orders[key]
            elif status == 'filled':
                print(f'Filled order: {order["coin"]} {order["side"]} {float(order["origSz"])-float(order["sz"])}@{order["limitPx"]} (size so far)')
                if float(order['sz']) == 0:
                    # Order is fully filled
                    if key in self.my_orders:
                        del self.my_orders[key]
        except Exception as e:
            print(f"Error processing my order: {e}")

    async def sync_order(self, copy_order):
        """Sync a single order from the copy account to our account"""
        try:
            # Wait for account values to be initialized
            if self.copy_account_value == 0 or self.my_account_value == 0:
                await self.update_account_values()
                
            coin = copy_order['coin']
            side = copy_order['side']
            limit_price = float(copy_order['limitPx'])
            order_size = float(copy_order['sz'])
            reduce_only = copy_order.get('reduceOnly', False)
            
            key = f"{coin}-{side}-{limit_price}"
            existing_order = self.my_orders.get(key, None)
            
            # Scale the order size based on account values and leverage
            scaled_size = (order_size * self.my_account_value) / self.copy_account_value
            scaled_size = round(scaled_size, self.sz_decimals[coin])
            scaled_nominal = scaled_size * limit_price
            min_size = 1 / (10 ** self.sz_decimals[coin])
            
            # Check if we need to place a new order
            if not existing_order:
                # Ensure minimum order size
                if scaled_size < min_size:
                    print(f"Skipping order for {coin} @ ${limit_price}: Order size {scaled_size} too small")
                    return
                if scaled_nominal < self.TRADE_LIMIT:
                    print(f"Skipping order for {coin} @ ${limit_price}: Order nominal {scaled_nominal} too small")
                    return

                print(f"Syncing order for {coin} {side} {scaled_size}@${limit_price}")
                await self.place_limit_order(
                    coin,
                    side == 'B',  # True for buy, False for sell
                    scaled_size,
                    limit_price,
                    reduce_only=reduce_only
                )
            else:
                # Check if we need to update the order size
                current_size = float(existing_order['sz'])
                size_diff = abs(current_size - scaled_size)
                
                if size_diff / current_size > 0.01:  # 1% threshold for size difference
                    # Cancel and replace the order
                    if await self.cancel_order(coin, existing_order['oid']):
                        await self.place_limit_order(
                            coin,
                            side == 'B',
                            scaled_size,
                            limit_price,
                            reduce_only=reduce_only
                        )
            
        except Exception as e:
            print(f"Error syncing order: {e}")

    async def cancel_my_matching_order(self, key):
        """Cancel our order that matches a key from the copy account"""
        try:
            if key in self.my_orders:
                order = self.my_orders[key]
                await self.cancel_order(order['coin'], order['oid'])
        except Exception as e:
            print(f"Error cancelling matching order: {e}")

    async def update_account_values(self):
        """Update account values for both accounts"""
        try:
            self.copy_account_value = await self.get_account_value(self.ACCOUNT_TO_COPY)
            raw_my_account_value = await self.get_account_value(self.TRADING_ADDRESS)
            self.my_account_value = raw_my_account_value * self.LEVERAGE
            
            print(f"Account values updated: Copy account: ${self.copy_account_value:,.2f}. My account (with {self.LEVERAGE}x leverage): ${self.my_account_value:,.2f}")
        except Exception as e:
            print(f"Error updating account values: {e}")

    async def snapshot_sync(self, initial):
        """Perform initial synchronization of orders"""
        try:
            # Update account values
            await self.update_account_values()
            
            # Get initial orders
            copy_orders = await self.get_open_orders(self.ACCOUNT_TO_COPY)
            my_orders = await self.get_open_orders(self.TRADING_ADDRESS)
            
            # Store orders in our tracking dictionaries
            for order in copy_orders:
                key = f"{order['coin']}-{order['side']}-{order['limitPx']}"
                self.copy_account_orders[key] = order
                
            for order in my_orders:
                key = f"{order['coin']}-{order['side']}-{order['limitPx']}"
                self.my_orders[key] = order

            if len(copy_orders) != len(my_orders) or initial:
                if initial:
                    print("Initial sync started")
                # Print initial order summary
                self.print_order_summary(copy_orders, "Copy Account Orders")
                self.print_order_summary(my_orders, "My Orders")
            
            # Cancel orders that don't match the copy account
            cancelled_count = 0
            for key, order in list(self.my_orders.items()):
                if key not in self.copy_account_orders:
                    if await self.cancel_order(order['coin'], order['oid']):
                        cancelled_count += 1
                        del self.my_orders[key]
            
            # Place orders that are in the copy account but not in ours
            placed_count = 0
            for key, order in self.copy_account_orders.items():
                if key not in self.my_orders:
                    await self.sync_order(order)
                    placed_count += 1
            
            self.last_sync_time = datetime.datetime.now().timestamp()
            
        except Exception as e:
            print(f"Error in initial sync: {e}")

    async def cancel_all_orders(self):
        """Cancel all open orders for the trading account"""
        print("Cancelling all open orders...")
        orders = await self.get_open_orders(self.TRADING_ADDRESS)
        print(f"Found {len(orders)} open orders")
        cancelled = 0
        failed = 0
        
        for order in orders:
            try:
                coin = order.get('coin')
                oid = order.get('oid')
                
                if await self.cancel_order(coin, oid):
                    cancelled += 1
                else:
                    failed += 1
                    print(f"✗ Failed to cancel order {oid}")
            except Exception as e:
                failed += 1
                print(f"Error cancelling order: {e}")
        
        print(f"Successfully cancelled: {cancelled}")
        print(f"Failed to cancel: {failed}")

    async def shutdown(self):
        """Clean shutdown of the bot"""
        print("\nInitiating shutdown sequence...")
        
        # Cancel all open orders
        await self.cancel_all_orders()
        
        # Disconnect WebSockets
        print("Disconnecting WebSockets...")
        self.info.disconnect_websocket()
        self.info2.disconnect_websocket()
        
        print("Shutdown complete")

    async def run(self):
        print("Starting order copy bot...")
        print(f"Copying from: {self.ACCOUNT_TO_COPY}")
        print(f"Trading with: {self.TRADING_ADDRESS}")
        print(f"Leverage: {self.LEVERAGE}x")
        
        try:
            # Perform initial synchronization
            await self.snapshot_sync(initial = True)
            
            # Subscribe to order updates for both accounts
            print("Setting up WebSocket subscriptions...")
            self.info.subscribe(
                {"type": "orderUpdates", "user": self.ACCOUNT_TO_COPY}, 
                self.handle_copy_account_order_update
            )
            self.info2.subscribe(
                {"type": "orderUpdates", "user": self.TRADING_ADDRESS}, 
                self.handle_my_order_update
            )
            
            print("WebSocket subscriptions active, now processing real-time updates")
            
            # Keep the main task alive
            while True:
                await asyncio.sleep(self.SLEEP_INTERVAL)  # Just keep the main task alive
                await self.snapshot_sync(initial = False)
                
        except asyncio.CancelledError:
            print("Bot operation cancelled")
        except Exception as e:
            print(f"Error in main loop: {e}")
        finally:
            await self.shutdown()

async def main():
    bot = OrderBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("Received shutdown signal, stopping bot...")

if __name__ == "__main__":
    asyncio.run(main())