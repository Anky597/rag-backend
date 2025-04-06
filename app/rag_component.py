# app/rag_components.py
# Optimized for Render deployment using ephemeral storage (/tmp/...)

import os
import json
import logging
import shutil # For removing potentially leftover ephemeral directories
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv # Still useful if you test locally before pushing

# Langchain Imports (ensure these are correct)
try:
    from langchain_core.documents import Document
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser
    from langchain_community.vectorstores.utils import filter_complex_metadata
except ImportError as e:
    print(f"Error importing LangChain components: {e}")
    # In production, you might want to log this and exit more gracefully
    exit(1)

# --- Load Environment Variables ---
# Loads .env ONLY if it exists (won't exist on Render)
load_dotenv()

# --- Configuration from Environment ---
# *** READ THE PATH FROM RENDER ENV VAR ***
# Default to /tmp for safety if not set, but it MUST be set correctly in Render Env Vars
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "/tmp/default_ephemeral_db")
JSON_DATA_PATH = os.getenv("JSON_DATA_PATH") # Must be set in Render to find data/..json
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash-latest")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Global cache/variables ---
embedding_model = None
vector_store = None
llm = None
rag_chain = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger(__name__)

# --- Document Loading and Processing Functions ---
# PASTE format_list_field and create_shl_documents_from_json HERE
# (Ensure these are identical to your working local versions)
# ... (function definitions omitted for brevity - they don't change) ...
def format_list_field(field_data: Optional[List[str]], field_name: str) -> str:
    if field_data and isinstance(field_data, list) and len(field_data) > 0:
        items = "\n".join([f"  - {str(item).strip()}" for item in field_data if str(item).strip()])
        if items: return f"\n{field_name}:\n{items}"
    return ""

def create_shl_documents_from_json(json_file_path: str) -> List[Document]:
    documents: List[Document] = []
    log.info(f"Attempting to load documents from: {json_file_path}")
    if not json_file_path or not os.path.exists(json_file_path):
        log.error(f"Error: JSON data path not set or file not found at '{json_file_path}'. Check JSON_DATA_PATH env var.")
        raise FileNotFoundError(f"Source JSON file not found or path not set: '{json_file_path}'")
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        log.info(f"Successfully loaded JSON data.")
    except Exception as e:
        log.error(f"Error loading or parsing JSON {json_file_path}: {e}")
        raise ValueError(f"Failed to load or parse JSON: {e}") from e
    if not isinstance(data, list):
         log.error("JSON data is not a list as expected.")
         raise TypeError("Expected JSON data to be a list of categories.")
    # Document creation logic
    for category in data:
        if not isinstance(category, dict): continue
        category_name = category.get("categoryName", "Unknown Category")
        products = category.get("products")
        if not products or not isinstance(products, list): continue
        for product in products:
            if not isinstance(product, dict): continue
            product_name = product.get("productName")
            description = product.get("description")
            if not product_name or not description: continue
            page_content_parts = [
                f"Category: {str(category_name).strip()}",
                f"Product: {str(product_name).strip()}",
                f"Description: {str(description).strip()}"]
            page_content_parts.append(format_list_field(product.get("specificUseCases"), "Specific Use Cases"))
            page_content_parts.append(format_list_field(product.get("targetAudience"), "Target Audience"))
            page_content_parts.append(format_list_field(product.get("measures"), "Measures"))
            page_content = "\n".join(filter(None, page_content_parts))
            metadata: Dict[str, Any] = {
                "source": os.path.basename(json_file_path),
                "category": str(category_name).strip(),
                "product_name": str(product_name).strip()}
            target_audience = product.get("targetAudience")
            if target_audience and isinstance(target_audience, list):
                metadata["target_audience"] = [str(ta).strip() for ta in target_audience if str(ta).strip()]
            measures = product.get("measures")
            if measures and isinstance(measures, list):
                metadata["measures"] = [str(m).strip() for m in measures if str(m).strip()]
            doc = Document(page_content=page_content, metadata=metadata)
            documents.append(doc)
    log.info(f"Successfully created {len(documents)} LangChain Document objects from {json_file_path}.")
    return documents

# --- Component Initialization Functions ---
def get_embedding_model():
    global embedding_model
    if embedding_model is None:
        log.info(f"(Re)Initializing embedding model: {EMBEDDING_MODEL_NAME}")
        try:
            embedding_model = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL_NAME,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            log.info("Embedding model initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize embedding model: {e}", exc_info=True)
            raise RuntimeError(f"Embedding model initialization failed: {e}") from e
    return embedding_model

