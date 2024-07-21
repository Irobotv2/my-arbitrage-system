// SPDX-License-Identifier: MIT
pragma solidity ^0.7.6;
pragma abicoder v2;

import "@balancer-labs/v2-interfaces/contracts/vault/IVault.sol";
import "@balancer-labs/v2-interfaces/contracts/vault/IFlashLoanRecipient.sol";
import "@balancer-labs/v2-interfaces/contracts/solidity-utils/helpers/BalancerErrors.sol";
import "@balancer-labs/v2-interfaces/contracts/solidity-utils/openzeppelin/IERC20.sol";
import "@openzeppelin/contracts/math/SafeMath.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol";
import "@uniswap/v3-core/contracts/interfaces/IUniswapV3Pool.sol";
import "@uniswap/v3-core/contracts/interfaces/IUniswapV3Factory.sol";
import '@uniswap/v3-core/contracts/libraries/TickMath.sol';
import '@uniswap/v3-periphery/contracts/interfaces/ISwapRouter.sol';

contract FlashLoanArbitrage is IFlashLoanRecipient {
    using SafeMath for uint256;

    IVault private constant BALANCER_VAULT = IVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);
    address private constant UNISWAP_V3_FACTORY = 0x1F98431c8aD98523631AE4a59f267346ea31F984;
    address private constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address public owner;

    struct SwapStep {
        address tokenIn;
        address tokenOut;
        address pool;
        bool isV3;
        uint24 fee;
        uint256 price;
    }

    event SimulationComplete(uint256 flashLoanAmount, uint256 finalAmount, uint256 profit);
    event SimulationError(string message);
    event ArbitrageExecuted(uint256 profit);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    function simulateArbitrage(
        SwapStep[] memory path,
        uint256 flashLoanAmount
    ) external view returns (uint256 estimatedProfit, uint256[] memory simulationResults) {
        uint256 flashLoanFee = flashLoanAmount.mul(1e15).div(1e18); // Assuming 0.1% fee
        
        simulationResults = new uint256[](path.length + 2);
        uint256 currentAmount = flashLoanAmount;

        // Step 1: Flash loan amount
        simulationResults[0] = currentAmount;

        // Simulate swaps
        for (uint i = 0; i < path.length; i++) {
            if (path[i].isV3) {
                currentAmount = simulateV3Swap(currentAmount, path[i].fee, path[i].price);
            } else {
                currentAmount = simulateV2Swap(currentAmount, path[i].price);
            }
            simulationResults[i + 1] = currentAmount;
        }

        // Calculate profit
        uint256 repaymentAmount = flashLoanAmount.add(flashLoanFee);
        if (currentAmount > repaymentAmount) {
            estimatedProfit = currentAmount.sub(repaymentAmount);
        } else {
            estimatedProfit = 0;
        }
        simulationResults[path.length + 1] = estimatedProfit;

        return (estimatedProfit, simulationResults);
    }

    function simulateV2Swap(
        uint256 amountIn,
        uint256 price
    ) public pure returns (uint256 amountOut) {
        amountOut = amountIn.mul(price).div(1e18);
    }

    function simulateV3Swap(
        uint256 amountIn,
        uint24 fee,
        uint256 price
    ) public pure returns (uint256 amountOut) {
        uint256 amountInAfterFee = amountIn.mul(1e6 - fee).div(1e6);
        amountOut = amountInAfterFee.mul(price).div(1e18);
    }

    function executeArbitrage(
        uint256 flashLoanAmount,
        SwapStep[] memory path
    ) external onlyOwner {
        IERC20[] memory tokens = new IERC20[](1);
        tokens[0] = IERC20(path[0].tokenIn);
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = flashLoanAmount;
        BALANCER_VAULT.flashLoan(this, tokens, amounts, abi.encode(path));
    }

    function receiveFlashLoan(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external override {
        require(msg.sender == address(BALANCER_VAULT), "Only Balancer Vault");
        
        SwapStep[] memory path = abi.decode(userData, (SwapStep[]));
        uint256 flashLoanAmount = amounts[0];
        uint256 flashLoanFee = feeAmounts[0];

        uint256 startBalance = IERC20(path[0].tokenIn).balanceOf(address(this));
        
        for (uint i = 0; i < path.length; i++) {
            uint256 amountIn = i == 0 ? flashLoanAmount : IERC20(path[i].tokenIn).balanceOf(address(this));
            if (path[i].isV3) {
                executeV3Swap(path[i].tokenIn, path[i].tokenOut, path[i].pool, amountIn, path[i].fee);
            } else {
                executeV2Swap(path[i].tokenIn, path[i].tokenOut, path[i].pool, amountIn);
            }
        }

        uint256 endBalance = IERC20(path[0].tokenIn).balanceOf(address(this));
        require(endBalance >= startBalance.add(flashLoanFee), "Arbitrage didn't profit");

        IERC20(path[0].tokenIn).transfer(address(BALANCER_VAULT), flashLoanAmount.add(flashLoanFee));

        emit ArbitrageExecuted(endBalance.sub(startBalance).sub(flashLoanFee));
    }

    function executeV2Swap(address tokenIn, address tokenOut, address pool, uint256 amountIn) internal {
        IERC20(tokenIn).transfer(pool, amountIn);
        (uint amount0Out, uint amount1Out) = IUniswapV2Pair(pool).token0() == tokenOut 
            ? (uint(0), IERC20(tokenOut).balanceOf(address(this)))
            : (IERC20(tokenOut).balanceOf(address(this)), uint(0));
        IUniswapV2Pair(pool).swap(amount0Out, amount1Out, address(this), new bytes(0));
    }

    function executeV3Swap(address tokenIn, address tokenOut, address pool, uint256 amountIn, uint24 fee) internal {
        IUniswapV3Pool(pool).swap(
            address(this),
            tokenIn < tokenOut,
            int256(amountIn),
            tokenIn < tokenOut ? TickMath.MAX_SQRT_RATIO - 1 : TickMath.MIN_SQRT_RATIO + 1,
            abi.encode(tokenIn, tokenOut, fee)
        );
    }

    function uniswapV3SwapCallback(
        int256 amount0Delta,
        int256 amount1Delta,
        bytes calldata data
    ) external {
        (address tokenIn, address tokenOut, uint24 fee) = abi.decode(data, (address, address, uint24));
        address pool = IUniswapV3Factory(UNISWAP_V3_FACTORY).getPool(tokenIn, tokenOut, fee);
        require(msg.sender == pool, "Only pool");

        uint256 amountToPay = amount0Delta > 0 ? uint256(amount0Delta) : uint256(amount1Delta);
        IERC20(tokenIn).transfer(msg.sender, amountToPay);
    }

    receive() external payable {}

    function withdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner).transfer(amount);
        } else {
            IERC20(token).transfer(owner, amount);
        }
    }
}