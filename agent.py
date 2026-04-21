
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import csv
import os 
import json
from dotenv import load_dotenv
import urllib.request as libreq
import urllib.parse as parse
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from fpdf import FPDF


try:
    # Newer docs often show this path.
    from google.adk.agents.llm_agent import Agent  # type: ignore
except Exception:  # pragma: no cover
    from google.adk.agents import Agent  # type: ignore


from google.adk.models.lite_llm import LiteLlm 

# ==========================================
# DEFINICIÓN DE TOOLS 
# ==========================================

def search_arxiv_abstracts(topic :str) -> Dict[str, str]:
    #Search in ArXiv's API top relevant papers about the topic
    #and return a dictionary with
    #key: ArXiv ID
    #value: Abstract

    maxResults = 3
    res = {}

    sortBy = "relevance" #other options are "lastUpdatedDate","submittedDate"
    searchQuery = "all:" + parse.quote(topic)
    link = f"http://export.arxiv.org/api/query?search_query={searchQuery}&sortBy={sortBy}&start=0&max_results={maxResults}" 

    try:
        with libreq.urlopen(link) as url:
            r = url.read()
        
        response = ET.fromstring(r)
        ns = {'atom': 'http://www.w3.org/2005/Atom'} #API's namespace

        
        for entry in response.findall('atom:entry',ns):
                
                abstract = entry.find("atom:summary",ns).text.replace('\n', ' ')
                id_url = entry.find("atom:id",ns).text
                paper_id = id_url.split("/")[-1] 

                title = entry.find("atom:title",ns).text.replace('\n', ' ').strip()
                year = entry.find("atom:published", ns).text[:4]
                authors_list = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]
                authors = ", ".join(authors_list)

                res[paper_id] = f"TITLE: {title} | AUTHORS: {authors} | YEAR: {year} | ABSTRACT: {abstract}" #We are also taking, title, authors and year now to build bibliography later
        
        if not res:
             return {"error": "No papers found for this topic"}
        else:
             return res
        
    except Exception as e:
        return {"Error": f"{e}"}
    
def read_section(paperID: str, sectionKW: str) -> str:
    # Fetches the HTML version of an ArXiv paper and extracts the text of a specific section 
    url = f"https://ar5iv.labs.arxiv.org/html/{paperID}"

    try:
        req = libreq.Request(url, headers={'User-Agent': 'Mozilla/5.0'}) # We use headers to avoid bans
        with libreq.urlopen(req) as response:
            html = response.read()
        
        soup = BeautifulSoup(html, 'html.parser')

        headers = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

        targetHeader = None
        for header in headers: 
            if sectionKW.lower() in header.get_text().lower():
                targetHeader = header
                break

        if not targetHeader:
            #In order to reduce token usage we are just taking the first words of the section
            sections = [" ".join(h.get_text().strip().split()[:4]) for h in headers if h.get_text().strip()]
            
            #To check there are not two equal named sections
            sections_unicas = list(dict.fromkeys(sections)) 
            sections_txt = ", ".join(sections_unicas)
            

            return f"Error: Section '{sectionKW}' not found in this paper. Available sections are: {sections_txt}. Please call this tool again using one of these exact section names."    

        content = []
        targetLevel = int(targetHeader.name[1])

        for sibling in targetHeader.find_next_siblings():
            if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                siblingLevel = int(sibling.name[1])

                if siblingLevel <= targetLevel:
                    break
                else:
                    content.append(f"\n--- {sibling.get_text().strip()} ---")

            else:
                text = sibling.get_text().strip()
                if text:  
                    content.append(text)
                
        res = " ".join(content)

        if not res:
            return f"Error: The section '{sectionKW}' does not have text."

        words = res.split()
        if len(words) > 800:
            res = " ".join(words[:800]) + "... [Text truncated to save context memory, try again with a more specific section?]"

        return f"SECTION '{sectionKW.upper()}' CONTENT:\n{res}"
    
    except Exception as e:
        return f"Error: {e}"

