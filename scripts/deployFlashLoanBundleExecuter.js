const hre = require("hardhat");
const { ethers } = hre;

async function main() {
  console.log("Deploying FlashLoanBundleExecutor...");

  // Get the ContractFactory and Signers
  const FlashLoanBundleExecutor = await ethers.getContractFactory("FlashLoanBundleExecutor");
  const [deployer] = await ethers.getSigners();

  console.log("Deploying contract with the account:", deployer.address);

  // We need to pass the executor address to the constructor
  // For this example, we'll use the deployer's address as the executor
  // In a real-world scenario, you might want to use a different address
  const executorAddress = deployer.address;

  // Deploy the contract
  const flashLoanBundleExecutor = await FlashLoanBundleExecutor.deploy(executorAddress);

  // Wait for the contract to be mined and deployed
  await flashLoanBundleExecutor.waitForDeployment();

  // Get the address of the deployed contract
  const contractAddress = await flashLoanBundleExecutor.getAddress();

  console.log("FlashLoanBundleExecutor deployed to:", contractAddress);
  console.log("Executor address set to:", executorAddress);

  // Verify the contract on Etherscan if not on a local network
  if (hre.network.name !== "hardhat" && hre.network.name !== "localhost") {
    console.log("Waiting for block confirmations...");
    // Wait for 6 block confirmations for Etherscan verification
    await flashLoanBundleExecutor.deploymentTransaction().wait(6);
    console.log("Verifying contract on Etherscan...");
    await hre.run("verify:verify", {
      address: contractAddress,
      constructorArguments: [executorAddress],
    });
    console.log("Contract verified on Etherscan");
  }
}

// Execute the deployment
main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });