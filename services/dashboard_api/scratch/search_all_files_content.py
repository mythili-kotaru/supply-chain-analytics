import os
import glob
import zipfile
import xml.etree.ElementTree as ET

search_paths = ["/Users/mythilikotaru/Downloads", "/Users/mythilikotaru/Desktop"]
doc_extensions = (".md", ".txt", ".html", ".docx")

def get_docx_text(path):
    try:
        with zipfile.ZipFile(path) as docx:
            xml_content = docx.read('word/document.xml')
            root = ET.fromstring(xml_content)
            paragraphs = []
            for para in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                texts = [node.text for node in para.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if node.text]
                if texts:
                    paragraphs.append(''.join(texts))
            return '\n'.join(paragraphs)
    except Exception:
        return ""

def search_text_file(path, queries):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            for q in queries:
                if q in content:
                    return q, content
    except Exception:
        pass
    return None

queries = ["Day 13", "Day 14", "Day 15", "Week 6"]

for base in search_paths:
    if os.path.exists(base):
        for root, dirs, files in os.walk(base):
            for f in files:
                path = os.path.join(root, f)
                ext = os.path.splitext(f)[1].lower()
                if ext == ".docx":
                    text = get_docx_text(path)
                    for q in queries:
                        if q in text:
                            print(f"Found '{q}' in docx: {path}")
                            # Print matching lines
                            for line in text.split('\n'):
                                if q in line:
                                    print(f"  {line[:150]}")
                elif ext in [".txt", ".md", ".html"]:
                    res = search_text_file(path, queries)
                    if res:
                        q, text = res
                        print(f"Found '{q}' in text file: {path}")
                        for line in text.split('\n'):
                            if q in line:
                                print(f"  {line[:150]}")
