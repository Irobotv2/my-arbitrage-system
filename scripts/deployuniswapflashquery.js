const ethers = require('ethers');
const solc = require('solc');
const fs = require('fs');
require('dotenv').config();

async function compileSolidity(sourceCode) {
    const input = {
        language: 'Solidity',
        sources: {
            'FlashBotsUniswapQuery.sol': {
                content: sourceCode
            }
        },
        settings: {
            outputSelection: {
                '*': {
                    '*': ['*']
                }
            }
        }
    };

    const output = JSON.parse(solc.compile(JSON.stringify(input)));
    const contract = output.contracts['FlashBotsUniswapQuery.sol']['FlashBotsUniswapQuery'];
    
    return {
        abi: contract.abi,
        bytecode: contract.evm.bytecode.object
    };
}

async function deployContract() {
    // Read the Solidity source code
    const sourceCode = fs.readFileSync('FlashBotsUniswapQuery.sol', 'utf8');

    // Compile the contract
    const { abi, bytecode } = await compileSolidity(sourceCode);

    // Connect to the Ethereum network
    const provider = new ethers.JsonRpcProvider(process.env.TENDERLY_URL);
    const wallet = new ethers.Wallet(process.env.PRIVATE_KEY, provider);

    // Create a factory for the contract
    const factory = new ethers.ContractFactory(abi, bytecode, wallet);

    console.log('Deploying contract...');
    const contract = await factory.deploy();
    await contract.waitForDeployment();

    const address = await contract.getAddress();
    console.log('Contract deployed at:', address);

    // Save the contract address and ABI
    const deploymentInfo = {
        address: address,
        abi: abi
    };

    fs.writeFileSync('flashbots_uniswap_query_contract.json', JSON.stringify(deploymentInfo, null, 2));
    console.log('Contract address and ABI saved to flashbots_uniswap_query_contract.json');

    return { address, abi };
}

deployContract().catch(console.error);