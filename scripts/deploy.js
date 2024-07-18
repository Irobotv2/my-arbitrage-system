const hre = require("hardhat");

async function main() {
  try {
    const [deployer] = await hre.ethers.getSigners();
    console.log("Deploying contracts with the account:", deployer.address);
    
    // For ethers v6, use provider.getBalance() instead of signer.getBalance()
    const balance = await hre.ethers.provider.getBalance(deployer.address);
    console.log("Account balance:", balance.toString());

    // Get the contract factory
    const DynamicFlashLoanArbitrage = await hre.ethers.getContractFactory("DynamicFlashLoanArbitrage");

    // Define Uniswap router addresses
    const UNISWAP_V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"; // Uniswap V2 router address on mainnet
    const UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"; // Uniswap V3 router address on mainnet

    console.log("Deploying DynamicFlashLoanArbitrage...");

    // Deploy the contract
    const dynamicFlashLoanArbitrage = await DynamicFlashLoanArbitrage.deploy(UNISWAP_V2_ROUTER, UNISWAP_V3_ROUTER);

    // Wait for the contract to be deployed
    await dynamicFlashLoanArbitrage.waitForDeployment();

    const deployedAddress = await dynamicFlashLoanArbitrage.getAddress();
    console.log("DynamicFlashLoanArbitrage deployed to:", deployedAddress);

    // Log the deployment transaction hash
    const deploymentTransaction = dynamicFlashLoanArbitrage.deploymentTransaction();
    if (deploymentTransaction) {
      console.log("Deployment transaction hash:", deploymentTransaction.hash);
    } else {
      console.log("Deployment transaction information not available");
    }

    console.log("Deployment completed successfully");

    // Optional: Verify the contract on Etherscan
    if (hre.network.name !== "hardhat" && hre.network.name !== "localhost") {
      console.log("Waiting for block confirmations...");
      await deploymentTransaction.wait(5); // Wait for 5 block confirmations

      console.log("Verifying contract on Etherscan...");
      try {
        await hre.run("verify:verify", {
          address: deployedAddress,
          constructorArguments: [UNISWAP_V2_ROUTER, UNISWAP_V3_ROUTER],
        });
        console.log("Contract verified on Etherscan");
      } catch (error) {
        console.error("Error verifying contract on Etherscan:", error);
      }
    } else {
      console.log("Skipping Etherscan verification on local network");
    }

  } catch (error) {
    console.error("Error during deployment:", error);
    process.exit(1);
  }
}

// Execute the deployment
main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Unhandled error:", error);
    process.exit(1);
  });