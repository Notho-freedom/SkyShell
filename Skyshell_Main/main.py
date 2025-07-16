from neoj4 import Neo4jClient, SkyShellMonitor

if __name__ == "__main__":
    client = Neo4jClient(
        uri="neo4j+s://eac1883e.databases.neo4j.io",
        user="neo4j",
        password="BfYuTIta_wx6hkyLleCVk7TqEb0NsH3OWbVmeIIk6uw"
    )

    monitor = SkyShellMonitor(client, interval_sec=5)
    try:
        monitor.run()
    finally:
        client.close()
