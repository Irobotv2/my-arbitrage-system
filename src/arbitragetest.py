import asyncio
import aiomysql
import logging
from decimal import Decimal, getcontext
from datetime import datetime, timedelta

# Set higher precision for Decimal calculations
getcontext().prec = 30

# Configure logging
logging.basicConfig(filename='arbitrage_opportunities.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'arbitrage_user',
    'password': 'Newpassword1!',
    'db': 'arbitrage_system',
    'maxsize': 5,
    'minsize': 1,
}

async def check_arbitrage(conn):
    opportunities = []
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT 
                t0.symbol AS token0_symbol,
                t1.symbol AS token1_symbol,
                v2.pair_address AS v2_pair,
                v3.pool_address AS v3_pool,
                v2.calculated_price AS v2_price,
                v3.calculated_price AS v3_price,
                ABS(v2.calculated_price - v3.calculated_price) / LEAST(v2.calculated_price, v3.calculated_price) * 10000 AS basis_points_diff
            FROM 
                uniswap_v2_pairs v2
            JOIN 
                uniswap_v3_pools v3 ON v2.token0_address = v3.token0_address AND v2.token1_address = v3.token1_address
            JOIN 
                tokens t0 ON v2.token0_address = t0.address
            JOIN 
                tokens t1 ON v2.token1_address = t1.address
            WHERE 
                v2.calculated_price > 0 AND v3.calculated_price > 0
            ORDER BY 
                basis_points_diff DESC
            LIMIT 100
        """)
        pairs = await cur.fetchall()

        logging.info(f"Checking {len(pairs)} matching V2-V3 pairs")

        for pair in pairs:
            token0_symbol, token1_symbol, v2_pair, v3_pool, v2_price, v3_price, basis_points_diff = pair
            
            logging.info(f"Analyzing pair: {token0_symbol}/{token1_symbol}")
            logging.info(f"V2 Pair: {v2_pair}, Price: {v2_price}")
            logging.info(f"V3 Pool: {v3_pool}, Price: {v3_price}")
            logging.info(f"Basis Points Difference: {basis_points_diff:.2f}")

            if basis_points_diff > 30:  # 0.3% threshold
                opportunity = {
                    'pair': f"{token0_symbol}/{token1_symbol}",
                    'v2_pair': v2_pair,
                    'v3_pool': v3_pool,
                    'v2_price': Decimal(v2_price),
                    'v3_price': Decimal(v3_price),
                    'basis_points': Decimal(basis_points_diff),
                    'direction': "Buy on V2, sell on V3" if Decimal(v2_price) < Decimal(v3_price) else "Buy on V3, sell on V2"
                }
                opportunities.append(opportunity)
                logging.info(f"Potential arbitrage opportunity found! {opportunity}")
            else:
                logging.info("No significant arbitrage opportunity.")
            
            logging.info("---")

    return opportunities

async def insert_opportunities(conn, opportunities):
    async with conn.cursor() as cur:
        for opp in opportunities:
            await cur.execute("""
                INSERT INTO arbitrage_opportunities 
                (pair, v2_pair, v3_pool, v2_price, v3_price, basis_points, direction)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                opp['pair'], opp['v2_pair'], opp['v3_pool'], 
                opp['v2_price'], opp['v3_price'], opp['basis_points'], opp['direction']
            ))
        await conn.commit()

async def monitor_arbitrage(duration_hours=12):
    pool = await aiomysql.create_pool(**DB_CONFIG)
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=duration_hours)
    total_opportunities = 0
    unique_pairs = set()
    last_insert_time = {}

    try:
        async with pool.acquire() as conn:
            while datetime.now() < end_time:
                opportunities = await check_arbitrage(conn)
                current_time = datetime.now()
                for opp in opportunities:
                    pair = opp['pair']
                    if pair not in last_insert_time or (current_time - last_insert_time[pair]).total_seconds() > 300:  # 5 minutes cooldown
                        try:
                            await insert_opportunities(conn, [opp])
                            total_opportunities += 1
                            unique_pairs.add(pair)
                            last_insert_time[pair] = current_time
                            logging.info(f"Inserted arbitrage opportunity: {opp}")
                        except Exception as e:
                            logging.error(f"Error inserting opportunity: {e}")

                await asyncio.sleep(60)  # Wait for 1 minute before next check

        logging.info(f"Monitoring completed. Duration: {duration_hours} hours")
        logging.info(f"Total arbitrage opportunities found: {total_opportunities}")
        logging.info(f"Unique pairs with arbitrage opportunities: {len(unique_pairs)}")
        logging.info(f"Average opportunities per hour: {total_opportunities / duration_hours:.2f}")

    except Exception as e:
        logging.error(f"An error occurred during monitoring: {e}")
    finally:
        pool.close()
        await pool.wait_closed()

async def main():
    await monitor_arbitrage(duration_hours=12)

if __name__ == "__main__":
    asyncio.run(main())
