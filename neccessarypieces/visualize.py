import matplotlib.pyplot as plt
import networkx as nx
import logging

# Import necessary functions from your main script
from main_script import load_configurations_from_redis, generate_arbitrage_paths  # Replace 'main_script' with the actual name of your main script

# Initialize logging
logging.basicConfig(level=logging.INFO)

def visualize_arbitrage_paths(graph, paths):
    """
    Visualizes the arbitrage paths using NetworkX and Matplotlib.
    """
    G = nx.DiGraph()  # Directed graph to show flow direction

    # Add nodes (tokens) to the graph
    for token_address, token in graph.tokens.items():
        G.add_node(token.symbol)

    # Add edges (pools) for each path
    for path in paths:
        for i, (pool, token_in, token_out) in enumerate(path):
            # Determine the pool type and set color accordingly
            pool_color = 'blue' if pool.is_v3 else 'green'
            G.add_edge(token_in.symbol, token_out.symbol, color=pool_color, weight=2)

    # Define node positions using spring layout
    pos = nx.spring_layout(G, k=0.5, iterations=50)

    # Get edge colors based on pool type
    edge_colors = [G[u][v]['color'] for u, v in G.edges()]

    # Draw nodes, edges, and labels
    plt.figure(figsize=(12, 10))
    nx.draw_networkx_nodes(G, pos, node_color='skyblue', node_size=1000)
    nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=2)
    nx.draw_networkx_labels(G, pos, font_size=10, font_weight='bold')

    plt.title("Arbitrage Paths Visualization")
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('arbitrage_paths.png', dpi=300)
    plt.show()
    logging.info("Arbitrage paths visualization saved as 'arbitrage_paths.png'")

if __name__ == "__main__":
    # Assume graph and paths are generated from your main script
    graph = load_configurations_from_redis()
    paths = generate_arbitrage_paths(graph)
    
    # Visualize the paths
    visualize_arbitrage_paths(graph, paths)
