# HyperLiquid Copy Trader

Copy trading application for HyperLiquid.

## Dev requirements
- Python 3.11+
- Poetry

For development you can just run the python modules locally after you fill in your .env based on env_sample.

## Deployment howto

```bash
# Setup docker
sudo apt install docker.io docker-compose-v2
# Enable crosscompilation of docker images for arm64
sudo apt-get install qemu binfmt-support qemu-user-static # Install the qemu packages
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes # This step will execute the registering scripts
docker run --platform=linux/arm64/v8 --rm -t arm64v8/ubuntu uname -m # Testing the emulation environment
```
You may need to add your user to docker group and relogin if the above fails.

Then fill in .env based on env_sample and run `./deploy.sh -b`.

You can check logs from server using eg.

   docker --context copytrader-remote compose --project-name copytrader logs -n 100 -f
 
## Scripts Overview

### OrderBot
A bot that copies orders from a target account:
- Monitors and copies open orders from a specified account
- Maintains proportional position sizes based on account values
- Only opens orders below entry price from target address
- Handles order placement, cancellation, and updates
- Includes 24-hour SLA monitoring
- Supports limit orders with reduce-only option

### TradingBot 
A position-based copy trading bot:
- Copies positions instead of individual orders
- Only opens positions below entry price from target address
- Automatically adjusts position sizes based on account values
- Includes price-aware entry strategy
- Supports delayed trades for better entry prices
- Provides detailed position monitoring and reporting
- Handles position updates and closures

## License
MIT License
