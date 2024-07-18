const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();

  console.log("Deploying contracts with the account:", deployer.address);

  console.log("Account balance:", (await deployer.getBalance()).toString());

  // Uniswap V2 Router address (Mainnet)
  const uniswapV2RouterAddress = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D";

  // Uniswap V3 Router address (Mainnet)
  const uniswapV3RouterAddress = "0xE592427A0AEce92De3Edee1F18E0157C05861564";

  const DynamicFlashLoanArbitrage = await hre.ethers.getContractFactory("DynamicFlashLoanArbitrage");
  const dynamicFlashLoanArbitrage = await DynamicFlashLoanArbitrage.deploy(
    uniswapV2RouterAddress,
    uniswapV3RouterAddress
  );

  await dynamicFlashLoanArbitrage.deployed();

  console.log("DynamicFlashLoanArbitrage deployed to:", dynamicFlashLoanArbitrage.address);

  // Verify the contract on Etherscan
  console.log("Waiting for 5 block confirmations...");
  await dynamicFlashLoanArbitrage.deployTransaction.wait(5);

  console.log("Verifying contract on Etherscan...");
  await hre.run("verify:verify", {
    address: dynamicFlashLoanArbitrage.address,
    constructorArguments: [uniswapV2RouterAddress, uniswapV3RouterAddress],
  });

  console.log("Contract verified on Etherscan");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });