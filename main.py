from dotenv import load_dotenv
import os
import asyncio
from pathlib import Path
from langchain_neo4j.graphs.neo4j_graph import Neo4jGraph
from langchain_groq import ChatGroq
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_neo4j import GraphCypherQAChain
from sqlalchemy import text



load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")
AURA_INSTANCEID = os.getenv("AURA_INSTANCEID")
AURA_INSTANCENAME = os.getenv("AURA_INSTANCENAME")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

graph=Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE
)

llm = ChatGroq(model="openai/gpt-oss-20b", api_key=GROQ_API_KEY)

def create_chain(graph, llm):
    text= """ Elon Musk is the CEO of SpaceX and Tesla. He was born in South Africa and later moved to the United States. He is known for his work in the fields of space exploration, electric vehicles, and renewable energy. He has also been involved in various other ventures, including Neuralink and The Boring Company. Also, he has a significant presence on social media and is known for his outspoken personality. """

    documents= [Document(page_content=text, metadata={"source": "input_text"})]

    llm_transformer=LLMGraphTransformer(llm=llm)

    graph_documents = asyncio.run(llm_transformer.aconvert_to_graph_documents(documents))

    print("Graph Documents:", graph_documents)
    print("Graph Nodes:", graph_documents[0].nodes)
    print("Graph Relationships:", graph_documents[0].relationships)


    # Load the dataset of movies and their genres from the local CSV
    csv_path = Path("movies_small.csv").resolve()


    def ingest_movies_from_csv(csv_path: Path, graph: Neo4jGraph) -> None:
        import csv

        rows = []
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                rows.append(
                    {
                        "movieId": r.get("movieId"),
                        "released": r.get("released"),
                        "title": r.get("title"),
                        "imdbRating": r.get("imdbRating") or "0",
                        "directors": [d.strip() for d in r.get("director", "").split("|") if d.strip()],
                        "actors": [a.strip() for a in r.get("actors", "").split("|") if a.strip()],
                        "genres": [g.strip() for g in r.get("genres", "").split("|") if g.strip()],
                    }
                )
        ingest_query = """
        UNWIND $rows AS row
        MERGE (m:Movie {id: row.movieId})
        SET m.released = date(row.released),
            m.title = row.title,
            m.imdbRating = toFloat(row.imdbRating)
        FOREACH (director IN row.directors |
            MERGE (p:Person {name:trim(director)})
            MERGE (p)-[:DIRECTED]->(m))
        FOREACH (actor IN row.actors |
            MERGE (p:Person {name:trim(actor)})
            MERGE (p)-[:ACTED_IN]->(m))
        FOREACH (genre IN row.genres |
            MERGE (g:Genre {name:trim(genre)})
            MERGE (m)-[:IN_GENRE]->(g))
        """

        graph.query(ingest_query, params={"rows": rows})


    # Ingest the local CSV into Neo4j using a parameterized query
    ingest_movies_from_csv(csv_path, graph)

    graph.refresh_schema()
    print("Graph schema after loading movies dataset:", graph.schema)

def main():
    print("Hello from graph-llm!")
    # create_chain(graph, llm)
    chain=GraphCypherQAChain.from_llm(graph=graph, llm=llm, allow_dangerous_requests=True)
    response= chain.invoke({"query":"Who was the director of the movie 'GoldenEye'?"})
    print("Response from GraphCypherQAChain:", response)



if __name__ == "__main__":
    main()
