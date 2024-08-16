import queue
import networkx as nx
import matplotlib.pyplot as plt

def orfer_bfs(graph, start_node):
    visited = set ()
    q = queue.Queue ()
    q.put(start_node)
    order = []

    while not q.empty():
        vertex = q.get()
        if vertex not in visited:
            order.append(vertex)
            visited.add(vertex)
            for node in graph [vertex]:
                if node not in visited:
                    q.put(node)
    return order


def order_dfs(graph, start_node):
    if visited is None:
        visited = set()

    order = []

    if start_node not in visited:
        order.append(start_node)
        visited.add(start_node)
        for node in graph[start_node]:
            if node not in visited:
                order.extend(order_dfs(graph, node, visited))

    return order


def visualize_search(order, title):
    plt.figure()
    plt.title(title)
    for i, node in enumerate(order, start=1):
        plt.clf()
        plt.title(title)
        nx.draw(G, pos, with_labels=True, node_color=['r' if n == node else 'g' for n in G.nodes])
        plt.draw()
        time.sleep(0.5)


G = nx.Graph()
G.add_edges_from([()])