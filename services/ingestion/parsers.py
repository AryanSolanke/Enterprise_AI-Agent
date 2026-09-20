import io

from fastapi import UploadFile


async def extract_text_from_upload(file: UploadFile) -> str:
    content = await file.read()
    
    if file.filename and file.filename.lower().endswith(".pdf"):
        import pypdf
        pdf_reader = pypdf.PdfReader(io.BytesIO(content))
        text = []
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text.append(extracted)
        return "\n\n".join(text)
        
    elif file.filename and file.filename.lower().endswith(".docx"):
        import docx
        doc = docx.Document(io.BytesIO(content))
        text = []
        for para in doc.paragraphs:
            if para.text:
                text.append(para.text)
        return "\n".join(text)
        
    else:
        # Fallback to plain text
        return content.decode("utf-8", errors="replace")
