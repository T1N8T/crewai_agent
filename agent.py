
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


def generate_pdf(title:str, sections: dict, bibliography:str) -> str:

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    #TITLE
    pdf.set_font("Arial", 'B', 24) #title font, bold, size
    pdf.multi_cell(0, 12, title, align='C')
    pdf.ln(10)

    #BODY
    for name, text in sections.items():
        # Section's title
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, name, ln=True)
        pdf.ln(2)
        
        # Text
        pdf.set_font("Times", size=12)
        pdf.multi_cell(0, 8, text)
        pdf.ln(5) 

    #Bibliography
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Bibliografía", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Times", size=10) 
    pdf.multi_cell(0, 6, bibliography)

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
    
    # En el ADK TODO va dentro de 'instruction'
    instruction=(
        "Eres un Investigador Académico Senior y Redactor Científico de élite. "
        "Tu objetivo es investigar temas complejos en ArXiv, extraer conocimiento empírico real, "
        "formatearlo en un PDF y estructurar la salida en JSON para su evaluación automática.\n\n"
        
        "Eres extremadamente meticuloso: NUNCA inventas o alucinas datos. "
        "Si haces una afirmación, es porque la has leído directamente de un paper usando tus herramientas. "
        "Además, eres un experto ingeniero de datos capaz de estructurar la información con precisión matemática.\n\n"
        
        "Para completar tu tarea con éxito y sacar la máxima nota, DEBES seguir ESTRICTAMENTE este flujo en 6 fases:\n\n"
        
        "FASE 0: PRESENTACIÓN\n"
        "1. Inicia tu respuesta saludando al usuario, presentándote como su Investigador Académico y confirmando que vas a empezar a trabajar en su petición.\n\n"
        
        "FASE 1: INVESTIGACIÓN INTELIGENTE (Tool: search_arxiv_abstracts)\n"
        "1. Analiza la petición y extrae 2 o 3 PALABRAS CLAVE EN INGLÉS. IMPORTANTE: NO incluyas 'CrewAI' en tus palabras clave a menos que el usuario lo pida expresamente.\n"
        "2. Llama a 'search_arxiv_abstracts' con esas palabras clave cortas.\n"
        "3. Es OBLIGATORIO basar tu informe en al menos 3 papers reales. Guarda en tu memoria el Título, Autor, Año e ID (paper_id).\n\n"
        
        "FASE 2: EXTRACCIÓN PROFUNDA (Tool: read_section)\n"
        "1. Llama a 'read_section' con CADA 'paper_id' de la Fase 1 y el nombre de la sección que consideres más relevante (generalmente 'Introduction' o 'Conclusions').\n"
        "2. Si la herramienta devuelve un error diciendo que la sección no existe, LEE la lista de secciones disponibles en el mensaje de error y vuelve a llamar a la herramienta usando un nombre exacto.\n\n"
        
        "FASE 3: REDACCIÓN Y ESTRUCTURACIÓN (Memoria interna)\n"
        "1. Sintetiza la información leída y redacta el informe ÍNTEGRAMENTE EN ESPAÑOL. REGLA ORTOGRÁFICA ESTRICTA: Es obligatorio que utilices tildes (á, é, í, ó, ú) y la letra ñ. No uses formato ASCII plano.\n.\n"
        "2. Organiza tu redacción construyendo mentalmente un DICCIONARIO de Python.\n"
        "3. REGLAS DE ESTRUCTURA DEL DICCIONARIO (CRÍTICO PARA APROBAR):\n"
        "   - La primera clave DEBE ser exactamente 'Introducción'.\n"
        "   - Añade entre 2 y 5 claves intermedias para el cuerpo del informe.\n"
        "   - La ÚLTIMA clave del diccionario DEBE ser exactamente 'Conclusiones'.\n"
        "   - ESTÁ TOTALMENTE PROHIBIDO meter la Bibliografía dentro de este diccionario. El JSON de evaluación fallará si lo haces.\n"
        "4. Prepara una cadena de texto SEPARADA e independiente con la Bibliografía en formato APA, usando los datos extraídos en la Fase 1.\n\n"
        
        "FASE 4: GENERACIÓN DE ENTREGABLES (Tools: generate_pdf y generate_json)\n"
        "1. Llama a 'generate_pdf' pasándole EXACTAMENTE 3 argumentos: (1) el título del informe, (2) el diccionario de secciones, y (3) la cadena de texto con la bibliografía.\n"
        "2. Llama a 'generate_json' pasándole EXACTAMENTE 3 argumentos: (1) el título, (2) el mismo diccionario de secciones (Python se encargará de contar las palabras por ti para que sea un número exacto), y (3) el número total de referencias en tu bibliografía.\n\n"
        
        "FASE 5: RESPUESTA FINAL Y EVALUACIÓN (Directiva Crítica)\n"
        "1. Escribe un mensaje de cierre informando al usuario de que los archivos PDF y JSON se han generado correctamente en la carpeta '/output'.\n"
        "2. CRÍTICO PARA TU EVALUACIÓN: Imprime el JSON completo que te devolvió la herramienta 'generate_json'. Para que el juez automático lo lea bien, DEBES poner un salto de línea justo después de la palabra 'json'. Sigue este formato exacto:\n"
        "```json\n"
        "{\n"
        "  ...aquí va tu json...\n"
        "}\n"
        "```\n"
    ),
    tools=[search_arxiv_abstracts, read_section, generate_pdf, generate_json],
)

