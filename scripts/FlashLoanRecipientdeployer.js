const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying contracts with the account:", deployer.address);

  // Fetch the contract factory
  const FlashLoanRecipient = await hre.ethers.getContractFactory("FlashLoanRecipient");

  // Deploy the contract
  const flashLoanRecipient = await FlashLoanRecipient.deploy();

  // Wait for the contract to be deployed
  await flashLoanRecipient.deployed();

  console.log("FlashLoanRecipient deployed to:", flashLoanRecipient.address);

  // Verify the contract on Etherscan (if not on a local network)
  if (hre.network.name !== "localhost" && hre.network.name !== "hardhat") {
    console.log("Waiting for block confirmations...");
    await flashLoanRecipient.deployTransaction.wait(5); // Wait for 5 block confirmations

    console.log("Verifying contract on Etherscan...");
    await hre.run("verify:verify", {
      address: flashLoanRecipient.address,
      constructorArguments: [],
    });
  }

  // Optional: Test the contract
  console.log("Testing contract...");
  const owner = await flashLoanRecipient.owner();
  console.log("Contract owner:", owner);

  // You can add more test calls here, for example:
  // const tx = await flashLoanRecipient.makeFlashLoan([token1.address, token2.address], [amount1, amount2], "0x");
  // await tx.wait();
  // console.log("Flash loan initiated");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });