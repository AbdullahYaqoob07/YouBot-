import io
import re
from typing import List, Dict, Any, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from docx import Document
except ImportError:
    Document = None

import tiktoken

class AdaptiveChunker:
    """
    Handles parsing and intelligent chunking of PDFs, DOCX, and text files.
    Supports Vector, Page, and Hybrid chunking modes.
    """
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None
            
    def _count_tokens(self, text: str) -> int:
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        return len(text) // 4  # Fallback approximation

    def extract_text_from_pdf(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract text from PDF returning a list of dicts with text and page numbers."""
        if not fitz:
            raise ImportError("PyMuPDF is required for PDF parsing.")
            
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append({"text": text, "page": i + 1})
        return pages

    def extract_text_from_docx(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract text from DOCX returning a single 'page' of paragraphs."""
        if not Document:
            raise ImportError("python-docx is required for DOCX parsing.")
            
        doc = Document(io.BytesIO(file_bytes))
        full_text = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        return [{"text": full_text, "page": 1}]

    def extract_text_from_txt(self, file_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract text from raw text files."""
        text = file_bytes.decode('utf-8', errors='replace').strip()
        return [{"text": text, "page": 1}]

    def chunk_text_vector_mode(self, text: str, base_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Sliding window semantic chunker targeting specific token sizes.
        Best for Vector-search index ingestion.
        """
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_tokens = self._count_tokens(para)
            if current_tokens + para_tokens > self.chunk_size and current_chunk:
                chunks.append({
                    "content": current_chunk.strip(),
                    "metadata": {**base_metadata, "chunk_size": current_tokens}
                })
                # Overlap logic (simple keep last few words if needed, or just hard restart)
                # Here we just reset for simplicity of Vector mode generic chunking 
                # (could be made more overlap-semantic using LangChain's RecursiveCharacterTextSplitter)
                current_chunk = para + "\n\n"
                current_tokens = para_tokens
            else:
                current_chunk += para + "\n\n"
                current_tokens += para_tokens
                
        if current_chunk:
             chunks.append({
                "content": current_chunk.strip(),
                "metadata": {**base_metadata, "chunk_size": current_tokens}
            })
             
        return chunks

    def process_file(self, file_bytes: bytes, filename: str, mode: str = "vector", metadata: dict = None) -> List[Dict[str, Any]]:
        """
        Main entry for processing a file into structured chunks.
        Modes: 'vector' (semantic sliding window), 'page' (exact page match), 'hybrid' (both).
        """
        base_meta = metadata or {}
        base_meta['source'] = filename
        
        # 1. Parse File
        ext = filename.lower().split('.')[-1]
        if ext == 'pdf':
            pages = self.extract_text_from_pdf(file_bytes)
        elif ext in ['docx', 'doc']:
            pages = self.extract_text_from_docx(file_bytes)
        elif ext in ['txt', 'md', 'csv']:
            pages = self.extract_text_from_txt(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
            
        final_chunks = []
        
        # 2. Chunk according to Mode
        if mode == "page":
            for p in pages:
                final_chunks.append({
                    "content": p['text'],
                    "metadata": {**base_meta, "page": p['page'], "mode": "page"}
                })
        
        elif mode == "vector":
            full_text = "\n\n".join([p['text'] for p in pages])
            final_chunks.extend(self.chunk_text_vector_mode(full_text, {**base_meta, "mode": "vector"}))
            
        elif mode == "hybrid":
            # Hybrid stores both page-level and vector-level chunks
            for p in pages:
                final_chunks.append({
                    "content": p['text'],
                    "metadata": {**base_meta, "page": p['page'], "mode": "page_level_hybrid"}
                })
                
                vector_chunks = self.chunk_text_vector_mode(
                    p['text'], 
                    {**base_meta, "page": p['page'], "mode": "vector_level_hybrid"}
                )
                final_chunks.extend(vector_chunks)

        return final_chunks
