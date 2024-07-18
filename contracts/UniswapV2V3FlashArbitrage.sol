// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@uniswap/v3-core/contracts/interfaces/IUniswapV3Pool.sol";
import "@uniswap/v3-periphery/contracts/interfaces/ISwapRouter.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract UniswapV2V3FlashArbitrage {
    IUniswapV2Router02 private immutable uniswapV2Router;
    ISwapRouter private immutable uniswapV3Router;
    address public owner;

    struct ArbitrageParameters {
        address tokenIn;
        address tokenOut;
        uint256 amount;
        uint256 minOutV2;
        uint256 minOutV3;
        uint24 v3Fee;
        bool useV3;
    }

    event ArbitrageInitiated(address tokenIn, address tokenOut, uint256 amount, bool useV3);
    event ArbitrageExecuted(address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut, uint256 profit);
    event ErrorOccurred(string step, string reason);

    constructor(address _uniswapV2Router, address _uniswapV3Router) {
        uniswapV2Router = IUniswapV2Router02(_uniswapV2Router);
        uniswapV3Router = ISwapRouter(_uniswapV3Router);
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    function initiateArbitrage(ArbitrageParameters memory params) external onlyOwner {
        emit ArbitrageInitiated(params.tokenIn, params.tokenOut, params.amount, params.useV3);
        
        if (params.useV3) {
            IUniswapV3Pool pool = IUniswapV3Pool(params.tokenIn);
            pool.flash(
                address(this),
                params.amount,
                0,
                abi.encode(params)
            );
        } else {
            IUniswapV2Pair pair = IUniswapV2Pair(params.tokenIn);
            pair.swap(
                params.amount,
                0,
                address(this),
                abi.encode(params)
            );
        }
    }

    function uniswapV3FlashCallback(
        uint256 fee0,
        uint256 fee1,
        bytes calldata data
    ) external {
        ArbitrageParameters memory params = abi.decode(data, (ArbitrageParameters));
        require(msg.sender == params.tokenIn, "Unauthorized callback");

        executeArbitrage(params, fee0);
    }

    function uniswapV2Call(
        address sender,
        uint amount0,
        uint amount1,
        bytes calldata data
    ) external {
        ArbitrageParameters memory params = abi.decode(data, (ArbitrageParameters));
        require(msg.sender == params.tokenIn, "Unauthorized callback");

        executeArbitrage(params, 0);
    }

    function executeArbitrage(ArbitrageParameters memory params, uint256 fee) internal {
        // Perform V2 to V3 swap
        IERC20(params.tokenIn).approve(address(uniswapV2Router), params.amount);
        address[] memory path = new address[](2);
        path[0] = params.tokenIn;
        path[1] = params.tokenOut;

        uint256[] memory amounts = uniswapV2Router.swapExactTokensForTokens(
            params.amount,
            params.minOutV2,
            path,
            address(this),
            block.timestamp
        );
        uint256 amountOutV2 = amounts[1];

        // Perform V3 to V2 swap
        IERC20(params.tokenOut).approve(address(uniswapV3Router), amountOutV2);
        ISwapRouter.ExactInputSingleParams memory v3Params = ISwapRouter.ExactInputSingleParams({
            tokenIn: params.tokenOut,
            tokenOut: params.tokenIn,
            fee: params.v3Fee,
            recipient: address(this),
            deadline: block.timestamp,
            amountIn: amountOutV2,
            amountOutMinimum: params.minOutV3,
            sqrtPriceLimitX96: 0
        });

        uint256 amountOutV3 = uniswapV3Router.exactInputSingle(v3Params);

        // Repay flash swap
        uint256 amountToRepay = params.amount + fee;
        require(amountOutV3 >= amountToRepay, "Insufficient funds to repay");
        IERC20(params.tokenIn).transfer(params.tokenIn, amountToRepay);

        uint256 profit = amountOutV3 - amountToRepay;
        emit ArbitrageExecuted(params.tokenIn, params.tokenOut, params.amount, amountOutV3, profit);
    }

    function withdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner).transfer(amount);
        } else {
            IERC20(token).transfer(owner, amount);
        }
    }

    receive() external payable {}
}