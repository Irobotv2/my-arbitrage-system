const hre = require("hardhat");
const { ethers } = hre;

const QUOTER_ABI = [
    {
      inputs: [
        { internalType: "address", name: "tokenIn", type: "address" },
        { internalType: "address", name: "tokenOut", type: "address" },
        { internalType: "uint24", name: "fee", type: "uint24" },
        { internalType: "uint256", name: "amountIn", type: "uint256" },
        { internalType: "uint160", name: "sqrtPriceLimitX96", type: "uint160" }
      ],
      name: "quoteExactInputSingle",
      outputs: [{ internalType: "uint256", name: "amountOut", type: "uint256" }],
      stateMutability: "nonpayable",
      type: "function"
    }
  ];
  
  const quoter = new ethers.Contract(uniswapV3QuoterAddress, QUOTER_ABI, deployer);
async function checkPrices(uniswapV2Router, quoter, wethAmount, path) {
  const amountsOutV2 = await uniswapV2Router.getAmountsOut(wethAmount, path);
  console.log("Uniswap V2 expected output:", ethers.formatUnits(amountsOutV2[1], 6));

  const fee = 3000; // 0.3% fee tier
  try {
    const quoteV3 = await quoter.callStatic.quoteExactInputSingle(
      path[0],
      path[1],
      fee,
      wethAmount,
      0
    );
    console.log("Uniswap V3 expected output:", ethers.formatUnits(quoteV3, 6));
  } catch (error) {
    console.error("Error getting Uniswap V3 quote:", error.message);
  }
}

async function main() {
  try {
    const [deployer] = await ethers.getSigners();
    console.log("Using account:", deployer.address);

    const provider = ethers.provider;
    console.log("Connected to network:", await provider.getNetwork());
    console.log("Current block number:", await provider.getBlockNumber());

    const arbitrageAddress = "0x16c2560bb2821e56a20c073963e9908298f68200";
    console.log("Using Arbitrage contract at:", arbitrageAddress);

    const ArbitrageContract = await ethers.getContractAt("FlashLoanArbitrage", arbitrageAddress);

    const contractOwner = await ArbitrageContract.owner();
    console.log("Contract owner:", contractOwner);
    console.log("Deployer address:", deployer.address);
    if (contractOwner !== deployer.address) {
      console.error("Deployer is not the contract owner. Only the owner can initiate arbitrage.");
      return;
    }

    const WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
    const USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";

    const WETH = await ethers.getContractAt("IWETH", WETH_ADDRESS);
    const USDC = await ethers.getContractAt("@openzeppelin/contracts/token/ERC20/IERC20.sol:IERC20", USDC_ADDRESS);

    const wethAmount = ethers.parseEther("1"); // 1 ETH for testing
    await WETH.deposit({ value: wethAmount });
    console.log(`Wrapped ${ethers.formatEther(wethAmount)} ETH to WETH`);

    await WETH.approve(arbitrageAddress, wethAmount);
    console.log("Approved arbitrage contract to spend WETH");

    // Transfer WETH to the arbitrage contract
    await WETH.transfer(arbitrageAddress, wethAmount);
    console.log(`Transferred ${ethers.formatEther(wethAmount)} WETH to arbitrage contract`);

    const uniswapV2RouterAddress = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D";
    const uniswapV3QuoterAddress = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"; // Uniswap V3 Quoter
    const uniswapV2Router = await ethers.getContractAt("IUniswapV2Router02", uniswapV2RouterAddress);
    const quoter = await ethers.getContractAt("IQuoter", uniswapV3QuoterAddress);

    await checkPrices(uniswapV2Router, quoter, wethAmount, [WETH_ADDRESS, USDC_ADDRESS]);

    const initialWethBalance = await WETH.balanceOf(arbitrageAddress);
    const initialUsdcBalance = await USDC.balanceOf(arbitrageAddress);
    console.log("Initial WETH balance of arbitrage contract:", ethers.formatEther(initialWethBalance));
    console.log("Initial USDC balance of arbitrage contract:", ethers.formatUnits(initialUsdcBalance, 6));

    const minOut = ethers.parseUnits("1000", 6); // Minimum expected USDC output

    // Prepare parameters for initiateArbitrage
    const tokens = [WETH_ADDRESS];
    const amounts = [wethAmount];
    const userData = ethers.AbiCoder.defaultAbiCoder().encode(
      ['address', 'address', 'uint256'],
      [WETH_ADDRESS, USDC_ADDRESS, minOut]
    );

    try {
      const gasEstimate = await ArbitrageContract.estimateGas.initiateArbitrage(tokens, amounts, userData);
      console.log("Estimated gas:", gasEstimate.toString());

      console.log("Initiating arbitrage...");
      const tx = await ArbitrageContract.initiateArbitrage(tokens, amounts, userData, {
        gasLimit: gasEstimate.mul(120).div(100) // Add 20% buffer
      });
      console.log("Transaction hash:", tx.hash);
      const receipt = await tx.wait();
      console.log(`Arbitrage initiation successful. Gas used: ${receipt.gasUsed.toString()}`);
    } catch (error) {
      console.error("Error initiating arbitrage:", error.message);
      if (error.data) {
        console.error("Error data:", error.data);
      }
    }

    const finalWethBalance = await WETH.balanceOf(arbitrageAddress);
    const finalUsdcBalance = await USDC.balanceOf(arbitrageAddress);
    console.log("Final WETH balance of arbitrage contract:", ethers.formatEther(finalWethBalance));
    console.log("Final USDC balance of arbitrage contract:", ethers.formatUnits(finalUsdcBalance, 6));

    // Check for profit
    const profit = finalWethBalance.sub(initialWethBalance);
    console.log("Profit in WETH:", ethers.formatEther(profit));

  } catch (error) {
    console.error("Error:", error);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Error in main execution:", error);
    process.exit(1);
  });