const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying contracts with the account:", deployer.address);

  // Fetch the contract factory
  const FlashLoanRecipient = await hre.ethers.getContractFactory("FlashLoanRecipient");

  // Deploy the contract
  const flashLoanRecipient = await FlashLoanRecipient.deploy();

  // Wait for the contract to be deployed
  await flashLoanRecipient.waitForDeployment();

  console.log("FlashLoanRecipient deployed to:", await flashLoanRecipient.getAddress());
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });