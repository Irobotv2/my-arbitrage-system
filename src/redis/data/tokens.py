import requests
import os
import logging

# Replace with your Etherscan API key
ETHERSCAN_API_KEY = 'E3519M3AP3NCS68GZGTYHR1FEHX62THRRI'

# Set the file path for the log file
log_file_path = '/home/irobot/projects/my-arbitrage-system/src/redis/data/token_ids.log'

# Set up logging
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Function to fetch token details
def fetch_token_details():
    url = f'https://api.etherscan.io/api?module=token&action=tokenlist&apikey={ETHERSCAN_API_KEY}'
    response = requests.get(url)
    data = response.json()
    
    if data['status'] == '1':
        tokens = data['result']
        for token in tokens[:1000]:  # Limit to the top 1000 tokens
            token_name = token['symbol']
            token_address = token['contractAddress']
            token_decimals = token['decimals']
            
            # Log in the format: WETH:0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2:18
            logging.info(f"{token_name}:{token_address}:{token_decimals}")
            print(f"{token_name}:{token_address}:{token_decimals}")  # Print to console for quick verification
            time.sleep(0.2)  # Respect the rate limit of 5 requests per second
    else:
        logging.error(f"Error fetching tokens: {data['message']}")

if __name__ == "__main__":
    fetch_token_details()
    logging.info(f"Token details fetched and saved to {log_file_path}")