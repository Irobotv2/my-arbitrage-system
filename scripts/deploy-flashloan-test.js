const hre = require("hardhat");

async function main() {
  console.log("Deploying FlashLoanTest contract...");

  // Get the ContractFactory and Signers
  const FlashLoanTest = await hre.ethers.getContractFactory("FlashLoanTest");
  const [deployer] = await hre.ethers.getSigners();

  console.log("Deploying contracts with the account:", deployer.address);

  // Deploy the contract
  const flashLoanTest = await FlashLoanTest.deploy();

  // Wait for the contract to be mined
  await flashLoanTest.waitForDeployment();

  console.log("FlashLoanTest deployed to:", await flashLoanTest.getAddress());

  // Optionally, you can verify the contract on Etherscan here
  // This step requires you to set up Etherscan API key in your Hardhat config
  if (hre.network.name !== "hardhat" && hre.network.name !== "localhost") {
    console.log("Waiting for block confirmations...");
    await flashLoanTest.deploymentTransaction().wait(5);

    console.log("Verifying contract on Etherscan...");
    await hre.run("verify:verify", {
      address: await flashLoanTest.getAddress(),
      constructorArguments: [],
    });
  }
}

// We recommend this pattern to be able to use async/await everywhere
// and properly handle errors.
main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });