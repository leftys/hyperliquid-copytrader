import asyncio
import os
import datetime
import math
import requests
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from dotenv import load_dotenv
from logger_config import setup_logging

# Load environment variables
load_dotenv(override=True)

# Initialize logger
logger = setup_logging('position_bot')

# Initialize Hyperliquid
account: LocalAccount = eth_account.Account.from_key(os.getenv("PRIVATE_KEY_API"))
exchange = Exchange(
    account, 
    constants.MAINNET_API_URL, 
    vault_address=os.getenv("VAULT_ADDRESS", "") or None, 
    account_address=os.getenv("ACCOUNT_ADDRESS", "") or None
)
info = Info(constants.MAINNET_API_URL, skip_ws=True)

# Get exchange metadata
meta = info.meta()

# Create szDecimals map
sz_decimals = {}
for asset_info in meta["universe"]:
    sz_decimals[asset_info["name"]] = asset_info["szDecimals"]

# Global variables from environment
ACCOUNT_TO_COPY = os.getenv("ACCOUNT_TO_COPY")
TRADING_ADDRESS = os.getenv("TRADING_ADDRESS")
LEVERAGE = float(os.getenv("LEVERAGE", "5"))
SLEEP_INTERVAL = float(os.getenv("SLEEP_INTERVAL", "5"))
TRADE_LIMIT = 10  # min trade size $10
MINI_ALLOC_OF_PF = 0  # mini allocation in percent

def print_position_summary(positions, title):
    if not positions:
        logger.info(f"\n{title}: No open positions")
        return
        
    logger.info(f"\n{title}:")
    total_value = 0
    
    for coin, pos in positions.items():
        direction = "Long" if pos["szi"] > 0 else "Short"
        size = abs(pos["szi"])
        entry_price = pos["entryPxTotal"]
        value = abs(pos["positionValue"])
        total_value += value
        
        logger.info(f"  {coin}: {direction} {size:.4f} @ ${entry_price:.2f} ({value:.2f}%)")
    
    logger.info(f"\nTotal Position Value: {total_value:.2f}%")

class TradingBot:
    def __init__(self, trading_address, account_to_copy, path_file):
        self.trading_address = trading_address
        self.account_to_copy = account_to_copy
        self.path_file = path_file
        self.previous_positions = {}
        logger.info(f"Initialized TradingBot with trading_address={trading_address}, account_to_copy={account_to_copy}")

    async def get_position(self, account):
        try:
            url = 'https://api.hyperliquid.xyz/info'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/json',
                'Origin': 'https://app.hyperliquid.xyz',
                'Referer': 'https://app.hyperliquid.xyz/',
            }
            
            response = requests.post(url, json={"type": "clearinghouseState", "user": account}, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if not data:
                raise ValueError("Empty response received")
                
            position_data = {
                "address": account,
                "accountValue": data["crossMarginSummary"]["accountValue"],
                "assetPositions": data["assetPositions"]
            }
            return position_data
        except Exception as e:
            logger.exception(f"Error in get_position for account {account}")
            raise

    async def get_allocations(self, account):
        try:
            top = [await self.get_position(account)]
            total_account_value = float(top[0]["accountValue"])
            positions = {}
            
            for item in top:
                for pos in item["assetPositions"]:
                    coin = pos["position"]["coin"]
                    entry_px = float(pos["position"]["entryPx"])
                    szi = float(pos["position"]["szi"])
                    position_value = float(pos["position"]["positionValue"])
                    
                    if szi < 0:
                        position_value = -position_value
                        
                    if coin in positions:
                        positions[coin]["positionValue"] += position_value
                        positions[coin]["szi"] += szi
                        positions[coin]["entryPxTotal"] += entry_px
                    else:
                        positions[coin] = {
                            "positionValue": position_value,
                            "szi": szi,
                            "entryPxTotal": entry_px
                        }

            # Calculate percentages and round values
            for coin in positions:
                positions[coin]["positionValue"] = round((positions[coin]["positionValue"] / total_account_value) * 100, 2)
                positions[coin]["szi"] = round(positions[coin]["szi"], 5)

            return dict(sorted(positions.items(), key=lambda x: abs(x[1]["positionValue"]), reverse=True))
        except Exception as e:
            logger.exception(f"Error in get_allocations for account {account}")
            raise

    async def get_perpetuals_price(self):
        try:
            response = requests.post(
                'https://api.hyperliquid.xyz/info',
                json={"type": "allMids"},
                headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Content-Type': 'application/json',
                    'Origin': 'https://app.hyperliquid.xyz',
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception(f"Error in get_perpetuals_price")
            raise

    async def cancel_all_orders_on_market(self, market):
        try:
            open_orders = info.open_orders(TRADING_ADDRESS)
                
            for order in open_orders:
                if order.get("coin") == market:
                    oid = order.get("oid")
                    cancel_result = exchange.cancel(market, oid)
                    if cancel_result["status"] != "ok":
                        logger.error(f"Failed to cancel order {oid} for {market}: {cancel_result}")
        except Exception as e:
            logger.exception(f"Error in cancel_all_orders_on_market for {market}")
            raise

    async def execute_trade(self, market, order_type, position_type, size):
        try:
            # Cancel all open orders for this market to avoid conflicts with order_bot if running as well
            await self.cancel_all_orders_on_market(market)
                
            size = round(float(size), sz_decimals[market])
            market_price = float((await self.get_perpetuals_price())[market])

            if size * market_price < TRADE_LIMIT:
                logger.info(f"Trade size {size} {market} is below minimum trade limit ${TRADE_LIMIT}")
                return False, f"Trade size {size} {market} is below minimum trade limit ${TRADE_LIMIT}"

            is_buy = order_type == "buy"
            
            logger.info(f"Executing {order_type} trade for {size} {market} at market price ${market_price}")
            
            order_result = exchange.market_open(market, is_buy, size, market_price, 0.01)
            
            if order_result["status"] == "ok":
                for status in order_result["response"]["data"]["statuses"]:
                    if "filled" in status:
                        filled = status["filled"]
                        trade_msg = f"{'Buy' if is_buy else 'Sell'} {filled['totalSz']} {market} @ ${float(filled['avgPx']):.2f}"
                        logger.info(f"Trade executed successfully: {trade_msg}")
                        return True, trade_msg
                    else:
                        error_msg = f"Trade Error: {status.get('error', 'Unknown error')}"
                        logger.error(error_msg)
                        return False, error_msg
            logger.error(f"Order failed: {order_result}")
            return False, "Order failed"
        except Exception as e:
            error_msg = f"Error executing trade: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

    async def process_positions(self):
        try:
            while True:
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                
                # Get account values
                copy_account_value = float(await self.get_balance(self.account_to_copy))
                my_account_value = float(await self.get_balance(self.trading_address)) * LEVERAGE
                
                logger.info(f"\n=== Position Update {current_time} ===")
                logger.info(f"Master Account: ${copy_account_value:,.2f}")
                logger.info(f"Copy Account: ${my_account_value:,.2f} (with {LEVERAGE}x leverage)")
                
                # Get current market prices
                prices = await self.get_perpetuals_price()
                pending_actions = []
                
                # Get and display positions
                my_positions = await self.get_allocations(self.trading_address)
                copy_positions = await self.get_allocations(self.account_to_copy)
                
                print_position_summary(copy_positions, "Master Account Positions")
                print_position_summary(my_positions, "Copy Account Positions")

                # Process pending changes
                # if self.pending_changes:
                #     for market, change in list(self.pending_changes.items()):
                #         current_price = float(prices[market])
                #         is_price_favorable = (change["direction"] == "long" and current_price <= change["entryPrice"]) or \
                #                           (change["direction"] == "short" and current_price >= change["entryPrice"])
                        
                #         if is_price_favorable:
                #             success, msg = await self.execute_trade(
                #                 market,
                #                 "buy" if change["direction"] == "long" else "sell",
                #                 change["direction"],
                #                 abs(change["size"])
                #             )
                #             if success:
                #                 pending_actions.append(f"Executed delayed trade: {msg}")
                #             del self.pending_changes[market]

                # Process position updates
                updates = await self.update_positions(my_positions, copy_positions, prices)
                pending_actions.extend(updates)

                # Print updates if any changes were made
                if pending_actions:
                    logger.info("\nPosition Updates:")
                    for action in pending_actions:
                        logger.info(f"• {action}")
                
                await asyncio.sleep(SLEEP_INTERVAL)

        except KeyboardInterrupt:
            logger.info("\nShutting down...")
            return
        except Exception as e:
            logger.error(f"Error in process_positions: {str(e)}", exc_info=True)
            await asyncio.sleep(5)
            await self.process_positions()

    async def update_positions(self, my_positions, copy_positions, prices):
        actions = []
        try:
            copy_account_value = float(await self.get_balance(self.account_to_copy))
            my_account_value = float(await self.get_balance(self.trading_address)) * LEVERAGE
            
            for coin, copy_pos in copy_positions.items():
                price = float(prices[coin])
                entry_price = copy_pos["entryPxTotal"]
                
                copy_position_value = abs(copy_pos["szi"] * price)
                target_size = (copy_position_value / copy_account_value) * my_account_value / price
                target_size_signed = math.copysign(target_size, copy_pos["szi"])
                target_size_value = target_size * price
                my_pos = my_positions.get(coin)  # Changed this line to use dictionary get
                
                if not my_pos and target_size_value > TRADE_LIMIT:
                    if ((copy_pos["szi"] > 0 and price < entry_price) or 
                        (copy_pos["szi"] < 0 and price > entry_price)):
                        success, msg = await self.execute_trade(
                            coin,
                            "buy" if copy_pos["szi"] > 0 else "sell",
                            "long" if copy_pos["szi"] > 0 else "short",
                            abs(target_size)
                        )
                        if success:
                            actions.append(f"Opened new position: {msg}")
                
                elif my_pos:
                    current_size = abs(my_pos["szi"])
                    size_diff = target_size_signed - my_pos['szi']
                    size_diff_value = size_diff * price
                    
                    if abs(size_diff_value) > TRADE_LIMIT:
                        is_size_up_and_same_dir = abs(target_size) > abs(current_size) and target_size * current_size > 0
                        
                        if is_size_up_and_same_dir:
                            is_favorable = ((size_diff > 0 and price <= entry_price) or 
                                        (size_diff < 0 and price >= entry_price))
                            
                            if not is_favorable:
                                # self.pending_changes[coin] = {
                                #     "timestamp": time.time(),
                                #     "size": abs(size_diff),
                                #     "direction": "long" if size_diff > 0 else "short",
                                #     "entryPrice": entry_price
                                # }
                                continue
                        
                        success, msg = await self.execute_trade(
                            coin,
                            "buy" if size_diff > 0 else "sell",
                            "long" if target_size_signed > 0 else "short",
                            abs(size_diff)
                        )
                        if success:
                            actions.append(f"Adjusted position: {msg}")
            
            # Close positions no longer in copy account
            for coin, pos in my_positions.items():  # Changed this line to iterate over dictionary items
                if coin not in copy_positions:
                    success, msg = await self.execute_trade(
                        coin,
                        "buy" if pos["szi"] < 0 else "sell",
                        "flat",
                        abs(pos["szi"])
                    )
                    if success:
                        actions.append(f"Closed position: {msg}")
                    
            return actions
            
        except Exception as e:
            logger.exception(f"Error in update_positions")
            return actions

    async def get_balance(self, address):
        try:
            response = requests.post(
                'https://api.hyperliquid.xyz/info',
                json={"type": "clearinghouseState", "user": address},
                headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Content-Type': 'application/json',
                    'Origin': 'https://app.hyperliquid.xyz',
                }
            )
            response.raise_for_status()
            data = response.json()
            if not data or "crossMarginSummary" not in data:
                raise ValueError("Invalid response format")
            return data["crossMarginSummary"]["accountValue"]
        except Exception as e:
            logger.exception(f"Error in get_balance")
            raise

async def main():
    # Initialize and start the trading bot
    bot = TradingBot(TRADING_ADDRESS, ACCOUNT_TO_COPY, "")
    await bot.process_positions()

if __name__ == "__main__":
    asyncio.run(main())