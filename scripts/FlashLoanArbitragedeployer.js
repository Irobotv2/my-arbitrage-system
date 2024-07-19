const hre = require("hardhat");

async function main() {
  // Get the ContractFactory and Signer
  const FlashLoanArbitrage = await hre.ethers.getContractFactory("FlashLoanArbitrage");
  const [deployer] = await hre.ethers.getSigners();

  console.log("Deploying FlashLoanArbitrage contract with the account:", deployer.address);

  // Deploy the contract
  const flashLoanArbitrage = await FlashLoanArbitrage.deploy();

  // Wait for the contract to be deployed
  await flashLoanArbitrage.waitForDeployment();

  console.log("FlashLoanArbitrage contract deployed to:", await flashLoanArbitrage.getAddress());

  // Verify the contract on Etherscan
  if (hre.network.name !== "hardhat" && hre.network.name !== "localhost") {
    console.log("Waiting for block confirmations...");
    // Wait for 6 block confirmations
    const deploymentReceipt = await flashLoanArbitrage.deploymentTransaction().wait(6);
    console.log("Verifying contract on Etherscan...");
    await hre.run("verify:verify", {
      address: await flashLoanArbitrage.getAddress(),
      constructorArguments: [],
    });
  }

  console.log("Deployment and verification complete!");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });