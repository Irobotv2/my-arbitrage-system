from web3 import Web3
import asyncio
import json
import time

# Infura WebSocket endpoint
wss = 'wss://mainnet.infura.io/ws/v3/0640f56f05a942d7a25cfeff50de344d'
web3 = Web3(Web3.WebsocketProvider(wss))

print(f"Connected to Ethereum mainnet: {web3.is_connected()}")

# Uniswap V3 Router address
uniswap_v3_router = web3.to_checksum_address('0xE592427A0AEce92De3Edee1F18E0157C05861564')

# Uniswap V3 Router ABI (only including relevant functions for brevity)
uniswap_v3_abi = json.loads('''
[
    {
        "inputs": [
            {
                "components": [
                    {
                        "internalType": "address",
                        "name": "tokenIn",
                        "type": "address"
                    },
                    {
                        "internalType": "address",
                        "name": "tokenOut",
                        "type": "address"
                    },
                    {
                        "internalType": "uint24",
                        "name": "fee",
                        "type": "uint24"
                    },
                    {
                        "internalType": "address",
                        "name": "recipient",
                        "type": "address"
                    },
                    {
                        "internalType": "uint256",
                        "name": "deadline",
                        "type": "uint256"
                    },
                    {
                        "internalType": "uint256",
                        "name": "amountIn",
                        "type": "uint256"
                    },
                    {
                        "internalType": "uint256",
                        "name": "amountOutMinimum",
                        "type": "uint256"
                    },
                    {
                        "internalType": "uint160",
                        "name": "sqrtPriceLimitX96",
                        "type": "uint160"
                    }
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInputSingle",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "amountOut",
                "type": "uint256"
            }
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "internalType": "bytes",
                        "name": "path",
                        "type": "bytes"
                    },
                    {
                        "internalType": "address",
                        "name": "recipient",
                        "type": "address"
                    },
                    {
                        "internalType": "uint256",
                        "name": "deadline",
                        "type": "uint256"
                    },
                    {
                        "internalType": "uint256",
                        "name": "amountIn",
                        "type": "uint256"
                    },
                    {
                        "internalType": "uint256",
                        "name": "amountOutMinimum",
                        "type": "uint256"
                    }
                ],
                "internalType": "struct ISwapRouter.ExactInputParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInput",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "amountOut",
                "type": "uint256"
            }
        ],
        "stateMutability": "payable",
        "type": "function"
    }
]
''')

uniswap_contract = web3.eth.contract(address=uniswap_v3_router, abi=uniswap_v3_abi)

def extract_volume(func_name, func_params):
    if func_name == 'exactInputSingle':
        return func_params['params']['amountIn']
    elif func_name == 'exactInput':
        return func_params['params']['amountIn']
    return 0

def handle_event(tx_hash):
    max_retries = 3
    retry_delay = 0.1  # seconds
    liquidity_threshold = Web3.to_wei(10, 'ether')  # 10 ETH threshold

    for attempt in range(max_retries):
        try:
            if isinstance(tx_hash, bytes):
                tx_hash = tx_hash.hex()

            trans = web3.eth.get_transaction(tx_hash)
            data = trans['input']
            to = trans['to']
            
            if to and to.lower() == uniswap_v3_router.lower():
                try:
                    decoded = uniswap_contract.decode_function_input(data)
                    func_name = decoded[0].fn_name
                    func_params = decoded[1]

                    volume = extract_volume(func_name, func_params)

                    if volume >= liquidity_threshold:
                        print(f"Large liquidity operation found: {func_name}")
                        print(f"Volume: {Web3.from_wei(volume, 'ether')} ETH")
                        print(f"Transaction hash: {tx_hash}")
                        print(f"Etherscan link: https://etherscan.io/tx/{tx_hash}")
                        print(f"Function details: {func_params}")
                        return  # Stop processing after finding a high liquidity transaction
                except Exception as decode_error:
                    print(f"Error decoding transaction: {decode_error}")
            else:
                print('Scanning...')

        except Exception as e:
            print(f'Error scanning liquidity: {e}')
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

async def log_loop(poll_interval):
    last_block = None
    while True:
        try:
            latest_block = web3.eth.get_block('latest')
            if latest_block and latest_block['number'] != last_block:
                print(f"Processing block {latest_block['number']}")
                for tx_hash in latest_block['transactions']:
                    handle_event(tx_hash)
                last_block = latest_block['number']
        except Exception as e:
            print(f"Error getting latest block: {e}")
        await asyncio.sleep(poll_interval)

def main():
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            asyncio.gather(
                log_loop(0.1)))  # Poll every 0.1 seconds
    finally:
        loop.close()

if __name__ == '__main__':
    main()