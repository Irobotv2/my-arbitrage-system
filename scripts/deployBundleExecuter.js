const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying contracts with the account:", deployer.address);

  const creatorAddress = "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF";
  console.log("Creator address:", creatorAddress);

  const BundleExecutor = await hre.ethers.getContractFactory("BundleExecutor");
  const bundleExecutor = await BundleExecutor.deploy(creatorAddress);

  // Wait for the deployment transaction to be mined
  await bundleExecutor.waitForDeployment();

  // Get the deployed contract address
  const deployedAddress = await bundleExecutor.getAddress();

  console.log("BundleExecutor deployed to:", deployedAddress);

  // Optionally, verify the contract on Tenderly
  if (hre.network.name === "virtual_mainnet") {
    console.log("Verifying contract on Tenderly...");
    await hre.tenderly.verify({
      name: "BundleExecutor",
      address: deployedAddress,
    });
    console.log("Contract verified on Tenderly");
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });