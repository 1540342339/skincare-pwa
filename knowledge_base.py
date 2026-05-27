import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings
    import warnings
    warnings.warn("langchain-huggingface 未安装，可用 'pip install -U langchain-huggingface' 消除弃用警告", UserWarning)
from langchain_community.vectorstores import Chroma

CHROMA_PATH = "chroma_db"

_embeddings = None

def _get_embeddings():
    """惰性加载 embedding 模型（首次调用时才下载）"""
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
    return _embeddings

def build_knowledge_base(data_dir="data"):
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        return None
    loader = DirectoryLoader(data_dir, glob="**/*.txt", loader_cls=TextLoader,
                             loader_kwargs={"encoding": "utf-8"})
    documents = loader.load()
    if not documents:
        return None
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(documents)
    emb = _get_embeddings()
    vectorstore = Chroma.from_documents(chunks, emb, persist_directory=CHROMA_PATH)
    vectorstore.persist()
    return vectorstore

def load_knowledge_base():
    if os.path.exists(CHROMA_PATH):
        emb = _get_embeddings()
        return Chroma(persist_directory=CHROMA_PATH, embedding_function=emb)
    return None