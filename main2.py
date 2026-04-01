from dotenv import load_dotenv
import os
import asyncio
from pathlib import Path

from langchain_neo4j.graphs.neo4j_graph import Neo4jGraph
from langchain_groq import ChatGroq
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_neo4j import GraphCypherQAChain

from pdf_utils import extract_text_from_pdf


load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE,
)

# Wrap graph.query to prevent sending non-Cypher text (e.g. model apologies)
# to the Neo4j server which causes a CypherSyntaxError. Invalid/unsafe
# generated output will be saved to `generated_cypher_debug.txt` and an
# empty result will be returned instead of calling the real driver.
_original_query = graph.query
def _safe_query(query, params=None, **kwargs):
    q = (query or "").strip()
    if not q:
        return []
    q_upper = q.upper()
    first_tok = q_upper.split()[0]
    allowed_start_tokens = {
        "ALTER","ORDER","CALL","CREATE","LOAD","START","STOP",
        "DEALLOCATE","DELETE","DENY","DETACH","DROP","DRYRUN",
        "FILTER","FINISH","FOREACH","GRANT","INSERT","LET","LIMIT",
        "MATCH","MERGE","NODETACH","OFFSET","OPTIONAL","REALLOCATE",
        "REMOVE","RENAME","RETURN","REVOKE","ENABLE","SET","SHOW",
        "SKIP","TERMINATE","UNWIND","USE","WHEN","WITH","UNWIND"
    }
    # Allow JSON-like queries starting with '{' as well
    if first_tok not in allowed_start_tokens and not q.startswith("{"):
        debug_path = Path("generated_cypher_debug.txt")
        with open(debug_path, "w", encoding="utf-8") as df:
            df.write(query)
        print(f"Blocked invalid Cypher and saved output to {debug_path}")
        return []
    return _original_query(query, params=params, **kwargs)

graph.query = _safe_query

llm = ChatGroq(model="openai/gpt-oss-20b", api_key=GROQ_API_KEY)


def ingest_pdf_to_graph(pdf_path: Path, graph: Neo4jGraph, llm) -> None:
    """Extract text from PDF, convert to graph documents with the LLM, and insert into Neo4j.

    Run this once to populate the DB; comment out the call afterwards when only
    running queries against the graph.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    text = extract_text_from_pdf(str(pdf_path))

    # Simple character-based chunking that avoids cutting words mid-token.
    def chunk_text(s: str, chunk_size: int = 3000, overlap: int = 300):
        start = 0
        n = len(s)
        chunks = []
        while start < n:
            end = min(start + chunk_size, n)
            if end < n:
                last_space = s.rfind(" ", start, end)
                if last_space > start:
                    end = last_space
            chunk = s[start:end].strip()
            if chunk:
                chunks.append(chunk)
            # advance with overlap
            next_start = end - overlap
            if next_start <= start:
                next_start = end
            start = next_start
        return chunks

    chunks = chunk_text(text)
    transformer = LLMGraphTransformer(llm=llm, ignore_tool_usage=True)

    all_graph_documents = []
    for idx, chunk in enumerate(chunks):
        doc = Document(page_content=chunk, metadata={"source": str(pdf_path), "chunk_index": idx})
        try:
            # convert each chunk individually so one failure doesn't block the whole ingest
            converted = asyncio.run(transformer.aconvert_to_graph_documents([doc]))
            if converted:
                all_graph_documents.extend(converted)
        except Exception as e:
            # Save per-chunk debug info and fall back to inserting the chunk as a Document node
            import traceback, datetime, hashlib

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            err_path = Path(f"groq_chunk_error_{idx}_{ts}.txt")
            with open(err_path, "w", encoding="utf-8") as ef:
                ef.write("Exception:\n")
                ef.write(repr(e) + "\n\n")
                ef.write("Traceback:\n")
                ef.write(traceback.format_exc())
                ef.write("\n\nChunk:\n")
                ef.write(chunk)

            print(f"Chunk conversion failed; saved debug info to {err_path}")
            # fallback: insert chunk as a Document node
            try:
                doc_id = hashlib.md5((str(pdf_path) + str(idx)).encode("utf-8")).hexdigest()
                ingest_cypher = (
                    "MERGE (d:Document {id: $id})\n"
                    "SET d.text = $text, d.source = $source, d.chunk_index = $chunk_index"
                )
                graph.query(ingest_cypher, params={
                    "id": doc_id,
                    "text": chunk,
                    "source": str(pdf_path),
                    "chunk_index": idx,
                })
                print(f"Inserted fallback Document chunk node id={doc_id}")
            except Exception as qe:
                print("Fallback ingest of chunk into Neo4j failed:", repr(qe))

    # import any converted graph documents
    if all_graph_documents:
        graph.add_graph_documents(all_graph_documents, include_source=True)

    graph.refresh_schema()
    print("Ingested PDF into graph. Imported chunks:", len(chunks), "graph_documents:", len(all_graph_documents))


def create_chain(graph: Neo4jGraph, llm):
    """Create and return a GraphCypherQAChain (acknowledging risks)."""
    return GraphCypherQAChain.from_llm(graph=graph, llm=llm, allow_dangerous_requests=True)


def main():
    pdf_path = Path("storybook.pdf")

    # Run this once to ingest the PDF into Neo4j. Comment out after first run
    # if you only want to create the chain and run queries.
    # try:
    #     ingest_pdf_to_graph(pdf_path, graph, llm)
    # except FileNotFoundError:
    #     print(f"storybook.pdf not found at {pdf_path}. Skipping ingestion.")

    chain = create_chain(graph, llm)
    print("Chain created. To run a query, call `chain.invoke({'query': '...'} )`.")
    response=chain.invoke({"query": "What is 'beard'?"})
    print("Response to query:", response)


if __name__ == "__main__":
    main()
