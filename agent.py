
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import csv
import os 
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
    #Search in ArXiv's API top relevant papers about CrewAI
    #and return a dictionary with
    #key: ArXiv ID
    #value: Abstract

    maxResults = 3
    res = {}

    sortBy = "relevance" #other options are "lastUpdatedDate","submittedDate"
    searchQuery = "all:CrewAI+AND+all:" + parse.quote(topic)
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
    pdf.cell(0, 20, title, ln=True, align='C')
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

def generate_json():
    return 0




# ---------------------------
# Root agent
# ---------------------------
load_dotenv()
api_key = os.getenv("POLI_API_KEY")
api_base = os.getenv("POLI_API_BASE")

root_agent = Agent(
    # Pick a model you have configured (Gemini via GOOGLE_API_KEY, or via Vertex).
    # You can also route via LiteLLM if your environment is set up that way.
    #model="gemini-3-flash-preview",
    
    model = LiteLlm(model="openai/gpt-oss-120b", api_base=api_base, api_key=api_key),

    name="root_agent",
    description=(
        "Planifica una salida sencilla (2 opciones) en función del tiempo, preferencia y presupuesto, "
        "usando tools para fundamentar la respuesta."
    ),
    instruction=(
        "Eres un planificador de salidas. SIEMPRE debes fundamentarte en herramientas.\n"
        "Pasos: (1) llama a get_weather(city).\n"
        "(2) decide la categoría (SOLO entre estas: museo, outdoor, ocio): en funcion del tiempo que haga, por ejemplo si llueve mejor ir a un museo\n"
        "(3) llama a search_places(city, category) y elige hasta 2 lugares.\n"
        "(4) llama a estimate_cost con los nombres seleccionados.\n"
        "(5) responde en español con: categoría elegida, tiempo (resumen), 2 planes y coste total, "
        "sin inventar lugares fuera de la tool."
    ),
    tools=[],
)