def clean_text(text):
    # Convierte el texto de UTF-8 a Latin-1 para que FPDF lo entienda
    return text.encode('latin-1', 'replace').decode('latin-1')


def generate_pdf(title:str, sections: dict, bibliography:str) -> str:
    
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    #TITLE
    pdf.set_font("Arial", 'B', 24) #title font, bold, size
    pdf.multi_cell(0, 12, clean_text(title), align='C')
    pdf.ln(10)
    #BODY
    for name, text in sections.items():
        # Section's title
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, clean_text(name), ln=True)
        pdf.ln(2)
        
        # Text
        pdf.set_font("Times", size=12)
        pdf.multi_cell(0, 8, clean_text(text))
        pdf.ln(5)
    #Bibliography
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, clean_text("Bibliografía"), ln=True)
    pdf.ln(5)
    
    pdf.set_font("Times", size=10) 
    pdf.multi_cell(0, 6, clean_text(bibliography))

    #Export
    try:
        os.makedirs("output", exist_ok=True)
        name =  "".join([c if c.isalnum() else "_" for c in title])
        path = f"output/informe_{name}.pdf"
        pdf.output(path)
        return f"SUCCESS: PDF generated successfully at {path}"
    except Exception as e:
        return f"ERROR: Failed to generate PDF: {e}"

def generate_json(title: str, sections: dict, num_references: int) -> str:
    
    sections_list = []
    total_words = 0
    
    
    for name, text in sections.items():
        
        word_count = len(text.split()) + len(name.split())
        total_words += word_count
        
       
        sections_list.append({
            "name": name,
            "word_count": word_count
        })

    
    safe_title = "".join([c if c.isalnum() else "_" for c in title])
    pdf_path = f"output/informe_{safe_title}.pdf"
    json_path = f"output/informe_{safe_title}.json"

    
    report_data = {
        "title": title,
        "sections": sections_list,
        "total_words": total_words,
        "num_sections": len(sections_list),
        "num_references": num_references,
        "pdf_path": pdf_path
    }
    
    
    try:
        os.makedirs("output", exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=4)
        
        
        return f"SUCCESS: JSON generado en {json_path}\n\nJSON RESULTANTE:\n{json.dumps(report_data, ensure_ascii=False, indent=2)}"
    
    except Exception as e:
        return f"ERROR: JSON generation failed: {e}"




# ---------------------------
# Root agent
# ---------------------------
load_dotenv()
api_key = os.getenv("POLI_API_KEY")
api_base = os.getenv("POLI_API_BASE")

