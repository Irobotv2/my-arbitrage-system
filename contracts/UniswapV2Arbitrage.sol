// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract UniswapV2Arbitrage is Ownable {
    IUniswapV2Router02 public uniswapV2Router;

    event ArbitrageExecuted(address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);

    constructor(address _uniswapV2Router) Ownable(msg.sender) {
        uniswapV2Router = IUniswapV2Router02(_uniswapV2Router);
    }

    function executeArbitrage(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minAmountOut
    ) external onlyOwner {
        IERC20(tokenIn).transferFrom(msg.sender, address(this), amountIn);
        IERC20(tokenIn).approve(address(uniswapV2Router), amountIn);

        address[] memory path = new address[](2);
        path[0] = tokenIn;
        path[1] = tokenOut;

        uint256[] memory amounts = uniswapV2Router.swapExactTokensForTokens(
            amountIn,
            minAmountOut,
            path,
            address(this),
            block.timestamp
        );

        uint256 amountOut = amounts[1];
        require(amountOut >= minAmountOut, "Insufficient output amount");

        // Transfer the output tokens to the owner
        IERC20(tokenOut).transfer(owner(), amountOut);

        emit ArbitrageExecuted(tokenIn, tokenOut, amountIn, amountOut);
    }

    // Function to withdraw any tokens stuck in the contract
    function withdrawToken(address token) external onlyOwner {
        uint256 balance = IERC20(token).balanceOf(address(this));
        IERC20(token).transfer(owner(), balance);
    }

    // Function to withdraw any ETH stuck in the contract
    function withdrawETH() external onlyOwner {
        payable(owner()).transfer(address(this).balance);
    }
}
