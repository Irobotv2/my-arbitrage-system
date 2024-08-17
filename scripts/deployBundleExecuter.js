const hre = require("hardhat");

async function main() {
  // Get the contract factory
  const FlashBotsMultiCall = await hre.ethers.getContractFactory("FlashBotsMultiCall");

  // Get the account that will deploy the contract
  const [deployer] = await hre.ethers.getSigners();

  console.log("Deploying FlashBotsMultiCall with the account:", deployer.address);

  // Deploy the contract
  // Note: We're passing the deployer's address as the executor for this example
  // You might want to use a different address for the executor in a real-world scenario
  const flashBotsMultiCall = await FlashBotsMultiCall.deploy(deployer.address);

  // Wait for the transaction to be mined
  await flashBotsMultiCall.waitForDeployment();

  // Get the deployed contract address
  const deployedAddress = await flashBotsMultiCall.getAddress();

  console.log("FlashBotsMultiCall deployed to:", deployedAddress);

  // Verify the contract on Etherscan (if not on a local network)
  if (hre.network.name !== "hardhat" && hre.network.name !== "localhost") {
    console.log("Waiting for block confirmations...");
    // Wait for 6 block confirmations
    const receipt = await flashBotsMultiCall.deploymentTransaction().wait(6);
    console.log("Verifying contract...");
    await hre.run("verify:verify", {
      address: deployedAddress,
      constructorArguments: [deployer.address],
    });
  }
}

// Execute the deployment
main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });