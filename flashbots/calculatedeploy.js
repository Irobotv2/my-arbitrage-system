const Web3 = require('web3');
const solc = require('solc');

// Connect to an Ethereum node (replace with your node URL)
const web3 = new Web3('https://mainnet.infura.io/v3/0640f56f05a942d7a25cfeff50de344d');

// Compile the contract (simplified, you might use a more robust compilation process)
const input = {
    language: 'Solidity',
    sources: {
        'FlashLoanBundleExecutor.sol': {
            content: '/* paste your contract code here */'
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

const compiledContract = JSON.parse(solc.compile(JSON.stringify(input)));
const bytecode = compiledContract.contracts['FlashLoanBundleExecutor.sol']['FlashLoanBundleExecutor'].evm.bytecode.object;
const abi = compiledContract.contracts['FlashLoanBundleExecutor.sol']['FlashLoanBundleExecutor'].abi;

// Create contract instance
const contract = new web3.eth.Contract(abi);

// Estimate gas
async function estimateDeploymentCost() {
    const deploymentData = contract.deploy({
        data: bytecode,
        arguments: ['0x742d35Cc6634C0532925a3b844Bc454e4438f44e'] // Example executor address
    }).encodeABI();

    const gasEstimate = await web3.eth.estimateGas({
        data: deploymentData
    });

    const gasPrice = await web3.eth.getGasPrice();

    const deploymentCostWei = web3.utils.toBN(gasEstimate).mul(web3.utils.toBN(gasPrice));
    const deploymentCostEth = web3.utils.fromWei(deploymentCostWei, 'ether');

    console.log(`Estimated gas: ${gasEstimate}`);
    console.log(`Current gas price: ${web3.utils.fromWei(gasPrice, 'gwei')} gwei`);
    console.log(`Estimated deployment cost: ${deploymentCostEth} ETH`);
}

estimateDeploymentCost();