def build_or_load_vector_store():
    """
    Builds the vector store on EVERY call for Render's ephemeral filesystem.
    Ensures it's fresh for the current container instance.
    """
    global vector_store # We will overwrite the global store each time
    emb_model = get_embedding_model()

    # --- Always remove directory if it exists ---
    # Important for ephemeral environment to ensure no stale data if /tmp wasn't cleared
    if os.path.exists(VECTOR_DB_PATH):
        log.warning(f"Removing existing directory at ephemeral path: {VECTOR_DB_PATH}")
        try:
            shutil.rmtree(VECTOR_DB_PATH)
        except Exception as e:
             log.error(f"Could not remove existing ephemeral directory {VECTOR_DB_PATH}: {e}")
             # Might proceed, but could indicate issues

    log.info(f"Building FRESH ephemeral Vector DB at '{VECTOR_DB_PATH}' using source: {JSON_DATA_PATH}")
    try:
        # Ensure parent directory exists for VECTOR_DB_PATH (especially for /tmp paths)
        os.makedirs(os.path.dirname(VECTOR_DB_PATH), exist_ok=True)

        all_documents = create_shl_documents_from_json(JSON_DATA_PATH)
        if not all_documents: raise ValueError("No documents created from JSON.")

        log.info("Applying metadata filter...")
        filtered_documents = filter_complex_metadata(all_documents)
        if not filtered_documents: raise ValueError("Filtering resulted in zero documents.")
        log.info(f"Proceeding with {len(filtered_documents)} filtered documents.")

        log.info(f"Creating NEW ephemeral Chroma DB at {VECTOR_DB_PATH}. This will take time...")
        # Create the store - it writes files to VECTOR_DB_PATH
        vector_store = Chroma.from_documents(
            documents=filtered_documents,
            embedding=emb_model,
            persist_directory=VECTOR_DB_PATH # Chroma needs this even if not truly persisting long-term
        )
        # NO NEED TO LOAD - we just built it.
        log.info(f"Successfully CREATED ephemeral vector store at {VECTOR_DB_PATH}")

    except FileNotFoundError as fnf:
         log.error(f"Build failed: Source JSON file not found. Check JSON_DATA_PATH. Error: {fnf}", exc_info=True)
         raise RuntimeError(f"Source data file error: {fnf}") from fnf
    except Exception as e:
         log.error(f"Error creating ephemeral vector store: {e}", exc_info=True)
         raise RuntimeError(f"Ephemeral vector store creation failed: {e}") from e

    # Return the newly created store instance
    return vector_store

def get_llm():
    global llm
    if llm is None:
        log.info(f"(Re)Initializing Google Gemini LLM: {LLM_MODEL_NAME}")
        if not GOOGLE_API_KEY:
            log.error("GOOGLE_API_KEY environment variable not set.")
            raise ValueError("Missing Google API Key configuration.")
        try:
            # Ensure env var is set for the langchain lib
            os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
            llm = ChatGoogleGenerativeAI(model=LLM_MODEL_NAME, temperature=0.3)
            log.info("Google Gemini LLM initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize Gemini LLM: {e}", exc_info=True)
            raise RuntimeError(f"LLM initialization failed: {e}") from e
    return llm

def format_docs(docs: List[Document]) -> str:
    # ... (format_docs function remains the same) ...
    formatted_list = []
    for i, doc in enumerate(docs):
        product = doc.metadata.get('product_name', 'N/A')
        category = doc.metadata.get('category', 'N/A')
        metadata_str = f"(Product: {product}, Category: {category})"
        formatted_list.append(f"--- Context Document {i+1} {metadata_str} ---\n{doc.page_content}")
    return "\n\n".join(formatted_list)

def get_rag_chain(num_docs=4):
    """
    Builds the RAG chain FOR THE CURRENT REQUEST/STARTUP.
    Crucially calls `build_or_load_vector_store` which ALWAYS rebuilds.
    """
    # NOTE: We are NOT caching the chain globally anymore because the underlying
    # vector store instance might change if this was kept alive between restarts
    # in a more complex setup. Rebuilding the chain definition is cheap.
    log.info(f"Building RAG chain for current request/startup (retrieving top {num_docs} docs)...")
    try:
        # *** ALWAYS BUILD/LOAD THE VECTOR STORE FOR THIS START ***
        # This is the core change for the ephemeral strategy
        current_vector_store = build_or_load_vector_store()
        if not current_vector_store:
             raise RuntimeError("Failed to get a valid vector store instance.")
        # ********************************************************

        retriever = current_vector_store.as_retriever(search_kwargs={'k': num_docs})
        llm_instance = get_llm() # Ensure LLM is ready

        # ... (Prompt template definition remains the same) ...
        prompt_template_str = """
        You are an expert AI assistant specializing in SHL assessments... (rest of prompt)

        CONTEXT:
        {context}

        QUESTION:
        {question}

        ANSWER:
        """
        prompt = ChatPromptTemplate.from_template(prompt_template_str)

        # Define the chain structure
        rag_chain_instance = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm_instance
            | StrOutputParser()
        )
        log.info("RAG chain built successfully for this request/startup.")
        return rag_chain_instance # Return the newly built chain

    except Exception as e:
         log.error(f"Failed to build RAG chain: {e}", exc_info=True)
         # Propagate the error up so main.py can handle it
         raise RuntimeError(f"RAG chain building failed: {e}") from e