root_agent = Agent(
    model = LiteLlm(model="openai/gpt-oss-120b", api_base=api_base, api_key=api_key),
    name="root_agent",
    description="Investigador experto que busca en ArXiv y estructura informes en PDF y JSON.",
    
    instruction=(
        "Eres un Investigador Académico Senior y Redactor Científico de élite. "
        "Tu objetivo es investigar temas complejos en ArXiv, extraer conocimiento empírico real, "
        "formatearlo en un PDF y estructurar la salida en JSON para su evaluación automática.\n\n"
        
        "Eres extremadamente meticuloso: NUNCA inventas o alucinas datos. "
        "Si haces una afirmación, es porque la has leído directamente de un paper usando tus herramientas.\n\n"

        "REGLA GLOBAL CRÍTICA PARA EL USO DE HERRAMIENTAS:\n"
        "Cuando llames a CUALQUIER herramienta (search_arxiv_abstracts, read_section, generate_pdf, generate_json), "
        "DEBES usar EXACTAMENTE su nombre real. ESTÁ TOTALMENTE PROHIBIDO añadir pensamientos, comentarios, etiquetas ocultas, "
        "o sufijos extraños como '<|channel|>commentary' al nombre de la herramienta. Llama a las funciones de forma limpia y directa.\n\n"
        
        "Para completar tu tarea con éxito DEBES seguir ESTRICTAMENTE este flujo en 6 fases:\n\n"
        
        "FASE 1: FILTRADO INTELIGENTE (Tool: search_arxiv_abstracts)\n"
        "1. Extrae 2 o 3 PALABRAS CLAVE en inglés del tema solicitado.\n"
        "2. Llama a 'search_arxiv_abstracts' para obtener los papers.\n"
        "3. LEE LOS ABSTRACTS y descarta los papers que no aporten valor real al tema. Guarda en memoria solo los datos (Título, Autor, Año, ID) de los 3 papers más relevantes.\n\n"
        
        "FASE 2: INVESTIGACIÓN PROFUNDA (Tool: read_section)\n"
        "1. Para los papers seleccionados en la Fase 1, llama a 'read_section' para leer secciones clave.\n"
        "2. Si una sección no existe, usa la lista de sugerencias del error para intentarlo de nuevo.\n"
        "3. NO copies y pegues el texto que leas. Tu objetivo es entender los conceptos, los resultados y las ideas principales para usarlos como base de tu redacción posterior.\n\n"
        
        "FASE 3: SÍNTESIS Y REDACCIÓN (Memoria interna)\n"
        "1. ESTRICTAMENTE PROHIBIDO COPIAR Y PEGAR TEXTOS DE LOS PAPERS. Debes SINTETIZAR la información leída, cruzar los datos de los diferentes papers y redactar un informe original, coherente y fluido ÍNTEGRAMENTE EN ESPAÑOL.\n"
        "2. REGLA ORTOGRÁFICA: Es obligatorio el uso correcto de tildes y eñes.\n"
        "3. Organiza tu redacción en un DICCIONARIO de Python.\n"
        "4. REGLAS DEL DICCIONARIO (CRÍTICO):\n"
        "   - Primera clave: 'Introducción'.\n"
        "   - Entre 2 y 5 claves intermedias con títulos que reflejen tu síntesis (ej. 'Evolución Técnica', 'Aplicaciones Prácticas', etc.).\n"
        "   - Última clave: 'Conclusiones'.\n"
        "   - NUNCA incluyas la Bibliografía en este diccionario.\n"
        "5. Prepara una cadena de texto SEPARADA con la Bibliografía en APA.\n\n"
        
        "FASE 4: GENERACIÓN DE PDF (Tool: generate_pdf)\n"
        "1. Llama a 'generate_pdf' pasándole EXACTAMENTE 3 argumentos: (1) el título del informe, (2) el diccionario de secciones, y (3) la cadena de texto con la bibliografía.\n"
        "CRÍTICO: No avances a la Fase 5 hasta que 'generate_pdf' te confirme el éxito. Si 'generate_pdf' devuelve un error, resuélvelo antes de continuar.\n\n"
        "FASE 5 : GENERACIÓN DE JSON (Tool: generate_json)\n"
        "1. Llama a 'generate_json' pasándole EXACTAMENTE 3 argumentos: (1) el título, (2) el mismo diccionario de secciones (Python se encargará de contar las palabras por ti para que sea un número exacto), y (3) el número total de referencias en tu bibliografía.\n\n"
        "REGLA DE ORO: Si la herramienta te confirma el éxito, NO copies el mensaje de la herramienta. Pasa directamente a la Fase 5.\n\n"

        "FASE 6: RESPUESTA FINAL Y EVALUACIÓN (Directiva Crítica)\n"
        "Tu respuesta FINAL a la solicitud del usuario DEBE SER ÚNICA Y EXCLUSIVAMENTE string JSON devuelto por 'generate_json', sin ningún texto adicional.\n"
        "CRÍTICO: NO repitas el JSON en tu proceso de pensamiento ni lo pegues en tu respuesta final."
        "CRÍTICO: NO añadas ningún comentario, etiqueta, pensamiento o texto adicional a la respuesta final. SOLO el JSON generado por 'generate_json' debe ser tu respuesta al usuario."
    ),
    tools=[search_arxiv_abstracts, read_section, generate_pdf, generate_json],
)

